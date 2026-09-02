"""API вкладки «Экономика» на in-memory репозитории."""
from __future__ import annotations

from decimal import Decimal

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


def _parameters(passport_id: str, **overrides) -> dict:
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


def test_block_economics_returns_four_prices(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post("/api/v1/economics/block-economics", json=_parameters(passport_id))

    assert response.status_code == 200
    body = response.json()
    assert set(body["price_per_m3"]) == {"marginal", "full", "with_margin", "with_vat"}
    assert body["price_per_m3"]["full"] > body["price_per_m3"]["marginal"]
    assert body["natural"]["values"]["rig_shifts"]
    assert any(line["cost_item_code"] == "DRILL_TOOLING" for line in body["lines"])


def test_unknown_passport_gives_404(client) -> None:
    test_client, _, _ = client
    response = test_client.post(
        "/api/v1/economics/block-economics", json=_parameters("no-such-passport")
    )
    assert response.status_code == 404


def test_run_is_saved_listed_and_read_back(client) -> None:
    test_client, _, passport_id = client
    created = test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "Базовый"}
    )
    assert created.status_code == 201
    run = created.json()
    assert run["name"] == "Базовый"
    assert run["reference_revision_id"]

    listed = test_client.get(
        "/api/v1/economics/runs", params={"technical_passport_id": passport_id}
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [run["id"]]
    assert listed.json()[0]["price_per_m3"]["full"] > 0

    single = test_client.get(f"/api/v1/economics/runs/{run['id']}")
    assert single.status_code == 200
    assert single.json()["result"]["price_per_m3"] == run["result"]["price_per_m3"]


def test_compare_shows_delta_per_item_and_price(client) -> None:
    test_client, _, passport_id = client
    first = test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "План 600 000"}
    ).json()
    second = test_client.post(
        "/api/v1/economics/runs",
        json={
            **_parameters(passport_id, unit_plan_volume_m3="400000"),
            "name": "План 400 000",
        },
    ).json()

    response = test_client.post(
        "/api/v1/economics/runs/compare", json={"run_ids": [first["id"], second["id"]]}
    )
    assert response.status_code == 200
    body = response.json()
    assert [run["name"] for run in body["runs"]] == ["План 600 000", "План 400 000"]
    assert body["delta_price_per_m3"]["full"] > 0
    assert body["delta_price_per_m3"]["marginal"] == 0
    unit_row = next(row for row in body["rows"] if row["cost_item_code"].startswith("UNIT_"))
    assert unit_row["delta_rub"] > 0
    assert len(unit_row["amounts"]) == 2


def test_sensitivity_is_sorted_by_effect(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post(
        "/api/v1/economics/block-economics/sensitivity", json=_parameters(passport_id)
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    deltas = [abs(row["delta_rub_m3"]) for row in rows]
    assert deltas == sorted(deltas, reverse=True)
    assert {row["code"] for row in rows} >= {"EXPLOSIVE_PRICE", "UNIT_PLAN_VOLUME"}


def test_model_defaults_come_from_references(client) -> None:
    test_client, _, passport_id = client
    response = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parameters"]["site_code"] == "SITE_MAIN"
    assert Decimal(body["parameters"]["unit_plan_volume_m3"]) == Decimal("600000")
    assert body["parameters"]["rig_code"] == "RIG_JK830"
    assert [member["position_code"] for member in body["parameters"]["crew"]] == [
        "POS_DRILLER",
        "POS_BLASTER",
        "POS_SZM_DRIVER",
    ]
    assert "PRODUCTION_DRILLING" in body["package_operations"]


def test_export_returns_xlsx_workbook(client) -> None:
    test_client, _, passport_id = client
    run = test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "Экспорт"}
    ).json()

    response = test_client.get(f"/api/v1/economics/runs/{run['id']}/export.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert response.content[:2] == b"PK"


def test_another_organization_does_not_see_runs(client) -> None:
    test_client, repository, passport_id = client
    test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "Свой"}
    )

    assert repository.list_economics_runs("other-org") == ()
