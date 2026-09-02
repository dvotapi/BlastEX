from decimal import Decimal

from cost.model import drilling
from cost.model.inputs import ModelContext
from tests import model_fixtures as fx


def _context(**params):
    return ModelContext(fx.references(), fx.parameters(**params), fx.physical())


def test_commercial_speed_and_rig_shifts() -> None:
    """12 м/ч при смене 11 ч и часе простоя дают 120 м за смену."""

    context = _context()
    norms = drilling.compute(context)

    assert norms is not None
    assert norms.v_commercial_m_per_shift == Decimal("120")
    assert context.value("rig_shifts") == context.value("drilling_m") / Decimal("120")
    assert round(float(context.value("rig_shifts")), 1) == 116.3
    assert norms.plan_metres == Decimal("4800")


def test_condition_picked_by_rock_and_recorded_in_lineage() -> None:
    context = _context()
    drilling.compute(context)

    assert context.lineage["drilling_condition"].startswith("drilling_conditions.COND_GRANITE")


def test_condition_falls_back_to_rig_default() -> None:
    """Нет нормы на породе блока — берётся норма станка по умолчанию."""

    references = fx.references(rocks=(fx.item("ROCK_OTHER", "Известняк", {}),))
    sites = tuple(
        fx.item(site.code, site.name, {**site.payload, "rock_code": "ROCK_OTHER"})
        for site in references.sections["sites"]
    )
    references = fx.references(rocks=references.sections["rocks"], sites=sites)
    context = ModelContext(references, fx.parameters(), fx.physical())
    norms = drilling.compute(context)

    assert norms is not None
    assert context.lineage["drilling_condition"].startswith("drilling_conditions.COND_DEFAULT")
    assert norms.v_commercial_m_per_shift == Decimal("100")


def test_rig_without_condition_gives_warning_and_zero_lines() -> None:
    context = ModelContext(
        fx.references(drilling_conditions=()), fx.parameters(), fx.physical()
    )
    assert drilling.compute(context) is None
    assert context.value("rig_shifts") == 0
    assert any("Бурение не рассчитано" in warning for warning in context.warnings)
    assert not [line for line in context.lines if line.cost_item_code.startswith("DRILL_")]


def test_fixed_part_per_metre_grows_when_plan_shifts_drop() -> None:
    """40 → 25 плановых смен: постоянная часть метра растёт на 60 %."""

    at_40 = drilling.compute(_context(rig_plan_shifts=Decimal("40")))
    at_25 = drilling.compute(_context(rig_plan_shifts=Decimal("25")))

    assert at_40 is not None and at_25 is not None
    growth = at_25.fixed_rub_per_m / at_40.fixed_rub_per_m
    assert round(float(growth), 3) == 1.6


def test_subcontractor_replaces_drilling_with_single_rate() -> None:
    context = _context(drilling_executor="SUBCONTRACTOR")
    drilling.compute(context)

    codes = {line.cost_item_code for line in context.lines}
    assert "DRILL_SUBCONTRACT" in codes
    assert "DRILL_TOOLING" not in codes
    assert "DRILL_UNALLOCATED_FIXED" in codes
    assert any("субподряде" in warning for warning in context.warnings)


def test_drilling_absent_from_package_produces_nothing() -> None:
    context = ModelContext(
        fx.references(), fx.parameters(package_code="VM_IN_HOLE"), fx.physical()
    )
    assert drilling.compute(context) is None
    assert context.lines == []
    assert context.warnings == []
