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


def test_other_units_costs_never_reach_the_block() -> None:
    """Затрата чужого юнита к блоку не относится, даже если юнит объекта пуст."""

    other = fx.item(
        "UFC_OTHER",
        "База юнита UNIT_2",
        {
            "production_unit_code": "UNIT_2",
            "scope": "UNIT",
            "category": "FACILITY",
            "monthly_rub": "1000000",
        },
    )
    context = ModelContext(
        fx.references(unit_fixed_costs=(*fx.UNIT_FIXED_COSTS, other)),
        fx.parameters(),
        fx.physical(),
    )
    unit.compute(context)
    assert "UNIT_UFC_OTHER" not in {line.cost_item_code for line in context.lines}


def test_site_without_unit_takes_only_unbound_costs_and_warns() -> None:
    sites = tuple(
        fx.item(site.code, site.name, {k: v for k, v in site.payload.items() if k != "production_unit_code"})
        for site in fx.SITES
    )
    organization_cost = fx.item(
        "UFC_ORG", "Лицензии организации", {"scope": "ORGANIZATION", "category": "OTHER", "monthly_rub": "100000"}
    )
    context = ModelContext(
        fx.references(sites=sites, unit_fixed_costs=(*fx.UNIT_FIXED_COSTS, organization_cost)),
        fx.parameters(),
        fx.physical(),
    )
    unit.compute(context)

    codes = {line.cost_item_code for line in context.lines}
    assert "UNIT_UFC_ORG" in codes
    assert "UNIT_UFC_BASE" not in codes
    assert any("не указан производственный юнит" in warning for warning in context.warnings)
