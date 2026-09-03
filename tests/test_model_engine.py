from decimal import Decimal

from cost.model import sensitivity
from cost.model.engine import compute_block_economics
from cost.v2.models import CostLayer
from tests import model_fixtures as fx


def _compute(**params):
    return compute_block_economics(fx.snapshot(), fx.parameters(**params), fx.references())


def test_layers_accumulate_and_prices_follow_markup_chain() -> None:
    result = _compute()

    totals = result.layer_totals
    assert totals[CostLayer.VARIABLE] < totals[CostLayer.PROJECT_DIRECT]
    assert totals[CostLayer.PROJECT_DIRECT] < totals[CostLayer.PRODUCTION]

    prices = result.price_per_m3
    assert prices["marginal"] == totals[CostLayer.PROJECT_DIRECT] / Decimal("60000")
    assert prices["full"] == totals[CostLayer.FULL] / Decimal("60000")
    expected_price = totals[CostLayer.FULL] * Decimal("1.1") * Decimal("1.1") / Decimal("60000")
    assert prices["with_margin"] == expected_price
    assert round(prices["with_vat"], 6) == round(expected_price * Decimal("1.2"), 6)


def test_lower_unit_plan_raises_full_price_and_leaves_marginal_alone() -> None:
    base = _compute()
    loaded_less = _compute(unit_plan_volume_m3=Decimal("400000"))

    assert loaded_less.price_per_m3["full"] > base.price_per_m3["full"]
    assert loaded_less.price_per_m3["marginal"] == base.price_per_m3["marginal"]


def test_cost_rules_price_the_natural_drivers() -> None:
    result = _compute()

    explosive = next(line for line in result.lines if line.cost_item_code == "MATERIAL_EXPLOSIVE")
    assert explosive.amount_rub == Decimal("42000") * 45
    assert explosive.layer is CostLayer.VARIABLE


def test_vm_in_hole_package_has_neither_drilling_nor_blasters() -> None:
    result = _compute(package_code="VM_IN_HOLE")

    codes = {line.cost_item_code for line in result.lines}
    assert not [code for code in codes if code.startswith("DRILL_")]
    assert "LABOR_POS_BLASTER" not in codes
    assert not [
        warning
        for warning in result.warnings
        if "бурен" in warning.lower() or "POS_BLASTER" in warning
    ]


def test_natural_drivers_carry_lineage() -> None:
    result = _compute()

    natural = result.natural
    assert natural.values["rig_shifts"] > 0
    assert "м/ч" in natural.lineage["v_commercial_m_per_shift"]
    assert natural.lineage["drilling_condition"].startswith("drilling_conditions.COND_GRANITE")


def test_subcontracted_drilling_shows_unallocated_rig_fixed_costs() -> None:
    result = _compute(drilling_executor="SUBCONTRACTOR")

    codes = {line.cost_item_code for line in result.lines}
    assert "DRILL_SUBCONTRACT" in codes
    assert "DRILL_UNALLOCATED_FIXED" in codes
    # Бригада подрядчика уже в ставке за метр: свой ФОТ бурения не начисляется.
    assert "LABOR_POS_DRILLER" not in codes
    assert _compute().price_per_m3["marginal"] != result.price_per_m3["marginal"]


def test_missing_references_produce_warnings_not_exceptions() -> None:
    references = fx.references(
        drilling_conditions=(), labor_rates=(), unit_fixed_costs=(), cost_rules=()
    )
    result = compute_block_economics(fx.snapshot(), fx.parameters(), references)

    assert result.warnings
    assert result.price_per_m3["full"] >= 0


def test_sensitivity_is_sorted_by_absolute_effect() -> None:
    rows = sensitivity.compute(fx.snapshot(), fx.parameters(), fx.references())

    codes = {row.code for row in rows}
    assert codes == {code for code, _, _ in sensitivity.PARAMETERS}
    deltas = [abs(row.delta) for row in rows]
    assert deltas == sorted(deltas, reverse=True)
    assert any(row.delta != 0 for row in rows)


def test_sensitivity_of_unit_plan_lowers_price_when_plan_grows() -> None:
    rows = {row.code: row for row in sensitivity.compute(fx.snapshot(), fx.parameters(), fx.references())}

    plan = rows["UNIT_PLAN_VOLUME"]
    assert plan.price_plus < plan.base_price < plan.price_minus
