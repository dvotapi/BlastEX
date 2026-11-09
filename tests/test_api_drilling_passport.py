"""HTTP-маршруты паспорта на бурение (TASK-015, PR 1): черновик, проверка, ревизия.

Хранилище — в памяти теста с тем же контрактом, что у PostgreSQL-репозитория
(сам репозиторий проверяет `test_drilling_passport_repository_pg.py`).
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from api.main import request_validation_handler
from api.routers import drilling_passport
from api.security import require_internal_access
from api.services import drilling_passport_service
from api.services.drilling_passport_service import get_drilling_passport_repository
from api.services.economics_service import get_economics_repository
from design.drilling_passport_repository import DrillingPassportConflictError, DrillingPassportNotFoundError
from tests.test_drilling_passport import _block66_design

BASE = "/api/v1/design/drilling-passports"
SESSION = {"sub": "engineer@example.ru", "role": "user", "org": "org-a"}
SITE = {"bench_face_angle_deg": "75", "stable_slope_angle_deg": "65"}
RIG = {"axis_offset_m": "1.2"}


class _Repository:
    """Хранилище в памяти: тот же контракт, что у PostgresDrillingPassportRepository."""

    def __init__(self) -> None:
        self.passports: dict[str, dict] = {}
        self.revisions: dict[str, dict] = {}

    def _get(self, organization_id, passport_id):
        item = self.passports.get(passport_id)
        if item is None or item["organization_id"] != organization_id:
            raise DrillingPassportNotFoundError(f"Паспорт на бурение {passport_id} не найден.")
        return item

    @staticmethod
    def _public(item):
        return {key: deepcopy(value) for key, value in item.items() if key != "organization_id"}

    def get_passport(self, organization_id, passport_id):
        return self._public(self._get(organization_id, passport_id))

    def create_passport(self, organization_id, actor, design_id, passport_no, passport_date, payload):
        passport_id = str(uuid4())
        self.passports[passport_id] = {
            "id": passport_id, "organization_id": organization_id, "design_id": design_id,
            "passport_no": passport_no, "passport_date": passport_date, "status": "draft", "version": 1,
            "current_revision_id": None, "payload": deepcopy(payload),
            "created_at": "2026-11-09T00:00:00+00:00", "created_by": actor,
            "updated_at": "2026-11-09T00:00:00+00:00", "updated_by": actor,
        }
        return self.get_passport(organization_id, passport_id)

    def update_passport(self, organization_id, actor, passport_id, passport_no, passport_date, payload, expected_version):
        item = self._get(organization_id, passport_id)
        if item["version"] != expected_version:
            raise DrillingPassportConflictError("Паспорт изменён другим пользователем.")
        item.update(passport_no=passport_no, passport_date=passport_date, payload=deepcopy(payload), updated_by=actor)
        item["version"] += 1
        return self.get_passport(organization_id, passport_id)

    def create_revision(self, organization_id, actor, passport_id, expected_version, reference_revision_id, context, content_sha256):
        item = self._get(organization_id, passport_id)
        if item["version"] != expected_version:
            raise DrillingPassportConflictError("Паспорт изменён другим пользователем.")
        number = sum(1 for rev in self.revisions.values() if rev["passport_id"] == passport_id) + 1
        revision_id = str(uuid4())
        self.revisions[revision_id] = {
            "id": revision_id, "passport_id": passport_id, "revision_no": number,
            "previous_revision_id": item["current_revision_id"], "reference_revision_id": reference_revision_id,
            "formula_version": context["formula_version"], "design_id": context["design_id"],
            "design_revision": context["design_revision"], "design_sha256": context["design_sha256"],
            "content_sha256": content_sha256, "context": deepcopy(context),
            "created_at": "2026-11-09T00:00:00+00:00", "created_by": actor,
        }
        item["current_revision_id"] = revision_id
        item["version"] += 1
        return self.get_revision(organization_id, revision_id)

    def get_revision(self, organization_id, revision_id):
        revision = self.revisions.get(revision_id)
        if revision is None:
            raise DrillingPassportNotFoundError(f"Ревизия {revision_id} не найдена.")
        self._get(organization_id, revision["passport_id"])
        return deepcopy(revision)


def _snapshot(site=SITE, rig=RIG):
    items = {("sites", "ZHK"): site, ("equipment_types", "JK830"): rig}

    def item(section, code):
        payload = items.get((section, code))
        return SimpleNamespace(payload=payload) if payload is not None else None

    return SimpleNamespace(revision_id="ref-1", item=item)


@pytest.fixture(scope="module")
def block66():
    return _block66_design()


@pytest.fixture()
def repository() -> _Repository:
    return _Repository()


@pytest.fixture()
def references() -> dict:
    return {"snapshot": _snapshot()}


@pytest.fixture()
def client(monkeypatch, repository, references, block66) -> TestClient:
    def load_design(organization_id, design_id):
        if organization_id != "org-a" or design_id != "block-66":
            raise drilling_passport_service.design_persistence.DesignNotFoundError(design_id)
        return block66

    monkeypatch.setattr(drilling_passport_service.design_persistence, "load_design", load_design)
    app = FastAPI()
    # Обработчик 422 приложения: бесконечность во входе он отдаёт без падения.
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.include_router(drilling_passport.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: dict(SESSION)
    app.dependency_overrides[get_drilling_passport_repository] = lambda: repository
    app.dependency_overrides[get_economics_repository] = lambda: SimpleNamespace(
        get_reference_snapshot=lambda organization_id, revision_id=None: references["snapshot"]
    )
    return TestClient(app)


PAYLOAD = {"site_code": "ZHK", "rig_type_code": "JK830", "block_area_m2": 2790, "w_max_m": 6.0}


def _create(client, payload=PAYLOAD) -> dict:
    response = client.post(BASE, json={"design_id": "block-66", "passport_date": "2026-11-09", "payload": payload})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_fills_defaults(client):
    passport = _create(client)
    assert passport["passport_no"] == "66-26/Б"
    assert passport["status"] == "draft"
    assert passport["payload"]["block"] == "66"
    assert passport["payload"]["acceptance"] == "исполнительная съёмка маркшейдерской службой заказчика"
    assert client.get(f"{BASE}/{passport['id']}").json()["payload"]["site_code"] == "ZHK"


def test_unknown_design_is_404(client):
    response = client.post(BASE, json={"design_id": "nope"})
    assert response.status_code == 404


def test_validate_returns_check_and_sources(client):
    passport = _create(client)
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    assert body["valid"] is True
    assert body["first_row_check"]["s_m"] == 2.4
    assert body["first_row_check"]["c_min_m"] == pytest.approx(1.2)
    assert body["summary"]["hole_count"] == 196
    assert body["provenance"]["alpha_deg"] == "REFERENCE"
    assert body["provenance"]["axis_offset_m"] == "REFERENCE"
    assert body["provenance"]["block_area_m2"] == "MANUAL_OVERRIDE"
    assert body["issues"] == []


def test_missing_angles_block_the_revision(client, references):
    references["snapshot"] = _snapshot(site={})
    passport = _create(client)
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    assert body["valid"] is False
    assert [issue["code"] for issue in body["issues"] if issue["level"] == "error"] == ["slope_angles_required"]
    response = client.post(f"{BASE}/{passport['id']}/revisions", json={"expected_version": passport["version"]})
    assert response.status_code == 422


def test_revision_needs_acknowledged_warnings(client):
    passport = _create(client, {**PAYLOAD, "first_row_offset_m": 2.0, "w_max_m": 4.9})
    url = f"{BASE}/{passport['id']}/revisions"

    refused = client.post(url, json={"expected_version": passport["version"]})
    assert refused.status_code == 409
    assert refused.json()["detail"]["unacknowledged_warnings"] == ["first_row_burden"]

    accepted = client.post(url, json={"expected_version": passport["version"], "acknowledged_warnings": ["first_row_burden"]})
    assert accepted.status_code == 201, accepted.text
    revision = accepted.json()
    assert revision["revision_no"] == 1
    assert revision["formula_version"] == "drill-v1"
    assert revision["reference_revision_id"] == "ref-1"
    assert revision["context"]["first_row_check"]["s_m"] == 2.4
    assert len(revision["context"]["holes"]) == 196


def test_revision_is_immutable_and_hash_repeats(client):
    passport = _create(client)
    url = f"{BASE}/{passport['id']}/revisions"
    first = client.post(url, json={"expected_version": 1}).json()

    # Черновик правят после выпуска — выпущенная ревизия не меняется.
    original = passport["payload"]
    changed = {**original, "w_max_m": 4.9, "first_row_offset_m": 2.0}
    put = client.put(
        f"{BASE}/{passport['id']}",
        json={"passport_no": "66-26/Б", "passport_date": "2026-11-09", "payload": changed, "expected_version": 2},
    )
    assert put.status_code == 200, put.text
    stored = client.get(f"{BASE}/revisions/{first['id']}").json()
    assert stored == first
    assert stored["context"]["passport"]["payload"]["w_max_m"] == 6.0

    # Вернули прежние поля — тот же снимок, тот же хэш.
    client.put(
        f"{BASE}/{passport['id']}",
        json={"passport_no": "66-26/Б", "passport_date": "2026-11-09", "payload": original, "expected_version": 3},
    )
    second = client.post(url, json={"expected_version": 4}).json()
    assert second["revision_no"] == 2
    assert second["content_sha256"] == first["content_sha256"]
    assert second["context"] == first["context"]


def test_stale_version_is_conflict(client):
    passport = _create(client)
    response = client.post(f"{BASE}/{passport['id']}/revisions", json={"expected_version": 7})
    assert response.status_code == 409


def test_foreign_organization_sees_nothing(client, repository):
    passport = _create(client)
    repository.passports[passport["id"]]["organization_id"] = "org-b"
    assert client.get(f"{BASE}/{passport['id']}").status_code == 404


def test_service_key_cannot_issue_revision(client):
    """Ревизию выпускает вошедший человек, а не внутренний ключ (как у массового взрыва)."""

    passport = _create(client)
    client.app.dependency_overrides[require_internal_access] = lambda: {"sub": "api-key", "role": "service", "org": "org-a"}
    response = client.post(f"{BASE}/{passport['id']}/revisions", json={"expected_version": passport["version"]})
    assert response.status_code == 403


def test_too_long_passport_number_is_422(client):
    response = client.post(BASE, json={"design_id": "block-66", "passport_no": "1" * 121})
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["w_max_m", "block_area_m2", "first_row_offset_m", "bit_diameter_mm"])
def test_infinite_number_is_422(client, field):
    # 1e400 в JSON — бесконечность: в JSONB её не записать, ответ не сериализовать.
    body = '{"design_id": "block-66", "payload": {"%s": 1e400}}' % field
    response = client.post(BASE, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
