from dataclasses import replace
from decimal import Decimal

import pytest

from cost.v2.engine import calculate_scenario
from cost.v2.models import EconomicScenario, ReferenceItem, ReferenceSnapshot
from cost.v2.references import default_reference_snapshot


def _references(
    *,
    cost_rules: tuple[ReferenceItem, ...] = (),
    resource_patches: dict[str, dict] | None = None,
    extra_sections: dict[str, tuple[ReferenceItem, ...]] | None = None,
) -> ReferenceSnapshot:
    base = default_reference_snapshot()
    sections = dict(base.sections)
    sections["cost_rules"] = cost_rules
    if resource_patches:
        resources = []
        for item in sections["resource_pools"]:
            patch = resource_patches.get(item.code)
            resources.append(replace(item, payload={**item.payload, **patch}) if patch else item)
        sections["resource_pools"] = tuple(resources)
    if extra_sections:
        sections.update(extra_sections)
    return ReferenceSnapshot("R1", sections)


def _line(
    package: str,
    *,
    line_id: str = "line",
    billing_unit: str = "M3",
    price: float = 0,
    billed: float = 1,
    physical: dict | None = None,
    options: dict | None = None,
    conditions: dict | None = None,
    overrides: list[dict] | None = None,
) -> dict:
    return {
        "id": line_id,
        "name": line_id,
        "package_code": package,
        "customer_code": f"C_{line_id}",
        "site_code": f"S_{line_id}",
        "billing_unit": billing_unit,
        "market_price_rub": price,
        "options": options or {},
        "site_conditions": conditions or {},
        "operation_overrides": overrides or [],
        "monthly_plans": [
            {
                "month": "2026-09",
                "billed_quantity": billed,
                "physical": physical or {},
            }
        ],
    }


def _scenario(*, baseline: list[dict] | None = None, candidate: list[dict] | None = None) -> EconomicScenario:
    return EconomicScenario.from_dict(
        {
            "id": "S1",
            "name": "Тест",
            "production_unit_code": "UNIT",
            "baseline_service_lines": baseline or [],
            "candidate_service_lines": candidate or [],
        }
    )


def test_vm_in_hole_excludes_initiation_and_hose_is_explicit_option() -> None:
    refs = _references(
        cost_rules=(
            ReferenceItem("VM", "ВМ", {"operation_code": "BULK_CHARGING_SZM", "behavior_type": "VARIABLE", "cost_layer": "variable", "driver": "explosive_kg", "rate_rub": 10}),
            ReferenceItem("HOSE", "Горнорабочий", {"operation_code": "CHARGING_HOSE_ASSISTANCE", "behavior_type": "VARIABLE", "cost_layer": "project_direct", "driver": "szm_hours", "rate_rub": 100}),
            ReferenceItem("NETWORK", "Сеть", {"operation_code": "INITIATION_NETWORK", "behavior_type": "VARIABLE", "cost_layer": "variable", "driver": "holes", "rate_rub": 999}),
        )
    )
    without_hose = _line(
        "VM_IN_HOLE",
        billing_unit="KG",
        price=20,
        billed=50,
        physical={"explosive_kg": 50, "szm_hours": 2, "holes": 10},
        options={"component_supply_mode": "PURCHASED_COMPONENTS"},
    )
    with_hose = {**without_hose, "id": "with-hose", "name": "with-hose", "options": {**without_hose["options"], "charging_hose_assistance": True}}

    first = calculate_scenario(_scenario(candidate=[without_hose]), refs)["after"]
    second = calculate_scenario(_scenario(candidate=[with_hose]), refs)["after"]

    assert first["totals"]["variable_cost"] == 500
    assert second["totals"]["project_direct_cost"] - first["totals"]["project_direct_cost"] == 200
    assert not any(row["cost_item_code"] == "NETWORK" for row in second["cost_lines"])
    szm = next(
        row for row in first["resource_utilization"] if row["resource_code"] == "SZM_HOUR"
    )
    assert szm["demand"] == 2


def test_bad_bench_surface_reduces_productivity_and_increases_drilling_cost() -> None:
    refs = _references(
        cost_rules=(
            ReferenceItem("DRILL", "Бурение", {"operation_code": "PRODUCTION_DRILLING", "behavior_type": "VARIABLE", "cost_layer": "project_direct", "driver": "drill_hours", "rate_rub": 100}),
        )
    )
    physical = {"drilling_m": 100, "base_drilling_productivity_m_h": 10}
    prepared = _line("DRILLING", physical=physical, conditions={"drilling_productivity_factor": 1})
    bad = _line("DRILLING", line_id="bad", physical=physical, conditions={"drilling_productivity_factor": 0.5})
    prepared_result = calculate_scenario(_scenario(candidate=[prepared]), refs)["after"]
    bad_result = calculate_scenario(_scenario(candidate=[bad]), refs)["after"]
    assert prepared_result["totals"]["project_direct_cost"] == 1000
    assert bad_result["totals"]["project_direct_cost"] == 2000
    prepared_rig = next(row for row in prepared_result["resource_utilization"] if row["resource_code"] == "DRILL_RIG_HOUR")
    bad_rig = next(row for row in bad_result["resource_utilization"] if row["resource_code"] == "DRILL_RIG_HOUR")
    assert bad_rig["demand"] == prepared_rig["demand"] * 2


