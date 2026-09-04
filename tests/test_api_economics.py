import time
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import economics
from api.security import SESSION_COOKIE, create_session_token
from api.services.economics_service import get_economics_repository
from api.services.public_sync_service import get_public_reader
from cost.v2.public_sync import StaticPublicReader
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


def test_reference_validate_publish_and_conflict(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    initial = client.get("/api/v1/economics/references/snapshot")
    assert initial.status_code == 200
    snapshot = initial.json()
    snapshot["sections"]["production_units"] = [
        {
            "code": "UNIT_1",
            "name": "Юнит 1",
            "payload": {},
            "is_active": True,
            "valid_from": None,
            "valid_to": None,
            "source": "test",
            "comment": "",
            "revision": 1,
        }
    ]
    validation = client.post(
        "/api/v1/economics/references/validate",
        json={"sections": snapshot["sections"]},
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is True
    payload = {
        "base_revision": snapshot["revision_id"],
        "sections": snapshot["sections"],
        "comment": "test",
    }
    published = client.post("/api/v1/economics/references/publish", json=payload)
    assert published.status_code == 200
    assert published.json()["revision_id"] != snapshot["revision_id"]
    conflict = client.post("/api/v1/economics/references/publish", json=payload)
    assert conflict.status_code == 409


def test_user_cannot_publish_references(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    snapshot = client.get("/api/v1/economics/references/snapshot").json()
    token = create_session_token(
        "user@example.ru",
        "user",
        "default",
        int(time.time()) + 3600,
    )
    user_client = TestClient(client.app)
    user_client.cookies.set(SESSION_COOKIE, token)
    response = user_client.post(
        "/api/v1/economics/references/publish",
        json={
            "base_revision": snapshot["revision_id"],
            "sections": snapshot["sections"],
            "comment": "forbidden",
        },
    )
    assert response.status_code == 403


def test_publish_with_exchange_enabled_links_new_counterparty(monkeypatch) -> None:
    """Обмен включён, данные проходят ограничения журнала — публикация штатная.

    In-memory репозиторий журнал не пишет, но связи вставок создаёт: по ним
    видно, что план выгрузки построен и валидация его не остановила.
    """

    client, repository = _client(monkeypatch)
    repository.public_snapshot = make_snapshot()
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())
    settings = client.put(
        "/api/v1/economics/references/public-settings",
        json={"exchange_enabled": True, "mirror_sections": {}},
    )
    assert settings.status_code == 200, settings.text

    snapshot = client.get("/api/v1/economics/references/snapshot").json()
    sections = snapshot["sections"]
    sections["counterparties"] = [
        {
            "code": "CP_NEW",
            "name": 'Общество с ограниченной ответственностью "Новый"',
            "payload": {"role": "SUPPLIER", "inn": "7708123456", "short_name": 'ООО "Новый"'},
            "is_active": True,
        }
    ]

    published = client.post(
        "/api/v1/economics/references/publish",
        json={
            "base_revision": snapshot["revision_id"],
            "sections": sections,
            "comment": "выгрузка",
        },
    )

    assert published.status_code == 200, published.text
    links = client.get("/api/v1/economics/references/public-links").json()
    created = [link for link in links if link["code"] == "CP_NEW"]
    assert len(created) == 1
    assert created[0]["section"] == "counterparties"
    assert created[0]["public_table"] == "counterparties"


def test_scenario_crud_and_calculation_run(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    revision = client.get("/api/v1/economics/references/snapshot").json()["revision_id"]
    scenario = {
        "id": "",
        "name": "Новый карьер",
        "description": "",
        "production_unit_code": "UNIT_1",
        "baseline_service_lines": [],
        "candidate_service_lines": [
            {
                "id": "line-1",
                "name": "Франко-скважина",
                "package_code": "VM_IN_HOLE",
                "customer_code": "C1",
                "site_code": "Q1",
                "billing_unit": "KG",
                "market_price_rub": 100,
                "monthly_plans": [
                    {
                        "month": "2026-09",
                        "billed_quantity": 10,
                        "physical": {"explosive_kg": 10, "szm_hours": 1},
                    }
                ],
                "operation_overrides": [],
                "site_conditions": {},
                "options": {"component_supply_mode": "PURCHASED_COMPONENTS"},
                "replaces_service_line_id": None,
            }
        ],
        "capacity_choices": [],
        "reference_revision_id": revision,
    }
    created = client.post("/api/v1/economics/scenarios", json=scenario)
    assert created.status_code == 201, created.text
    scenario_id = created.json()["id"]
    assert scenario_id
    calculated = client.post(
        f"/api/v1/economics/scenarios/{scenario_id}/calculate", json={}
    )
    assert calculated.status_code == 200, calculated.text
    run = calculated.json()
    assert run["scenario_id"] == scenario_id
    assert run["result"]["after"]["totals"]["revenue_rub"] == 1000
    loaded = client.get(f"/api/v1/economics/calculation-runs/{run['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["result"] == run["result"]


def test_technical_geometry_adapter_endpoint(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    response = client.post(
        "/api/v1/economics/technical-drivers",
        json={
            "source_id": "BLOCK-API-1",
            "existing_physical": {"szm_hours": 8},
            "block": {
                "block_volume_m3": 25000,
                "drilling_footage_m": 650,
                "total_charge_mass_kg": 12000,
                "total_holes": 50,
            },
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source_id"] == "BLOCK-API-1"
    assert Decimal(payload["physical"]["rock_volume_m3"]) == Decimal("25000")
    assert Decimal(payload["physical"]["szm_hours"]) == Decimal("8")
    assert Decimal(payload["physical"]["blasts"]) == Decimal("1")
