"""HTTP-маршруты съёмки к проекту блока (TASK-014, PR 5а): чтение, оценка, применение.

Паспорта на бурение — хранилище в памяти теста с контрактом PostgreSQL-репозитория
(`tests/test_api_drilling_passport.py::_Repository`), планы — во временном каталоге.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from api.main import request_validation_handler
from api.routers import survey
from api.schemas.design import BlastDesignSchema
from api.security import require_internal_access
from api.services.drilling_passport_service import get_drilling_passport_repository
from design import persistence as design_persistence
from design.lifecycle import STATUS_APPROVED, STATUS_IN_REVIEW
from design.models import BlastDesign
from tests.front_rows_fixtures import GAP_PATTERN, design_with, grid_rows
from tests.test_api_drilling_passport import _Repository

BASE = "/api/v1/design/survey"
ORG = "org-a"
SESSION = {"sub": "mark@example.ru", "role": "user", "org": ORG}
EXPLOSIVE = {"name": "Э-100", "density_t_m3": 1.2, "power_mj_kg": 3.8}


@pytest.fixture()
def data_dir():
    with tempfile.TemporaryDirectory() as tmp, patch("cost.persistence.data_root", return_value=Path(tmp)):
        yield Path(tmp)


@pytest.fixture()
def repository() -> _Repository:
    return _Repository()


@pytest.fixture()
def client(data_dir, repository) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.include_router(survey.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: dict(SESSION)
    app.dependency_overrides[get_drilling_passport_repository] = lambda: repository
    return TestClient(app)


def _design() -> BlastDesign:
    design = design_with(grid_rows(), GAP_PATTERN)
    design.design_id = ""
    return design


def _saved(design: BlastDesign | None = None, *, status: str = "") -> BlastDesign:
    saved = design_persistence.save_design(ORG, design or _design(), actor="eng")
    if status:
        saved.lifecycle_status = status
        design_persistence._write_json(design_persistence.design_path(ORG, saved.design_id), saved.to_dict())
    return design_persistence.load_design(ORG, saved.design_id)


def _schema(design: BlastDesign) -> dict:
    return BlastDesignSchema.model_validate(design.to_dict()).model_dump(mode="json")


def _points(design: BlastDesign, *, shift: dict[str, float] | None = None) -> list[dict]:
    shift = shift or {}
    return [
        {
            "name": hole.id, "x": hole.collar.x + shift.get(hole.id, 0.0), "y": hole.collar.y,
            "z": hole.collar.z, "depth_m": hole.length_m, "line": index + 2,
        }
        for index, hole in enumerate(design.holes)
    ]


def _passport(repository: _Repository, design_id: str, payload: dict) -> dict:
    passport = repository.create_passport(ORG, "eng", design_id, "66-26/Б", "2026-11-10", payload)
    context = {
        "formula_version": "drill-v1", "design_id": design_id, "design_revision": 1, "design_sha256": "x",
        "passport": {"passport_no": "66-26/Б", "passport_date": "2026-11-10", "payload": payload},
    }
    return repository.create_revision(ORG, "eng", passport["id"], passport["version"], "ref-1", context, "sha")


def _evaluate(client: TestClient, design: BlastDesign, **extra) -> dict:
    body = {"design": _schema(design), "design_id": design.design_id, "points": _points(design), **extra}
    response = client.post(f"{BASE}/evaluate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _apply_body(design: BlastDesign, points: list[dict], **extra) -> dict:
    return {
        "design": _schema(design), "design_id": design.design_id, "points": points,
        "file_name": "s66.csv", "file_sha256": "ab" * 32, "survey_date": "2026-11-13", **extra,
    }


def test_read_csv_returns_points(client):
    content = "№;E;N;Z;Глубина\n1-01;8,0;2,0;0,0;11,0\n1-02;12,5;2,0;0,0;10,9\n".encode("cp1251")
    response = client.post(f"{BASE}/read", files={"file": ("s66.csv", content, "text/csv")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["format"] == "TABLE"
    assert body["file_name"] == "s66.csv"
    assert len(body["sha256"]) == 64
    assert body["points"][0] == {
        "name": "1-01", "x": 8.0, "y": 2.0, "z": 0.0, "depth_m": 11.0, "line": 2,
        "angle_deg": None, "azimuth_deg": None, "wet": None, "water_depth_m": None,
    }
    assert body["columns"]["depth"] == "Глубина"


def test_read_bad_file_is_422_with_message(client):
    response = client.post(f"{BASE}/read", files={"file": ("s66.csv", b"   ", "text/csv")})
    assert response.status_code == 422
    assert response.json()["detail"] == "Файл съёмки пустой."


def test_read_columns_must_be_json_object(client):
    response = client.post(
        f"{BASE}/read", files={"file": ("s66.csv", b"a,b\n1,2\n", "text/csv")}, data={"columns": "[1]"}
    )
    assert response.status_code == 422


def test_evaluate_uses_passport_revision_tolerances(client, repository):
    design = _saved()
    _passport(repository, design.design_id, {"tol_collar_m": 0.5, "block": "66"})
    body = _evaluate(client, design)
    assert body["tolerances"]["collar_m"] == 0.5
    assert body["tolerances"]["depth_m"] == 0.3
    assert body["tolerances"]["source"] == "passport"
    assert body["tolerances"]["passport_no"] == "66-26/Б"
    assert body["tolerances"]["revision_no"] == 1
    assert body["block"] == "66"
    assert body["warnings"] == []
    assert body["swap_suggested"] is False
    first = next(match for match in body["matches"] if match["hole_id"] == "1-01")
    assert first["by"] == "name" and first["issue"] == "" and first["point"]["name"] == "1-01"
    verdict = next(item for item in body["verdicts"] if item["hole_id"] == "1-01")
    assert verdict["codes"] == ["ok"] and verdict["unchanged"] is True
    assert verdict["point"]["x"] == design.holes[0].collar.x


def test_evaluate_draft_passport_without_revision_is_skipped(client, repository):
    design = _saved()
    _passport(repository, design.design_id, {"tol_collar_m": 0.5})
    repository.create_passport(ORG, "eng", design.design_id, "66-27/Б", "2026-11-11", {"tol_collar_m": 0.9})
    assert _evaluate(client, design)["tolerances"]["collar_m"] == 0.5


def test_evaluate_falls_back_to_parent_then_default(client, repository):
    original = _saved()
    _passport(repository, original.design_id, {"tol_depth_m": 0.4, "block": "66"})
    copy = design_persistence.fork_design(ORG, original.design_id, actor="eng")
    body = _evaluate(client, copy)
    assert body["tolerances"]["source"] == "parent_passport"
    assert body["tolerances"]["depth_m"] == 0.4
    assert body["tolerances"]["passport_design_id"] == original.design_id
    assert body["block"] == "66"

    lonely = _saved()
    body = _evaluate(client, lonely)
    assert body["tolerances"]["source"] == "default"
    assert body["tolerances"]["collar_m"] == 0.3
    assert body["tolerances"]["revision_no"] is None
    assert any("умолчани" in text for text in body["warnings"])

    unsaved = _design()
    assert _evaluate(client, unsaved)["tolerances"]["source"] == "default"


def test_evaluate_block_from_request_wins(client, repository):
    design = _saved()
    _passport(repository, design.design_id, {"block": "66"})
    assert _evaluate(client, design, block="67")["block"] == "67"


def test_evaluate_extra_point_is_unmatched(client):
    design = _design()
    points = [*_points(design), {"name": "Rp1", "x": 500.0, "y": 500.0, "line": 99}]
    response = client.post(f"{BASE}/evaluate", json={"design": _schema(design), "points": points})
    body = response.json()
    extra = next(match for match in body["matches"] if match["point"] and match["point"]["name"] == "Rp1")
    assert extra["hole_id"] is None and extra["issue"] == "unmatched_point"


def test_apply_returns_changed_holes_and_application(client):
    design = _design()
    points = _points(design, shift={"1-01": 0.2})
    body = _apply_body(design, points)
    response = client.post(f"{BASE}/apply", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["changed_ids"] == ["1-01"]
    moved = next(hole for hole in result["holes"] if hole["id"] == "1-01")
    assert moved["collar"]["x"] == pytest.approx(design.holes[0].collar.x + 0.2)
    assert result["loads"] is None
    assert len(result["as_drilled_holes"]) == len(design.holes)
    application = result["survey_application"]
    assert application["file_name"] == "s66.csv"
    assert application["survey_date"] == "2026-11-13"
    assert application["actor"] == "mark@example.ru"
    assert application["applied_at"].endswith("Z") or "+00:00" in application["applied_at"]
    assert application["counts"]["changed"] == 1


def test_apply_recharges_changed_holes(client):
    from Blast import ExplosiveProperties
    from design.charging import apply_charge_rules

    design = _design()
    design.loads = apply_charge_rules(design.holes, {"stemming_m": 3.0}, ExplosiveProperties(**EXPLOSIVE))
    points = _points(design)
    points[0]["depth_m"] = design.holes[0].length_m + 1.0
    charge = {"holes": [], "rules": {"stemming_m": 3.0}, "explosive": EXPLOSIVE}
    response = client.post(f"{BASE}/apply", json=_apply_body(design, points, charge=charge))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["changed_ids"] == ["1-01"]
    assert len(result["loads"]) == len(design.loads)

    without = client.post(f"{BASE}/apply", json=_apply_body(design, points)).json()
    assert without["loads"] is None
    assert any("заряд" in text.lower() for text in without["warnings"])


def test_apply_on_approved_is_409(client):
    design = _saved(status=STATUS_APPROVED)
    response = client.post(f"{BASE}/apply", json=_apply_body(design, _points(design, shift={"1-01": 0.2})))
    assert response.status_code == 409
    assert response.json()["detail"] == "Проект утверждён: правка по съёмке — через «Копию по съёмке»"


def test_apply_on_approved_is_409_when_only_design_carries_id(client):
    design = _saved(status=STATUS_APPROVED)
    body = _apply_body(design, _points(design))
    body["design_id"] = ""
    assert client.post(f"{BASE}/apply", json=body).status_code == 409


def test_apply_in_review_is_409_with_hint(client):
    design = _saved(status=STATUS_IN_REVIEW)
    response = client.post(f"{BASE}/apply", json=_apply_body(design, _points(design)))
    assert response.status_code == 409
    assert response.json()["detail"] == "Проект на проверке: верните его в черновик"


def test_apply_mismatched_design_id_is_400(client):
    design = _saved()
    body = _apply_body(design, _points(design))
    body["design_id"] = "other"
    assert client.post(f"{BASE}/apply", json=body).status_code == 400


def test_apply_unknown_saved_design_is_404(client):
    design = _design()
    body = _apply_body(design, _points(design))
    body["design_id"] = "nope"
    assert client.post(f"{BASE}/apply", json=body).status_code == 404


def test_apply_on_draft_does_not_persist(client):
    design = _saved()
    before = design_persistence.load_design(ORG, design.design_id).to_dict()
    response = client.post(f"{BASE}/apply", json=_apply_body(design, _points(design, shift={"1-01": 0.2})))
    assert response.status_code == 200, response.text
    assert response.json()["changed_ids"] == ["1-01"]
    assert design_persistence.load_design(ORG, design.design_id).to_dict() == before


def test_apply_rejects_bad_survey_date(client):
    design = _design()
    body = _apply_body(design, _points(design))
    body["survey_date"] = "13.11.2026"
    assert client.post(f"{BASE}/apply", json=body).status_code == 422


def test_evaluate_without_passport_storage_uses_defaults(client, repository, monkeypatch):
    from design.drilling_passport_repository import DrillingPassportRepositoryError

    def broken(*_args, **_kwargs):
        raise DrillingPassportRepositoryError("нет связи")

    monkeypatch.setattr(repository, "list_passports", broken)
    body = _evaluate(client, _saved())
    assert body["tolerances"]["source"] == "default"
    assert body["warnings"] == ["Паспорта на бурение сейчас недоступны — допуски по умолчанию."]


def test_survey_routes_are_in_the_app():
    from api.main import app

    paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert {f"{BASE}/read", f"{BASE}/evaluate", f"{BASE}/apply"} <= paths.keys()


# --- съёмка старого блока на объекте ------------------------------------------------

SITE = "KGOK"
SITES_URL = f"{BASE}/sites/{SITE}"
OTHER_SESSION = {"sub": "eve@example.ru", "role": "user", "org": "org-b"}
CSV = "№;E;N;Z;Глубина\n1-01;8,0;2,0;0,0;11,0\n1-02;12,5;2,0;0,0;10,9\n".encode("cp1251")


class _Snapshot:
    def item(self, section: str, code: str):
        return object() if section == "sites" and code == SITE else None


@pytest.fixture()
def sites_client(data_dir, repository):
    from api.services.legacy_references import current_reference_snapshot
    from api.services.survey_service import get_site_survey_repository
    from design.survey.site_repository import InMemorySiteSurveyRepository

    store = InMemorySiteSurveyRepository()
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.include_router(survey.router, prefix="/api/v1")
    app.state.session = dict(SESSION)
    app.dependency_overrides[require_internal_access] = lambda: dict(app.state.session)
    app.dependency_overrides[current_reference_snapshot] = lambda: _Snapshot()
    app.dependency_overrides[get_site_survey_repository] = lambda: store
    return TestClient(app)


def _upload(client, content: bytes = CSV, *, url: str = SITES_URL, **form):
    data = {"block_label": " Б-12 ", "survey_date": "2026-10-01", "horizon_m": "410.5", **form}
    data = {key: value for key, value in data.items() if value is not None}
    return client.post(url, files={"file": ("b12.csv", content, "text/csv")}, data=data)


def test_site_survey_create_list_get_delete(sites_client):
    created = _upload(sites_client)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["block_label"] == "Б-12"
    assert body["horizon_m"] == 410.5
    assert body["survey_date"] == "2026-10-01"
    assert body["file_name"] == "b12.csv"
    assert body["points_count"] == 2
    assert [point["name"] for point in body["points"]] == ["1-01", "1-02"]
    assert "organization_id" not in body

    listing = sites_client.get(SITES_URL).json()
    assert [item["id"] for item in listing] == [body["id"]]
    assert "points" not in listing[0]
    assert listing[0]["points_count"] == 2

    detail = sites_client.get(f"{SITES_URL}/{body['id']}").json()
    assert detail["points"][0]["depth_m"] == 11.0

    assert sites_client.delete(f"{SITES_URL}/{body['id']}").status_code == 204
    assert sites_client.get(SITES_URL).json() == []
    assert sites_client.get(f"{SITES_URL}/{body['id']}").status_code == 404


def test_site_surveys_newest_first(sites_client):
    old = _upload(sites_client, CSV + b"1-03;1;1;0;5\n", survey_date="2026-01-01").json()
    new = _upload(sites_client, survey_date="2026-09-01").json()
    assert [item["id"] for item in sites_client.get(SITES_URL).json()] == [new["id"], old["id"]]


def test_site_survey_unknown_site_is_404(sites_client):
    other = f"{BASE}/sites/NOPE"
    assert sites_client.get(other).status_code == 404
    assert _upload(sites_client, url=other).status_code == 404


def test_site_survey_duplicate_file_is_409(sites_client):
    assert _upload(sites_client).status_code == 201
    again = _upload(sites_client, block_label="Б-12")
    assert again.status_code == 409
    assert again.json()["detail"] == "Этот файл уже загружен"
    # Тот же файл для другого блока — отдельная съёмка.
    assert _upload(sites_client, block_label="Б-13").status_code == 201


def test_site_survey_other_organization_gets_404_and_keeps_record(sites_client):
    created = _upload(sites_client).json()
    sites_client.app.state.session = dict(OTHER_SESSION)
    assert sites_client.get(SITES_URL).json() == []
    assert sites_client.get(f"{SITES_URL}/{created['id']}").status_code == 404
    assert sites_client.delete(f"{SITES_URL}/{created['id']}").status_code == 404
    sites_client.app.state.session = dict(SESSION)
    assert sites_client.get(f"{SITES_URL}/{created['id']}").status_code == 200


def test_site_survey_validates_form(sites_client):
    assert _upload(sites_client, block_label="   ").status_code == 422
    assert _upload(sites_client, survey_date="01.10.2026").status_code == 422
    assert _upload(sites_client, survey_date=None).status_code == 422
    assert _upload(sites_client, b"   ").status_code == 422
    assert _upload(sites_client, horizon_m=None).json()["horizon_m"] is None
