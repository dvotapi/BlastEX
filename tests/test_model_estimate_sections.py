"""Раздел бумажной сметы у строки затрат: сметчик ищет строку глазами по нему."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.engine import compute_block_economics
from tests import model_fixtures as fx

NOMENCLATURE = {
    "EXPLOSIVE": "MAT_EVERSIN",
    "BOOSTER": "MAT_BOOSTER",
    "NSI_DOWNHOLE": "MAT_NSI",
    "NSI_SURFACE": "MAT_NSI_SURFACE",
    "NSI_START": "MAT_NSI_START",
}


def compute(**params):
    """Блок со всеми разделами сметы: патроны едут со склада, объект вахтовый."""

    rates = fx.item(
        "RATES_REMOTE",
        "Ставки с вахтой",
        {"per_diem_rub": "700", "lodging_rub": "1500", "shift_hours": "11"},
    )
    return compute_block_economics(
        {"physical": fx.physical(cartridge_kg=2200, bulk_kg=39800), "lineage": {}},
        fx.parameters(nomenclature=NOMENCLATURE, emulsion_truck_code="TRUCK_EMULSION_20T", **params),
        fx.references(organization_rates=(rates,)),
    )


def sections_by_code(result) -> dict[str, str]:
    return {line.cost_item_code: line.section for line in result.lines}


def test_every_line_names_its_estimate_section() -> None:
    result = compute()
    sections = sections_by_code(result)

    assert sections["MATERIAL_EXPLOSIVE"] == "EXPLOSIVES"
    assert sections["MATERIAL_NSI_DOWNHOLE"] == "EXPLOSIVES"
    assert sections["DRILL_TOOLING"] == "DRILLING"
    assert sections["DRILL_FUEL"] == "DRILLING"
    assert sections["DRILL_DEPRECIATION"] == "DRILLING"
    assert sections["VM_DELIVERY"] == "VM_LOGISTICS"
    assert sections["MOBILIZATION"] == "VM_LOGISTICS"
    assert sections["LABOR_POS_BLASTER"] == "LABOR"
    assert sections["LABOR_CONTRIBUTIONS"] == "LABOR"
    assert sections["SZM_FUEL"] == "FUEL"
    assert sections["EMULSION_TRUCK_FUEL"] == "FUEL"
    assert sections["SZM_DEPRECIATION"] == "DEPRECIATION"
    assert sections["SZM_MAINTENANCE"] == "OVERHEAD"
    assert all(line.section for line in result.lines)


def test_per_diem_is_its_own_section() -> None:
    """Суточные и проживание — отдельный раздел сметы, а не часть ФОТ."""

    result = compute()

    per_diem = next(line for line in result.lines if line.cost_item_code == "LABOR_PER_DIEM")
    assert per_diem.section == "PER_DIEM"


def test_unit_fixed_costs_go_to_overhead() -> None:
    result = compute()
    unit_lines = [line for line in result.lines if line.cost_item_code.startswith("UNIT_")]

    assert unit_lines
    assert {line.section for line in unit_lines} == {"OVERHEAD"}


def test_cost_rule_names_its_section_and_falls_back_to_overhead() -> None:
    plain = fx.item(
        "RULE_PLAIN",
        "Прочее по скважинам",
        {"operation_code": "STEMMING", "cost_item_code": "RULE_PLAIN", "driver": "holes", "rate_rub": "60"},
    )
    stemming = fx.item(
        "RULE_STEMMING",
        "Забойка скважин",
        {
            "operation_code": "STEMMING",
            "cost_item_code": "RULE_STEMMING",
            "driver": "holes",
            "rate_rub": "60",
            "estimate_section": "EXPLOSIVES",
        },
    )
    result = compute_block_economics(
        fx.snapshot(), fx.parameters(), fx.references(cost_rules=(plain, stemming))
    )

    sections = sections_by_code(result)
    assert sections["RULE_PLAIN"] == "OVERHEAD"
    assert sections["RULE_STEMMING"] == "EXPLOSIVES"


def test_service_line_carries_the_section_of_its_layer() -> None:
    from cost.model.inputs import ServiceCharge

    result = compute_block_economics(
        fx.snapshot(),
        fx.parameters(
            services=(ServiceCharge("Проживание бригады", Decimal("120000"), "project_direct", "BLAST_EXECUTION"),)
        ),
        fx.references(),
    )

    service = next(line for line in result.lines if line.cost_item_name == "Проживание бригады")
    assert service.section == "OVERHEAD"


def test_section_survives_serialisation() -> None:
    result = compute()

    row = next(item for item in result.to_dict()["lines"] if item["cost_item_code"] == "MATERIAL_EXPLOSIVE")
    assert row["section"] == "EXPLOSIVES"


# --- количество, единица и цена -------------------------------------------


def line_by_code(result, code: str):
    return next(row for row in result.lines if row.cost_item_code == code)


def test_material_line_carries_quantity_unit_and_price() -> None:
    result = compute()

    line = line_by_code(result, "MATERIAL_EXPLOSIVE")
    assert line.unit == "кг"
    assert line.unit_price_rub == Decimal("48.9")
    assert line.quantity * line.unit_price_rub == line.amount_rub


def test_booster_quantity_is_in_the_units_of_its_price() -> None:
    """Паспорт считает боевики штуками, справочник хранит цену килограмма."""

    result = compute()

    line = line_by_code(result, "MATERIAL_BOOSTER")
    assert line.unit == "кг"
    assert line.quantity == Decimal("1224") * Decimal("0.8")
    assert line.quantity * line.unit_price_rub == line.amount_rub


def test_drilling_line_counts_metres_and_fuel_counts_litres() -> None:
    result = compute()

    fuel = line_by_code(result, "DRILL_FUEL")
    assert fuel.unit == "л"
    assert fuel.quantity == result.natural.get("drilling_fuel_l")
    assert fuel.quantity * fuel.unit_price_rub == fuel.amount_rub


def test_depreciation_counts_shifts_with_a_rate_per_shift() -> None:
    result = compute()

    line = line_by_code(result, "SZM_DEPRECIATION")
    assert line.unit == "см"
    assert line.quantity == result.natural.get("szm_shifts")
    assert line.quantity * line.unit_price_rub == line.amount_rub


def test_labor_counts_person_shifts_without_a_unit_price() -> None:
    """У ФОТ цена за единицу теряет смысл: оклад, сделка и НДФЛ дают разную ставку."""

    result = compute()

    line = line_by_code(result, "LABOR_POS_BLASTER")
    assert line.unit == "чел·см"
    assert line.quantity > 0
    assert line.unit_price_rub is None


def test_lines_without_a_countable_quantity_leave_it_empty() -> None:
    """Доля постоянных затрат юнита — не количество: единицы у неё нет."""

    result = compute()

    line = next(row for row in result.lines if row.cost_item_code.startswith("UNIT_"))
    assert line.quantity is None
    assert line.unit == ""
    assert line.unit_price_rub is None


def test_quantity_and_price_survive_serialisation() -> None:
    result = compute()

    row = next(item for item in result.to_dict()["lines"] if item["cost_item_code"] == "MATERIAL_EXPLOSIVE")
    assert row["unit"] == "кг"
    # Роль ВВ считает всю массу заряда, а не только насыпную часть.
    assert row["quantity"] == pytest.approx(42000.0)
    assert row["unit_price_rub"] == pytest.approx(48.9)


def test_cost_rule_line_shows_its_driver_and_rate() -> None:
    """Правило «цена × драйвер» — ровно та строка, где норма и цена очевидны."""

    result = compute()

    delivery = line_by_code(result, "VM_DELIVERY")
    assert delivery.unit == "vm_tkm"
    assert delivery.quantity == result.natural.get("vm_tkm")
    assert delivery.unit_price_rub == Decimal("25")
    assert delivery.quantity * delivery.unit_price_rub == delivery.amount_rub


def test_maintenance_counts_shifts_with_its_rate() -> None:
    result = compute()

    drilling_toir = line_by_code(result, "DRILL_MAINTENANCE")
    assert drilling_toir.unit == "см"
    assert drilling_toir.quantity > 0
    assert drilling_toir.unit_price_rub == Decimal("750")

    szm_toir = line_by_code(result, "SZM_MAINTENANCE")
    assert szm_toir.unit_price_rub == Decimal("500")
