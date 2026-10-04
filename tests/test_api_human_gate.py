"""Статус и согласование подтверждает человек, а не сервисный ключ.

Сервисный ключ (`X-API-Key`) получает сессию ``role=service`` от имени
``api-key`` в организации default. Человеческий шлюз в домене отсекал только
системных акторов («system», «cron»…), поэтому ключ с ``confirm=true``
утверждал и закрывал паспорта организации, подписывал согласования массового
взрыва, продвигал модели и сам ставил им статус. Решение владельца:
утверждать и закрывать может любой вошедший человек (admin, reference_editor,
user), ключ статусы не меняет вовсе.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

import api.security as security
from api.routers import calibration, design, drift, learning, mass_blast, outcomes, registry, spatial
from api.schemas.design import BlastDesignSchema
from api.schemas.drift import DriftCheckRequest
from api.schemas.learning import LearningGlobalTrainRequest
from api.schemas.registry import RegistryPromoteRequest
from api.security import SESSION_COOKIE, create_session_token, require_internal_access
from api.services import design_service, drift_service, learning_service, registry_service
from api.services.economics_service import get_economics_repository
from api.services.mass_blast_service import get_mass_blast_repository
from cost.auth import ALLOWED_ROLES
from design import lifecycle as design_lifecycle
from design.mass_blast_repository import MassBlastConflictError, MassBlastNotFoundError
from intelligence.datasets.persistence import save_snapshot
from intelligence.drift import types as drift_types
from intelligence.registry import types as registry_types
from tests.outcome_fixtures import synthetic_outcome_snapshot
from tests.scenario_fixtures import charged_design
from tests.test_drift_engine import _shift_snapshot

ORG = "default"
PASSPORT_CHAIN = ("in_review", "approved", "executed", "closed")


@pytest.fixture()
def data_root(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    with patch("cost.persistence.data_root", return_value=tmp_path):
        yield tmp_path


def _app(*routers) -> FastAPI:
    """Роутеры подключены так же, как в `api.main`: за общим входом."""

    app = FastAPI()
    for router in routers:
        app.include_router(router, prefix="/api/v1", dependencies=[Depends(require_internal_access)])
    return app


def _key_client(app: FastAPI, *, raise_server_exceptions: bool = True) -> TestClient:
    return TestClient(
        app, headers={"X-API-Key": "test-api-key"}, raise_server_exceptions=raise_server_exceptions
    )


def _human_client(app: FastAPI, role: str) -> TestClient:
    token = create_session_token(f"{role}@example.ru", role, ORG, int(time.time()) + 3600)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, token)
    return client


# --- Шлюз --------------------------------------------------------------------


def test_service_session_is_not_a_human() -> None:
    with pytest.raises(HTTPException) as error:
        security.require_human({"sub": "api-key", "role": "service", "org": ORG})
    assert error.value.status_code == 403


@pytest.mark.parametrize("role", sorted(ALLOWED_ROLES))
def test_every_user_account_role_is_human(role: str) -> None:
    session: dict[str, object] = {"sub": f"{role}@example.ru", "role": role, "org": ORG}
    assert security.require_human(session) is session


def test_service_key_actor_is_not_human_in_domain_gates(monkeypatch) -> None:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    actor = require_internal_access(x_api_key="test-api-key", blastex_session=None)["sub"]
    assert actor in design_lifecycle.AUTO_ACTORS
    assert actor in registry_types.AUTO_ACTORS
    assert actor in drift_types.AUTO_ACTORS


# --- Паспорт БВР ---------------------------------------------------------------


def _passport() -> str:
    payload = BlastDesignSchema(**charged_design("human-gate").to_dict())
    return design_service.create_plan(ORG, payload, actor="engineer@example.ru").design_id


def _transition(client: TestClient, design_id: str, to_status: str):
    return client.post(
        f"/api/v1/design/plans/{design_id}/lifecycle",
        json={"to_status": to_status, "confirm": True, "note": "проверено"},
    )


def test_service_key_cannot_make_any_passport_transition(data_root) -> None:
    app = _app(design.router)
    key, human = _key_client(app), _human_client(app, "user")
    design_id = _passport()

    for to_status in PASSPORT_CHAIN:
        before = design_service.get_plan(ORG, design_id).lifecycle_status
        response = _transition(key, design_id, to_status)
        assert response.status_code == 403, (to_status, response.text)
        assert design_service.get_plan(ORG, design_id).lifecycle_status == before
        assert _transition(human, design_id, to_status).status_code == 200


@pytest.mark.parametrize("role", sorted(ALLOWED_ROLES))
def test_any_signed_in_role_approves_and_closes_passport(data_root, role: str) -> None:
    app = _app(design.router)
    human = _human_client(app, role)
    design_id = _passport()

    for to_status in PASSPORT_CHAIN:
        response = _transition(human, design_id, to_status)
        assert response.status_code == 200, (to_status, response.text)

    plan = design_service.get_plan(ORG, design_id)
    assert plan.lifecycle_status == "closed"
    assert plan.lifecycle_events[-1].actor == f"{role}@example.ru"


# --- Массовый взрыв -------------------------------------------------------------


class _RecordingMassBlastRepository:
    """Запоминает, кто дошёл до хранилища; Postgres тесту не нужен."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def approve_revision(self, organization_id, actor, revision_id, role_code, decision, comment):
        self.calls.append(("approve", organization_id, actor))
        return {
            "id": "approval-1",
            "revision_id": revision_id,
            "role_code": role_code,
            "actor": actor,
            "decision": decision,
            "comment": comment,
            "content_sha256": "0" * 64,
            "created_at": "2026-10-04T00:00:00+00:00",
        }

    def transition_project(self, organization_id, actor, project_id, to_status, expected_version, note):
        self.calls.append(("transition", organization_id, actor))
        raise MassBlastConflictError("Заглушка: до хранилища дошли.")

    def get_project(self, organization_id, project_id):
        # Выпуск ревизии начинается с чтения проекта; актор сюда не передаётся.
        self.calls.append(("get_project", organization_id, ""))
        raise MassBlastNotFoundError("Заглушка: до хранилища дошли.")


