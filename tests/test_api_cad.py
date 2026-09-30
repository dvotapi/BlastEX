"""HTTP-маршруты импорта чертежа: загрузка, источник, повторный разбор, роли."""
from __future__ import annotations

import io

import ezdxf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import cad
from api.security import require_internal_access
from api.services import cad_service
from api.services.cad_service import get_cad_repository
from api.services.legacy_references import current_reference_snapshot
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from design.spatial.cad.repository import InMemoryCadRepository

SNAPSHOT = ReferenceSnapshot(
    revision_id="rev-1",
    sections={"sites": (ReferenceItem(code="SITE_ZK", name="Жуков камень"),)},
)
SESSION_A = {"sub": "a@example.ru", "role": "admin", "org": "org-a"}
SESSION_B = {"sub": "b@example.ru", "role": "admin", "org": "org-b"}
BASE = "/api/v1/design/cad"


def _dxf(shift: float = 0.0) -> bytes:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_polyline3d([(0, 0, 410.5), (30, 0, 411.0)], dxfattribs={"layer": "Горизонт +410"})
    msp.add_polyline3d([(0, 20, 420.5), (30, 20 + shift, 421.0)], dxfattribs={"layer": "Горизонт +410"})
    msp.add_polyline3d([(50, 0, 421.5), (60, 0, 421.8)], dxfattribs={"layer": "Отвал вскрышных пород"})
    msp.add_point((5, 5, 415.2), dxfattribs={"layer": "Отметка"})
    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode("utf-8")


@pytest.fixture()
def repository() -> InMemoryCadRepository:
    return InMemoryCadRepository()


