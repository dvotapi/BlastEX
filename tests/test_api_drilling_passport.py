"""HTTP-маршруты паспорта на бурение (TASK-015, PR 1): черновик, проверка, ревизия.

Хранилище — в памяти теста с тем же контрактом, что у PostgreSQL-репозитория
(сам репозиторий проверяет `test_drilling_passport_repository_pg.py`).
"""
from __future__ import annotations

import json
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


PROFILE = {
    "safety_items": [{"text": "Только по паспорту."}, {"text": "Осмотреть бровку."}],
    "safety_basis": "Основание: ФНП 505.",
    "drilling_technology": "Продувать скважину.",
}


def _snapshot(site=SITE, rig=RIG):
    items = {("sites", "ZHK"): site, ("equipment_types", "JK830"): rig, ("drill_passport_profiles", "KGOK"): PROFILE}

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

    # Вернули прежние поля — тот же снимок: новая ревизия не выпускается,
    # возвращается последняя (один PDF — один номер ревизии).
    client.put(
        f"{BASE}/{passport['id']}",
        json={"passport_no": "66-26/Б", "passport_date": "2026-11-09", "payload": original, "expected_version": 3},
    )
    second = client.post(url, json={"expected_version": 4}).json()
    assert second == first


def test_changed_snapshot_gets_next_revision(client):
    passport = _create(client)
    url = f"{BASE}/{passport['id']}/revisions"
    first = client.post(url, json={"expected_version": 1}).json()
    changed = {**passport["payload"], "rig_number": "7"}
    client.put(
        f"{BASE}/{passport['id']}",
        json={"passport_no": "66-26/Б", "passport_date": "2026-11-09", "payload": changed, "expected_version": 2},
    )
    second = client.post(url, json={"expected_version": 3}).json()
    assert second["revision_no"] == 2
    assert second["content_sha256"] != first["content_sha256"]


def test_profile_texts_go_to_revision(client):
    passport = _create(client, {**PAYLOAD, "profile_code": "KGOK"})
    revision = client.post(f"{BASE}/{passport['id']}/revisions", json={"expected_version": 1}).json()
    profile = revision["context"]["profile"]
    assert profile == {
        "code": "KGOK",
        "safety_items": ["Только по паспорту.", "Осмотреть бровку."],
        "safety_basis": "Основание: ФНП 505.",
        "drilling_technology": "Продувать скважину.",
    }


def test_unknown_profile_is_warned_and_default_used(client):
    passport = _create(client, {**PAYLOAD, "profile_code": "NOPE"})
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    assert [issue["code"] for issue in body["issues"]] == ["drill_profile_not_found"]
    revision = client.post(
        f"{BASE}/{passport['id']}/revisions",
        json={"expected_version": 1, "acknowledged_warnings": ["drill_profile_not_found"]},
    ).json()
    assert len(revision["context"]["profile"]["safety_items"]) == 10
    assert revision["context"]["profile"]["code"] == ""


def test_empty_profile_code_uses_default_without_warning(client):
    passport = _create(client)
    assert passport["payload"]["profile_code"] == ""
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    assert body["issues"] == []


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


def _codes(client, payload) -> list[str]:
    passport = _create(client, payload)
    return [issue["code"] for issue in client.post(f"{BASE}/{passport['id']}/validate").json()["issues"]]


def test_unknown_site_and_rig_codes_are_warned(client):
    codes = _codes(client, {**PAYLOAD, "site_code": "NOPE", "rig_type_code": "JK999", "alpha_deg": 75, "gamma_deg": 65})
    assert "site_not_found" in codes
    assert "rig_type_not_found" in codes


def test_unread_references_are_warned(client, references):
    references["snapshot"] = None
    codes = _codes(client, {**PAYLOAD, "alpha_deg": 75, "gamma_deg": 65})
    assert "references_unavailable" in codes
    assert "site_not_found" not in codes and "rig_type_not_found" not in codes


def test_empty_codes_are_not_warned_as_unknown(client):
    codes = _codes(client, {**PAYLOAD, "rig_type_code": ""})
    assert "rig_type_not_found" not in codes
    assert "axis_offset_missing" in codes


# --- форма v0.7 -------------------------------------------------------------


def test_new_draft_has_form_v07_defaults(client):
    passport = _create(client)
    payload = passport["payload"]
    assert payload["site_preparation"] == "бульдозером под руководством горного мастера заказчика; приём площадки по акту"
    assert payload["extra_approvals"] == ["маркшейдер", "геолог"]
    assert (payload["tol_depth_m"], payload["tol_collar_m"]) == (0.3, 0.3)
    assert payload["bench_height_for_s_m"] is None
    # Должности без «ведущий»: на карьерах они разные.
    assert "ведущ" not in json.dumps(payload, ensure_ascii=False)


