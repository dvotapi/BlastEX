"""`GET/PUT /economics/references/public-settings` и ошибки выгрузки в public."""
from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import economics
from api.security import SESSION_COOKIE, create_session_token
from api.services.economics_service import get_economics_repository
from api.services.public_sync_service import get_public_reader
from cost.v2.public_sync import PublicUnavailable, PublicWriteError, StaticPublicReader
from cost.v2.repository import InMemoryEconomicsRepository
from tests.test_public_sync_mapping import make_snapshot


class _FailingReader:
    """Читалка, всегда падающая — модель недоступности схемы public."""

    def read(self):
        raise PublicUnavailable("Схема public недоступна: нет прав")


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    """Клиент с внутренним ключом: у него роль `service`, то есть права админа."""

    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(economics.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


def _client_as(app: FastAPI, role: str) -> TestClient:
    """Клиент с сессией указанной роли — без внутреннего ключа."""

    token = create_session_token(f"{role}@example.ru", role, "default", int(time.time()) + 3600)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, token)
    return client


def test_public_settings_are_disabled_by_default(monkeypatch) -> None:
    client, _ = _client(monkeypatch)

    response = client.get("/api/v1/economics/references/public-settings")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["exchange_enabled"] is False
    assert set(body["mirror_sections"]) == set(body["mirrorable_sections"])
    assert not any(body["mirror_sections"].values())
    assert "rocks" in body["mirrorable_sections"]
    # Сопоставленные разделы зеркалами не выгружаются: их нет среди
    # переключателей, но фронт должен знать их список.
    assert "sites" in body["mapped_sections"]
    assert "sites" not in body["mirror_sections"]


def test_admin_enables_exchange_and_rocks_mirror(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    admin_client = _client_as(client.app, "admin")

    response = admin_client.put(
        "/api/v1/economics/references/public-settings",
        json={"exchange_enabled": True, "mirror_sections": {"rocks": True}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["exchange_enabled"] is True
    assert body["mirror_sections"]["rocks"] is True
    assert body["mirror_sections"]["units"] is False

    saved = admin_client.get("/api/v1/economics/references/public-settings").json()
    assert saved["exchange_enabled"] is True
    assert saved["mirror_sections"]["rocks"] is True


def test_reference_editor_cannot_change_public_settings(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    editor_client = _client_as(client.app, "reference_editor")

    response = editor_client.put(
        "/api/v1/economics/references/public-settings",
        json={"exchange_enabled": True, "mirror_sections": {}},
    )

    assert response.status_code == 403, response.text
    # Читать настройки редактор всё же может: без них не показать плашку.
    assert editor_client.get("/api/v1/economics/references/public-settings").status_code == 200


def test_mapped_section_cannot_be_mirrored(monkeypatch) -> None:
    client, _ = _client(monkeypatch)

    response = client.put(
        "/api/v1/economics/references/public-settings",
        json={"exchange_enabled": True, "mirror_sections": {"sites": True}},
    )

    assert response.status_code == 422, response.text
    assert "sites" in response.json()["detail"]["message"]


def _draft_with_counterparty(client: TestClient, payload: dict) -> dict:
    """Черновик из системной ревизии плюс один контрагент."""

    sections = client.get("/api/v1/economics/references/snapshot").json()["sections"]
    sections["counterparties"] = [
        {"code": "CP_NEW", "name": 'ООО "Новый"', "payload": payload, "is_active": True}
    ]
    return sections


def _issues(response, section: str, field: str) -> list[dict]:
    return [
        issue
        for issue in response.json()["issues"]
        if issue["section"] == section and issue["field"] == field
    ]


def test_validate_reports_counterparty_without_inn_when_exchange_enabled(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())
    sections = _draft_with_counterparty(client, {"role": "CUSTOMER"})

    without_exchange = client.post(
        "/api/v1/economics/references/validate", json={"sections": sections}
    )
    assert without_exchange.status_code == 200, without_exchange.text
    assert without_exchange.json()["valid"] is True
    assert _issues(without_exchange, "counterparties", "inn") == []

    client.put(
        "/api/v1/economics/references/public-settings",
        json={"exchange_enabled": True, "mirror_sections": {}},
    )
    with_exchange = client.post(
        "/api/v1/economics/references/validate", json={"sections": sections}
    )

    assert with_exchange.status_code == 200, with_exchange.text
    body = with_exchange.json()
    assert body["valid"] is False
    inn_issues = _issues(with_exchange, "counterparties", "inn")
    assert len(inn_issues) == 1
    assert inn_issues[0]["code"] == "CP_NEW"
    assert "ИНН" in inn_issues[0]["message"]


def test_validate_finds_inn_taken_in_journal(monkeypatch) -> None:
    """Со снимком журнала ловится и занятый ИНН: такую запись надо связать."""

    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())
    client.put(
        "/api/v1/economics/references/public-settings",
        json={"exchange_enabled": True, "mirror_sections": {}},
    )
    sections = _draft_with_counterparty(client, {"role": "CUSTOMER", "inn": "6608002092"})

    response = client.post("/api/v1/economics/references/validate", json={"sections": sections})

    assert response.status_code == 200, response.text
    assert response.json()["valid"] is False
    assert "уже есть в журнале" in _issues(response, "counterparties", "inn")[0]["message"]


def test_validate_without_journal_still_checks_own_constraints(monkeypatch) -> None:
    """Журнал недоступен — проверка идёт без снимка, а не пропускается."""

    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: _FailingReader()
    client.put(
        "/api/v1/economics/references/public-settings",
        json={"exchange_enabled": True, "mirror_sections": {}},
    )

    missing_inn = client.post(
        "/api/v1/economics/references/validate",
        json={"sections": _draft_with_counterparty(client, {"role": "CUSTOMER"})},
    )
    taken_inn = client.post(
        "/api/v1/economics/references/validate",
        json={
            "sections": _draft_with_counterparty(client, {"role": "CUSTOMER", "inn": "6608002092"})
        },
    )

    assert missing_inn.status_code == 200, missing_inn.text
    assert missing_inn.json()["valid"] is False
    # Уникальность ключа без снимка не проверить — эта запись проходит.
    assert taken_inn.json()["valid"] is True


def test_publish_returns_502_when_journal_rejects_write(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    snapshot = client.get("/api/v1/economics/references/snapshot").json()

    def _failing_publish(**_kwargs):
        raise PublicWriteError("нет прав на public.counterparties")

    monkeypatch.setattr(repository, "publish_references", _failing_publish)

    response = client.post(
        "/api/v1/economics/references/publish",
        json={
            "base_revision": snapshot["revision_id"],
            "sections": snapshot["sections"],
            "comment": "выгрузка",
        },
    )

    assert response.status_code == 502, response.text
    message = response.json()["detail"]["message"]
    assert message.startswith("Не удалось записать в project1.public:")


def test_enabling_exchange_without_access_returns_502(monkeypatch) -> None:
    """Обмен включают пробой журнала: без доступа это отказ чужой схемы."""

    client, repository = _client(monkeypatch)

    def _failing_settings(*_args, **_kwargs):
        raise PublicWriteError("нет прав на public.counterparties")

    monkeypatch.setattr(repository, "set_public_sync_settings", _failing_settings)

    response = client.put(
        "/api/v1/economics/references/public-settings",
        json={"exchange_enabled": True, "mirror_sections": {}},
    )

    assert response.status_code == 502, response.text
    assert response.json()["detail"]["message"].startswith(
        "Не удалось записать в project1.public:"
    )
