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
from cost.v2.models import ReferenceSnapshot
from cost.v2.payroll_defaults import (
    DOWNTIME_REASONS,
    DRILLER_SCALE,
    EXTRA_TARIFFS,
    HARDNESS_BANDS,
    PAYROLL_PARAMS,
)
from tests import model_fixtures as fx

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


_DRILLING_POSITION = {
    "category": "DIRECT",
    "operation_code": "PRODUCTION_DRILLING",
    "department": "DRILLING_BLASTING",
    "pay_system": "PIECE_PROGRESSIVE",
    "work_conditions_class": "3.2",
    "hazard_pct": "0.04",
    "extra_vacation_days": "7",
    "night_hours_per_shift": "8",
    "output_source": "OWN_OUTPUT",
    "difficulty": "NORMALIZED_METERS",
}

PAYROLL_SECTIONS: dict[str, tuple] = {
    "payroll_params": (fx.item("PAYROLL_PARAMS_2026", "Параметры ФОТ 2026", PAYROLL_PARAMS),),
    "organization_rates": (
        fx.item(
            "ORG_RATES",
            "Ставки организации",
            {
                "income_tax_rate": "0.13",
                "social_contribution_rate": "0.15",
                "injury_insurance_rate": "0.021",
                "per_diem_rub": "700",
                "shift_hours": "11",
                "extra_tariffs": [dict(row) for row in EXTRA_TARIFFS],
            },
        ),
    ),
    "positions": (
        fx.item("P_DRILLER", "Машинист буровой установки", _DRILLING_POSITION),
        fx.item("P_ASSISTANT", "Помощник машиниста", _DRILLING_POSITION),
        fx.item(
            "P_STOREKEEPER",
            "Кладовщик",
            {"category": "INDIRECT", "department": "WAREHOUSE", "pay_system": "TIME_BONUS"},
        ),
    ),
    "labor_rates": (
        fx.item("LR_DRILLER", "Машинист", {"position_code": "P_DRILLER", "fixed_monthly_rub": "27093", **DRILLER_SCALE}),
        fx.item("LR_ASSISTANT", "Помощник", {"position_code": "P_ASSISTANT", "fixed_monthly_rub": "27093", **DRILLER_SCALE}),
    ),
    "sites": (fx.item("SITE_LOM", "Ломовское месторождение", {"is_remote": True}),),
    "rocks": (
        fx.item("ROCK_F10", "Порода f10", {"hardness_f": "10"}),
        fx.item("ROCK_F17", "Порода f17", {"hardness_f": "17"}),
        fx.item("ROCK_NO_F", "Порода без крепости", {}),
    ),
    "drilling_difficulty": (
        fx.item(
            "DD_MAIN",
            "Сложность бурения",
            {
                "hardness": [dict(band) for band in HARDNESS_BANDS],
                "diameter": [{"diameter_mm": format(d, "f"), "k": format(k, "f")} for d, k in DIAMETERS.items()],
            },
        ),
    ),
    "downtime_reasons": tuple(
        fx.item(code, name, {"excusable": excusable, "planned_maintenance": maintenance})
        for code, name, excusable, maintenance in DOWNTIME_REASONS
    ),
}


def payroll_references(**overrides: Any) -> ReferenceSnapshot:
    """Снимок с разделами методики ФОТ; любой раздел можно подменить."""

    return fx.references(**{**PAYROLL_SECTIONS, **overrides})
