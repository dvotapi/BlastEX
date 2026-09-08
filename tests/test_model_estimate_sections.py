"""Раздел бумажной сметы у строки затрат: сметчик ищет строку глазами по нему."""
from __future__ import annotations

from decimal import Decimal

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