def test_form_v07_fields_are_stored(client):
    payload = {
        **PAYLOAD,
        "site_preparation": "грейдером",
        "extra_approvals": ["маркшейдер Иванов И. И."],
        "tol_depth_m": 0.2,
        "tol_collar_m": 0.5,
        "bench_height_for_s_m": 10.0,
    }
    passport = _create(client, payload)
    stored = client.get(f"{BASE}/{passport['id']}").json()["payload"]
    for key in ("site_preparation", "extra_approvals", "tol_depth_m", "tol_collar_m", "bench_height_for_s_m"):
        assert stored[key] == payload[key]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("extra_approvals", ["маркшейдер", "геолог", "технолог"]),
        ("extra_approvals", ["х" * 121]),
        ("bench_height_for_s_m", 0),
        ("bench_height_for_s_m", 31),
        ("tol_depth_m", 0),
        ("tol_collar_m", 2.5),
    ],
)
def test_form_v07_fields_out_of_range_are_422(client, field, value):
    response = client.post(BASE, json={"design_id": "block-66", "payload": {**PAYLOAD, field: value}})
    assert response.status_code == 422


def test_validate_returns_design_bench_height(client):
    passport = _create(client, {**PAYLOAD, "bench_height_for_s_m": 10.0})
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    check = body["first_row_check"]
    assert (check["hs_m"], check["hs_source"], check["s_m"]) == (10.0, "MANUAL_OVERRIDE", 2.0)
    assert body["inputs"]["bench_height_for_s_m"] == 10.0
    assert body["provenance"]["bench_height_for_s_m"] == "MANUAL_OVERRIDE"
    assert "bench_above_design" in [issue["code"] for issue in body["issues"]]

    plain = client.post(f"{BASE}/{_create(client)['id']}/validate").json()
    assert plain["inputs"]["bench_height_for_s_m"] == pytest.approx(11.7)
    assert plain["provenance"]["bench_height_for_s_m"] == "CALCULATED"


# --- PDF из ревизии (PR 2) -------------------------------------------------

def _revision(client, payload=PAYLOAD) -> dict:
    passport = _create(client, payload)
    response = client.post(f"{BASE}/{passport['id']}/revisions", json={"expected_version": passport["version"]})
    assert response.status_code == 201, response.text
    return response.json()


def test_passport_pdf_from_revision(client):
    revision = _revision(client)
    response = client.get(f"{BASE}/revisions/{revision['id']}/passport.pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in disposition
    assert "66-26-%D0%91" in disposition          # «/» в номере заменён
    assert disposition.endswith("rev1.pdf")
    again = client.get(f"{BASE}/revisions/{revision['id']}/passport.pdf")
    assert again.content == response.content


def test_passport_pdf_uses_revision_snapshot_only(client, repository):
    revision = _revision(client)
    url = f"{BASE}/revisions/{revision['id']}/passport.pdf"
    before = client.get(url).content
    # Черновик правят после выпуска — PDF ревизии тот же.
    passport_id = revision["passport_id"]
    draft = client.get(f"{BASE}/{passport_id}").json()
    client.put(
        f"{BASE}/{passport_id}",
        json={"passport_no": "ДРУГОЙ", "passport_date": "2026-11-10",
              "payload": {**draft["payload"], "rig_name": "СБШ-250"}, "expected_version": draft["version"]},
    )
    assert client.get(url).content == before
    # Меняется снимок — меняется PDF.
    repository.revisions[revision["id"]]["context"]["passport"]["passport_no"] = "77-26/Б"
    assert client.get(url).content != before


def test_passport_pdf_of_foreign_or_unknown_revision_is_404(client, repository):
    revision = _revision(client)
    repository.passports[revision["passport_id"]]["organization_id"] = "org-b"
    assert client.get(f"{BASE}/revisions/{revision['id']}/passport.pdf").status_code == 404
    assert client.get(f"{BASE}/revisions/nope/passport.pdf").status_code == 404


# --- правки по ревью PR 2 ----------------------------------------------------

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("drilling_order", "т" * 301),
        ("basis", "т" * 301),
        ("object_name", "т" * 201),
        ("personnel", [{"name": "Иванов", "position": "машинист"}] * 21),
    ],
    ids=["drilling_order", "basis", "object_name", "personnel"],
)
def test_printed_fields_have_length_limits(client, field, value):
    response = client.post(BASE, json={"design_id": "block-66", "payload": {**PAYLOAD, field: value}})
    assert response.status_code == 422


def test_unchanged_snapshot_of_approved_passport_is_conflict(client, repository):
    revision = _revision(client)
    passport = repository.passports[revision["passport_id"]]
    passport["status"] = "approved"
    response = client.post(f"{BASE}/{passport['id']}/revisions", json={"expected_version": passport["version"]})
    assert response.status_code == 409
    assert "только из черновика" in response.json()["detail"]
