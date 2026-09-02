from decimal import Decimal

from cost.model import unit
from cost.model.inputs import ModelContext
from tests import model_fixtures as fx


def _context(**params) -> ModelContext:
    return ModelContext(fx.references(), fx.parameters(**params), fx.physical())


def _line(context: ModelContext, code: str):
    return next(item for item in context.lines if item.cost_item_code == code)


def test_share_is_block_volume_over_unit_plan() -> None:
    context = _context()
    unit.compute(context)

    assert context.value("unit_allocation_share") == Decimal("0.1")
    assert _line(context, "UNIT_UFC_BASE").amount_rub == Decimal("400000") * Decimal("0.1")


def test_indirect_labour_is_built_from_rates_with_contributions() -> None:
    context = _context()
    unit.compute(context)

    accrued = Decimal("40000")
    contributions = accrued * Decimal("0.3042")
    monthly = accrued + contributions + (accrued + contributions) * Decimal("0.20")
    assert _line(context, "UNIT_UFC_WH_HEAD").amount_rub == monthly * Decimal("0.1")


def test_lower_unit_plan_raises_the_allocated_share() -> None:
    high = _context()
    low = _context(unit_plan_volume_m3=Decimal("400000"))
    unit.compute(high)
    unit.compute(low)

    assert _line(low, "UNIT_UFC_BASE").amount_rub > _line(high, "UNIT_UFC_BASE").amount_rub


def test_warehouse_area_steps_up_and_warns() -> None:
    """1 224 НСИ на блок при плане в десять блоков — 41 м² вместо десяти."""

    context = _context()
    unit.compute(context)

    assert context.value("warehouse_area_m2") == Decimal("41")
    rent = _line(context, "UNIT_WAREHOUSE_RENT").amount_rub
    monthly = Decimal("83333") + Decimal("31") * Decimal("8333")
    assert rent == monthly * Decimal("0.1")
    assert context.capacity[0].required == Decimal("41")
    assert "41" in context.capacity[0].message


def test_missing_unit_plan_warns_and_allocates_nothing() -> None:
    context = _context(unit_plan_volume_m3=Decimal("0"))
    unit.compute(context)

    assert context.lines == []
    assert any("плановый объём юнита" in warning for warning in context.warnings)
