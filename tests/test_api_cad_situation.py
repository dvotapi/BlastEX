"""Ситуация карьера и система координат объекта: HTTP-маршруты (TASK-013, PR 4)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import cad
from api.security import require_internal_access
from api.services.cad_service import get_cad_repository
from api.services.legacy_references import current_reference_snapshot
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from design.spatial.cad.repository import InMemoryCadRepository
from tests.cad_situation_fixtures import block_dxf, situation_dxf

SNAPSHOT = ReferenceSnapshot(
    revision_id="rev-1",
    sections={
        "sites": (
            ReferenceItem(code="SITE_ZK", name="Жуков камень"),
            ReferenceItem(code="SITE_OTHER", name="Другой карьер"),
        )
    },
)
SESSION_A = {"sub": "a@example.ru", "role": "admin", "org": "org-a"}
SESSION_B = {"sub": "b@example.ru", "role": "admin", "org": "org-b"}
BASE = "/api/v1/design/cad"
MSK66 = {"name": "МСК-66 зона 1", "height_system": "Балтийская 1977", "epsg": None}


@pytest.fixture()
def repository() -> InMemoryCadRepository:
    return InMemoryCadRepository()


def _client(
    repository: InMemoryCadRepository, session: dict = SESSION_A, work_object: str = "Жуков камень"
) -> TestClient:
    app = FastAPI()
    app.include_router(cad.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: session
    app.dependency_overrides[get_cad_repository] = lambda: repository
    app.dependency_overrides[current_reference_snapshot] = lambda: SNAPSHOT
    app.dependency_overrides[cad.current_work_object_name] = lambda: work_object
    return TestClient(app)


def _upload(client: TestClient, *files: tuple[str, bytes], **form) -> list[dict]:
    response = client.post(
        f"{BASE}/sources",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
        data={key: str(value) for key, value in form.items()},
    )
    assert response.status_code == 201, response.text
    return response.json()["sources"]


def _codes(source: dict) -> set[str]:
    return {item["code"] for item in source["warnings"]}


def _layer(source: dict, name: str) -> dict:
    return next(item for item in source["layers"] if item["name"] == name)


# --- повторный файл -------------------------------------------------------


def test_same_file_on_the_same_site_opens_the_previous_source(repository):
    client = _client(repository)
    content = situation_dxf()  # ezdxf пишет в файл GUID и время — байты одного вызова
    first = _upload(client, ("Положение горных работ на 01.09.2026.dxf", content))[0]
    again = _upload(client, ("копия.dxf", content))[0]

    assert again["id"] == first["id"]
    assert again["file_name"] == first["file_name"]
    assert "already_loaded" in _codes(again)
    assert "already_loaded" not in _codes(first)
    assert len(repository.list_site_sources("org-a", "SITE_ZK", limit=50)) == 1


def test_same_file_twice_in_one_upload_is_one_source(repository):
    content = situation_dxf()
    sources = _upload(_client(repository), ("a.dxf", content), ("b.dxf", content))

    assert sources[0]["id"] == sources[1]["id"]
    assert len(repository.list_site_sources("org-a", "SITE_ZK", limit=50)) == 1


def test_same_file_on_another_site_or_without_site_is_a_new_source(repository):
    content = situation_dxf()
    first = _upload(_client(repository), ("a.dxf", content))[0]
    other_site = _upload(_client(repository, work_object="Другой карьер"), ("a.dxf", content))[0]
    no_site = _upload(_client(repository, work_object=""), ("a.dxf", content))[0]
    again_no_site = _upload(_client(repository, work_object=""), ("a.dxf", content))[0]

    assert len({first["id"], other_site["id"], no_site["id"], again_no_site["id"]}) == 4


# --- название, дата, серия -----------------------------------------------


def test_title_and_survey_date_come_from_the_file_name(repository):
    source = _upload(_client(repository), ("Положение горных работ на 01.09.2026.dxf", situation_dxf()))[0]

    assert source["title"] == "Положение горных работ"
    assert source["survey_date"] == "2026-09-01"


def test_survey_date_of_the_form_wins_over_the_file_name(repository):
    source = _upload(
        _client(repository), ("Положение горных работ на 01.09.2026.dxf", situation_dxf()), survey_date="2026-09-05"
    )[0]

    assert source["survey_date"] == "2026-09-05"


def test_title_and_date_are_edited_and_checked(repository):
    client = _client(repository)
    source = _upload(client, ("ситуация.dxf", situation_dxf()))[0]
    url = f"{BASE}/sources/{source['id']}"

    edited = client.patch(url, json={"title": "  Положение горных работ ", "survey_date": "2026-10-01"})
    assert edited.status_code == 200, edited.text
    assert (edited.json()["title"], edited.json()["survey_date"]) == ("Положение горных работ", "2026-10-01")

    cleared = client.patch(url, json={"survey_date": None}).json()
    assert (cleared["title"], cleared["survey_date"]) == ("Положение горных работ", None)

    assert client.patch(url, json={"title": "   "}).status_code == 422
    assert client.patch(url, json={"survey_date": "01.10.2026"}).status_code == 422
    assert _client(repository, SESSION_B).patch(url, json={"title": "x"}).status_code == 404


def test_versions_of_one_series_see_each_other(repository):
    client = _client(repository)
    september = _upload(client, ("Положение горных работ на 01.09.2026.dxf", situation_dxf()))[0]
    october = _upload(client, ("01.10.2026 положение горных работ.dxf", situation_dxf(roads=2)))[0]
    block = _upload(client, ("28.09.2026г граница блока 70.dxf", block_dxf()))[0]

    fresh = client.get(f"{BASE}/sources/{october['id']}").json()
    assert [item["id"] for item in fresh["series"]] == [september["id"]]
    assert fresh["series"][0]["survey_date"] == "2026-09-01"
    assert client.get(f"{BASE}/sources/{block['id']}").json()["series"] == []


# --- система координат объекта -------------------------------------------


def test_crs_is_set_once_and_the_next_file_inherits_it(repository):
    client = _client(repository)
    first = _upload(client, ("block.dxf", block_dxf()))[0]
    assert "crs_missing" in _codes(first)
    assert first["crs"] is None

    saved = client.put(f"{BASE}/sources/{first['id']}/crs", json=MSK66)
    assert saved.status_code == 200, saved.text
    assert saved.json()["saved"] is True
    assert saved.json()["crs"] == MSK66
    assert "crs_missing" not in {item["code"] for item in saved.json()["warnings"]}

    # §3 PR 4, п. 5: второй файл в МСК-66 предупреждения о СК не даёт.
    second = _upload(client, ("Положение горных работ на 01.09.2026.dxf", situation_dxf(dx=300)))[0]
    assert second["crs"] == MSK66
    assert not {"crs_missing", "crs_far"} & _codes(second)
    assert repository.get_source("org-a", second["id"]).coordinate_system == MSK66


def test_file_shifted_by_50_km_is_reported(repository):
    client = _client(repository)
    first = _upload(client, ("block.dxf", block_dxf()))[0]
    client.put(f"{BASE}/sources/{first['id']}/crs", json=MSK66).raise_for_status()

    shifted = _upload(client, ("чужой.dxf", situation_dxf(dx=50_000)))[0]

    far = next(item for item in shifted["warnings"] if item["code"] == "crs_far")
    assert "км" in far["message"]
    assert "crs_far" not in _codes(client.get(f"{BASE}/sources/{first['id']}").json())


def test_outlier_at_the_origin_does_not_raise_crs_far(repository):
    client = _client(repository)
    _upload(client, ("block.dxf", block_dxf()))
    with_outlier = _upload(client, ("ситуация.dxf", situation_dxf(origin_outlier=True)))[0]

    assert "crs_far" not in _codes(with_outlier)


def test_crs_without_a_site_is_not_saved(repository):
    client = _client(repository, work_object="")
    source = _upload(client, ("block.dxf", block_dxf()))[0]

    assert "crs_missing" not in _codes(source)
    answer = client.put(f"{BASE}/sources/{source['id']}/crs", json=MSK66).json()
    assert answer["saved"] is False


def test_crs_fields_are_checked(repository):
    client = _client(repository)
    source = _upload(client, ("block.dxf", block_dxf()))[0]
    url = f"{BASE}/sources/{source['id']}/crs"

    assert client.put(url, json={**MSK66, "epsg": -5}).status_code == 422
    assert client.put(url, json={**MSK66, "name": "x" * 121}).status_code == 422
    assert _client(repository, SESSION_B).put(url, json=MSK66).status_code == 404


# --- виды объектов ситуации ----------------------------------------------


def test_meta_lists_situation_kinds(repository):
    meta = _client(repository).get(f"{BASE}/meta").json()

    assert [item["code"] for item in meta["situation_kinds"]] == [
        "pit",
        "road",
        "power_line",
        "stockpile",
        "building",
        "other",
    ]


def test_situation_layers_get_a_kind_by_name(repository):
    source = _upload(_client(repository), ("ситуация.dxf", situation_dxf()))[0]

    kinds = {item["name"]: (item["situation_kind"], item["situation_kind_origin"]) for item in source["layers"]}
    assert kinds["Автодорога"] == ("road", "auto")
    assert kinds["ВЛ-6кВ"] == ("power_line", "auto")
    assert kinds["Склад негабарита"] == ("stockpile", "auto")
    assert kinds["Здания"] == ("building", "auto")
    assert kinds["Граница карьера"] == ("pit", "auto")


def test_layer_without_situation_has_no_kind(repository):
    source = _upload(_client(repository), ("block.dxf", block_dxf()))[0]

    assert _layer(source, "Отметка")["situation_kind"] is None
    assert _layer(source, "Отвал вскрышных пород")["situation_kind"] == "stockpile"


def test_manual_kind_goes_to_the_site_template_and_can_be_reset(repository):
    client = _client(repository)
    first = _upload(client, ("a.dxf", situation_dxf()))[0]
    url = f"{BASE}/sources/{first['id']}/roles"

    answer = client.put(url, json={"kinds": {"Здания": "stockpile"}})
    assert answer.status_code == 200, answer.text
    assert (_layer(answer.json(), "Здания")["situation_kind"], _layer(answer.json(), "Здания")["situation_kind_origin"]) == (
        "stockpile",
        "manual",
    )

    second = _upload(client, ("b.dxf", situation_dxf(roads=2)))[0]
    assert (_layer(second, "Здания")["situation_kind"], _layer(second, "Здания")["situation_kind_origin"]) == (
        "stockpile",
        "template",
    )

    reset = client.put(url, json={"kinds": {"Здания": None}}).json()
    assert (_layer(reset, "Здания")["situation_kind"], _layer(reset, "Здания")["situation_kind_origin"]) == (
        "building",
        "auto",
    )
    third = _upload(client, ("c.dxf", situation_dxf(roads=3)))[0]
    assert _layer(third, "Здания")["situation_kind_origin"] == "auto"


def test_manual_kind_survives_reparse(repository):
    client = _client(repository)
    source = _upload(client, ("a.dxf", situation_dxf()))[0]
    client.put(f"{BASE}/sources/{source['id']}/roles", json={"kinds": {"Здания": "other"}}).raise_for_status()

    reparsed = client.post(f"{BASE}/sources/{source['id']}/reparse", json={**source["params"], "label_radius_m": 2.0})
    assert reparsed.status_code == 200, reparsed.text
    assert _layer(reparsed.json(), "Здания")["situation_kind"] == "other"


def test_unknown_kind_or_layer_without_situation_is_rejected(repository):
    client = _client(repository)
    source = _upload(client, ("block.dxf", block_dxf()))[0]
    url = f"{BASE}/sources/{source['id']}/roles"

    assert client.put(url, json={"kinds": {"Отвал вскрышных пород": "castle"}}).status_code == 422
    assert client.put(url, json={"kinds": {"Отметка": "road"}}).status_code == 422
    assert client.put(url, json={"kinds": {"Нет такого": "road"}}).status_code == 422


def test_source_uploaded_before_pr4_gets_kinds_by_layer_name(repository):
    client = _client(repository)
    source = _upload(client, ("ситуация.dxf", situation_dxf()))[0]
    stored = repository.get_source("org-a", source["id"])
    stored.summary = {key: value for key, value in stored.summary.items() if key not in {"layer_kinds", "manual_kinds"}}
    repository._sources[("org-a", source["id"])].summary = stored.summary

    fresh = client.get(f"{BASE}/sources/{source['id']}").json()
    assert (_layer(fresh, "Автодорога")["situation_kind"], _layer(fresh, "Автодорога")["situation_kind_origin"]) == (
        "road",
        "auto",
    )


# --- каталог ситуации объекта и геометрия (задача 5) ------------------------


def _catalogue(client: TestClient, *source_ids: str) -> dict:
    response = client.get(f"{BASE}/situation", params=[("source_ids", item) for item in source_ids])
    assert response.status_code == 200, response.text
    return response.json()


def _series(catalogue: dict) -> dict[str, dict]:
    """Серии по ключу: название без регистра и лишних пробелов."""

    return {item["key"]: item for item in catalogue["series"]}


def test_situation_of_a_separate_file_is_seen_by_another_passport(repository):
    """§3 PR 4, п. 5: ситуация из отдельного файла видна в другом паспорте объекта."""

    client = _client(repository)
    block = _upload(client, ("28.09.2026г граница блока 70.dxf", block_dxf()))[0]
    situation = _upload(client, ("Положение горных работ на 01.09.2026.dxf", situation_dxf()))[0]

    # Паспорт блока 70 ссылается только на свой файл — положение работ всё равно видно.
    seen = _series(_catalogue(client, block["id"]))
    assert set(seen) == {"граница блока 70", "положение горных работ"}
    assert seen["положение горных работ"]["title"] == "Положение горных работ"
    assert seen["положение горных работ"]["default_source_id"] == situation["id"]
    assert seen["граница блока 70"]["default_source_id"] == block["id"]

    # Паспорт без ссылки (старый или построенный вручную) видит ту же ситуацию объекта.
    assert set(_series(_catalogue(client))) == {"граница блока 70", "положение горных работ"}


def test_newest_version_by_default_reference_keeps_its_own(repository):
    client = _client(repository)
    september = _upload(client, ("Положение горных работ на 01.09.2026.dxf", situation_dxf()))[0]
    october = _upload(client, ("01.10.2026 положение горных работ.dxf", situation_dxf(roads=2)))[0]

    fresh = _series(_catalogue(client))["положение горных работ"]
    assert fresh["title"] == "положение горных работ"  # название свежей версии
    assert [item["source_id"] for item in fresh["versions"]] == [october["id"], september["id"]]
    assert fresh["default_source_id"] == october["id"]
    assert fresh["versions"][0]["situation_count"] > 0

    pinned = _series(_catalogue(client, september["id"]))["положение горных работ"]
    assert pinned["default_source_id"] == september["id"]


def test_deleted_reference_is_missing_and_the_rest_is_served(repository):
    client = _client(repository)
    block = _upload(client, ("block.dxf", block_dxf()))[0]
    situation = _upload(client, ("Положение горных работ на 01.09.2026.dxf", situation_dxf()))[0]

    assert client.delete(f"{BASE}/sources/{situation['id']}").status_code == 204

    catalogue = _catalogue(client, block["id"], situation["id"])
    assert catalogue["missing"] == [situation["id"]]
    assert set(_series(catalogue)) == {"block"}


def test_files_without_situation_are_not_in_the_catalogue(repository):
    client = _client(repository)
    content = block_dxf()
    source = _upload(client, ("block.dxf", content))[0]
    client.put(
        f"{BASE}/sources/{source['id']}/roles", json={"layers": {"Отвал вскрышных пород": "ignore"}}
    ).raise_for_status()

    assert _catalogue(client)["series"] == []


def test_catalogue_of_another_organization_is_empty(repository):
    client = _client(repository)
    situation = _upload(client, ("ситуация.dxf", situation_dxf()))[0]

    foreign = _catalogue(_client(repository, SESSION_B), situation["id"])
    assert foreign["series"] == []
    assert foreign["missing"] == [situation["id"]]


def test_passport_of_a_file_without_site_sees_its_own_situation(repository):
    client = _client(repository, work_object="")
    source = _upload(client, ("ситуация.dxf", situation_dxf()))[0]

    catalogue = _catalogue(client, source["id"])
    assert [item["default_source_id"] for item in catalogue["series"]] == [source["id"]]
    assert _catalogue(client)["series"] == []


def test_situation_geometry_by_layer_with_kind_and_color(repository):
    client = _client(repository)
    source = _upload(client, ("ситуация.dxf", situation_dxf()))[0]

    answer = client.get(f"{BASE}/sources/{source['id']}/situation")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    layers = {item["name"]: item for item in body["layers"]}
    assert set(layers) == {"Автодорога", "ВЛ-6кВ", "Склад негабарита", "Здания", "Граница карьера"}
    assert layers["Автодорога"]["kind"] == "road"
    assert layers["Автодорога"]["kind_label"] == "Дорога"
    assert layers["Автодорога"]["color"] == "#ffffff"  # цвет DXF как есть: затемняет фронт
    assert layers["ВЛ-6кВ"]["color"] == "#ff0000"
    road = layers["Автодорога"]["lines"][0]
    assert len(road["points"]) == 3 and road["closed"] is False
    assert layers["Склад негабарита"]["lines"][0]["closed"] is True
    assert body["revision"] == 1
    assert body["title"] == "ситуация"


def test_situation_geometry_is_simplified(repository):
    import ezdxf

    from tests.cad_situation_fixtures import X0, Y0, _bytes

    doc = ezdxf.new("R2010")
    # 1001 вершина на прямой с шумом 1 мм — после упрощения 0,05 м остаются концы.
    points = [(X0 + index * 0.5, Y0 + (0.001 if index % 2 else 0.0)) for index in range(1001)]
    doc.modelspace().add_lwpolyline(points, dxfattribs={"layer": "Дорога"})
    client = _client(repository)
    source = _upload(client, ("дорога.dxf", _bytes(doc)))[0]

    line = client.get(f"{BASE}/sources/{source['id']}/situation").json()["layers"][0]["lines"][0]
    assert len(line["points"]) == 2
    assert line["points"][0][:2] == pytest.approx([X0, Y0])
    assert line["points"][-1][:2] == pytest.approx([X0 + 500, Y0], abs=0.01)


def test_tiny_closed_ring_keeps_its_vertices(repository):
    """Опора ЛЭП в 3 см: упрощение 0,05 м свело бы кольцо к двум одинаковым точкам."""

    import ezdxf

    from tests.cad_situation_fixtures import X0, Y0, _bytes

    doc = ezdxf.new("R2010")
    square = [(X0, Y0), (X0 + 0.03, Y0), (X0 + 0.03, Y0 + 0.03), (X0, Y0 + 0.03)]
    doc.modelspace().add_lwpolyline(square, close=True, dxfattribs={"layer": "ЛЭП"})
    client = _client(repository)
    source = _upload(client, ("опора.dxf", _bytes(doc)))[0]

    line = client.get(f"{BASE}/sources/{source['id']}/situation").json()["layers"][0]["lines"][0]
    assert line["closed"] is True
    assert [point[:2] for point in line["points"]] == [pytest.approx(list(xy), abs=0.001) for xy in square]


def test_situation_over_the_vertex_limit_omits_whole_layers(repository, monkeypatch):
    from api.services import cad_situation_service

    monkeypatch.setattr(cad_situation_service, "MAX_SITUATION_VERTICES", 12)
    client = _client(repository)
    source = _upload(client, ("ситуация.dxf", situation_dxf()))[0]

    body = client.get(f"{BASE}/sources/{source['id']}/situation").json()
    omitted = [item for item in body["layers"] if item["omitted"]]
    assert omitted
    assert all(not item["lines"] and not item["points"] for item in omitted)
    assert sum(item["vertex_count"] for item in body["layers"] if not item["omitted"]) <= 12
    assert "situation_capped" in {item["code"] for item in body["warnings"]}


def test_situation_geometry_of_another_organization_is_404(repository):
    source = _upload(_client(repository), ("ситуация.dxf", situation_dxf()))[0]

    assert _client(repository, SESSION_B).get(f"{BASE}/sources/{source['id']}/situation").status_code == 404


# --- «Чертежи объекта»: список и удаление -------------------------------------


def test_site_sources_are_listed_with_situation_counts(repository):
    client = _client(repository)
    block = _upload(client, ("28.09.2026г граница блока 70.dxf", block_dxf()))[0]
    situation = _upload(client, ("Положение горных работ на 01.09.2026.dxf", situation_dxf()))[0]
    _upload(_client(repository, work_object="Другой карьер"), ("чужой объект.dxf", situation_dxf()))

    listed = client.get(f"{BASE}/sources")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["site_code"] == "SITE_ZK"
    assert [item["id"] for item in body["sources"]] == [situation["id"], block["id"]]
    first = body["sources"][0]
    assert (first["title"], first["survey_date"], first["uploaded_by"]) == (
        "Положение горных работ",
        "2026-09-01",
        "a@example.ru",
    )
    assert first["situation_count"] == 5
    assert body["sources"][1]["situation_count"] == 1


def test_without_a_site_the_list_is_empty(repository):
    _upload(_client(repository, work_object=""), ("a.dxf", situation_dxf()))

    assert _client(repository, work_object="").get(f"{BASE}/sources").json() == {
        "site_code": "",
        "sources": [],
        "truncated": False,
    }


def test_delete_removes_the_source_for_good(repository):
    client = _client(repository)
    source = _upload(client, ("a.dxf", situation_dxf()))[0]

    assert _client(repository, SESSION_B).delete(f"{BASE}/sources/{source['id']}").status_code == 404
    assert client.delete(f"{BASE}/sources/{source['id']}").status_code == 204
    assert client.get(f"{BASE}/sources/{source['id']}").status_code == 404
    assert client.delete(f"{BASE}/sources/{source['id']}").status_code == 404


def test_too_many_references_are_refused(repository):
    client = _client(repository)

    answer = client.get(f"{BASE}/situation", params=[("source_ids", f"id-{index}") for index in range(51)])
    assert answer.status_code == 422


def test_role_edit_keeps_crs_warnings_in_the_answer(repository):
    # Окно заменяет предупреждения ответом правки ролей — подсказка о СК не должна пропадать.
    client = _client(repository)
    source = _upload(client, ("block.dxf", block_dxf()))[0]

    answer = client.put(f"{BASE}/sources/{source['id']}/roles", json={"layers": {"Отметка": "situation"}}).json()

    assert "crs_missing" in {item["code"] for item in answer["warnings"]}


def test_rare_situation_series_survives_many_block_files(repository):
    """Ревью: предел каталога — не 50 последних файлов объекта, а версии на серию."""

    from design.spatial.cad.repository import CadSourceRecord

    client = _client(repository)
    situation = _upload(client, ("ЛЭП объекта на 01.06.2026.dxf", situation_dxf()))[0]
    # Шестьдесят файлов блоков без ситуации загружены позже.
    template = repository.get_source("org-a", situation["id"])
    for index in range(60):
        repository.create_sources(
            "org-a",
            [
                (
                    CadSourceRecord(
                        id=f"block-{index}",
                        site_code="SITE_ZK",
                        work_object_name="Жуков камень",
                        file_name=f"блок {index}.dxf",
                        file_format="dxf",
                        file_size=1,
                        file_sha256=f"{index:064d}",
                        params=template.params,
                        summary={},
                        uploaded_by="a@example.ru",
                        uploaded_at=template.uploaded_at.replace(year=2027),
                        title=f"блок {index}",
                    ),
                    [],
                )
            ],
        )

    catalogue = _catalogue(client)
    assert [item["default_source_id"] for item in catalogue["series"]] == [situation["id"]]
    assert catalogue["truncated"] is False


def test_catalogue_series_fit_the_reference_limit(repository):
    """Codex (#108): у каждого файла блока со слоем ситуации своя серия.

    Каталог отдаёт не больше серий, чем `GET /situation` принимает ссылок, —
    иначе паспорт после «Построить блок» запомнит больше 50 версий и получит
    422 на всю подложку. Серии ссылки остаются, остальные — свежие.
    """

    from datetime import timedelta

    from api.schemas.cad import MAX_SITUATION_REFERENCES
    from design.spatial.cad.model import CadEntity
    from design.spatial.cad.repository import CadSourceRecord

    client = _client(repository)
    oldest = _upload(client, ("ЛЭП объекта на 01.06.2026.dxf", situation_dxf()))[0]
    template = repository.get_source("org-a", oldest["id"])
    road = CadEntity(handle="R1", layer="Дорога", kind="LWPOLYLINE", points=[(0, 0, 0), (5, 0, 0)], role="situation")
    total = MAX_SITUATION_REFERENCES + 10
    for index in range(total):
        repository.create_sources(
            "org-a",
            [
                (
                    CadSourceRecord(
                        id=f"block-{index:03d}",
                        site_code="SITE_ZK",
                        work_object_name="Жуков камень",
                        file_name=f"граница блока {index}.dxf",
                        file_format="dxf",
                        file_size=1,
                        file_sha256=f"{index:064d}",
                        params=template.params,
                        summary={},
                        uploaded_by="a@example.ru",
                        uploaded_at=template.uploaded_at + timedelta(days=index + 1),
                        title=f"граница блока {index}",
                    ),
                    [road],
                )
            ],
        )

    fresh = _catalogue(client)
    assert len(fresh["series"]) == MAX_SITUATION_REFERENCES
    assert fresh["truncated"] is True
    defaults = {item["default_source_id"] for item in fresh["series"]}
    assert f"block-{total - 1:03d}" in defaults and oldest["id"] not in defaults
    # Ссылки «Построить блок» — версии по умолчанию каталога — запрос принимает.
    _catalogue(client, *sorted(defaults))

    # Серия из ссылки паспорта видна, даже если старше всех.
    pinned = _catalogue(client, oldest["id"])
    assert len(pinned["series"]) == MAX_SITUATION_REFERENCES
    assert oldest["id"] in {item["default_source_id"] for item in pinned["series"]}


def test_long_series_keeps_the_newest_versions_and_the_pinned_one(repository, monkeypatch):
    from api.services import cad_situation_service

    monkeypatch.setattr(cad_situation_service, "MAX_VERSIONS_PER_SERIES", 3)
    client = _client(repository)
    ids = [
        _upload(client, (f"Положение горных работ на 0{day}.09.2026.dxf", situation_dxf(roads=day)))[0]["id"]
        for day in range(1, 6)
    ]

    fresh = _series(_catalogue(client))["положение горных работ"]
    assert [item["source_id"] for item in fresh["versions"]] == [ids[4], ids[3], ids[2]]
    assert _catalogue(client)["truncated"] is True

    # Версия из ссылки паспорта видна, даже если старше предела.
    pinned = _series(_catalogue(client, ids[0]))["положение горных работ"]
    assert pinned["default_source_id"] == ids[0]
    assert ids[0] in [item["source_id"] for item in pinned["versions"]]
