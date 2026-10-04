"""Справочники методики ФОТ для тестов: параметры файла «Расчёт заработной платы» 2026.

Ставки взносов — из файла (СФР 15 %, травматизм 2,1 %), а не умолчания
организации: регрессия по файлу передаёт их явно (решения, Т2).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from cost.model.payroll import (
    DifficultyTables,
    DowntimeReason,
    HardnessBand,
    PayrollCalendar,
    PayrollInputs,
    PayrollRates,
    PositionPay,
    Scale,
    SiteSchedule,
)
from cost.v2.payroll_defaults import DOWNTIME_REASONS, EXTRA_TARIFFS, HARDNESS_BANDS

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


CURVE_X = Scale(
    "CURVE_POWER",
    norm_per_shift=Decimal("115.3846"),
    rate_norm=Decimal("45"),
    ceiling_per_shift=Decimal("184.6154"),
    rate_ceiling=Decimal("168.66"),
)

REASONS = {code: DowntimeReason(code, name, excusable, maintenance) for code, name, excusable, maintenance in DOWNTIME_REASONS}


def file_inputs(**position_overrides: Any) -> PayrollInputs:
    """Машинист из файла: МРОТ, класс 3.2, вредность 4 %, доп. отпуск 7 дн, 8 ночных часов."""

    position = {
        "code": "P_DRILLER",
        "name": "Машинист буровой установки",
        "salary": Decimal("27093"),
        "salary_source": "labor_rates.LR_DRILLER",
        "week_hours": 40,
        "work_conditions_class": "3.2",
        "hazard_pct": Decimal("0.04"),
        "night_hours_per_shift": Decimal("8"),
        "extra_vacation_days": Decimal("7"),
        "pay_system": "PIECE_PROGRESSIVE",
        "difficulty": "NORMALIZED_METERS",
        "scale": CURVE_X,
    }
    position.update(position_overrides)
    return PayrollInputs(
        calendar=PayrollCalendar(
            year=2026,
            mrot=Decimal("27093"),
            annual_hours_40=Decimal("1972"),
            annual_hours_36=Decimal("1774.4"),
            work_days_year=Decimal("247"),
            holidays_year=Decimal("14"),
            night_pct=Decimal("0.20"),
            vacation_days_base=Decimal("28"),
            margin_share_warn=Decimal("0.70"),
        ),
        position=PositionPay(**position),
        site=SiteSchedule(code="SITE_LOM", name="Ломовское месторождение"),
        rates=PayrollRates(
            ndfl_rate=Decimal("0.13"),
            sfr_rate=Decimal("0.15"),
            injury_rate=Decimal("0.021"),
            shift_allowance_per_day=Decimal("700"),
            shift_hours=Decimal("11"),
            extra_tariffs={row["work_conditions_class"]: Decimal(row["rate"]) for row in EXTRA_TARIFFS},
        ),
    )
