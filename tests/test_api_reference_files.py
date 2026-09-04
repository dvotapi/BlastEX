"""`GET /economics/references/export` и `POST /economics/references/import`."""
from __future__ import annotations

import asyncio
import io
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.routers import economics
from api.security import SESSION_COOKIE, create_session_token
from api.services.economics_service import get_economics_repository
from cost.v2.models import ReferenceItem
from cost.v2.repository import InMemoryEconomicsRepository


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(economics.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


def _publish_site(repository: InMemoryEconomicsRepository) -> str:
    current = repository.get_reference_snapshot("default")
    sections = dict(current.sections)
    sections["sites"] = (ReferenceItem("SITE_X", "Карьер X", {"mobilization_km": "15"}),)
    return repository.publish_references("default", "tester", current.revision_id, sections, "test").revision_id


def test_export_xlsx_returns_a_workbook_attachment(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    revision = _publish_site(repository)
    response = client.get("/api/v1/economics/references/export?format=xlsx")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert response.headers["content-disposition"] == f'attachment; filename="references-{revision[:8]}.xlsx"'
    book = load_workbook(io.BytesIO(response.content))
    assert book["sites"]["A3"].value == "SITE_X"


def test_export_json_matches_snapshot_and_accepts_revision_id(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    first = repository.get_reference_snapshot("default").revision_id
    second = _publish_site(repository)
    latest = client.get("/api/v1/economics/references/export?format=json")
    assert latest.status_code == 200
    assert latest.headers["content-disposition"].endswith(f'references-{second[:8]}.json"')
    assert latest.json()["sections"]["sites"][0]["code"] == "SITE_X"
    old = client.get(f"/api/v1/economics/references/export?format=json&revision_id={first}")
    assert old.json()["revision_id"] == first
    assert old.json()["sections"]["sites"] == []


def test_export_rejects_unknown_format(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    assert client.get("/api/v1/economics/references/export?format=csv").status_code == 422


def test_export_does_not_reach_another_organization(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    other = repository.get_reference_snapshot("other")
    foreign = repository.publish_references(
        "other", "tester", other.revision_id, dict(other.sections), "чужая ревизия"
    ).revision_id
    response = client.get(f"/api/v1/economics/references/export?format=json&revision_id={foreign}")
    assert response.status_code == 404, response.text


def test_import_xlsx_returns_sections_without_writing(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    exported = client.get("/api/v1/economics/references/export?format=xlsx").content
    before = repository.get_reference_snapshot("default").revision_id
    response = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.xlsx", exported, "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["file_name"] == "refs.xlsx"
    assert body["counts"]["units"] > 0
    # Источник — колонка файла: круг «выгрузили — загрузили» его не меняет.
    assert body["sections"]["units"][0]["source"] == "BlastEX Cost V2"
    assert repository.get_reference_snapshot("default").revision_id == before


def test_import_json_and_bad_file(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    snapshot = client.get("/api/v1/economics/references/export?format=json").json()
    ok = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.json", json.dumps(snapshot).encode("utf-8"), "application/json")},
    )
    assert ok.status_code == 200
    bad = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.json", b"not json", "application/json")},
    )
    assert bad.status_code == 422
    assert "JSON" in bad.json()["detail"]["message"]


def test_import_parses_the_file_outside_the_event_loop(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    exported = client.get("/api/v1/economics/references/export?format=json").content
    original = economics.import_file
    seen: dict[str, bool] = {}

    def spy(name: str, data: bytes):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            seen["on_loop"] = False
        else:
            seen["on_loop"] = True
        return original(name, data)

    monkeypatch.setattr(economics, "import_file", spy)
    response = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.json", exported, "application/json")},
    )
    assert response.status_code == 200, response.text
    # Разбор книги синхронный: в цикле событий он останавливает весь сервер.
    assert seen == {"on_loop": False}


def test_import_reports_a_broken_workbook_as_unprocessable(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    response = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.xlsx", b"PK\x03\x04 not a zip", "application/octet-stream")},
    )
    assert response.status_code == 422, response.text
    assert "xlsx" in response.json()["detail"]["message"]


def test_import_rejects_a_file_over_the_limit(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    oversized = b"x" * (economics.MAX_REFERENCE_FILE_BYTES + 1)
    response = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.xlsx", oversized, "application/octet-stream")},
    )
    assert response.status_code == 413, response.status_code
    assert response.json()["detail"] == "Файл больше 20 МБ."


def test_user_cannot_import(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    token = create_session_token("user@example.ru", "user", "default", int(time.time()) + 3600)
    user_client = TestClient(client.app)
    user_client.cookies.set(SESSION_COOKIE, token)
    response = user_client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.json", b"{}", "application/json")},
    )
    assert response.status_code == 403
