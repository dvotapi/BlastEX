"""Справочники методики ФОТ для тестов: параметры файла «Расчёт заработной платы» 2026.

Ставки взносов — из файла (СФР 15 %, травматизм 2,1 %), а не умолчания
организации: регрессия по файлу передаёт их явно (решения, Т2).
"""
from __future__ import annotations

from decimal import Decimal

from cost.model.payroll import DifficultyTables, HardnessBand
from cost.v2.payroll_defaults import HARDNESS_BANDS

CENT = Decimal("0.01")

DIAMETERS = {
    Decimal("110"): Decimal("0.72"),
    Decimal("127"): Decimal("0.84"),
    Decimal("140"): Decimal("0.92"),
    Decimal("152"): Decimal("1"),
    Decimal("165"): Decimal("1.09"),
    Decimal("190"): Decimal("1.25"),
    Decimal("215"): Decimal("1.41"),
    Decimal("250"): Decimal("1.64"),
}
TABLES = DifficultyTables(
    hardness=tuple(
        HardnessBand(
            Decimal(band["f_from"]) if band["f_from"] else None,
            Decimal(band["f_to"]) if band["f_to"] else None,
            Decimal(band["k"]),
        )
        for band in HARDNESS_BANDS
    ),
    diameter=DIAMETERS,
    source="drilling_difficulty.DD_MAIN",
)


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT)
