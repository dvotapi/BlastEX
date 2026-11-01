"""Цена метра бурения для листа «Расчёт» (TASK-010, PR 3)."""
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import cost as cost_router
from api.services.economics_service import get_economics_repository
from cost.model import drilling_price
from cost.model.drilling import DRILLING_OPERATION
from cost.model.engine import compute_block_economics
from cost.model.inputs import CrewMember
from cost.v2.repository import InMemoryEconomicsRepository
from tests import model_fixtures as fx

DRILLING_M = Decimal("5000")


def _price(**params):
    return drilling_price.compute(fx.parameters(**params), fx.references(), drilling_m=DRILLING_M)


def test_price_is_drilling_lines_per_metre_with_markups() -> None:
    price = _price()
    economics = compute_block_economics(
        {"physical": {"drilling_m": DRILLING_M}, "lineage": {}}, fx.parameters(), fx.references()
    )
    total = sum(
        (line.amount_rub for line in economics.lines if line.operation_code == DRILLING_OPERATION),
        Decimal("0"),
    )

    assert price.cost_rub_per_m == total / DRILLING_M
    assert price.price_rub_per_m == price.cost_rub_per_m * (1 + price.overhead_rate) * (1 + price.margin_rate)
    assert price.price_rub_per_m > 0


def test_price_does_not_depend_on_block_volume_or_explosives() -> None:
    """Лист даёт модели один драйвер — метры: ВВ и объём на цену метра не влияют."""

    with_explosives = compute_block_economics(fx.snapshot(drilling_m=DRILLING_M), fx.parameters(), fx.references())
    drilling_only = _price()
    total = sum(
        (line.amount_rub for line in with_explosives.lines if line.operation_code == DRILLING_OPERATION),
        Decimal("0"),
    )

    assert drilling_only.cost_rub_per_m == total / DRILLING_M


def test_crew_payroll_is_in_the_price() -> None:
    without_driller = _price(crew=(CrewMember("POS_BLASTER", Decimal("2")),))
    with_driller = _price(crew=(CrewMember("POS_DRILLER", Decimal("1")),))

    assert with_driller.price_rub_per_m > without_driller.price_rub_per_m


def test_markup_params_move_the_price() -> None:
    base = _price(overhead_rate=Decimal("0"), target_margin_rate=Decimal("0"))
    marked = _price(overhead_rate=Decimal("0.1"), target_margin_rate=Decimal("0.2"))

    assert marked.price_rub_per_m == pytest.approx(base.price_rub_per_m * Decimal("1.1") * Decimal("1.2"))


def test_payroll_mode_price_is_computed() -> None:
    price = _price(payroll_source="PAYROLL", crew=(CrewMember("POS_DRILLER", Decimal("1")),))

    assert price.payroll_source == "PAYROLL"
    assert price.price_rub_per_m > 0


def test_no_metres_gives_zero_price_and_warning() -> None:
    price = drilling_price.compute(fx.parameters(), fx.references(), drilling_m=Decimal("0"))

    assert price.price_rub_per_m == 0
    assert any("Метров бурения нет" in warning for warning in price.warnings)


def test_rig_without_condition_gives_zero_price_and_model_warning() -> None:
    price = drilling_price.compute(
        fx.parameters(), fx.references(drilling_conditions=()), drilling_m=DRILLING_M
    )

    assert price.price_rub_per_m == 0
    assert any("Бурение не рассчитано" in warning for warning in price.warnings)


def test_default_source_takes_first_rig_and_site_by_name() -> None:
    references = fx.references()
    source = drilling_price.default_source(references)

    assert source is not None
    assert source.params.rig_code == "RIG_JK830"
    assert source.params.package_code == "DRILL_AND_BLAST"
    assert source.params.site_code
    by_name = drilling_price.default_source(references, site_name="нет такого карьера")
    assert by_name is not None and by_name.params.site_code == source.params.site_code


def test_default_source_without_rigs_is_none() -> None:
    assert drilling_price.default_source(fx.references(equipment_types=())) is None


# --- лист «Расчёт»: POST /cost/calculate --------------------------------------


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    base = repository.get_reference_snapshot("default")
    repository.publish_references("default", "tester", base.revision_id, dict(fx.references().sections), "test")
    app = FastAPI()
    app.include_router(cost_router.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


def _body(**context) -> dict:
    return {
        "scenario_id": "drilling_only",
        "block": {
            "hole": {"grid_a_m": 5, "grid_b_m": 5, "depth_m": 15},
            "block": {
                "block_volume_m3": 60000,
                "total_holes": 400,
                "drilling_footage_m": 6000,
                "hole_count": 400,
                "yield_per_hole_m3": 150,
                "additional_holes_pct": 0,
                "additional_holes": 0,
                "total_charge_mass_kg": 1,
                "specific_q_kg_m3": 0.5,
            },
            "initiation": {},
            "explosive_key": "",
            "hole_depth_m": 15,
        },
        "context": context,
    }


def _parameters(**override) -> dict:
    return {
        "package_code": "DRILL_AND_BLAST",
        "site_code": "SITE_MAIN",
        "rig_code": "RIG_JK830",
        "rig_plan_shifts": "40",
        "crew": [{"position_code": "POS_DRILLER", "headcount": "1"}],
        **override,
    }


def test_sheet_price_comes_from_the_draft_parameters(monkeypatch) -> None:
    client, _ = _client(monkeypatch)

    response = client.post("/api/v1/cost/calculate", json=_body(drilling_model={"parameters": _parameters()}))

    assert response.status_code == 200, response.text
    drilling = response.json()["drilling_total_cost"]
    expected = drilling_price.compute(
        fx.parameters(
            crew=(CrewMember("POS_DRILLER", Decimal("1")),),
        ),
        fx.references(),
        drilling_m=Decimal("6000"),
    )
    assert drilling["price_per_m"] == pytest.approx(float(expected.price_rub_per_m))
    assert drilling["amount"] == pytest.approx(6000 * float(expected.price_rub_per_m))


def test_sheet_without_draft_gets_zero_price_and_a_note(monkeypatch) -> None:
    client, _ = _client(monkeypatch)

    response = client.post("/api/v1/cost/calculate", json=_body())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["drilling_total_cost"]["price_per_m"] == 0
    assert body["drilling_total_cost"]["amount"] == 0
    assert any("нет параметров бурения" in note for note in body["notes"])


def test_sheet_without_rig_gets_zero_price_and_a_note(monkeypatch) -> None:
    client, _ = _client(monkeypatch)

    response = client.post(
        "/api/v1/cost/calculate", json=_body(drilling_model={"parameters": _parameters(rig_code=None)})
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["drilling_total_cost"]["price_per_m"] == 0
    assert any("не выбран буровой станок" in note for note in body["notes"])


def test_design_source_reads_the_callers_organization(monkeypatch) -> None:
    """Расчёты «Проектирования» берут цену из ревизии организации вызывающего, а не «default»."""

    from api.schemas.cost import CostCalculateRequest
    from api.services import economics_service
    from api.services.cost_service import default_design_price_source

    repository = InMemoryEconomicsRepository()
    base = repository.get_reference_snapshot("org-a")
    repository.publish_references("org-a", "tester", base.revision_id, dict(fx.references().sections), "test")
    monkeypatch.setattr(economics_service, "get_economics_repository", lambda: repository)
    request = CostCalculateRequest(scenario_id="drill_blast")

    assert default_design_price_source(request, "org-a") is not None
    assert default_design_price_source(request, "org-b") is None
