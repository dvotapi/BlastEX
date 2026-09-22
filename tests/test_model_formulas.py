"""Формулу строки сметы читает сметчик: служебных имён и сырых чисел в ней нет.

Коды драйверов (`vm_tkm`), записей справочников (`PR_EVERSIN`) и ссылки
«раздел.код» — внутренняя кухня модели, а 28 знаков Decimal — шум. Тесты
проходят по всем строкам нескольких типичных расчётов, чтобы новая статья
не принесла ни код, ни сырое число обратно.
"""
from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal

import pytest

from cost.model.engine import compute_block_economics
from cost.model.inputs import ServiceCharge, formula_number
from tests import model_fixtures as fx

NOMENCLATURE = {
    "EXPLOSIVE": "MAT_EVERSIN",
    "BOOSTER": "MAT_BOOSTER",
    "NSI_DOWNHOLE": "MAT_NSI",
    "NSI_SURFACE": "MAT_NSI_SURFACE",
    "NSI_START": "MAT_NSI_START",
    "DETONATOR_ELECTRIC": "MAT_DETONATOR_EL",
}

REMOTE_RATES = fx.item(
    "RATES_REMOTE",
    "Ставки с вахтой",
    {"per_diem_rub": "700", "lodging_rub": "1500", "shift_hours": "11"},
)

SCENARIOS = {
    # Все разделы сметы: номенклатура с электродетонаторами, введёнными
    # вручную, патроны со склада, эмульсия, вахта, услуга с вкладки.
    "full": (
        {"cartridge_kg": 2200, "bulk_kg": 39800},
        {
            "nomenclature": NOMENCLATURE,
            "electric_detonators_qty": Decimal("10"),
            "emulsion_truck_code": "TRUCK_EMULSION_20T",
            "services": (ServiceCharge("Проживание бригады", Decimal("120000")),),
        },
    ),
    # ВМ считают правила затрат, а не выбранная номенклатура.
    "rules_only": ({}, {}),
    "subcontract": ({}, {"drilling_executor": "SUBCONTRACTOR"}),
    "vm_in_hole": ({}, {"package_code": "VM_IN_HOLE"}),
    # Ветки, которых нет в остальных сценариях: правило с постоянной частью и
    # ступенями, услуга за смену, ТОиР техники по месячному бюджету.
    "extras": (
        {},
        {"services": (ServiceCharge("Охрана буровой", Decimal("3500"), operation_code="PRODUCTION_DRILLING", per_shift=True),)},
    ),
}

STEP_RULE = fx.item(
    "RULE_STEMMING_STEPS",
    "Забойка со ступенями",
    {
        "operation_code": "STEMMING",
        "cost_item_code": "RULE_STEMMING_STEPS",
        "driver": "holes",
        "rate_rub": "0.5",
        "fixed_rub": "1000.5",
        "step_capacity": "700",
        "step_cost_rub": "250.25",
        "estimate_section": "EXPLOSIVES",
    },
)


def _budget_maintenance(item):
    if item.code != "SZM_12T":
        return item
    payload = {**item.payload, "maintenance_mode": "MONTHLY_BUDGET", "maintenance_monthly_rub": "33333.333"}
    return replace(item, payload=payload)


REFERENCE_OVERRIDES = {
    "extras": {
        "cost_rules": (*fx.COST_RULES, STEP_RULE),
        "equipment_types": tuple(_budget_maintenance(item) for item in fx.EQUIPMENT_TYPES),
    },
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


def compute(scenario: str):
    drivers, params = SCENARIOS[scenario]
    references = fx.references(
        organization_rates=(REMOTE_RATES,), **REFERENCE_OVERRIDES.get(scenario, {})
    )
    result = compute_block_economics(
        {"physical": fx.physical(**drivers), "lineage": {}},
        fx.parameters(**params),
        references,
    )
    return result, references


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_formulas_show_no_service_names(scenario: str) -> None:
    result, references = compute(scenario)

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


# --- числа ------------------------------------------------------------------

NBSP = "\u00a0"


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("474166.6666666666666666666667", "474 166,67"),
        ("132.5581395340000000000000000", "132,56"),
        ("42000", "42 000"),
        ("4800", "4 800"),
        ("594.0", "594"),
        ("48.9", "48,9"),
        ("4.1666667", "4,17"),
        ("0.3042", "0,3042"),
        ("0.45", "0,45"),
        ("0.123456", "0,1235"),
        ("0.00012345", "0,0001235"),
        ("0.99996", "1"),
        ("0", "0"),
        ("0E-10", "0"),
        ("1E+3", "1 000"),
        ("-1234.5", "-1 234,5"),
        # Ровно посередине — от нуля, как Intl в колонках, а не к чётному.
        ("2.345", "2,35"),
        ("0.12345", "0,1235"),
        (3, "3"),
        # Больше 28 знаков вместе с сотыми: общий контекст Decimal их не вмещает.
        ("1E+26", "100 000 000 000 000 000 000 000 000"),
        ("123456789012345678901234567.891", "123 456 789 012 345 678 901 234 567,89"),
    ],
)
def test_formula_number_reads_like_the_columns(value: str, text: str) -> None:
    """Как колонки «Кол-во» и «Цена» (Intl ru-RU): запятая, разряды через
    неразрывный пробел, не больше двух знаков; меньше единицы — четыре значащих."""

    assert formula_number(Decimal(value)) == text.replace(" ", NBSP)


def test_formula_number_does_not_break_the_calculation_on_a_non_finite_value() -> None:
    """Формула — пояснение: странное число показывается как есть, расчёт не падает."""

    assert formula_number(Decimal("Infinity")) == "Infinity"
    assert formula_number(Decimal("NaN")) == "NaN"


DATE = re.compile(r"\d{2}\.\d{2}\.\d{4}")
RAW_NUMBER = re.compile(
    "|".join(
        (
            r"\d\.\d",  # точка вместо запятой
            r"\d[eE][+-]?\d",  # экспонента Decimal
            r"(?<![\d,])\d{4,}",  # тысячи без разрядов
            rf"(?<![\d,{NBSP}])[1-9][\d{NBSP}]*,\d{{3,}}",  # больше двух знаков у числа от единицы
            rf"(?<![\d{NBSP}])0,0*[1-9]\d{{4,}}",  # больше четырёх значащих у дроби
        )
    )
)


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_formula_numbers_read_like_the_columns(scenario: str) -> None:
    result, _ = compute(scenario)

    raw = {
        line.cost_item_code: line.formula
        for line in result.lines
        if RAW_NUMBER.search(DATE.sub("", line.formula))
    }
    assert result.lines
    assert raw == {}
