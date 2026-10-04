"""HTTP-маршруты массового взрыва: учётки ответственных и отказ чужой подписи."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import mass_blast
from api.security import require_internal_access
from api.services import mass_blast_service
from api.services.economics_service import get_economics_repository
from api.services.mass_blast_service import get_mass_blast_repository
from design.mass_blast_repository import MassBlastForbiddenError

BASE = "/api/v1/design/mass-blast-projects"
SESSION = {"sub": "designer@example.ru", "role": "user", "org": "org-a"}
USERS = [
    {"email": "Manager@Example.ru", "password_hash": "x", "role": "user", "display_name": "Иванов И. И.",
     "organization_id": "org-a"},
    {"email": "supervisor@example.ru", "password_hash": "x", "role": "admin", "organization_id": "org-a"},
    {"email": "retired@example.ru", "password_hash": "x", "role": "user", "display_name": "Уволен",
     "organization_id": "org-a", "active": False},
    {"email": "outsider@example.ru", "password_hash": "x", "role": "user", "display_name": "Чужой",
     "organization_id": "org-b"},
]


class _Repository:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def approve_revision(self, organization_id, actor, revision_id, role_code, decision, comment):
        raise MassBlastForbiddenError("Согласовать роль «blast_manager» может только назначенная учётка manager@example.ru.")

    def create_project(self, organization_id, actor, payload):
        self.created.append(payload)
        return {
            **payload, "id": "project-1", "lifecycle_status": "draft", "version": 1, "current_revision_id": None,
            "block_design_ids": [], "updated_at": "2026-10-04T00:00:00+00:00",
            "created_at": "2026-10-04T00:00:00+00:00", "created_by": actor, "updated_by": actor,
        }


@pytest.fixture()
def repository() -> _Repository:
    return _Repository()


@pytest.fixture()
def client(monkeypatch, repository: _Repository) -> TestClient:
    monkeypatch.setenv("BLASTEX_USERS_JSON", json.dumps(USERS))
    # Технический снимок блока читается из файлового хранилища паспортов — тесту он не нужен.
    monkeypatch.setattr(mass_blast_service, "_blocks_from_payload", lambda organization_id, payload: [])
    app = FastAPI()
    app.include_router(mass_blast.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: SESSION
    app.dependency_overrides[get_mass_blast_repository] = lambda: repository
    app.dependency_overrides[get_economics_repository] = lambda: SimpleNamespace(
        get_reference_snapshot=lambda organization_id, requested: SimpleNamespace(revision_id="ref-1")
    )
    return TestClient(app)


def _project(manager: str = "manager@example.ru", supervisor: str = "supervisor@example.ru") -> dict:
    return {
        "name": "Массовый взрыв №1", "site_code": "SITE-1", "object_name": "Карьер", "blast_date": "2026-10-10",
        "blocks": [{"design_id": "design-1"}],
        "responsibilities": [
            {"role_code": "blast_manager", "employee_code": "Иванов", "account_email": manager},
            {"role_code": "explosives_supervisor", "employee_code": "Петров", "account_email": supervisor},
        ],
    }


def test_approval_by_a_foreign_account_is_forbidden(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/revisions/rev-1/approvals", json={"role_code": "blast_manager", "decision": "approved"}
    )

    assert response.status_code == 403
    assert "manager@example.ru" in response.json()["detail"]


def test_accounts_are_active_accounts_of_own_organization(client: TestClient) -> None:
    response = client.get(f"{BASE}/accounts")

    assert response.status_code == 200
    assert response.json() == [
        {"email": "manager@example.ru", "display_name": "Иванов И. И."},
        {"email": "supervisor@example.ru", "display_name": "supervisor@example.ru"},
    ]


@pytest.mark.parametrize("email", ["stranger@example.ru", "outsider@example.ru", "retired@example.ru"])
def test_project_with_an_account_outside_the_organization_is_rejected(
    client: TestClient, repository: _Repository, email: str
) -> None:
    response = client.post(BASE, json=_project(supervisor=email))

    assert response.status_code == 422
    assert email in response.json()["detail"]
    assert repository.created == []


def test_draft_keeps_accounts_normalized_and_allows_an_empty_one(
    client: TestClient, repository: _Repository
) -> None:
    response = client.post(BASE, json=_project(manager=" Manager@Example.RU ", supervisor=""))

    assert response.status_code == 201, response.text
    assert [item["account_email"] for item in repository.created[0]["responsibilities"]] == [
        "manager@example.ru", ""
    ]
