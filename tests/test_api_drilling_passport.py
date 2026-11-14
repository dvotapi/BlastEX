"""HTTP-маршруты паспорта на бурение (TASK-015, PR 1): черновик, проверка, ревизия.

Хранилище — в памяти теста с тем же контрактом, что у PostgreSQL-репозитория
(сам репозиторий проверяет `test_drilling_passport_repository_pg.py`).
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timezone
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

    def list_passports(self, organization_id, design_id=None):
        # Как у PostgreSQL — последний изменённый первым (здесь — последний созданный).
        items = [
            item for item in self.passports.values()
            if item["organization_id"] == organization_id and (not design_id or item["design_id"] == design_id)
        ]
        return tuple(self._public(item) for item in reversed(items))

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


def _snapshot(site=SITE, rig=RIG, stakeout_profiles=None, extra=None):
    """Справочники теста; `extra` — {(раздел, код): (название, payload)}."""

    items = {
        ("sites", "ZHK"): site, ("equipment_types", "JK830"): rig, ("drill_passport_profiles", "KGOK"): PROFILE,
        # Норматив станка: без него проверка предупреждает `drilling_norm_missing`.
        ("drilling_conditions", "JK830"): {"equipment_type_code": "JK830", "tech_speed_m_per_h": "25"},
    }
    names: dict[tuple[str, str], str] = {}
    for code, (name, payload) in (stakeout_profiles or {}).items():
        items[("stakeout_profiles", code)] = payload
        names[("stakeout_profiles", code)] = name
    for key, (name, payload) in (extra or {}).items():
        items[key] = payload
        names[key] = name

    def item(section, code):
        payload = items.get((section, code))
        return SimpleNamespace(code=code, name=names.get((section, code), code), payload=payload) if payload is not None else None

    def active_items(section):
        return tuple(item(sec, code) for sec, code in items if sec == section)

    return SimpleNamespace(revision_id="ref-1", item=item, active_items=active_items)


@pytest.fixture(scope="module")
def block66():
    # W проекта 6,0 м (сетка 3,7 × 6,0): ЛСПП первого ряда у подошвы (до 5,94 м)
    # в допуске — у выпуска нет предупреждения `first_row_burden`. С исходной
    # квадратной 3,7 оно есть (см. `test_revision_needs_acknowledged_warnings`).
    design = _block66_design()
    design.pattern_params = {"pattern": "rectangular", "spacing_a_m": 3.7, "burden_b_m": 6.0}
    return design


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


PAYLOAD = {"site_code": "ZHK", "rig_type_code": "JK830", "block_area_m2": 2790, "bit_diameter_mm": 140}


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


def test_revision_needs_acknowledged_warnings(client, block66):
    # Квадратная 3,7: ЛСПП первого ряда до 5,94 м больше W проекта + 3 % = 3,81 м.
    block66.pattern_params = {"pattern": "square", "spacing_a_m": 3.7}
    try:
        _check_acknowledged_warnings(client)
    finally:
        block66.pattern_params = {"pattern": "rectangular", "spacing_a_m": 3.7, "burden_b_m": 6.0}


def _check_acknowledged_warnings(client):
    passport = _create(client)
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
    changed = {**original, "horizon": "+398"}
    put = client.put(
        f"{BASE}/{passport['id']}",
        json={"passport_no": "66-26/Б", "passport_date": "2026-11-09", "payload": changed, "expected_version": 2},
    )
    assert put.status_code == 200, put.text
    stored = client.get(f"{BASE}/revisions/{first['id']}").json()
    assert stored == first
    assert stored["context"]["passport"]["payload"]["horizon"] == original["horizon"]

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


@pytest.mark.parametrize("field", ["block_area_m2", "bit_diameter_mm", "alpha_deg"])
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


SURVEY_TOLERANCES = ("tol_angle_deg", "tol_burden_pct", "tol_spacing_pct")


def test_survey_tolerances_are_stored_only_when_set(client):
    # Допуски съёмки (TASK-014, PR 5а) не меняют payload прежних паспортов: ключ — только заданный.
    passport = _create(client)
    assert not set(SURVEY_TOLERANCES) & set(passport["payload"])
    payload = {**PAYLOAD, "tol_angle_deg": 1.5, "tol_burden_pct": 7.0, "tol_spacing_pct": None}
    stored = client.get(f"{BASE}/{_create(client, payload)['id']}").json()["payload"]
    assert (stored["tol_angle_deg"], stored["tol_burden_pct"]) == (1.5, 7.0)
    assert "tol_spacing_pct" not in stored


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("extra_approvals", ["маркшейдер", "геолог", "технолог"]),
        ("extra_approvals", ["х" * 121]),
        ("bench_height_for_s_m", 0),
        ("bench_height_for_s_m", 31),
        ("tol_depth_m", 0),
        ("tol_collar_m", 2.5),
        ("tol_angle_deg", 0),
        ("tol_angle_deg", 10.5),
        ("tol_burden_pct", 0),
        ("tol_burden_pct", 51),
        ("tol_spacing_pct", -1),
        ("tol_spacing_pct", 50.5),
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
        ("personnel", [{"name": "Иванов", "position": "т" * 101}]),
    ],
    ids=["drilling_order", "basis", "object_name", "personnel", "position"],
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


def test_old_draft_with_long_texts_still_opens(client, repository):
    passport = _create(client)
    stored = repository.passports[passport["id"]]
    stored["payload"]["basis"] = "т" * 400
    stored["payload"]["personnel"] = [{"name": "Иванов", "position": "машинист"}] * 25
    response = client.get(f"{BASE}/{passport['id']}")
    assert response.status_code == 200, response.text
    assert len(response.json()["payload"]["personnel"]) == 25


def test_long_contour_name_is_cut_to_block_limit(client, block66, monkeypatch):
    """Блок по умолчанию — имя контура; длиннее предела — обрезается, черновик сохраняется."""

    monkeypatch.setattr(block66.contour, "name", "Б" * 45)
    response = client.post(BASE, json={"design_id": "block-66", "passport_date": "2026-11-09", "payload": {"site_code": "ZHK"}})
    assert response.status_code == 201, response.text
    passport = response.json()
    assert passport["payload"]["block"] == "Б" * 40
    saved = client.put(
        f"{BASE}/{passport['id']}",
        json={"passport_no": "66-26/Б", "passport_date": "2026-11-09", "payload": passport["payload"],
              "expected_version": passport["version"]},
    )
    assert saved.status_code == 200, saved.text


# --- PR 3: ситуация TASK-013 на плане -----------------------------------------

from design.spatial.cad.repository import CadSourceNotFound  # noqa: E402

SITUATION_REF = [{"source_id": "sit-1", "title": "Ситуация 10.2026", "survey_date": "2026-10-01"}]


def _situation_response(x: float, y: float, *, omitted: bool = False):
    line = SimpleNamespace(points=[[x - 10, y, 400.0], [x + 10, y, 400.0]], closed=False)
    layer = SimpleNamespace(kind="road", lines=[] if omitted else [line], omitted=omitted, name="Дороги")
    return SimpleNamespace(layers=[layer])


class _CadRepository:
    """Каталог источников: версия (`revision`) — ключ кэша ситуации."""

    def __init__(self) -> None:
        self.revisions = {"sit-1": 1}
        # Источники объекта (план карьера — назначение «ситуация»).
        self.plans: list = []

    def list_site_sources(self, organization_id, site_code, *, limit, summary_keys=()):
        return list(self.plans)

    def get_source(self, organization_id, source_id, *, with_file=False):
        revision = self.revisions.get(source_id)
        return None if revision is None else SimpleNamespace(id=source_id, revision=revision)

    def __repr__(self) -> str:
        return "cad-repo"


@pytest.fixture()
def cad_repository(monkeypatch) -> _CadRepository:
    repository = _CadRepository()
    monkeypatch.setattr(drilling_passport_service, "get_cad_repository", lambda: repository)
    drilling_passport_service._SITUATION_CACHE.clear()
    yield repository
    drilling_passport_service._SITUATION_CACHE.clear()


@pytest.fixture()
def situation_refs(monkeypatch, block66, cad_repository):
    monkeypatch.setattr(block66.contour, "cad", {"situation": deepcopy(SITUATION_REF)})
    return block66


def test_context_takes_situation_of_passport_design(client, situation_refs, monkeypatch):
    collar = situation_refs.holes[0].collar
    calls = []

    def source_situation(repository, organization_id, source_id):
        calls.append((repository, organization_id, source_id))
        return _situation_response(collar.x, collar.y)

    monkeypatch.setattr(drilling_passport_service, "source_situation", source_situation)
    passport = _create(client)
    revision = client.post(f"{BASE}/{passport['id']}/revisions", json={"expected_version": passport["version"]})
    assert revision.status_code == 201, revision.text
    assert [(organization_id, source_id) for _, organization_id, source_id in calls] == [("org-a", "sit-1")]
    (layer,) = revision.json()["context"]["plan"]["situation"]
    assert layer["kind"] == "road"
    assert layer["lines"][0]["points"] == [
        [round(collar.x - 10, 3), round(collar.y, 3)], [round(collar.x + 10, 3), round(collar.y, 3)],
    ]


def test_missing_situation_source_warns(client, situation_refs, monkeypatch):
    def source_situation(repository, organization_id, source_id):
        raise CadSourceNotFound(source_id)

    monkeypatch.setattr(drilling_passport_service, "source_situation", source_situation)
    passport = _create(client)
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    (issue,) = [item for item in body["issues"] if item["code"] == "plan_situation_missing"]
    assert issue["level"] == "warning" and "Ситуация 10.2026" in issue["message"]
    url = f"{BASE}/{passport['id']}/revisions"
    refused = client.post(url, json={"expected_version": passport["version"]})
    assert refused.status_code == 409
    accepted = client.post(
        url, json={"expected_version": passport["version"], "acknowledged_warnings": ["plan_situation_missing"]}
    )
    assert accepted.status_code == 201
    assert accepted.json()["context"]["plan"]["situation"] == []


def test_capped_situation_layer_warns(client, situation_refs, monkeypatch):
    collar = situation_refs.holes[0].collar
    monkeypatch.setattr(
        drilling_passport_service, "source_situation",
        lambda repository, organization_id, source_id: _situation_response(collar.x, collar.y, omitted=True),
    )
    passport = _create(client)
    codes = [item["code"] for item in client.post(f"{BASE}/{passport['id']}/validate").json()["issues"]]
    assert "plan_situation_capped" in codes


def test_no_situation_refs_and_no_pit_plan_no_situation(client, cad_repository, monkeypatch):
    """Без ссылок блока и без плана карьера у объекта ситуации нет — и предупреждений тоже."""

    def fail(*args, **kwargs):
        raise AssertionError("без плана карьера геометрию не читают")

    cad_repository.plans = []
    monkeypatch.setattr(drilling_passport_service, "source_situation", fail)
    passport = _create(client)
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    assert body["issues"] == []


def test_block_without_refs_takes_pit_plan_of_site(client, block66, cad_repository, monkeypatch):
    """Ситуация объекта (план карьера) — у блока без своих ссылок (план 2026-11-13, §3.3)."""

    collar = block66.holes[0].collar
    cad_repository.revisions["plan-2"] = 1
    cad_repository.plans = [
        SimpleNamespace(id="plan-1", title="Ситуационный план", file_name="", survey_date=date(2026, 9, 24),
                        uploaded_at=datetime(2026, 9, 25, tzinfo=timezone.utc), summary={"purpose": "situation"}),
        SimpleNamespace(id="plan-2", title="Ситуационный план", file_name="", survey_date=date(2026, 11, 1),
                        uploaded_at=datetime(2026, 11, 2, tzinfo=timezone.utc), summary={"purpose": "situation"}),
        SimpleNamespace(id="blk-70", title="граница блока 70", file_name="", survey_date=date(2026, 11, 5),
                        uploaded_at=datetime(2026, 11, 5, tzinfo=timezone.utc), summary={}),
    ]
    calls = []

    def source_situation(repository, organization_id, source_id):
        calls.append(source_id)
        return _situation_response(collar.x, collar.y)

    monkeypatch.setattr(drilling_passport_service, "source_situation", source_situation)
    passport = _create(client)
    revision = client.post(f"{BASE}/{passport['id']}/revisions", json={"expected_version": passport["version"]})
    assert revision.status_code == 201, revision.text
    assert calls == ["plan-2"]
    assert [layer["kind"] for layer in revision.json()["context"]["plan"]["situation"]] == ["road"]


def test_broken_situation_source_warns(client, situation_refs, monkeypatch):
    def source_situation(repository, organization_id, source_id):
        raise ValueError("рваные точки")

    monkeypatch.setattr(drilling_passport_service, "source_situation", source_situation)
    passport = _create(client)
    codes = [item["code"] for item in client.post(f"{BASE}/{passport['id']}/validate").json()["issues"]]
    assert "plan_situation_unavailable" in codes


def test_duplicate_situation_refs_read_once(client, situation_refs, monkeypatch):
    situation_refs.contour.cad["situation"] = deepcopy(SITUATION_REF) * 2
    collar = situation_refs.holes[0].collar
    calls = []

    def source_situation(repository, organization_id, source_id):
        calls.append(source_id)
        return _situation_response(collar.x, collar.y)

    monkeypatch.setattr(drilling_passport_service, "source_situation", source_situation)
    passport = _create(client)
    client.post(f"{BASE}/{passport['id']}/validate")
    assert calls == ["sit-1"]


def test_situation_is_read_once_per_source_revision(client, situation_refs, cad_repository, monkeypatch):
    collar = situation_refs.holes[0].collar
    calls = []

    def source_situation(repository, organization_id, source_id):
        calls.append(source_id)
        return _situation_response(collar.x, collar.y)

    monkeypatch.setattr(drilling_passport_service, "source_situation", source_situation)
    passport = _create(client)
    url = f"{BASE}/{passport['id']}/validate"
    client.post(url)
    client.post(url)
    assert calls == ["sit-1"]
    cad_repository.revisions["sit-1"] = 2   # файл ситуации переимпортирован
    client.post(url)
    assert calls == ["sit-1", "sit-1"]


def test_deleted_situation_source_is_not_read(client, situation_refs, cad_repository, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("удалённый источник не читают")

    monkeypatch.setattr(drilling_passport_service, "source_situation", fail)
    del cad_repository.revisions["sit-1"]
    passport = _create(client)
    codes = [item["code"] for item in client.post(f"{BASE}/{passport['id']}/validate").json()["issues"]]
    assert "plan_situation_missing" in codes


# --- чертёж скважин DXF / DWG (PR 4) -----------------------------------------

def _disposition_name(response) -> str:
    from urllib.parse import unquote

    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment; filename*=UTF-8''")
    return unquote(disposition.split("''", 1)[1])


def test_holes_dxf_from_revision(client):
    revision = _revision(client)
    response = client.get(f"{BASE}/revisions/{revision['id']}/holes.dxf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/vnd.dxf"
    assert _disposition_name(response) == f"Скважины {revision['context']['passport']['passport_no'].replace('/', '-')} rev1.dxf"
    assert b"AC1024" in response.content[:2000]
    assert b"BLX_HOLE" in response.content
    assert "x-blastex-warning" not in response.headers
    assert client.get(f"{BASE}/revisions/{revision['id']}/holes.dxf").content == response.content


def test_holes_dxf_info_carries_passport_date(client):
    revision = _revision(client)
    content = client.get(f"{BASE}/revisions/{revision['id']}/holes.dxf").content.decode("utf-8")
    assert "от 09.11.2026, ревизия 1" in content


def test_holes_dxf_uses_revision_snapshot_only(client, repository):
    revision = _revision(client)
    url = f"{BASE}/revisions/{revision['id']}/holes.dxf"
    before = client.get(url).content
    passport_id = revision["passport_id"]
    draft = client.get(f"{BASE}/{passport_id}").json()
    client.put(
        f"{BASE}/{passport_id}",
        json={"passport_no": "ДРУГОЙ", "passport_date": "2026-11-10",
              "payload": {**draft["payload"], "block": "99"}, "expected_version": draft["version"]},
    )
    assert client.get(url).content == before
    repository.revisions[revision["id"]]["context"]["holes"][0]["collar"]["x"] += 1.0
    assert client.get(url).content != before


def test_holes_dwg_is_disabled_by_default(client, monkeypatch):
    # LibreDWG 0.14 пишет R2000, который AutoCAD 2022 не открывает (решение
    # владельца 10.11.2026): без флага DWG не строится, отдаётся DXF.
    from urllib.parse import unquote

    from api.services import drilling_passport_service

    def forbidden(dxf):
        raise AssertionError("DWG не должен строиться без флага")

    monkeypatch.delenv("BLASTEX_DWG_EXPORT_ENABLED", raising=False)
    monkeypatch.setattr(drilling_passport_service, "holes_dwg", forbidden)
    revision = _revision(client)
    response = client.get(f"{BASE}/revisions/{revision['id']}/holes.dwg")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/vnd.dxf"
    assert _disposition_name(response).endswith("rev1.dxf")
    assert unquote(response.headers["x-blastex-warning"]).startswith("DWG пока не формируется")
    assert response.content == client.get(f"{BASE}/revisions/{revision['id']}/holes.dxf").content


def test_holes_dwg_without_writer_returns_dxf_with_warning(client, monkeypatch):
    monkeypatch.setenv("BLASTEX_DWG_EXPORT_ENABLED", "1")
    from urllib.parse import unquote

    monkeypatch.setenv("BLASTEX_DXF2DWG", "/nowhere/dxf2dwg")
    revision = _revision(client)
    response = client.get(f"{BASE}/revisions/{revision['id']}/holes.dwg")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/vnd.dxf"
    assert _disposition_name(response).endswith("rev1.dxf")
    assert unquote(response.headers["x-blastex-warning"]).startswith("DWG не сформирован")
    assert response.content == client.get(f"{BASE}/revisions/{revision['id']}/holes.dxf").content


def test_holes_dwg_returns_dwg(client, monkeypatch):
    monkeypatch.setenv("BLASTEX_DWG_EXPORT_ENABLED", "1")
    from api.services import drilling_passport_service
    from design.export_survey import DwgExport

    monkeypatch.setattr(drilling_passport_service, "holes_dwg", lambda dxf: DwgExport(b"AC1015 dwg", "dwg"))
    revision = _revision(client)
    response = client.get(f"{BASE}/revisions/{revision['id']}/holes.dwg")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/vnd.dwg"
    assert _disposition_name(response).endswith("rev1.dwg")
    assert response.content == b"AC1015 dwg"
    assert "x-blastex-warning" not in response.headers


@pytest.mark.parametrize(
    "name", ["holes.dxf", "holes.dwg", "stakeout", "coords.pdf", "coords.xlsx", "package.zip"]
)
def test_holes_of_foreign_or_unknown_revision_is_404(client, repository, name):
    revision = _revision(client)
    repository.passports[revision["passport_id"]]["organization_id"] = "org-b"
    assert client.get(f"{BASE}/revisions/{revision['id']}/{name}").status_code == 404
    assert client.get(f"{BASE}/revisions/nope/{name}").status_code == 404


def test_holes_dwg_is_built_once_per_revision(client, monkeypatch):
    monkeypatch.setenv("BLASTEX_DWG_EXPORT_ENABLED", "1")
    from api.services import drilling_passport_service
    from design.export_survey import DwgExport

    calls = []

    def fake(dxf):
        calls.append(dxf)
        return DwgExport(b"AC1015 dwg", "dwg")

    monkeypatch.setattr(drilling_passport_service, "holes_dwg", fake)
    revision = _revision(client)
    url = f"{BASE}/revisions/{revision['id']}/holes.dwg"
    assert client.get(url).content == client.get(url).content == b"AC1015 dwg"
    assert len(calls) == 1


def test_holes_dwg_fallback_is_not_cached(client, monkeypatch):
    monkeypatch.setenv("BLASTEX_DWG_EXPORT_ENABLED", "1")
    from api.services import drilling_passport_service
    from design.export_survey import DWG_FALLBACK_WARNING, DwgExport

    calls = []

    def fake(dxf):
        calls.append(dxf)
        return DwgExport(dxf, "dxf", DWG_FALLBACK_WARNING)

    monkeypatch.setattr(drilling_passport_service, "holes_dwg", fake)
    revision = _revision(client)
    url = f"{BASE}/revisions/{revision['id']}/holes.dwg"
    client.get(url)
    client.get(url)
    assert len(calls) == 2


# --- файл выноса и ведомость (PR 5) ----------------------------------------

def test_revision_snapshot_carries_builtin_stakeout_profiles(client):
    revision = _revision(client)
    stakeout = revision["context"]["stakeout"]
    assert stakeout["default"] == "PNEZD_CSV"
    assert list(stakeout["profiles"]) == ["PNEZD_CSV", "PENZD_CSV", "PNEZ_TXT", "DXF_POINTS"]


def test_site_stakeout_profile_goes_to_snapshot(client, references):
    references["snapshot"] = _snapshot(
        site={**SITE, "stakeout_profile_code": "TRIMBLE"},
        stakeout_profiles={"TRIMBLE": ("Trimble Access", {"format": "PENZD_CSV", "header": True})},
    )
    revision = _revision(client)
    stakeout = revision["context"]["stakeout"]
    assert stakeout["default"] == "TRIMBLE"
    assert stakeout["profiles"]["TRIMBLE"] == {
        "name": "Trimble Access", "format": "PENZD_CSV", "header": True, "elevation": True, "include_toe": False,
    }


def test_unknown_site_stakeout_profile_is_warned(client, references):
    references["snapshot"] = _snapshot(site={**SITE, "stakeout_profile_code": "NOPE"})
    passport = _create(client)
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    assert [issue["code"] for issue in body["issues"]] == ["stakeout_profile_not_found"]


def test_stakeout_from_revision(client):
    revision = _revision(client)
    url = f"{BASE}/revisions/{revision['id']}/stakeout"
    response = client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert _disposition_name(response) == "ZHK_66_66-26-B_r1_PNEZD_CSV.csv"
    assert response.content.split(b"\r\n")[0] == b"66-001,593722.990,1472880.040,419.210,R1 L10.7"
    assert client.get(url).content == response.content
    text = client.get(url, params={"profile": "PNEZ_TXT"})
    assert text.status_code == 200
    assert text.headers["content-type"].startswith("text/plain")
    assert _disposition_name(text) == "ZHK_66_66-26-B_r1_PNEZ_TXT.txt"
    dxf = client.get(url, params={"profile": "DXF_POINTS"})
    assert dxf.headers["content-type"] == "image/vnd.dxf"
    assert _disposition_name(dxf).endswith("_DXF_POINTS.dxf")


def test_stakeout_uses_site_profile(client, references):
    references["snapshot"] = _snapshot(
        site={**SITE, "stakeout_profile_code": "TRIMBLE"},
        stakeout_profiles={"TRIMBLE": ("Trimble Access", {"format": "PENZD_CSV", "header": True})},
    )
    revision = _revision(client)
    response = client.get(f"{BASE}/revisions/{revision['id']}/stakeout")
    assert _disposition_name(response) == "ZHK_66_66-26-B_r1_TRIMBLE.csv"
    assert response.content.split(b"\r\n")[0] == b"Point,Easting,Northing,Elevation,Description"


def test_stakeout_unknown_profile_is_422(client):
    revision = _revision(client)
    response = client.get(f"{BASE}/revisions/{revision['id']}/stakeout", params={"profile": "GSI"})
    assert response.status_code == 422
    assert "PNEZD_CSV" in response.json()["detail"]


def test_stakeout_name_conflict_is_422(client, repository):
    revision = _revision(client)
    holes = repository.revisions[revision["id"]]["context"]["holes"]
    holes[0]["number"], holes[1]["number"] = "Р1", "R1"
    response = client.get(f"{BASE}/revisions/{revision['id']}/stakeout")
    assert response.status_code == 422
    assert "Р1" in response.json()["detail"]


def test_coords_pdf_and_xlsx_from_revision(client):
    revision = _revision(client)
    pdf = client.get(f"{BASE}/revisions/{revision['id']}/coords.pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert _disposition_name(pdf) == "Ведомость координат 66-26-Б rev1.pdf"
    assert client.get(f"{BASE}/revisions/{revision['id']}/coords.pdf").content == pdf.content
    xlsx = client.get(f"{BASE}/revisions/{revision['id']}/coords.xlsx")
    assert xlsx.status_code == 200, xlsx.text
    assert xlsx.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert _disposition_name(xlsx) == "Ведомость координат 66-26-Б rev1.xlsx"
    assert client.get(f"{BASE}/revisions/{revision['id']}/coords.xlsx").content == xlsx.content


def test_package_zip(client):
    import io
    import zipfile

    revision = _revision(client)
    base = f"{BASE}/revisions/{revision['id']}"
    response = client.get(f"{base}/package.zip")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert _disposition_name(response) == "Паспорт на бурение 66-26-Б rev1.zip"
    assert client.get(f"{base}/package.zip").content == response.content
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert names == [
            "Паспорт на бурение 66-26-Б rev1.pdf",
            "Скважины 66-26-Б rev1.dxf",
            "ZHK_66_66-26-B_r1_PNEZD_CSV.csv",
            "Ведомость координат 66-26-Б rev1.pdf",
            "Ведомость координат 66-26-Б rev1.xlsx",
        ]
        assert archive.read(names[0]) == client.get(f"{base}/passport.pdf").content
        assert archive.read(names[1]) == client.get(f"{base}/holes.dxf").content
        assert archive.read(names[2]) == client.get(f"{base}/stakeout").content
        assert archive.read(names[3]) == client.get(f"{base}/coords.pdf").content
        assert archive.read(names[4]) == client.get(f"{base}/coords.xlsx").content


def test_stakeout_and_coords_use_revision_snapshot_only(client, references):
    revision = _revision(client)
    base = f"{BASE}/revisions/{revision['id']}"
    before = {name: client.get(f"{base}/{name}").content for name in ("stakeout", "coords.pdf", "coords.xlsx")}
    passport_id = revision["passport_id"]
    draft = client.get(f"{BASE}/{passport_id}").json()
    client.put(
        f"{BASE}/{passport_id}",
        json={"passport_no": "ДРУГОЙ", "passport_date": "2026-11-10",
              "payload": {**draft["payload"], "block": "99"}, "expected_version": draft["version"]},
    )
    references["snapshot"] = _snapshot(site={**SITE, "stakeout_profile_code": "PNEZ_TXT"})
    assert {name: client.get(f"{base}/{name}").content for name in before} == before


def test_long_block_name_is_warned_before_revision(client):
    passport = _create(client, {**PAYLOAD, "block": "Уступ 120/108"})
    body = client.post(f"{BASE}/{passport['id']}/validate").json()
    issues = {issue["code"]: issue for issue in body["issues"]}
    assert "stakeout_names_invalid" in issues
    assert "«Блок»" in issues["stakeout_names_invalid"]["message"]


def test_package_without_stakeout_explains_why(client, repository):
    import io
    import zipfile

    revision = _revision(client)
    holes = repository.revisions[revision["id"]]["context"]["holes"]
    holes[0]["number"], holes[1]["number"] = "Р1", "R1"
    response = client.get(f"{BASE}/revisions/{revision['id']}/package.zip")
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert not any(name.endswith(".csv") for name in names)
        note = archive.read("Файл выноса не сформирован.txt").decode("utf-8")
    assert "Р1" in note
    assert len(names) == 5


# --- список паспортов проекта и PDF черновика (PR 6) ----------------------

def _pdf_text(pdf: bytes, tmp_path) -> str:
    import subprocess

    source = tmp_path / "preview.pdf"
    source.write_bytes(pdf)
    # -raw: повёрнутая пометка черновика в обычном режиме рвётся на буквы.
    return subprocess.run(["pdftotext", "-raw", str(source), "-"], check=True, capture_output=True).stdout.decode()


def test_list_passports_of_design(client):
    first = _create(client)
    second = _create(client)
    items = client.get(BASE, params={"design_id": "block-66"}).json()
    assert [item["id"] for item in items] == [second["id"], first["id"]]
    assert items[0]["payload"]["site_code"] == "ZHK"
    assert client.get(BASE, params={"design_id": "other"}).json() == []


def test_list_passports_of_foreign_organization_is_empty(client, repository):
    passport = _create(client)
    repository.passports[passport["id"]]["organization_id"] = "org-b"
    assert client.get(BASE, params={"design_id": "block-66"}).json() == []


@pytest.mark.skipif(__import__("shutil").which("pdftotext") is None, reason="нет pdftotext (poppler)")
def test_draft_preview_pdf_is_marked(client, tmp_path):
    passport = _create(client)
    response = client.get(f"{BASE}/{passport['id']}/preview.pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("inline;")
    assert "%D1%87%D0%B5%D1%80%D0%BD%D0%BE%D0%B2%D0%B8%D0%BA.pdf" in disposition  # «черновик.pdf»
    assert "ЧЕРНОВИК" in _pdf_text(response.content, tmp_path)
    assert client.get(f"{BASE}/{passport['id']}").json()["current_revision_id"] is None


def test_draft_preview_with_errors_is_422(client, references):
    references["snapshot"] = _snapshot(site={})
    passport = _create(client)
    response = client.get(f"{BASE}/{passport['id']}/preview.pdf")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith("Предпросмотр недоступен:")
    assert "угол откоса" in detail


def test_draft_preview_of_foreign_passport_is_404(client, repository):
    passport = _create(client)
    repository.passports[passport["id"]]["organization_id"] = "org-b"
    assert client.get(f"{BASE}/{passport['id']}/preview.pdf").status_code == 404


def test_list_passports_needs_design(client):
    # Весь список организации с payload фронту не нужен: только паспорт проекта.
    _create(client)
    assert client.get(BASE).status_code == 422
    assert client.get(BASE, params={"design_id": ""}).status_code == 422


# --- «Порядок работ» нового паспорта: профиль объекта или умолчания (PR 6) --

WORK_ORDER_V07 = {
    "site_preparation": "бульдозером под руководством горного мастера заказчика; приём площадки по акту",
    "stakeout": "маркшейдерская служба заказчика по листу «Координаты скважин»",
    "drilling_order": (
        "с левого фланга вглубь массива, рядами; скважины, ближайшие к бровке, обуривать с соблюдением "
        "мер предосторожности, преимущественно в светлое время суток"
    ),
    "access_route": "по съезду, мачта в транспортном положении",
    "power_lines": "нет",
    "adjacent_works": "нет",
    "acceptance": "исполнительная съёмка маркшейдерской службой заказчика",
}


def test_new_draft_work_order_is_filled_by_default(client):
    payload = _create(client)["payload"]
    assert {key: payload[key] for key in WORK_ORDER_V07} == WORK_ORDER_V07
    assert payload["profile_code"] == ""


def test_new_draft_takes_work_order_from_site_profile(client, references):
    profile = {**PROFILE, "drilling_order": "с левого фланга, рядами", "power_lines": "ЛЭП 6 кВ в 40 м — по наряду-допуску"}
    snapshot = _snapshot(site={**SITE, "drill_passport_profile_code": "KGOK"})
    item = snapshot.item
    snapshot.item = lambda section, code: (
        SimpleNamespace(code=code, name="КГОК", payload=profile) if (section, code) == ("drill_passport_profiles", "KGOK") else item(section, code)
    )
    references["snapshot"] = snapshot
    payload = _create(client)["payload"]
    assert payload["profile_code"] == "KGOK"
    assert payload["drilling_order"] == "с левого фланга, рядами"
    assert payload["power_lines"] == "ЛЭП 6 кВ в 40 м — по наряду-допуску"
    # Пустое поле профиля — текст по умолчанию.
    assert payload["stakeout"] == WORK_ORDER_V07["stakeout"]


def test_new_draft_keeps_explicit_work_order_and_profile(client, references):
    references["snapshot"] = _snapshot(site={**SITE, "drill_passport_profile_code": "KGOK"})
    payload = _create(client, {**PAYLOAD, "power_lines": "ЛЭП 10 кВ", "profile_code": ""})["payload"]
    assert payload["power_lines"] == "ЛЭП 10 кВ"
    # Явно пустой профиль в запросе — профиль объекта не подставляется.
    assert payload["profile_code"] == ""


def test_unknown_site_profile_falls_back_to_defaults(client, references):
    references["snapshot"] = _snapshot(site={**SITE, "drill_passport_profile_code": "NOPE"})
    payload = _create(client)["payload"]
    assert payload["profile_code"] == ""
    assert payload["drilling_order"] == WORK_ORDER_V07["drilling_order"]



# --- остальные поля нового паспорта: справочники и прошлый паспорт (PR 6) --

DRILL_REFERENCES = {
    ("sites", "ZHK"): ("Жуков Камень", {**SITE, "customer_legal_name": "АО «КГОК»", "shift_hours": "11"}),
    ("equipment_types", "JK830"): ("JK 830-2", {**RIG, "kind": "DRILL_RIG"}),
    ("equipment_assets", "JK830-07"): ("JK 830-2 № 7", {"equipment_type_code": "JK830", "inventory_number": "07"}),
    ("drilling_conditions", "JK830-ZHK"): (
        "JK830 на Жуковом Камне",
        {"equipment_type_code": "JK830", "site_code": "ZHK", "tech_speed_m_per_h": "25", "unproductive_h_per_shift": "1.5",
         "bit_material_code": "BIT140"},
    ),
    ("materials", "BIT140"): ("Коронка 140 мм", {"diameter_mm": "140"}),
}


def _bare(client, site_code="ZHK", **extra):
    response = client.post(
        BASE, json={"design_id": "block-66", "passport_date": "2026-11-10", "payload": {"site_code": site_code, **extra}}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_new_draft_prefilled_from_references(client, references):
    references["snapshot"] = _snapshot(site=None, rig=None, extra=DRILL_REFERENCES)
    payload = _bare(client)["payload"]
    assert payload["object_name"] == "Жуков Камень"
    assert payload["customer"] == "АО «КГОК»"
    assert payload["horizon"] == "+410"
    assert (payload["rig_type_code"], payload["rig_name"], payload["rig_number"]) == ("JK830", "JK 830-2", "07")
    assert payload["bit_diameter_mm"] == 140
    # 2 280,5 п. м / (25 м/ч × (11 − 1,5) ч × 2 смены) = 4,8 → 5 суток: 10.11 … 14.11.
    assert (payload["drilling_start"], payload["drilling_end"]) == ("2026-11-10", "2026-11-14")


def test_customer_from_counterparty(client, references):
    extra = {**DRILL_REFERENCES, ("sites", "ZHK"): ("Жуков Камень", {**SITE, "customer_code": "KGOK"}),
             ("counterparties", "KGOK"): ("АО «Качканарский ГОК»", {})}
    references["snapshot"] = _snapshot(site=None, rig=None, extra=extra)
    assert _bare(client)["payload"]["customer"] == "АО «Качканарский ГОК»"


def test_without_drilling_norm_end_is_start_and_warned(client, references):
    extra = {key: value for key, value in DRILL_REFERENCES.items() if key[0] != "drilling_conditions"}
    references["snapshot"] = _snapshot(site=None, rig=None, extra=extra)
    snapshot = references["snapshot"]
    item, active = snapshot.item, snapshot.active_items
    snapshot.item = lambda section, code: None if section == "drilling_conditions" else item(section, code)
    snapshot.active_items = lambda section: () if section == "drilling_conditions" else active(section)
    passport = _bare(client, rig_type_code="JK830")
    assert passport["payload"]["drilling_end"] == passport["payload"]["drilling_start"] == "2026-11-10"
    issues = client.post(f"{BASE}/{passport['id']}/validate").json()["issues"]
    norm = [issue for issue in issues if issue["code"] == "drilling_norm_missing"]
    assert norm and norm[0]["path"] == "drilling_end"


def test_new_draft_copies_previous_passport_of_site(client, references):
    references["snapshot"] = _snapshot(site=None, rig=None, extra=DRILL_REFERENCES)
    people = {
        "agreed_by": {"position": "Главный инженер", "organization": "АО «КГОК»", "name": "Иванов И. И."},
        "approved_by": {"position": "Директор", "organization": "ООО «Комплексные решения»", "name": "Петров П. П."},
        "compiled_by": {"position": "Инженер БВР", "organization": "", "name": "Сидоров С. С."},
        "personnel": [{"name": "Кузнецов", "position": "машинист"}],
        "basis": "проект БВР № 12", "rig_number": "12", "bit_diameter_mm": 152,
        "extra_approvals": ["маркшейдер Орлова"], "tol_depth_m": 0.2, "tol_angle_deg": 1.5,
    }
    _bare(client, **people)
    payload = _bare(client)["payload"]
    for key, value in people.items():
        assert payload[key] == value, key
    # Тип станка и паспорта на других объектах не мешают.
    assert payload["rig_type_code"] == "JK830"


def test_previous_passport_of_other_site_is_not_copied(client, references):
    extra = {**DRILL_REFERENCES, ("sites", "OTHER"): ("Другой карьер", {})}
    references["snapshot"] = _snapshot(site=None, rig=None, extra=extra)
    _bare(client, site_code="OTHER", basis="проект другого карьера", rig_number="99")
    payload = _bare(client)["payload"]
    assert payload["basis"] == ""
    assert payload["rig_number"] == "07"


def test_explicit_fields_are_kept(client, references):
    references["snapshot"] = _snapshot(site=None, rig=None, extra=DRILL_REFERENCES)
    payload = _bare(client, horizon="+398", object_name="Блок у дороги", drilling_end="2026-11-30")["payload"]
    assert (payload["horizon"], payload["object_name"], payload["drilling_end"]) == ("+398", "Блок у дороги", "2026-11-30")


def test_without_active_site_takes_site_of_last_passport(client, references, monkeypatch):
    # Активный объект не определился (кнопка «Создать паспорт» шлёт только проект):
    # объект — у последнего паспорта организации, дальше — его справочники и люди.
    monkeypatch.setattr(drilling_passport_service, "_default_site_code", lambda *args: "")
    references["snapshot"] = _snapshot(site=None, rig=None, extra=DRILL_REFERENCES)
    _bare(client, basis="проект БВР № 12")
    response = client.post(BASE, json={"design_id": "block-66", "passport_date": "2026-11-11"})
    payload = response.json()["payload"]
    assert payload["site_code"] == "ZHK"
    assert payload["object_name"] == "Жуков Камень"
    assert payload["basis"] == "проект БВР № 12"


def test_prefilled_texts_fit_passport_limits(client, references):
    # Названия в справочнике — до 300 знаков, поля паспорта короче: черновик
    # с подставленными значениями должен сохраняться (иначе 422 на любую правку).
    extra = {
        **DRILL_REFERENCES,
        ("sites", "ZHK"): ("К" * 250, {**SITE, "customer_legal_name": "З" * 250}),
        ("equipment_types", "JK830"): ("С" * 120, {**RIG, "kind": "DRILL_RIG"}),
        ("equipment_assets", "JK830-07"): ("JK", {"equipment_type_code": "JK830", "inventory_number": "Н" * 60}),
    }
    references["snapshot"] = _snapshot(site=None, rig=None, extra=extra)
    passport = _bare(client)
    payload = passport["payload"]
    assert (len(payload["object_name"]), len(payload["customer"])) == (200, 200)
    assert (len(payload["rig_name"]), len(payload["rig_number"])) == (80, 40)
    saved = client.put(
        f"{BASE}/{passport['id']}",
        json={"passport_no": passport["passport_no"], "passport_date": passport["passport_date"],
              "payload": payload, "expected_version": passport["version"]},
    )
    assert saved.status_code == 200, saved.text


def test_rig_details_inherited_only_for_same_rig_type(client, references):
    extra = {
        **DRILL_REFERENCES,
        ("equipment_types", "ZEGA"): ("ZEGA D480A", {"kind": "DRILL_RIG"}),
        ("equipment_assets", "ZEGA-03"): ("ZEGA № 3", {"equipment_type_code": "ZEGA", "inventory_number": "03"}),
    }
    references["snapshot"] = _snapshot(site=None, rig=None, extra=extra)
    _bare(client, rig_number="12", bit_diameter_mm=152)
    payload = _bare(client, rig_type_code="ZEGA")["payload"]
    # Другой станок — его название и № из справочников, не от JK830.
    assert (payload["rig_name"], payload["rig_number"]) == ("ZEGA D480A", "03")
    assert payload["bit_diameter_mm"] is None
    same = _bare(client)["payload"]
    assert (same["rig_type_code"], same["rig_number"]) == ("ZEGA", "03")



def test_old_draft_with_manual_c_and_w_max_opens_and_saves(client, repository):
    # До доработок 10.11.2026 c и Wпред вводились вручную: ключи старого
    # черновика игнорируются, расчёт — по проекту блока.
    passport = _create(client)
    repository.passports[passport["id"]]["payload"].update(first_row_offset_m=2.0, w_max_m=4.9)
    stored = client.get(f"{BASE}/{passport['id']}").json()
    assert "w_max_m" not in stored["payload"]
    saved = client.put(
        f"{BASE}/{passport['id']}",
        json={"passport_no": stored["passport_no"], "passport_date": stored["passport_date"],
              "payload": {**stored["payload"], "w_max_m": 4.9}, "expected_version": stored["version"]},
    )
    assert saved.status_code == 200, saved.text
    check = client.post(f"{BASE}/{passport['id']}/validate").json()["first_row_check"]
    assert check["w_max_m"] == pytest.approx(6.0 * 1.03)


@pytest.mark.parametrize(
    ("contour_name", "design_name", "expected"),
    [
        ("Блок", "Блок 67", "67"),  # имя контура по умолчанию — номер из названия проекта
        ("Блок", "блок №67-2", "67-2"),
        ("Блок", "Уступ 120", "Уступ 120"),
        ("Блок", "Новый паспорт", ""),  # в названии нет номера — поле пустое, а не «блок № Новый паспорт»
        ("Блок", "Блок", ""),
        ("66", "Блок 66", "66"),  # имя контура задано — оно
        ("Блок", "", ""),
    ],
)
def test_block_of_new_passport_skips_default_contour_name(client, block66, monkeypatch, contour_name, design_name, expected):
    monkeypatch.setattr(block66.contour, "name", contour_name)
    monkeypatch.setattr(block66, "name", design_name)
    response = client.post(BASE, json={"design_id": "block-66", "passport_date": "2026-11-09", "payload": {"site_code": "ZHK"}})
    assert response.status_code == 201, response.text
    assert response.json()["payload"]["block"] == expected
