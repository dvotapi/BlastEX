"""Ситуация объекта: план карьера одним файлом на все блоки, отбор слоёв (план 2026-11-13)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import cad
from api.security import require_internal_access
from api.services.cad_service import get_cad_repository
from api.services.cad_situation_service import block_situation_refs, site_situation_ref, source_situation
from api.services.legacy_references import current_reference_snapshot
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from design.mass_blast_graphics import _clipped_situation
from design.spatial.cad.model import CadEntity
from design.spatial.cad.repository import InMemoryCadRepository
from design.spatial.cad.situation import assign_situation_roles, situation_kind_for_layer, situation_layer_shown
from tests.cad_situation_fixtures import X0, Y0, block_dxf, pit_plan_dxf

SNAPSHOT = ReferenceSnapshot(revision_id="rev-1", sections={"sites": (ReferenceItem(code="SITE_ZK", name="Жуков камень"),)})
SESSION = {"sub": "a@example.ru", "role": "admin", "org": "org-a"}
BASE = "/api/v1/design/cad"
PLAN = "24.09.2026 Ситуационный план.dxf"


@pytest.fixture()
def repository() -> InMemoryCadRepository:
    return InMemoryCadRepository()


def _client(repository: InMemoryCadRepository) -> TestClient:
    app = FastAPI()
    app.include_router(cad.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: SESSION
    app.dependency_overrides[get_cad_repository] = lambda: repository
    app.dependency_overrides[current_reference_snapshot] = lambda: SNAPSHOT
    app.dependency_overrides[cad.current_work_object_name] = lambda: "Жуков камень"
    return TestClient(app)


def _upload(client: TestClient, name: str, content: bytes, **form) -> dict:
    response = client.post(
        f"{BASE}/sources",
        files=[("files", (name, content, "application/octet-stream"))],
        data={key: str(value) for key, value in form.items()},
    )
    assert response.status_code == 201, response.text
    return response.json()["sources"][0]


def _layers(source: dict) -> dict[str, dict]:
    return {item["name"]: item for item in source["layers"]}


# --- умолчания отбора -------------------------------------------------------


def _line(layer: str) -> CadEntity:
    return CadEntity(handle=layer, layer=layer, kind="LWPOLYLINE", points=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)])


def test_kinds_of_pit_plan_layers():
    assert situation_kind_for_layer("Горизонт +410") == "bench"
    assert situation_kind_for_layer("Откосы") == "bench"
    assert situation_kind_for_layer("31.10.25 карьер") == "bench"
    assert situation_kind_for_layer("Граница горного отвода") == "boundary"
    assert situation_kind_for_layer("контур лицензии СВЕ 07963 ТЭ") == "boundary"
    assert situation_kind_for_layer("ЗО_дог.аренды 8459 от 2020г") == "boundary"
    assert situation_kind_for_layer("КПП") == "building"
    assert situation_kind_for_layer("ДСК") == "building"
    assert situation_kind_for_layer("Конвейер") == "building"
    assert situation_kind_for_layer("Граница карьера") == "pit"
    assert situation_kind_for_layer("Горизонтали") == "other"


@pytest.mark.parametrize(
    ("name", "hidden", "shown"),
    [
        ("Дороги", True, True),  # дороги — всегда (решение владельца 13.11.2026)
        ("КПП", True, True),  # объекты на поверхности — всегда
        ("ЛЭП", True, True),
        ("Склады_2023", True, False),  # старые склады, скрытые маркшейдером, — нет
        ("Горизонт +410", False, True),
        ("Горизонт +410", True, False),
        ("Блок 48 факт 14.10.2024", False, False),
        ("блк 55 факт", False, False),
        ("граница блока 67 для проектирования", False, False),
        ("Блоки_2025", False, False),
        ("Сетка координат_2000", False, False),
        ("DIM-GRID", False, False),
        ("Надписи", False, False),
        ("Рельеф", False, True),
    ],
)
def test_default_selection(name, hidden, shown):
    assert situation_layer_shown(name, [_line(name)], hidden) is shown


def test_layer_of_points_only_is_not_shown_even_if_road():
    point = CadEntity(handle="p", layer="Дорога отметки", kind="POINT", points=[(0.0, 0.0, 420.0)])
    assert situation_layer_shown("Дорога отметки", [point], False) is False


def test_numeric_labels_and_spot_points_are_not_situation():
    entities = [
        _line("Сооружения"),
        CadEntity(handle="t1", layer="Сооружения", kind="TEXT", points=[(0.0, 0.0, 0.0)], text="ДСК"),
        CadEntity(handle="t2", layer="Сооружения", kind="TEXT", points=[(0.0, 0.0, 0.0)], text="423.47"),
        CadEntity(handle="p1", layer="Сооружения", kind="POINT", points=[(0.0, 0.0, 423.0)]),
        CadEntity(handle="i1", layer="Сооружения", kind="INSERT", points=[(0.0, 0.0, 0.0)]),
    ]
    assign_situation_roles(entities, {})
    roles = {item.handle: item.role for item in entities}
    assert roles == {"Сооружения": "situation", "t1": "situation", "t2": "ignore", "p1": "ignore", "i1": "situation"}


def test_manual_choice_beats_template_beats_default():
    entities = [_line("Дороги"), _line("Рельеф"), _line("Сетка")]
    result = assign_situation_roles(entities, {"дороги": False, "сетка": True}, manual_layers={"Рельеф": "ignore"})
    layers = {item.name: (item.role, item.origin) for item in result.layers}
    assert layers == {
        "Дороги": ("ignore", "template"),
        "Рельеф": ("ignore", "manual"),
        "Сетка": ("situation", "template"),
    }


# --- загрузка плана карьера --------------------------------------------------


def test_pit_plan_upload_selects_layers(repository):
    source = _upload(_client(repository), PLAN, pit_plan_dxf(), purpose="situation")
    layers = _layers(source)
    shown = {name for name, item in layers.items() if item["role"] == "situation"}

    assert source["purpose"] == "situation"
    assert shown == {"Дороги", "Сооружения", "КПП", "Горизонт +410", "Граница горного отвода"}
    assert layers["КПП"]["hidden"] is True and layers["Склады_2023"]["hidden"] is True
    assert layers["Дороги"]["hidden"] is False
    # Вид — у всех слоёв, и у снятых.
    assert layers["Склады_2023"]["situation_kind"] == "stockpile"
    assert layers["Горизонт +410"]["situation_kind"] == "bench"
    # Роли блока (бровки, контур, отметки) у плана карьера не появляются.
    assert {item["role"] for item in source["layers"]} <= {"situation", "ignore"}
    # Шаблон ролей блоков не пополняется: «Горизонт +410» у блока — бровки.
    assert repository.get_layer_template("org-a", "SITE_ZK") == {}


def test_pit_plan_labels_without_elevations(repository):
    client = _client(repository)
    source = _upload(client, PLAN, pit_plan_dxf(), purpose="situation")
    geometry = source_situation(repository, "org-a", source["id"])
    labels = {layer.name: [label.text for label in layer.labels] for layer in geometry.layers}
    assert labels["Сооружения"] == ["ДСК"]
    assert labels["КПП"] == ["КПП"]
    assert labels["Горизонт +410"] == []


def test_selection_is_remembered_for_the_next_plan_and_not_for_blocks(repository):
    client = _client(repository)
    first = _upload(client, PLAN, pit_plan_dxf(), purpose="situation")
    response = client.put(
        f"{BASE}/sources/{first['id']}/roles",
        json={"layers": {"Граница горного отвода": "ignore", "Склады_2023": "situation"}, "kinds": {"Сооружения": "stockpile"}},
    )
    assert response.status_code == 200, response.text
    layers = _layers(response.json())
    assert layers["Граница горного отвода"]["role"] == "ignore"
    assert layers["Склады_2023"]["role"] == "situation"
    assert layers["Сооружения"]["situation_kind"] == "stockpile"

    second = _upload(client, "15.11.2026 Ситуационный план.dxf", pit_plan_dxf(extra_layer="Новый слой"), purpose="situation")
    layers = _layers(second)
    assert (layers["Граница горного отвода"]["role"], layers["Граница горного отвода"]["origin"]) == ("ignore", "template")
    assert layers["Склады_2023"]["role"] == "situation"
    assert layers["Сооружения"]["situation_kind"] == "stockpile"
    assert layers["Новый слой"]["origin"] == "auto"

    # Чертёж блока того же объекта отбор плана карьера не наследует.
    block = _upload(client, "28.09.2026 граница блока 70.dxf", block_dxf())
    assert block["purpose"] == "block"
    assert {item["role"] for item in block["layers"] if item["name"] == "Горизонт +410"} != {"situation"}


def test_pit_plan_refuses_block_roles_and_entity_overrides(repository):
    client = _client(repository)
    source = _upload(client, PLAN, pit_plan_dxf(), purpose="situation")
    bad_role = client.put(f"{BASE}/sources/{source['id']}/roles", json={"layers": {"Горизонт +410": "crest_top"}})
    assert bad_role.status_code == 422
    entity = source["entities"][0]["handle"]
    bad_entity = client.put(f"{BASE}/sources/{source['id']}/roles", json={"entities": {entity: "ignore"}})
    assert bad_entity.status_code == 422


def test_same_file_as_block_and_as_pit_plan_are_separate_sources(repository):
    """Чертёж блока и план карьера из одного файла — разные источники: план не ломает разбор блока."""

    client = _client(repository)
    content = pit_plan_dxf()
    block = _upload(client, PLAN, content)
    plan = _upload(client, PLAN, content, purpose="situation")
    assert block["purpose"] == "block" and plan["purpose"] == "situation"
    assert plan["id"] != block["id"]
    assert repository.get_source("org-a", block["id"]).summary.get("purpose") == "block"
    # Повтор плана открывает прежний план, повтор блока — прежний блок.
    assert _upload(client, PLAN, content, purpose="situation")["id"] == plan["id"]
    assert _upload(client, PLAN, content)["id"] == block["id"]


def test_unknown_purpose_is_refused(repository):
    response = _client(repository).post(
        f"{BASE}/sources",
        files=[("files", (PLAN, pit_plan_dxf(), "application/octet-stream"))],
        data={"purpose": "map"},
    )
    assert response.status_code == 422


def test_site_sources_list_marks_pit_plan(repository):
    client = _client(repository)
    _upload(client, PLAN, pit_plan_dxf(), purpose="situation")
    _upload(client, "28.09.2026 граница блока 70.dxf", block_dxf())
    listed = client.get(f"{BASE}/sources").json()["sources"]
    assert {item["title"]: item["purpose"] for item in listed} == {
        "Ситуационный план": "situation",
        "граница блока 70": "block",
    }


# --- одна ситуация на все блоки ---------------------------------------------


def test_block_without_links_takes_the_latest_pit_plan(repository):
    client = _client(repository)
    old = _upload(client, PLAN, pit_plan_dxf(), purpose="situation")
    new = _upload(client, "15.11.2026 Ситуационный план.dxf", pit_plan_dxf(extra_layer="x"), purpose="situation")
    block = _upload(client, "28.09.2026 граница блока 70.dxf", block_dxf())

    assert site_situation_ref(repository, "org-a", "SITE_ZK")["source_id"] == new["id"]
    # Блок без ссылок: объект — по источнику контура блока.
    refs, from_site = block_situation_refs(lambda: repository, "org-a", {"source_id": block["id"]})
    assert [ref["source_id"] for ref in refs] == [new["id"]] and from_site is True
    # Без источника контура — объект документа.
    refs, _ = block_situation_refs(lambda: repository, "org-a", None, "SITE_ZK")
    assert [ref["source_id"] for ref in refs] == [new["id"]]
    # Ссылки блока главнее ситуации объекта.
    linked = {"source_id": block["id"], "situation": [{"source_id": old["id"], "title": "Ситуационный план"}]}
    refs, from_site = block_situation_refs(lambda: repository, "org-a", linked)
    assert [ref["source_id"] for ref in refs] == [old["id"]] and from_site is False


def test_block_situation_without_database_is_empty():
    def broken():
        raise RuntimeError("нет базы")

    assert block_situation_refs(broken, "org-a", None, "SITE_ZK") == ([], False)


def test_object_without_pit_plan_has_no_site_situation(repository):
    _upload(_client(repository), "28.09.2026 граница блока 70.dxf", block_dxf())
    assert site_situation_ref(repository, "org-a", "SITE_ZK") is None
    assert site_situation_ref(repository, "org-a", "") is None


def test_graphics_keep_labels_inside_the_frame():
    layers = [
        {
            "name": "Сооружения",
            "kind": "building",
            "lines": [{"points": [[X0, Y0], [X0 + 10, Y0]], "closed": False}],
            "labels": [{"text": "ДСК", "point": [X0 + 5, Y0 + 1]}, {"text": "КПП", "point": [X0 + 5000, Y0]}],
        }
    ]
    clipped, _, _ = _clipped_situation(layers, (X0 - 100, Y0 - 100, X0 + 100, Y0 + 100))
    assert clipped[0]["labels"] == [{"text": "ДСК", "point": [X0 + 5, Y0 + 1]}]
    # Без подписей ключа нет: Г.5 прежних ревизий не меняется.
    plain = [{**layers[0], "labels": []}]
    assert "labels" not in _clipped_situation(plain, (X0 - 100, Y0 - 100, X0 + 100, Y0 + 100))[0][0]


def test_pit_plans_with_different_names_are_one_series(repository):
    """Съёмки плана карьера с разными именами файлов — одна серия, по умолчанию самая свежая."""

    client = _client(repository)
    old = _upload(client, "24.09.2026 Блок 66 ВЗ А3 5000.dxf", pit_plan_dxf(), purpose="situation")
    new = _upload(client, "15.11.2026 Блок 67 ВЗ А3 5000.dxf", pit_plan_dxf(extra_layer="x"), purpose="situation")
    _upload(client, "28.09.2026 граница блока 70.dxf", block_dxf())
    catalogue = client.get(f"{BASE}/situation").json()
    plans = [series for series in catalogue["series"] if {item["source_id"] for item in series["versions"]} & {old["id"], new["id"]}]
    assert len(plans) == 1
    assert [item["source_id"] for item in plans[0]["versions"]] == [new["id"], old["id"]]
    assert plans[0]["default_source_id"] == new["id"]
    current = client.get(f"{BASE}/site-situation").json()
    assert current == {"site_code": "SITE_ZK", "source_id": new["id"]}


def test_site_situation_without_plan(repository):
    assert _client(repository).get(f"{BASE}/site-situation").json() == {"site_code": "SITE_ZK", "source_id": None}
