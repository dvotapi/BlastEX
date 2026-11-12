"""Окно проекта МВ (TASK-018, PR 6): новый проект с предзаполнением, подсказки,
доступные слои, адресаты уведомлений; флаг по умолчанию включён."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import config
from api.routers import mass_blast
from api.security import require_human, require_internal_access
from api.services import mass_blast_service
from api.services.economics_service import get_economics_repository
from api.services.mass_blast_service import get_mass_blast_repository
from design.lifecycle import designed_sha256
from design.mass_blast import block_from_design
from tests.mass_blast_block66 import design66
from tests.test_api_mass_blast import USERS

BASE = "/api/v1/design/mass-blast-projects"
SESSION = {"sub": "supervisor@example.ru", "role": "admin", "org": "org-a"}


@pytest.fixture(scope="module")
def design():
    design = design66()
    design.name = "Блок 66"
    design.designed_sha256 = designed_sha256(design)
    return design


def _item(code, name, payload):
    return SimpleNamespace(code=code, name=name, payload=payload, is_active=True)


def _snapshot(*, notifications=()):
    sections = {
        "sites": (_item("ZK", "Жуков Камень", {"customer_code": "CUST"}),),
        "counterparties": (_item("CUST", "АО «Заказчик»", {}),),
        "blast_notifications": tuple(notifications),
    }

    def item(section, code):
        return next((entry for entry in sections.get(section, ()) if entry.code == code), None)

    return SimpleNamespace(revision_id="ref-1", active_items=lambda section: sections.get(section, ()), item=item)


class _Repository:
    def __init__(self, projects=(), layers=(), revisions=None) -> None:
        self.projects = {item["id"]: copy.deepcopy(item) for item in projects}
        self.layers = list(layers)
        self.revisions = dict(revisions or {})
        self.created: list[dict] = []

    def list_projects(self, organization_id):
        return [
            {"id": item["id"], "site_code": item["site_code"], "name": item["name"]}
            for item in self.projects.values()
        ]

    def get_project(self, organization_id, project_id):
        return copy.deepcopy(self.projects[project_id])

    def create_project(self, organization_id, actor, payload):
        self.created.append(payload)
        return {
            **payload, "id": "new-1", "lifecycle_status": "draft", "version": 1, "current_revision_id": None,
            "block_design_ids": [], "updated_at": "", "created_at": "", "created_by": actor, "updated_by": actor,
        }

    def list_layers(self, organization_id, project_id):
        return [layer for layer in self.layers if layer["project_id"] == project_id]

    def get_revision(self, organization_id, revision_id):
        return copy.deepcopy(self.revisions[revision_id])


def _client(monkeypatch, repository, design, *, snapshot=None, flag: str | None = None) -> TestClient:
    monkeypatch.setenv("BLASTEX_USERS_JSON", json.dumps(USERS))
    if flag is None:
        monkeypatch.delenv(config.MASS_BLAST_V2_ENABLED_ENV, raising=False)
    else:
        monkeypatch.setenv(config.MASS_BLAST_V2_ENABLED_ENV, flag)
    monkeypatch.setattr(mass_blast_service.design_persistence, "load_design", lambda organization_id, design_id: design)
    monkeypatch.setattr(
        mass_blast_service, "_blocks_from_payload",
        lambda organization_id, payload: [block_from_design(design, code="66", horizon="+410") for _ in payload["blocks"]],
    )
    app = FastAPI()
    app.include_router(mass_blast.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: SESSION
    app.dependency_overrides[require_human] = lambda: SESSION
    app.dependency_overrides[get_mass_blast_repository] = lambda: repository
    snapshot = snapshot or _snapshot()
    app.dependency_overrides[get_economics_repository] = lambda: SimpleNamespace(
        get_reference_snapshot=lambda organization_id, requested=None: snapshot,
        get_legacy_workspace=lambda organization_id: SimpleNamespace(active_work_object_name="Жуков Камень"),
    )
    return TestClient(app)


def _previous() -> dict:
    return {
        "id": "old-1", "site_code": "ZK", "name": "Массовый взрыв — блок 65", "object_name": "Жуков Камень",
        "context_version": 2, "document_profile_code": "STANDARD", "signal_plan": {},
        "requisites": {
            "project_no": "65-МВ", "project_date": "2026-11-01", "tp_basis": "ТП БВР 2026",
            "made_by": {"position": "Инженер БВР", "name": "Иванов И. И."},
            "contractor_approver": {"position": "Технический директор", "name": "Петров П. П.", "authority": "", "is_head": True},
            "surveyor_name": "Сидоров С. С.", "drilled_by": "CUSTOMER",
        },
        "schedule": {"station": "Будка у въезда", "siren": "СС-1", "charging_from": "2026-11-01", "other_conditions": "ЛЭП рядом"},
        "personnel": [{"role_code": "senior_blaster", "position": "Старший взрывник", "name": "Трегубов Т. Т."}],
        "responsibilities": [
            {"role_code": "blast_manager", "employee_code": "M", "employee_name": "М", "position_name": "Руководитель",
             "account_email": "manager@example.ru"},
            {"role_code": "explosives_supervisor", "employee_code": "S", "employee_name": "С", "position_name": "Отв. за ВМ",
             "account_email": "gone@example.ru"},
        ],
        "guard_posts": [{"code": "1", "location": "дорога"}],
        "layout_points": [{"kind": "blast_station", "x": 1, "y": 2}],
        "protected_objects": [{"name": "ЛЭП"}],
    }


def test_new_project_is_prefilled_from_reference_and_previous_project(monkeypatch, design):
    repository = _Repository([_previous()])
    response = _client(monkeypatch, repository, design).post(
        f"{BASE}/new", json={"design_ids": ["block-66"], "blast_date": "2026-11-20", "blast_time": "13:00"}
    )
    assert response.status_code == 201, response.text
    stored = repository.created[-1]
    assert stored["context_version"] == 2
    assert stored["site_code"] == "ZK" and stored["object_name"] == "Жуков Камень"
    assert stored["blast_date"] == "2026-11-20" and stored["blast_time"] == "13:00"
    assert stored["name"] == "Массовый взрыв — блок 66"
    assert stored["requisites"]["customer_name"] == "АО «Заказчик»"
    # Люди и постоянные тексты — из прошлого проекта объекта.
    assert stored["requisites"]["made_by"]["name"] == "Иванов И. И."
    assert stored["requisites"]["surveyor_name"] == "Сидоров С. С."
    assert {key: value for key, value in stored["schedule"].items() if value} == {"station": "Будка у въезда", "siren": "СС-1"}
    assert stored["personnel"][0]["name"] == "Трегубов Т. Т."
    accounts = {item["role_code"]: item["account_email"] for item in stored["responsibilities"]}
    assert accounts == {"blast_manager": "manager@example.ru", "explosives_supervisor": ""}
    # № и дата проекта, посты, точки, объекты — не переносятся (В3, В4).
    assert stored["requisites"]["project_no"] == "" and stored["requisites"]["project_date"] == ""
    assert stored["guard_posts"] == [] and stored.get("layout_points") == [] and stored.get("protected_objects") == []


def test_new_project_without_previous_and_site_fails_clearly(monkeypatch, design):
    snapshot = _snapshot()
    snapshot.active_items = lambda section: ()
    snapshot.item = lambda section, code: None
    response = _client(monkeypatch, _Repository(), design, snapshot=snapshot).post(
        f"{BASE}/new", json={"design_ids": ["block-66"], "blast_date": "2026-11-20"}
    )
    assert response.status_code == 422 and "Не определён объект" in response.json()["detail"]


def test_new_project_needs_a_blast_date_and_the_flag(monkeypatch, design):
    client = _client(monkeypatch, _Repository([_previous()]), design)
    assert client.post(f"{BASE}/new", json={"design_ids": ["block-66"], "blast_date": ""}).status_code == 422
    off = _client(monkeypatch, _Repository([_previous()]), design, flag="нет")
    assert off.post(f"{BASE}/new", json={"design_ids": ["block-66"], "blast_date": "2026-11-20"}).status_code == 404


def test_hints_give_the_previous_number(monkeypatch, design):
    current = {**_previous(), "id": "cur", "requisites": {}}
    response = _client(monkeypatch, _Repository([_previous(), current]), design).get(f"{BASE}/cur/hints")
    assert response.status_code == 200
    assert response.json()["previous_project_no"] == "65-МВ"
    roles = {item["code"]: item["label"] for item in response.json()["personnel_roles"]}
    assert len(roles) == 10 and roles["blaster"] == "Взрывник по наряд-путёвке"


def _approved(status="approved") -> dict:
    return {**_previous(), "id": "p1", "lifecycle_status": status, "current_revision_id": "rev-1"}


def _revision(drilled_by="CUSTOMER") -> dict:
    return {"rev-1": {"id": "rev-1", "context": {
        "document_context_version": 2,
        "project": {"site_code": "ZK", "reference_revision_id": "ref-1"},
        "requisites": {"drilled_by": drilled_by},
    }}}


def test_available_layers_follow_the_open_rule(monkeypatch, design):
    layers = [{"id": "l1", "project_id": "p1", "kind": "EXECUTION", "payload": {}}]
    repository = _Repository([_approved()], layers, _revision())
    rows = {row["kind"]: row for row in _client(monkeypatch, repository, design).get(f"{BASE}/p1/layers/available").json()}
    assert rows["NARYAD"]["can_open"] and rows["NARYAD"]["multiple"]
    assert not rows["TALON"]["can_open"] and "отметки взрыва" in rows["TALON"]["reason"]
    assert not rows["EXECUTION"]["can_open"] and rows["EXECUTION"]["count"] == 1
    executed = _Repository([_approved("executed")], [], _revision(drilled_by="CONTRACTOR"))
    rows = {row["kind"]: row for row in _client(monkeypatch, executed, design).get(f"{BASE}/p1/layers/available").json()}
    assert rows["TALON"]["can_open"] and rows["ACCEPTANCE_ACT"]["can_open"]
    assert not rows["READINESS_ACT"]["can_open"] and "п. 413" in rows["READINESS_ACT"]["reason"]


def test_available_layers_of_a_draft_without_revision(monkeypatch, design):
    draft = {**_previous(), "id": "p1", "lifecycle_status": "draft", "current_revision_id": None}
    rows = _client(monkeypatch, _Repository([draft]), design).get(f"{BASE}/p1/layers/available").json()
    assert rows and not any(row["can_open"] for row in rows)


def test_notification_addressees_are_labelled_by_the_server(monkeypatch, design):
    notifications = (
        _item("N1", "Гостехнадзор", {"site_code": "ZK", "recipient_position": "Начальнику отдела", "recipient_name": "Кузнецову К. К.",
                                     "channel": "EMAIL", "lead_days": 2}),
        _item("N2", "Посёлок", {"site_code": "ZK", "recipient_position": "Главе посёлка", "channel": "LETTER", "lead_days": 1}),
        _item("N3", "Чужой", {"site_code": "OTHER", "recipient_position": "Кому-то"}),
    )
    layers = [{"id": "l1", "project_id": "p1", "kind": "NOTIFICATION", "payload": {"notification_code": "N2"}}]
    repository = _Repository([_approved()], layers, _revision())
    data = _client(monkeypatch, repository, design, snapshot=_snapshot(notifications=notifications)).get(
        f"{BASE}/p1/notification-addressees"
    ).json()
    assert data["registry"] is True
    assert data["items"] == [
        {"code": "N1", "label": "Начальнику отдела Кузнецову К. К. (эл. почта, за 2 сут.)", "taken": False},
        {"code": "N2", "label": "Главе посёлка (письмо, за 1 сут.)", "taken": True},
    ]
    empty = _client(monkeypatch, _Repository([_approved()], [], _revision()), design).get(f"{BASE}/p1/notification-addressees")
    assert empty.json() == {"registry": False, "items": []}


def test_layer_changes_are_described_in_words():
    from design.mass_blast_layer_diff import describe_change

    row = describe_change({"path": "blocks_fact[0].12.depth_fact_m", "before": 10.7, "after": 10.95})
    assert (row["label"], row["before_text"], row["after_text"]) == ("Блок 1, скв. 12 — глубина Ф, м", "10,7", "10,95")
    row = describe_change({"path": "zones.people", "before": 750.0, "after": 900.0})
    assert row["label"] == "Опасная зона для людей, м" and row["after_text"] == "900"
    row = describe_change({"path": "people.blaster.name", "before": "", "after": "Трегубов Т. Т."})
    assert row["label"] == "Взрывник по наряд-путёвке — Ф. И. О." and row["before_text"] == "—"
    row = describe_change({"path": "materials", "before": [], "after": [{"name": "ПД", "project_qty": 198.0, "unit": "шт"}]})
    assert row["label"] == "ВМ по проекту" and row["after_text"] == "ПД — 198 шт"
    row = describe_change({"path": "drilled_by", "before": "CUSTOMER", "after": "CONTRACTOR"})
    assert (row["before_text"], row["after_text"]) == ("заказчик", "Общество")
    assert describe_change({"path": "something.odd", "before": 1, "after": 2})["label"] == "Прочие данные проекта"


def test_fact_summary_change_has_no_service_ids():
    from design.mass_blast_layer_diff import describe_change

    fact = {"execution_revision_id": "dc570e01-3a00-4c23-8d6b-a019a36ce344", "blast_date": "2026-11-20", "blast_time": "13:05",
            "blocks": [{"code": "66", "holes": 196, "charged": 190, "charged_kg": 31500.0}], "consumption": []}
    row = describe_change({"path": "fact", "before": None, "after": fact})
    assert row["label"] == "Сводка выпущенного слоя «Факт»" and row["before_text"] == "—"
    assert row["after_text"] == "взрыв 20.11.2026 13:05; блок 66: заряжено 190 из 196 скв., 31 500 кг"
    row = describe_change({"path": "fact.execution_revision_id", "before": "a" * 8 + "-0000-0000-0000-" + "b" * 12, "after": fact["execution_revision_id"]})
    assert (row["label"], row["before_text"], row["after_text"]) == ("Сводка выпущенного слоя «Факт» — ревизия", "прежняя", "новая")
    assert "dc570e01" not in describe_change({"path": "something", "before": None, "after": fact["execution_revision_id"]})["after_text"]


def test_v2_validation_drops_v1_signal_and_notification_checks(monkeypatch):
    """Профиль сигналов и получатель уведомления — проверки v1: в форме ВМ.09.03 сигналы
    из профиля документов, уведомления — слои дня взрыва (PR 6)."""

    from tests import test_api_mass_blast_v2 as v2

    design = design66()
    design.designed_sha256 = designed_sha256(design)
    block = block_from_design(design, code="66", horizon="410")
    stored = v2._stored_v2(block)
    stored["signal_plan"] = {}
    stored["notifications"] = []
    response = v2._client(monkeypatch, v2._Repository(stored), design).post(f"{v2.BASE}/p1/validate")
    codes = {issue["code"] for issue in response.json()["issues"]}
    assert not codes & {"signal_profile", "notification"}
    assert response.json()["valid"] is True
