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


def test_cost_per_metre_matches_the_drilling_lines() -> None:
    """Цена метра на вкладке должна совпадать со структурой затрат."""

    context = _context()
    norms = drilling.compute(context)

    assert norms is not None
    lines = sum(
        (line.amount_rub for line in context.lines if line.cost_item_code.startswith("DRILL_")),
        Decimal("0"),
    )
    per_metre = lines / context.value("drilling_m")
    assert round(context.value("drilling_rub_per_m"), 6) == round(per_metre, 6)
    assert norms.cost_rub_per_m == context.value("drilling_rub_per_m")


def test_missing_condition_names_the_rig_and_the_reference_section() -> None:
    """Сметчик должен понять, какую запись завести, а не только что бурение нулевое."""

    context = ModelContext(fx.references(drilling_conditions=()), fx.parameters(), fx.physical())
    drilling.compute(context)

    warning = next(text for text in context.warnings if "Бурение не рассчитано" in text)
    assert "RIG_JK830" in warning
    assert "«Условия бурения»" in warning


def test_breakdown_values_are_exposed_as_natural_drivers() -> None:
    """Разложение метра на вкладке собирается из натуральных величин — без второго расчёта."""

    context = _context()
    drilling.compute(context)

    assert context.value("drilling_tech_speed_m_per_h") == Decimal("12")
    assert context.value("v_commercial_m_per_shift") == Decimal("120")
    assert context.value("drilling_rub_per_m") == (
        context.value("drilling_variable_rub_per_m") + context.value("drilling_fixed_rub_per_m")
    )
    assert context.lineage["drilling_condition"].startswith("drilling_conditions.")


def test_asset_without_depreciable_value_warns_instead_of_silent_zero() -> None:
    """Единица есть, но стоимости в ней нет: постоянная часть метра молча нулевая."""

    assets = (
        fx.item("ASSET_EMPTY", "JK830 Б-01", {"equipment_type_code": "RIG_JK830", "inventory_number": "Б-01"}),
    )
    context = ModelContext(fx.references(equipment_assets=assets), fx.parameters(), fx.physical())
    drilling.compute(context)

    assert not [line for line in context.lines if line.cost_item_code == "DRILL_DEPRECIATION"]
    assert any(
        "ASSET_EMPTY" in warning and "стоимость" in warning.lower() for warning in context.warnings
    ), context.warnings
