"""Общие фикстуры тестов API вкладки «Экономика блока»."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import block_economics
from api.services.economics_service import get_economics_repository
from cost.v2.repository import InMemoryEconomicsRepository
from tests import model_fixtures as fx


@pytest.fixture()
def client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository, str]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    references = fx.references()
    snapshot = repository.publish_references(
        "default",
        "tester",
        repository.list_reference_revisions("default")[0].id,
        {section: list(items) for section, items in references.sections.items()},
        "фикстура тестов",
    )
    passport = repository.save_technical_passport(
        "default",
        "tester",
        site_code="SITE_MAIN",
        object_name="Блок 60 000 м³",
        previous_passport_id=None,
        reference_revision_id=snapshot.revision_id,
        formula_version="blast-geometry-v1",
        input_snapshot={},
        selected_variant={},
        block_snapshot={},
        physical={key: str(value) for key, value in fx.physical().items()},
        lineage={"rock_volume_m3": "BlastGeometry.block.block_volume_m3"},
    )
    app = FastAPI()
    app.include_router(block_economics.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    test_client = TestClient(app, headers={"X-API-Key": "test-api-key"})
    return test_client, repository, passport.id


def parameters_payload(passport_id: str, **overrides) -> dict:
    """Тело запроса `/block-economics`: нормативный набор параметров с точечными правками."""

    parameters = {
        "package_code": "DRILL_AND_BLAST",
        "site_code": "SITE_MAIN",
        "reference_revision_id": "",
        "unit_plan_volume_m3": "600000",
        "rig_code": "RIG_JK830",
        "rig_plan_shifts": "40",
        "szm_code": "SZM_12T",
        "delivery_truck_code": "TRUCK_3T",
        "crew": [
            {"position_code": "POS_BLASTER", "headcount": "2"},
            {"position_code": "POS_DRILLER", "headcount": "0"},
        ],
    }
    parameters.update(overrides)
    return {"technical_passport_id": passport_id, "parameters": parameters}
