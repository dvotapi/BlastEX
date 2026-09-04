"""`POST /economics/references/public-delta` и `.../public-links`."""
from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import economics
from api.security import SESSION_COOKIE, create_session_token
from api.services.economics_service import get_economics_repository
from api.services.public_sync_service import get_public_reader
from cost.v2.public_sync import PublicUnavailable, StaticPublicReader
from cost.v2.repository import InMemoryEconomicsRepository
from tests.test_public_sync_mapping import make_snapshot


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(economics.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


class _FailingReader:
    """Читалка, всегда падающая — модель недоступности схемы public."""

    def read(self):
        raise PublicUnavailable("Схема public недоступна: нет прав")


def test_public_delta_for_empty_draft_lists_new_counterparty_first(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())

    response = client.post("/api/v1/economics/references/public-delta", json={"sections": {}})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    assert body["error"] == ""
    assert body["counts"]["new"] > 0
    assert body["entries"][0]["kind"] == "new"
    assert body["entries"][0]["section"] == "counterparties"


def test_public_delta_shows_changed_after_link_is_saved(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())

    link_response = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1},
    )
    assert link_response.status_code == 201, link_response.text

    draft_item = {
        "code": "SITE_LOM",
        "name": "Ломоватский карьер",
        "payload": {"mineral_type": "иной тип полезного ископаемого"},
        "is_active": True,
    }
    response = client.post(
        "/api/v1/economics/references/public-delta",
        json={"sections": {"sites": [draft_item]}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    lom_entries = [
        entry
        for entry in body["entries"]
        if entry["section"] == "sites" and entry["code"] == "SITE_LOM"
    ]
    assert len(lom_entries) == 1
    assert lom_entries[0]["kind"] == "changed"


def test_linking_same_public_row_twice_with_different_code_conflicts(monkeypatch) -> None:
    client, _ = _client(monkeypatch)

    first = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM_2", "public_table": "sites", "public_id": 1},
    )
    assert second.status_code == 409, second.text
    message = second.json()["detail"]["message"]
    assert "уже связана с другой записью справочника" in message
    # Код записи, которой строка журнала уже принадлежит, наружу не уходит.
    assert "SITE_LOM" not in message


def test_user_role_cannot_link_but_can_read_delta(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())
    token = create_session_token("user@example.ru", "user", "default", int(time.time()) + 3600)
    user_client = TestClient(client.app)
    user_client.cookies.set(SESSION_COOKIE, token)

    link_response = user_client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1},
    )
    assert link_response.status_code == 403

    delta_response = user_client.post(
        "/api/v1/economics/references/public-delta", json={"sections": {}}
    )
    assert delta_response.status_code == 200, delta_response.text


def test_public_delta_reports_unavailable_schema(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: _FailingReader()

    response = client.post("/api/v1/economics/references/public-delta", json={"sections": {}})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is False
    assert "Схема public недоступна" in body["error"]
    assert body["counts"] == {"new": 0, "changed": 0, "deactivated": 0}
    assert body["entries"] == []