def _client(repository: InMemoryCadRepository, session: dict = SESSION_A) -> TestClient:
    app = FastAPI()
    app.include_router(cad.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: session
    app.dependency_overrides[get_cad_repository] = lambda: repository
    app.dependency_overrides[current_reference_snapshot] = lambda: SNAPSHOT
    return TestClient(app)


def _upload(client: TestClient, *files: tuple[str, bytes], **form) -> dict:
    data = {"work_object_name": "Жуков камень", **{key: str(value) for key, value in form.items()}}
    response = client.post(
        f"{BASE}/sources",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
        data=data,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _roles(source: dict) -> dict[str, tuple[str, str]]:
    return {item["handle"]: (item["role"], item["role_origin"]) for item in source["entities"]}


def _layers(source: dict) -> dict[str, tuple[str, str]]:
    return {item["name"]: (item["role"], item["origin"]) for item in source["layers"]}


def test_meta_lists_roles_and_origins_in_russian(repository):
    meta = _client(repository).get(f"{BASE}/meta").json()

    assert [item["code"] for item in meta["roles"]] == [
        "block_contour",
        "design_line",
        "crest_top",
        "crest_bottom",
        "feature_line",
        "contour_line",
        "spot_heights",
        "situation",
        "ignore",
    ]
    assert meta["layer_roles"] == [{"code": "crests_by_z", "label": "Бровки (по Z)", "applies_to": ["line"]}]
    assert {item["code"]: item["label"] for item in meta["origins"]} == {
        "template": "шаблон",
        "auto": "авто",
        "z": "по Z",
        "manual": "вручную",
    }
    assert meta["defaults"]["label_radius_m"] == 3.0


def test_upload_of_two_files_creates_two_sources(repository):
    body = _upload(_client(repository), ("a.dxf", _dxf()), ("b.dxf", _dxf(0.5)))

    assert len(body["sources"]) == 2
    source = body["sources"][0]
    assert source["file_name"] == "a.dxf"
    assert source["site_code"] == "SITE_ZK"
    assert source["template_saved"] is True
    assert _layers(source) == {
        "Горизонт +410": ("crests_by_z", "auto"),
        "Отвал вскрышных пород": ("situation", "auto"),
        "Отметка": ("spot_heights", "auto"),
    }
    horizon = next(item for item in source["layers"] if item["name"] == "Горизонт +410")
    assert horizon["entity_count"] == 2
    assert horizon["counts_by_role"] == {"crest_bottom": 1, "crest_top": 1}
    assert (horizon["z_min"], horizon["z_max"]) == (410.5, 421.0)
    assert source["floor_z_m"] == 410.0
    line = next(item for item in source["entities"] if item["kind"] == "POLYLINE3D")
    assert line["points"][0] == [0.0, 0.0, 410.5]
    assert line["geometry_type"] == "line"
    assert repository.get_layer_template("org-a", "SITE_ZK")["горизонт +410"] == "crests_by_z"


def test_source_is_read_back(repository):
    client = _client(repository)
    created = _upload(client, ("a.dxf", _dxf()))["sources"][0]

    fetched = client.get(f"{BASE}/sources/{created['id']}").json()

    assert fetched == created


def test_oversized_file_is_refused_with_its_name(repository, monkeypatch):
    monkeypatch.setattr(cad_service, "MAX_FILE_BYTES", 100)
    response = _client(repository).post(
        f"{BASE}/sources", files=[("files", ("большой.dxf", _dxf(), "application/octet-stream"))]
    )

    assert response.status_code == 413
    assert "большой.dxf" in response.json()["detail"]


def test_unreadable_file_saves_nothing_from_the_request(repository):
    response = _client(repository).post(
        f"{BASE}/sources",
        files=[
            ("files", ("хороший.dxf", _dxf(), "application/octet-stream")),
            ("files", ("битый.dxf", b"garbage bytes", "application/octet-stream")),
        ],
    )

    assert response.status_code == 422
    assert "битый.dxf" in response.json()["detail"]
    assert repository.get_layer_template("org-a", "SITE_ZK") == {}


def test_without_a_work_object_the_template_is_not_saved(repository):
    source = _upload(_client(repository), ("a.dxf", _dxf()), work_object_name="")["sources"][0]

    assert source["template_saved"] is False
    assert any(item["code"] == "template_not_saved" for item in source["warnings"])


def test_second_file_is_labelled_by_the_site_template(repository):
    client = _client(repository)
    first = _upload(client, ("a.dxf", _dxf()))["sources"][0]
    client.put(
        f"{BASE}/sources/{first['id']}/roles", json={"layers": {"Отвал вскрышных пород": "ignore"}}
    ).raise_for_status()

    second = _upload(client, ("b.dxf", _dxf(0.5)))["sources"][0]

    assert _layers(second) == {
        "Горизонт +410": ("crests_by_z", "template"),
        "Отвал вскрышных пород": ("ignore", "template"),
        "Отметка": ("spot_heights", "template"),
    }
    assert {role for role, _ in _roles(second).values()} >= {"crest_top", "crest_bottom"}


def test_manual_roles_are_saved_and_can_be_reset(repository):
    client = _client(repository)
    source = _upload(client, ("a.dxf", _dxf()))["sources"][0]
    point = next(item["handle"] for item in source["entities"] if item["kind"] == "POINT")

    changed = client.put(
        f"{BASE}/sources/{source['id']}/roles",
        json={"layers": {"Отвал вскрышных пород": "ignore"}, "entities": {point: "situation"}},
    ).json()

    assert _layers(changed)["Отвал вскрышных пород"] == ("ignore", "manual")
    assert _roles(changed)[point] == ("situation", "manual")
    assert repository.get_layer_template("org-a", "SITE_ZK")["отвал вскрышных пород"] == "ignore"

    reset = client.put(f"{BASE}/sources/{source['id']}/roles", json={"entities": {point: None}}).json()

    assert _roles(reset)[point] == ("spot_heights", "auto")
    assert _layers(reset)["Отвал вскрышных пород"] == ("ignore", "manual")


def test_unknown_role_or_layer_is_rejected(repository):
    client = _client(repository)
    source = _upload(client, ("a.dxf", _dxf()))["sources"][0]

    bad_role = client.put(f"{BASE}/sources/{source['id']}/roles", json={"layers": {"Отметка": "boss"}})
    bad_layer = client.put(f"{BASE}/sources/{source['id']}/roles", json={"layers": {"Нет такого": "ignore"}})

    assert bad_role.status_code == 422
    assert bad_layer.status_code == 422
    assert "Нет такого" in bad_layer.json()["detail"]


def test_reparse_rescales_and_keeps_manual_roles(repository):
    client = _client(repository)
    source = _upload(client, ("a.dxf", _dxf()))["sources"][0]
    point = next(item["handle"] for item in source["entities"] if item["kind"] == "POINT")
    client.put(f"{BASE}/sources/{source['id']}/roles", json={"entities": {point: "ignore"}}).raise_for_status()

    reparsed = client.post(
        f"{BASE}/sources/{source['id']}/reparse",
        json={"scale": 0.001, "label_radius_m": 3, "floor_z_m": None, "bench_height_m": 10},
    ).json()

    moved = next(item for item in reparsed["entities"] if item["handle"] == point)
    assert moved["points"][0] == pytest.approx([0.005, 0.005, 0.4152])
    assert (moved["role"], moved["role_origin"]) == ("ignore", "manual")
    assert reparsed["params"]["scale"] == 0.001


def test_reparse_with_an_explicit_floor_moves_crests(repository):
    client = _client(repository)
    source = _upload(client, ("a.dxf", _dxf()))["sources"][0]

    reparsed = client.post(
        f"{BASE}/sources/{source['id']}/reparse",
        json={"scale": 1, "label_radius_m": 3, "floor_z_m": 400, "bench_height_m": 10},
    ).json()

    horizon = next(item for item in reparsed["layers"] if item["name"] == "Горизонт +410")
    assert horizon["counts_by_role"] == {"crest_top": 2}
    assert reparsed["floor_z_m"] == 400


def test_other_organization_gets_404(repository):
    source = _upload(_client(repository), ("a.dxf", _dxf()))["sources"][0]
    foreign = _client(repository, SESSION_B)

    assert foreign.get(f"{BASE}/sources/{source['id']}").status_code == 404
    assert foreign.put(f"{BASE}/sources/{source['id']}/roles", json={"layers": {}}).status_code == 404
    assert (
        foreign.post(
            f"{BASE}/sources/{source['id']}/reparse",
            json={"scale": 1, "label_radius_m": 3, "floor_z_m": None, "bench_height_m": 10},
        ).status_code
        == 404
    )
    assert repository.get_layer_template("org-b", "SITE_ZK") == {}
