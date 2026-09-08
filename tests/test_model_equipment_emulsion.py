"""Тягач с полуприцепом под эмульсию: рейсы из массы, амортизация по плановым сменам."""
from __future__ import annotations

from decimal import Decimal

from cost.model import equipment, labor, logistics
from cost.model.engine import compute_block_economics
from cost.model.inputs import CrewMember, ModelContext
from tests import model_fixtures as fx


def _context(**params) -> ModelContext:
    return ModelContext(fx.references(), fx.parameters(**params), fx.physical())


def _line(context: ModelContext, code: str):
    return next(row for row in context.lines if row.cost_item_code == code)


def test_emulsion_trips_and_shifts_come_from_bulk_mass_and_capacity() -> None:
    """42 т насыпных компонентов при 20 т на рейс — три рейса, три смены тягача."""

    context = _context(emulsion_truck_code="TRUCK_EMULSION_20T")
    logistics.compute(context)

    assert context.value("emulsion_trips") == Decimal("3")
    assert context.value("emulsion_shifts") == Decimal("3")
    fuel = _line(context, "EMULSION_TRUCK_FUEL")
    price_l = Decimal("52200") / Decimal("1176.47")
    # Плечо — от базы (пункт изготовления компонентов), туда и обратно.
    assert fuel.amount_rub == Decimal("3") * 220 * 2 * Decimal("0.5") * price_l


def test_missing_emulsion_truck_warns_but_keeps_tonne_kilometres() -> None:
    context = _context(emulsion_truck_code=None)
    logistics.compute(context)

    assert "emulsion_shifts" not in context.values
    assert context.value("component_tkm") == Decimal("42") * 220
    assert any("тягач" in text.lower() for text in context.warnings)


def test_manual_plan_shifts_override_the_reference_norm() -> None:
    """Норматив тягача 18 смен, сметчик задал 12: доля амортизации на смену растёт."""

    by_norm = _context(emulsion_truck_code="TRUCK_EMULSION_20T")
    logistics.compute(by_norm)
    equipment.compute(by_norm)

    manual = _context(
        emulsion_truck_code="TRUCK_EMULSION_20T",
        machine_plan_shifts={"TRUCK_EMULSION_20T": Decimal("12")},
    )
    logistics.compute(manual)
    equipment.compute(manual)

    norm_line = _line(by_norm, "EMULSION_TRUCK_DEPRECIATION")
    manual_line = _line(manual, "EMULSION_TRUCK_DEPRECIATION")
    assert norm_line.amount_rub == Decimal("9000000") / 60 / 18 * 3
    assert manual_line.amount_rub == Decimal("9000000") / 60 / 12 * 3
    assert "12 см" in manual_line.formula


def test_manual_plan_shifts_apply_to_szm_too() -> None:
    manual = _context(machine_plan_shifts={"SZM_12T": Decimal("10")})
    logistics.compute(manual)
    equipment.compute(manual)

    assert _line(manual, "SZM_DEPRECIATION").amount_rub == Decimal("12000000") / 60 / 10 * 4


def test_component_delivery_driver_works_the_emulsion_truck_shifts() -> None:
    """Водитель доставки компонентов ездит на тягаче, а не на доставщике патронов."""

    references = fx.references(
        positions=(
            *fx.POSITIONS,
            fx.item(
                "POS_EMULSION_DRIVER",
                "Водитель тягача",
                {"category": "DIRECT", "operation_code": "COMPONENT_DELIVERY", "norm_shifts_per_month": "21"},
            ),
        ),
        labor_rates=(
            *fx.LABOR_RATES,
            fx.item("LR_EMULSION", "Водитель тягача", {"position_code": "POS_EMULSION_DRIVER", "fixed_monthly_rub": "63000"}),
        ),
    )
    context = ModelContext(
        references,
        fx.parameters(
            emulsion_truck_code="TRUCK_EMULSION_20T",
            crew=(CrewMember("POS_EMULSION_DRIVER", Decimal("1")),),
        ),
        fx.physical(),
    )
    logistics.compute(context)
    labor.compute(context)

    driver = _line(context, "LABOR_POS_EMULSION_DRIVER")
    assert context.value("crew_shifts.POS_EMULSION_DRIVER") == Decimal("3")
    assert driver.amount_rub == Decimal("63000") / 21 * 3


def test_engine_reports_emulsion_truck_lines_and_keeps_the_round_trip() -> None:
    result = compute_block_economics(
        fx.snapshot(), fx.parameters(emulsion_truck_code="TRUCK_EMULSION_20T"), fx.references()
    )

    codes = {line.cost_item_code for line in result.lines}
    assert {"EMULSION_TRUCK_DEPRECIATION", "EMULSION_TRUCK_MAINTENANCE", "EMULSION_TRUCK_FUEL"} <= codes
    restored = result.natural.to_dict()
    assert restored["values"]["emulsion_trips"] == "3"


def test_explicit_zero_plan_shifts_is_respected() -> None:
    """Ноль в поле «Смен в месяц» — осознанный ввод, а не пустое значение.

    Пустое поле фронт убирает из machine_plan_shifts; ноль означает «плановой
    загрузки нет», и распределять по ней амортизацию нельзя.
    """

    context = _context(machine_plan_shifts={"SZM_12T": Decimal("0")})
    logistics.compute(context)
    equipment.compute(context)

    assert not [row for row in context.lines if row.cost_item_code == "SZM_DEPRECIATION"]
    assert any("плановые смены" in text.lower() for text in context.warnings), context.warnings


def test_depreciation_names_the_unit_and_its_shifts() -> None:
    """Строка называет единицу техники, а не только тип: несколько СЗМ отличают по инвентарному номеру."""

    assets = (
        fx.item(
            "ASSET_SZM",
            "СЗМ инв. 002",
            {
                "equipment_type_code": "SZM_12T",
                "inventory_number": "002",
                "initial_cost_rub": "12000000",
                "useful_life_months": "60",
            },
        ),
    )
    context = ModelContext(fx.references(equipment_assets=assets), fx.parameters(), fx.physical())
    logistics.compute(context)
    equipment.compute(context)

    line = _line(context, "SZM_DEPRECIATION")
    assert "инв. 002" in line.cost_item_name
    assert line.quantity == Decimal("4")
    assert line.unit == "см"


def test_depreciation_falls_back_to_the_type_name_without_an_asset_number() -> None:
    """Ни инвентарного, ни заводского номера — строка называет тип, а не пустоту."""

    assets = (
        fx.item(
            "ASSET_SZM",
            "СЗМ",
            {"equipment_type_code": "SZM_12T", "initial_cost_rub": "12000000", "useful_life_months": "60"},
        ),
    )
    context = ModelContext(fx.references(equipment_assets=assets), fx.parameters(), fx.physical())
    logistics.compute(context)
    equipment.compute(context)

    assert _line(context, "SZM_DEPRECIATION").cost_item_name == "Амортизация: СЗМ 12 т"
