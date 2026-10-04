"""`POST /api/v1/economics/payroll/preview` на in-memory репозитории (TASK-010)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import block_economics
from api.services.economics_service import get_economics_repository
from cost.v2.repository import InMemoryEconomicsRepository
from tests.payroll_fixtures import payroll_references

URL = "/api/v1/economics/payroll/preview"


@pytest.fixture
def api(monkeypatch) -> TestClient:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    references = payroll_references()
    repository.publish_references(
        "default",
        "tester",
        repository.list_reference_revisions("default")[0].id,
        {section: list(items) for section, items in references.sections.items()},
        "фикстура ФОТ",
    )
    app = FastAPI()
    app.include_router(block_economics.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


def body(**fields) -> dict:
    return {"position_code": "P_DRILLER", "site_code": "SITE_LOM", "month": "2026-09", **fields}


def test_plan_preview_without_price_returns_200_and_no_share(api: TestClient) -> None:
    response = api.post(URL, json=body(meters_total="2400"))
    assert response.status_code == 200
    data = response.json()
    assert data["reference_revision_id"]
    assert data["premium"]["total"] == pytest.approx(156000.67, abs=0.01)
    assert data["shifts"]["effective"] == 13
    assert data["margin"]["status"] == "NOT_CHECKED"
    assert data["margin"]["ceiling"] is None
    assert data["rows"][-1]["code"] == "COMPANY_COST"
    assert data["series"]


def test_share_in_two_points_and_the_warning_flag(api: TestClient) -> None:
    response = api.post(URL, json=body(meters_total="2000", price_rub_per_m="800", variable_rub_per_m="250"))
    assert response.status_code == 200
    margin = response.json()["margin"]
    assert margin["ceiling"]["crew_share"] == pytest.approx(0.9646, abs=1e-4)
    assert margin["plan"]["crew_share"] == pytest.approx(0.5778, abs=1e-4)
    assert margin["ceiling"]["main_share"] == pytest.approx(0.3067, abs=1e-4)
    assert [flag["code"] for flag in response.json()["flags"]] == ["MARGIN_SHARE_ABOVE_WARN"]


def test_meters_by_rock_and_downtime_flags(api: TestClient) -> None:
    response = api.post(
        URL,
        json=body(
            items=[
                {"meters": "800", "diameter_mm": "152", "rock_code": "ROCK_F10"},
                {"meters": "900", "diameter_mm": "250", "rock_code": "ROCK_F17"},
            ],
            shifts="13",
            downtime=[{"code": "DT_WAIT_BLOCK", "hours": "40"}],
        ),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meters"]["total"] == pytest.approx(2571.2)
    assert data["shifts"]["written_off_share"] == pytest.approx(40 / 143)
    assert "DOWNTIME_OVER_25" in [flag["code"] for flag in data["flags"]]


@pytest.mark.parametrize("hours", ["143", "150"])
def test_downtime_for_the_whole_rotation_is_422(api: TestClient, hours: str) -> None:
    response = api.post(
        URL, json=body(meters_total="2000", shifts="13", downtime=[{"code": "DT_RIG_REPAIR", "hours": hours}])
    )
    assert response.status_code == 422
    assert "вахт" in response.json()["detail"]


def test_unknown_position_is_422(api: TestClient) -> None:
    response = api.post(URL, json=body(position_code="NOPE"))
    assert response.status_code == 422
    assert "NOPE" in response.json()["detail"]


@pytest.mark.parametrize(
    "fields",
    [
        {"meters_total": "100", "items": [{"meters": "100", "diameter_mm": "152"}]},
        {"downtime": [{"code": "DT_RIG_REPAIR", "hours": "5"}]},
        {"month": "2026-13"},
        {"items": [{"meters": "100", "diameter_mm": "152", "rock_code": "ROCK_F10", "f": "10"}]},
    ],
)
def test_inconsistent_request_is_rejected_by_the_schema(api: TestClient, fields: dict) -> None:
    assert api.post(URL, json=body(**fields)).status_code == 422
