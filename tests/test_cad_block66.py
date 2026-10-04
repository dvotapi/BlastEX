"""Блок 66 («Жуков камень», файл маркшейдера 28.09.2026) — эталон импорта.

Фикстура — DWG маркшейдера, сконвертированный в полный DXF и сдвинутый на
константу (см. `tests/fixtures/cad/README.md`). Ожидания взяты из файла, а не
из TASK-013: в нём 23 фрагмента на «Горизонт +410» (ещё 2 линии — на слое
«Отвал вскрышных пород»), контур не помечен замкнутым, но концы совпадают.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from api.schemas.cad import CadParamsSchema, CadRolesRequest
from api.services import cad_service
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from design.spatial.cad.repository import InMemoryCadRepository

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"
SNAPSHOT = ReferenceSnapshot(
    revision_id="rev-1",
    sections={"sites": (ReferenceItem(code="SITE_ZK", name="Жуков камень"),)},
)
ORG = "org-zk"
LOWER_CRESTS = {"733", "73B", "753", "75A"}


def _import(repository: InMemoryCadRepository, content: bytes | None = None) -> dict:
    response = cad_service.import_files(
        repository,
        ORG,
        "engineer@example.ru",
        [("block66.dxf", content if content is not None else FIXTURE.read_bytes())],
        CadParamsSchema(),
        "Жуков камень",
        None,
        SNAPSHOT,
    )
    return response.sources[0].model_dump()


@pytest.fixture(scope="module")
def first_import() -> tuple[InMemoryCadRepository, dict]:
    repository = InMemoryCadRepository()
    return repository, _import(repository)


def _layer(source: dict, name: str) -> dict:
    return next(item for item in source["layers"] if item["name"] == name)


def test_all_entities_are_read(first_import):
    _, source = first_import
    kinds = Counter(item["kind"] for item in source["entities"])

    assert kinds == {"POLYLINE3D": 25, "LWPOLYLINE": 1, "POINT": 207, "TEXT": 203}
    assert sum(1 for item in source["entities"] if item["geometry_type"] == "line") == 26


def test_block_66_variant_2_is_the_contour(first_import):
    _, source = first_import
    contour = next(item for item in source["entities"] if item["handle"] == "769")

    assert (contour["layer"], contour["role"], contour["role_origin"]) == ("блок 66 вар 2", "block_contour", "auto")
    assert contour["closed"] and contour["closed_by_gap"]
    assert contour["vertex_count"] == 33
    assert contour["area_m2"] == pytest.approx(2789.93, abs=0.05)
    assert contour["z_kind"] == "const"
    assert _layer(source, "блок 66 вар 2")["role"] == "block_contour"


def test_bench_fragments_split_into_top_and_bottom_crests(first_import):
    _, source = first_import
    horizon = _layer(source, "Горизонт +410")
    crests = [item for item in source["entities"] if item["layer"] == "Горизонт +410" and item["geometry_type"] == "line"]

    assert (horizon["role"], horizon["origin"]) == ("crests_by_z", "auto")
    assert len(crests) == 23
    assert {item["handle"] for item in crests if item["role"] == "crest_bottom"} == LOWER_CRESTS
    assert sum(1 for item in crests if item["role"] == "crest_top") == 19
    assert {item["role_origin"] for item in crests} == {"z"}
    assert source["floor_z_m"] == 410.0


def test_other_layers(first_import):
    _, source = first_import

    assert _layer(source, "Отметка")["role"] == "spot_heights"
    assert _layer(source, "Отвал вскрышных пород")["role"] == "situation"
    marks = [item for item in source["entities"] if item["layer"] == "Отметка" and item["kind"] == "POINT"]
    assert len(marks) == 198 and {item["role"] for item in marks} == {"spot_heights"}


def test_millimetre_insunits_do_not_rescale_the_drawing(first_import):
    _, source = first_import

    assert source["insunits"] == 4
    assert source["suggested_scale"] is None
    assert any(item["code"] == "units_declared" for item in source["warnings"])
    xmin, ymin, xmax, ymax = source["extent"]
    assert (xmax - xmin, ymax - ymin) == (pytest.approx(84.51, abs=0.01), pytest.approx(186.28, abs=0.01))


def test_repeat_import_is_labelled_by_the_template_without_manual_steps():
    repository = InMemoryCadRepository()
    first = _import(repository)
    cad_service.save_roles(
        repository,
        ORG,
        "engineer@example.ru",
        first["id"],
        CadRolesRequest(layers={"Отвал вскрышных пород": "ignore"}),
    )

    # Следующий файл того же маркшейдера — другие байты (тот же файл открыл бы
    # прежний разбор, PR 4): комментарий DXF в начале, содержание то же.
    second = _import(repository, "999\nповторная выгрузка\n".encode() + FIXTURE.read_bytes())

    assert second["id"] != first["id"]
    assert {item["name"]: (item["role"], item["origin"]) for item in second["layers"]} == {
        "блок 66 вар 2": ("block_contour", "template"),
        "Горизонт +410": ("crests_by_z", "template"),
        "Отвал вскрышных пород": ("ignore", "template"),
        "Отметка": ("spot_heights", "template"),
    }
    lower = {item["handle"] for item in second["entities"] if item["role"] == "crest_bottom"}
    assert lower == LOWER_CRESTS
    assert not any(item["role_origin"] == "manual" for item in second["entities"])


def test_the_same_file_again_opens_the_previous_parse():
    repository = InMemoryCadRepository()
    first = _import(repository)
    cad_service.save_roles(
        repository,
        ORG,
        "engineer@example.ru",
        first["id"],
        CadRolesRequest(layers={"Отвал вскрышных пород": "ignore"}),
    )

    again = _import(repository)

    assert again["id"] == first["id"]
    assert "already_loaded" in {item["code"] for item in again["warnings"]}
    assert _layer(again, "Отвал вскрышных пород")["role"] == "ignore"
