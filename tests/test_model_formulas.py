"""Формулу строки сметы читает сметчик: служебных имён в ней быть не должно.

Коды драйверов (`vm_tkm`), записей справочников (`PR_EVERSIN`) и ссылки
«раздел.код» — внутренняя кухня модели. Тест проходит по всем строкам
нескольких типичных расчётов, чтобы новая статья не принесла код обратно.
"""
from __future__ import annotations

import re

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

REMOTE_RATES = fx.item(
    "RATES_REMOTE",
    "Ставки с вахтой",
    {"per_diem_rub": "700", "lodging_rub": "1500", "shift_hours": "11"},
)

SCENARIOS = {
    # Все разделы сметы: номенклатура, патроны со склада, эмульсия, вахта.
    "full": (
        {"cartridge_kg": 2200, "bulk_kg": 39800},
        {"nomenclature": NOMENCLATURE, "emulsion_truck_code": "TRUCK_EMULSION_20T"},
    ),
    # ВМ считают правила затрат, а не выбранная номенклатура.
    "rules_only": ({}, {}),
    "subcontract": ({}, {"drilling_executor": "SUBCONTRACTOR"}),
    "vm_in_hole": ({}, {"package_code": "VM_IN_HOLE"}),
}

# Латинский идентификатор с подчёркиванием или точкой: `vm_tkm`,
# `PR_EVERSIN`, `material_prices.PR_EVERSIN`, `crew_shifts.POS_BLASTER`.
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[_.][A-Za-z0-9]+)+")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def service_names(formula: str, known: set[str]) -> set[str]:
    """Служебные имена в формуле; однословные (`holes`) ловит словарь известных."""

    found = set(IDENTIFIER.findall(formula))
    found |= set(LATIN_WORD.findall(formula)) & known
    return found


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_formulas_show_no_service_names(scenario: str) -> None:
    drivers, params = SCENARIOS[scenario]
    references = fx.references(organization_rates=(REMOTE_RATES,))
    result = compute_block_economics(
        {"physical": fx.physical(**drivers), "lineage": {}},
        fx.parameters(**params),
        references,
    )

    known = set(result.natural.values) | {
        item.code for items in references.sections.values() for item in items
    }
    leaks = {
        line.cost_item_code: sorted(names)
        for line in result.lines
        if (names := service_names(line.formula, known))
    }
    assert result.lines
    assert leaks == {}
