"""Маршруты наряда ↔ MagEX, JWKS, настройки ключа и клиент (TASK-018 PR 7, §2, §8)."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import config
from api.routers import mass_blast
from api.security import require_human, require_internal_access
from api.services import magex_naryad_service as magex
from api.services import magex_settings
from api.services.economics_service import get_economics_repository
from api.services.magex_client import MagexAuthError, MagexClient, MagexRejected, MagexUnavailable
from api.services.mass_blast_service import get_mass_blast_repository
from design.magex import jws
from tests.magex_contract import FIXTURES
from tests.magex_fakes import LAYER_ID, ORG, FakeMagex, MemoryRepository, configure, economics

BASE = "/api/v1/design/mass-blast-projects"
SESSION = {"sub": "manager@example.ru", "role": "admin", "org": ORG}


@pytest.fixture()
def fake(monkeypatch):
    configure(monkeypatch)
    magex._catalog_cache.clear()
    transport = FakeMagex()
    monkeypatch.setattr(magex, "TRANSPORT", transport)
    yield transport
    magex._catalog_cache.clear()


def _client(repository) -> TestClient:
    app = FastAPI()
    app.include_router(mass_blast.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: SESSION
    app.dependency_overrides[require_human] = lambda: SESSION
    app.dependency_overrides[get_mass_blast_repository] = lambda: repository
    app.dependency_overrides[get_economics_repository] = lambda: economics()
    return TestClient(app)


def test_routes_are_hidden_without_the_flag(monkeypatch, fake):
    monkeypatch.setenv(config.MAGEX_INTEGRATION_ENABLED_ENV, "0")
    client = _client(MemoryRepository())
    assert client.get(f"{BASE}/magex/materials").status_code == 404
    assert client.post(f"{BASE}/layers/{LAYER_ID}/magex/approve", json={"expected_version": 1}).status_code == 404


def test_approve_route_and_state(fake):
    repository = MemoryRepository()
    client = _client(repository)
    response = client.post(f"{BASE}/layers/{LAYER_ID}/magex/approve", json={"expected_version": 1})
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "ACCEPTED"
    state = client.get(f"{BASE}/layers/{LAYER_ID}/magex", params={"refresh": True}).json()
    assert state["accepted_ver"] == 1 and state["execution"]["status_label"] == "разрешена"
    revision_id = repository.versions[0]["layer_revision_id"]
    pdf = client.get(f"{BASE}/layers/revisions/{revision_id}/document.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_validation_errors_are_fields_not_text(fake):
    client = _client(MemoryRepository(payload={"number": ""}))
    response = client.post(f"{BASE}/layers/{LAYER_ID}/magex/approve", json={"expected_version": 1})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert {"magex_number_missing", "magex_admissions_unconfirmed"} <= {item["code"] for item in detail["issues"]}
    assert all(item["path"] for item in detail["issues"])


def test_plain_issue_of_naryad_is_refused_when_online(fake):
    client = _client(MemoryRepository())
    response = client.post(f"{BASE}/layers/{LAYER_ID}/revisions", json={"expected_version": 1})
    assert response.status_code == 422 and "Разрешить" in response.json()["detail"]


def test_pending_revision_print_is_conflict(fake):
    repository = MemoryRepository()
    client = _client(repository)
    client.get(f"{BASE}/layers/{LAYER_ID}/magex/availability")
    fake.down = True
    assert client.post(f"{BASE}/layers/{LAYER_ID}/magex/approve", json={"expected_version": 1}).json()["outcome"] == "PENDING"
    revision_id = repository.versions[0]["layer_revision_id"]
    response = client.get(f"{BASE}/layers/revisions/{revision_id}/document.pdf")
    assert response.status_code == 409 and "ожидает MagEX" in response.json()["detail"]
    fake.down = False
    assert client.post(f"{BASE}/layers/{LAYER_ID}/magex/retry").json()["outcome"] == "ACCEPTED"
    assert client.get(f"{BASE}/layers/revisions/{revision_id}/document.pdf").status_code == 200


def test_material_options_and_blasters(fake):
    client = _client(MemoryRepository())
    options = client.get(f"{BASE}/magex/materials").json()
    assert {"value": "1245e861-01f5-52d7-9c66-88a950bbc1be", "label": "Сферит-ДП 1000 — ПД, шт"} in options
    options = client.get(f"{BASE}/options/naryad").json()
    assert options["blasters"] == [{"value": "BL-01", "label": "Трегубов Александр Иванович — ЮФ60АВ",
                                    "fill": {"blaster_name": "Трегубов Александр Иванович", "blaster_index": "ЮФ60АВ"}}]
    assert options["vehicles"] == [{"value": "V-01", "label": "КамАЗ стенда — А123ВС96",
                                    "fill": {"vehicle_model": "КамАЗ 43118", "vehicle_plate": "А123ВС96", "driver": "Петров П. П."}}]
    assert client.get(f"{BASE}/magex/warehouses").json()[0]["label"] == "Склад ВМ № 1"


# --- JWKS и настройки ключа ---------------------------------------------

def test_jwks_endpoint_publishes_public_keys_only(monkeypatch):
    from api.main import app

    configure(monkeypatch)
    response = TestClient(app).get("/.well-known/jwks.json")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    keys = response.json()["keys"]
    assert keys == json.loads((FIXTURES / "keys" / "jwks.json").read_text())["keys"]
    assert all("d" not in key for key in keys)


def test_jwks_404_without_key(monkeypatch):
    from api.main import app

    monkeypatch.delenv(config.SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(config.SIGNING_KID_ENV, raising=False)
    monkeypatch.delenv(config.JWKS_EXTRA_ENV, raising=False)
    magex_settings.reset_magex_settings()
    assert TestClient(app).get("/.well-known/jwks.json").status_code == 404


def test_test_key_needs_explicit_permission(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv(config.ALLOW_TEST_KEY_ENV, "")
    with pytest.raises(RuntimeError, match="Тестовый ключ"):
        magex_settings.load_magex_settings()


def test_extra_keys_must_be_public_and_unique(monkeypatch):
    configure(monkeypatch)
    public = json.loads((FIXTURES / "keys" / "jwks.json").read_text())["keys"][0]
    monkeypatch.setenv(config.JWKS_EXTRA_ENV, json.dumps({"keys": [{**public, "kid": "next", "d": "secret"}]}))
    with pytest.raises(RuntimeError, match="закрытая часть"):
        magex_settings.load_magex_settings()
    monkeypatch.setenv(config.JWKS_EXTRA_ENV, json.dumps({"keys": [public]}))
    with pytest.raises(RuntimeError, match="kid повторяется"):
        magex_settings.load_magex_settings()
    monkeypatch.setenv(config.JWKS_EXTRA_ENV, json.dumps({"keys": [{**public, "kid": "old"}]}))
    assert [key["kid"] for key in magex_settings.load_magex_settings().published_keys] == ["TEST-ONLY-magex-fixture", "old"]


def test_offline_reasons(monkeypatch):
    configure(monkeypatch, url="")
    assert magex_settings.magex_mode(ORG) == "OFFLINE"
    assert "MAGEX_API_URL" in magex_settings.offline_reason(ORG)
    configure(monkeypatch)
    assert magex_settings.magex_mode(ORG) == "ONLINE"
    assert "сопоставлена" in magex_settings.offline_reason("other-org")
    monkeypatch.setenv(config.MAGEX_INTEGRATION_ENABLED_ENV, "0")
    assert magex_settings.magex_mode(ORG) is None


def test_organizations_must_be_uuids(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv(config.MAGEX_ORGANIZATIONS_ENV, json.dumps({ORG: "default"}))
    with pytest.raises(RuntimeError, match="не UUID"):
        magex_settings.load_magex_settings()


# --- клиент -----------------------------------------------------------------

def _key():
    return jws.load_signing_key((FIXTURES / "keys" / "TEST-ONLY-private.pem").read_text(), "TEST-ONLY-magex-fixture")


@pytest.mark.parametrize(("status", "error"), [
    (503, MagexUnavailable), (500, MagexUnavailable), (409, MagexRejected), (422, MagexRejected),
    (404, MagexRejected), (401, MagexAuthError), (403, MagexAuthError),
])
def test_client_maps_statuses(status, error):
    client = MagexClient("http://magex/api/v1", "org", _key(),
                         transport=lambda *args: (status, {"code": "X", "message": "m", "details": {"a": 1}}))
    with pytest.raises(error) as caught:
        client.get_naryad("id")
    assert caught.value.status == status


def test_client_network_failure_is_unavailable_and_hides_token():
    def broken(method, url, headers, params, body):
        raise OSError("connection refused " + headers["Authorization"])

    with pytest.raises(MagexUnavailable) as caught:
        MagexClient("http://magex/api/v1", "org", _key(), transport=broken).put_naryad("id", "secret.jws.string")
    assert "Bearer" not in str(caught.value) and "secret" not in str(caught.value)
