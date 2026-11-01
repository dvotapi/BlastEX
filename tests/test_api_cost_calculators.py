"""api.routers.cost: калькулятор ФОТ даёт те же цифры, что и прежний
Streamlit-калькулятор (cost/labor_ui.py); цена бурения — из модели блока."""
import unittest

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import cost as cost_router
from api.schemas.cost import (
    JobPositionSchema,
    LaborAssignmentSchema,
    LaborCalculateRequest,
)
from api.services.cost_service import calculate_labor
from api.services.economics_service import get_economics_repository
from cost.labor import LaborFOTSettings, calculate_labor_fot, labor_assignments_from_records, labor_catalog_from_records
from cost.v2.legacy_adapter import default_legacy_references, legacy_references_from_snapshot
from cost.v2.models import ReferenceItem
from cost.v2.repository import InMemoryEconomicsRepository


class LaborCalculatorTests(unittest.TestCase):
    def test_matches_direct_engine_call(self):
        catalog_records = [
            {"id": "p1", "name": "Мастер", "fixed_salary_monthly": 80_000.0, "piece_rate_per_m3": 0.25}
        ]
        assignment_records = [
            {"id": "a1", "position_id": "p1", "headcount": 1.0, "volume_m3": 30_000.0, "employee_shifts": 5.0}
        ]
        request = LaborCalculateRequest(
            labor_catalog=[JobPositionSchema(**catalog_records[0])],
            labor_assignments=[LaborAssignmentSchema(**assignment_records[0])],
        )
        response = calculate_labor(request)

        expected = calculate_labor_fot(
            catalog=labor_catalog_from_records(catalog_records),
            assignments=labor_assignments_from_records(assignment_records),
            settings=LaborFOTSettings(),
        )
        self.assertAlmostEqual(response.result.total_fot, expected.total_fot)
        self.assertEqual(len(response.table_rows), 1)


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(cost_router.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


def _snapshot_without_the_default_object(repository: InMemoryEconomicsRepository):
    """Ревизия организации, в которой объекта Cost V1 по умолчанию нет."""

    snapshot = repository.get_reference_snapshot("default")
    sections = dict(snapshot.sections)
    sections["sites"] = (
        ReferenceItem("SITE_FAR", "Дальний карьер", {"mobilization_km": "1500"}),
        ReferenceItem("SITE_NEAR", "Ближний карьер", {"mobilization_km": "10"}),
    )
    return repository.publish_references("default", "tester", snapshot.revision_id, sections, "test")


def test_context_without_object_name_takes_an_object_from_the_revision(monkeypatch):
    """Запрос без имени объекта (расчёт из «Проектирования») не должен падать
    на объекте Cost V1, которого в справочнике организации нет."""

    from api.schemas.cost import CostCalculateRequest
    from api.services.converters import build_calculation_context

    _, repository = _client(monkeypatch)
    legacy = legacy_references_from_snapshot(_snapshot_without_the_default_object(repository))

    context = build_calculation_context(CostCalculateRequest(scenario_id="drill_blast"), legacy)

    assert context.work_object.name == "Дальний карьер"
    assert context.drilling_price_source is None


def test_unknown_object_name_is_still_an_error(monkeypatch):
    from api.exceptions import WorkObjectNotFoundError
    from api.schemas.cost import CostCalculateRequest
    from api.services.converters import build_calculation_context

    _, repository = _client(monkeypatch)
    legacy = legacy_references_from_snapshot(_snapshot_without_the_default_object(repository))

    with pytest.raises(WorkObjectNotFoundError):
        build_calculation_context(
            CostCalculateRequest(scenario_id="drill_blast", work_object_name="Карьер, которого нет"),
            legacy,
        )


def test_cost_calculate_without_object_name_works_on_such_a_revision(monkeypatch):
    client, repository = _client(monkeypatch)
    _snapshot_without_the_default_object(repository)

    response = client.post(
        "/api/v1/cost/calculate",
        json={"scenario_id": "evv_manufacturing", "production_volume_tons": 1000},
    )

    assert response.status_code == 200, response.text