def _mass_blast_app(monkeypatch) -> tuple[FastAPI, _RecordingMassBlastRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = _RecordingMassBlastRepository()
    app = _app(mass_blast.router)
    app.dependency_overrides[get_mass_blast_repository] = lambda: repository
    app.dependency_overrides[get_economics_repository] = lambda: None
    return app, repository


def _approve(client: TestClient):
    return client.post(
        "/api/v1/design/mass-blast-projects/revisions/rev-1/approvals",
        json={"role_code": "blast_manager", "decision": "approved", "comment": ""},
    )


def _mass_blast_transition(client: TestClient):
    return client.post(
        "/api/v1/design/mass-blast-projects/project-1/lifecycle",
        json={"to_status": "approved", "expected_version": 1, "confirm": True, "note": ""},
    )


def _issue_revision(client: TestClient):
    # Выпуск ревизии переводит проект из черновика «на проверку».
    return client.post(
        "/api/v1/design/mass-blast-projects/project-1/revisions",
        json={"expected_version": 1, "require_attachments": False},
    )


def test_service_key_cannot_issue_mass_blast_revision(monkeypatch) -> None:
    app, repository = _mass_blast_app(monkeypatch)

    response = _issue_revision(_key_client(app))

    assert response.status_code == 403, response.text
    assert repository.calls == []


def test_signed_in_user_reaches_mass_blast_revision(monkeypatch) -> None:
    app, repository = _mass_blast_app(monkeypatch)

    response = _issue_revision(_human_client(app, "user"))

    assert response.status_code == 404, response.text
    assert repository.calls == [("get_project", ORG, "")]


def test_service_key_cannot_sign_mass_blast_approval(monkeypatch) -> None:
    app, repository = _mass_blast_app(monkeypatch)

    response = _approve(_key_client(app))

    assert response.status_code == 403, response.text
    assert repository.calls == []


def test_service_key_cannot_change_mass_blast_status(monkeypatch) -> None:
    app, repository = _mass_blast_app(monkeypatch)

    response = _mass_blast_transition(_key_client(app))

    assert response.status_code == 403, response.text
    assert repository.calls == []


def test_signed_in_user_signs_mass_blast_approval(monkeypatch) -> None:
    app, repository = _mass_blast_app(monkeypatch)
    # Подписывает только действующая учётка организации (PR #113).
    monkeypatch.setenv("BLASTEX_USERS_JSON", json.dumps([
        {"email": "user@example.ru", "password_hash": "x", "role": "user", "organization_id": ORG},
    ]))

    response = _approve(_human_client(app, "user"))

    assert response.status_code == 200, response.text
    assert repository.calls == [("approve", ORG, "user@example.ru")]


def test_signed_in_user_reaches_mass_blast_transition(monkeypatch) -> None:
    app, repository = _mass_blast_app(monkeypatch)

    response = _mass_blast_transition(_human_client(app, "user"))

    assert response.status_code == 409, response.text
    assert repository.calls == [("transition", ORG, "user@example.ru")]


# --- Реестр моделей и дрифт (ML-слой) --------------------------------------------


def _candidate_model():
    snapshot = save_snapshot(ORG, synthetic_outcome_snapshot(dataset_id="human-gate-train"))
    trained = learning_service.train_global_model(
        ORG, LearningGlobalTrainRequest(dataset_ids=[snapshot.dataset_id], model_type="fragmentation")
    )
    return trained, snapshot


def _promote(client: TestClient, model_id: str):
    return client.post(
        f"/api/v1/registry/models/learning/{model_id}/promote",
        json={"to_status": "staging", "confirm": True, "note": ""},
    )


def test_service_key_cannot_promote_model(data_root) -> None:
    trained, _ = _candidate_model()

    response = _promote(_key_client(_app(registry.router)), trained.model_id)

    assert response.status_code == 403, response.text
    assert registry_service.get_registry_model(ORG, "learning", trained.model_id).status == "candidate"


def test_signed_in_user_promotes_model(data_root) -> None:
    trained, _ = _candidate_model()

    response = _promote(_human_client(_app(registry.router), "user"), trained.model_id)

    assert response.status_code == 200, response.text
    assert response.json()["promoted_by"] == "user@example.ru"


def _drift_alert_id() -> str:
    trained, snapshot = _candidate_model()
    registry_service.promote_registry_model(
        ORG,
        "learning",
        trained.model_id,
        RegistryPromoteRequest(to_status="production", confirm=True),
        actor="lead@example.ru",
    )
    current = save_snapshot(ORG, _shift_snapshot(snapshot, dataset_id="human-gate-now"))
    report = drift_service.run_check(
        ORG,
        DriftCheckRequest(family="learning", model_id=trained.model_id, current_dataset_id=current.dataset_id),
    )
    assert report.alerts, "фикстура должна дать сигнал дрифта"
    return report.alerts[0].alert_id


def _acknowledge(client: TestClient, alert_id: str):
    return client.post(f"/api/v1/drift/alerts/{alert_id}/acknowledge", json={"confirm": True})


def test_service_key_cannot_acknowledge_drift_alert(data_root) -> None:
    alert_id = _drift_alert_id()

    response = _acknowledge(_key_client(_app(drift.router)), alert_id)

    assert response.status_code == 403, response.text
    assert drift_service.get_drift_alert(ORG, alert_id).acknowledged is False


def test_signed_in_user_acknowledges_drift_alert(data_root) -> None:
    alert_id = _drift_alert_id()

    response = _acknowledge(_human_client(_app(drift.router), "user"), alert_id)

    assert response.status_code == 200, response.text
    assert response.json()["acknowledged_by"] == "user@example.ru"


# --- Статус моделей ML в обход реестра --------------------------------------------


@pytest.mark.parametrize("router", [calibration.router, learning.router, outcomes.router, spatial.router], ids=lambda r: r.prefix)
def test_service_key_cannot_set_ml_model_status(data_root, router) -> None:
    # Шлюз срабатывает до чтения модели: несуществующего id достаточно.
    client = _key_client(_app(router), raise_server_exceptions=False)

    response = client.post(f"/api/v1{router.prefix}/models/missing-model/status", json={"status": "production"})

    assert response.status_code == 403, response.text


def test_service_key_cannot_put_learning_model_into_production(data_root) -> None:
    trained, _ = _candidate_model()

    response = _key_client(_app(learning.router)).post(
        f"/api/v1/learning/models/{trained.model_id}/status", json={"status": "production"}
    )

    assert response.status_code == 403, response.text
    assert registry_service.get_registry_model(ORG, "learning", trained.model_id).status == "candidate"


def test_signed_in_user_sets_learning_model_status(data_root) -> None:
    trained, _ = _candidate_model()

    response = _human_client(_app(learning.router), "user").post(
        f"/api/v1/learning/models/{trained.model_id}/status", json={"status": "production"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "production"