@pytest.mark.parametrize(
    ("mode", "expected_cost"),
    [
        ("CUSTOMER_ALL_HOLES", 0),
        ("CUSTOMER_CONTROL_POINTS", 850),
        ("CONTRACTOR_ALL_HOLES", 1000),
    ],
)
def test_stakeout_responsibility_changes_own_cost(mode: str, expected_cost: float) -> None:
    refs = _references(
        cost_rules=(
            ReferenceItem("STAKEOUT", "Разбивка", {"operation_code": "SURVEY_STAKEOUT", "behavior_type": "VARIABLE", "cost_layer": "project_direct", "driver": "stakeout_holes", "rate_rub": 10}),
        )
    )
    line = _line("DRILLING", physical={"holes": 100}, conditions={"stakeout_mode": mode})
    result = calculate_scenario(_scenario(candidate=[line]), refs)["after"]
    assert result["totals"]["project_direct_cost"] == expected_cost


def test_missing_site_infrastructure_creates_alternative_direct_costs() -> None:
    line = _line(
        "DRILLING",
        physical={"fuel_delivery_trips": 3, "mobile_maintenance_shifts": 2, "person_days": 10, "person_nights": 8},
        conditions={
            "refueling_available": False,
            "maintenance_box_available": False,
            "canteen_available": False,
            "accommodation_available": False,
            "own_fuel_delivery_cost_rub_trip": 1000,
            "mobile_maintenance_cost_rub_shift": 2000,
            "meal_cost_rub_person_day": 300,
            "accommodation_cost_rub_person_night": 500,
        },
    )
    result = calculate_scenario(_scenario(candidate=[line]), _references())["after"]
    assert result["totals"]["project_direct_cost"] == 14_000


def test_fixed_resource_cost_stays_constant_until_capacity_step() -> None:
    refs = _references(
        resource_patches={
            "DRILL_RIG_HOUR": {
                "monthly_capacity": 10,
                "fixed_cost_rub": 1000,
                "variable_rate_rub": 0,
                "step_capacity": 5,
                "step_cost_rub": 500,
            }
        }
    )
    baseline = _line("DRILLING", line_id="base", physical={"drilling_m": 50, "base_drilling_productivity_m_h": 10})
    addition = _line("DRILLING", line_id="new", physical={"drilling_m": 100, "base_drilling_productivity_m_h": 10})
    result = calculate_scenario(_scenario(baseline=[baseline], candidate=[addition]), refs)
    assert result["before"]["totals"]["production_cost"] == 1000
    assert result["after"]["totals"]["production_cost"] == 1500
    rig = next(row for row in result["after"]["resource_utilization"] if row["resource_code"] == "DRILL_RIG_HOUR")
    assert rig["excess"] == 5


def test_subcontract_drilling_does_not_consume_own_rig_capacity() -> None:
    line = _line(
        "DRILLING",
        physical={"drilling_m": 100, "base_drilling_productivity_m_h": 10},
        overrides=[{"operation_code": "PRODUCTION_DRILLING", "executor": "SUBCONTRACTOR", "subcontract_rate_rub": 500}],
    )
    result = calculate_scenario(_scenario(candidate=[line]), _references())["after"]
    assert result["totals"]["project_direct_cost"] == 5000
    rig = next(row for row in result["resource_utilization"] if row["resource_code"] == "DRILL_RIG_HOUR")
    assert rig["demand"] == 0


def test_internal_warehouse_transfer_has_no_revenue() -> None:
    line = _line(
        "VM_WAREHOUSE_TRANSFER",
        billing_unit="KG",
        price=100,
        billed=1000,
        physical={"explosive_kg": 1000, "distance_km": 50},
        options={"internal_transfer": True},
    )
    result = calculate_scenario(_scenario(candidate=[line]), _references())["after"]
    assert result["totals"]["revenue_rub"] == 0


def test_oversize_breaking_uses_own_excavator_demand() -> None:
    line = _line("OVERSIZE_BREAKING", billing_unit="HOUR", billed=12, price=1000)
    result = calculate_scenario(_scenario(candidate=[line]), _references())["after"]
    excavator = next(row for row in result["resource_utilization"] if row["resource_code"] == "OWN_EXCAVATOR_HOUR")
    assert excavator["demand"] == 12


def test_price_below_full_cost_can_still_improve_unit_result() -> None:
    refs = _references(
        cost_rules=(
            ReferenceItem("VM", "ВМ", {"operation_code": "BULK_CHARGING_SZM", "behavior_type": "VARIABLE", "cost_layer": "variable", "driver": "explosive_kg", "rate_rub": 40}),
        ),
        resource_patches={"UNIT_AHP": {"fixed_cost_rub": 1000, "cost_layer": "full", "allocation_driver": "revenue"}},
    )
    addition = _line(
        "VM_IN_HOLE",
        billing_unit="KG",
        price=60,
        billed=10,
        physical={"explosive_kg": 10, "szm_hours": 1},
        options={"component_supply_mode": "PURCHASED_COMPONENTS"},
    )
    result = calculate_scenario(_scenario(candidate=[addition]), refs)
    assert result["after"]["totals"]["full_cost_margin"] == -800
    assert result["delta"]["totals"]["full_cost_margin"] == 200
    assert result["after"]["totals"]["contribution_margin"] == 200
