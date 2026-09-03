"""Рабочее пространство Cost V1 хранится в PostgreSQL через репозиторий;
справочники приходят из опубликованной ревизии, а не из файлов."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import workspace
from api.services.economics_service import get_economics_repository
from cost.drilling_data import DEFAULT_OBJECT_NAME, DEFAULT_WORK_OBJECTS
from cost.labor import DEFAULT_LABOR_CATALOG
from cost.v2.models import ReferenceItem
from cost.v2.repository import InMemoryEconomicsRepository


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(workspace.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


def test_fresh_organization_gets_defaults(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    response = client.get("/api/v1/workspace")
    assert response.status_code == 200
    state = response.json()
    assert state["settings"]["active_scenario_id"] == "drill_blast"
    assert state["settings"]["active_work_object_name"] == DEFAULT_OBJECT_NAME
    assert [o["name"] for o in state["references"]["work_object_records"]] == [o.name for o in DEFAULT_WORK_OBJECTS]
    assert [p["id"] for p in state["snapshot"]["labor_catalog_records"]] == [p.id for p in DEFAULT_LABOR_CATALOG]
    assert state["snapshot"]["cost_catalog_records"]
    assert state["snapshot"]["fixed_cost_records"]
    assert state["drilling_price_per_m"] > 0


def test_snapshot_and_active_object_are_persisted(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    state = client.get("/api/v1/workspace").json()
    snapshot = state["snapshot"]
    snapshot["labor_shifts_per_month"] = 9
    snapshot["labor_assignment_records"] = [
        {"id": "la_x", "position_id": "labor_master", "headcount": 2, "volume_m3": 100, "employee_shifts": 1}
    ]
    snapshot["drilling_calculator_input"] = {**snapshot["drilling_calculator_input"], "volume_m": 500}
    saved = client.put(
        "/api/v1/workspace/snapshot",
        json={"snapshot": snapshot, "active_work_object_name": DEFAULT_WORK_OBJECTS[1].name},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["settings"]["active_work_object_name"] == DEFAULT_WORK_OBJECTS[1].name
    assert body["snapshot"]["labor_shifts_per_month"] == 9
    assert body["snapshot"]["labor_assignment_records"][0]["id"] == "la_x"
    assert body["snapshot"]["drilling_calculator_input"]["volume_m"] == 500

    stored = repository.get_legacy_scenario("default", "drill_blast")
    assert stored["labor_shifts_per_month"] == 9
    assert "cost_catalog_records" not in stored

    again = client.get("/api/v1/workspace").json()
    assert again["snapshot"]["labor_shifts_per_month"] == 9
    assert again["settings"]["active_work_object_name"] == DEFAULT_WORK_OBJECTS[1].name


def test_switching_scenario_keeps_each_scenario_state(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    state = client.get("/api/v1/workspace").json()
    snapshot = {**state["snapshot"], "labor_shifts_per_month": 3}
    client.put("/api/v1/workspace/snapshot", json={"snapshot": snapshot, "active_work_object_name": ""})

    switched = client.put("/api/v1/workspace/active-scenario", json={"scenario_id": "drilling"}).json()
    assert switched["settings"]["active_scenario_id"] == "drilling"
    assert switched["snapshot"]["scenario_id"] == "drilling"
    assert switched["snapshot"]["labor_shifts_per_month"] == 5.0

    back = client.put("/api/v1/workspace/active-scenario", json={"scenario_id": "drill_blast"}).json()
    assert back["snapshot"]["labor_shifts_per_month"] == 3


def test_published_sites_feed_the_workspace(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    current = repository.get_reference_snapshot("default")
    sections = dict(current.sections)
    sections["sites"] = (ReferenceItem("SITE_NEW", "Новый карьер", {"mobilization_km": "15"}),)
    repository.publish_references("default", "tester", current.revision_id, sections, "test")

    state = client.get("/api/v1/workspace").json()
    assert [o["name"] for o in state["references"]["work_object_records"]] == ["Новый карьер"]
