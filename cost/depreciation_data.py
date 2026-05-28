"""Справочник норм амортизации основных средств."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable


def format_rub_amount(value: float | int | str | None, *, decimals: int = 0) -> str:
    """Формат суммы в рублях с разделителем разрядов (пробел)."""
    if value is None or value == "":
        return ""
    num = float(value)
    sign = "-" if num < 0 else ""
    num = abs(num)
    if decimals == 0:
        digits = str(int(round(num)))
    else:
        rounded = round(num, decimals)
        int_part, dec_part = f"{rounded:.{decimals}f}".split(".")
        grouped_int = _group_digits(int_part)
        return f"{sign}{grouped_int},{dec_part}"
    return f"{sign}{_group_digits(digits)}"


def parse_rub_amount(value: float | int | str | None) -> float:
    """Разбор суммы из числа или строки с пробелами/запятой."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    negative = text.startswith("-")
    cleaned = text.lstrip("-").replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    if not cleaned:
        return 0.0
    result = float(cleaned)
    return -result if negative else result


def _group_digits(digits: str) -> str:
    parts: list[str] = []
    while digits:
        parts.append(digits[-3:])
        digits = digits[:-3]
    return " ".join(reversed(parts))


@dataclass(frozen=True)
class FixedAssetDepreciation:
    """Норма амортизации ОС для сметных расчётов."""

    name: str
    initial_cost_rub: float
    useful_life_months: float
    productive_shifts_per_month: float
    depreciation_per_shift_rub: float

    @property
    def calculated_depreciation_per_shift_rub(self) -> float:
        return calculate_depreciation_per_shift_rub(
            self.initial_cost_rub,
            self.useful_life_months,
            self.productive_shifts_per_month,
        )


def calculate_depreciation_per_shift_rub(
    initial_cost_rub: float,
    useful_life_months: float,
    productive_shifts_per_month: float,
) -> float:
    """Норма амортизации = первоначальная стоимость ÷ СПИ ÷ смен в месяц."""
    if useful_life_months <= 0 or productive_shifts_per_month <= 0:
        return 0.0
    return initial_cost_rub / useful_life_months / productive_shifts_per_month


def _default_asset(
    name: str,
    depreciation_per_shift_rub: float,
    *,
    useful_life_months: float = 84.0,
    productive_shifts_per_month: float = 22.0,
) -> FixedAssetDepreciation:
    initial_cost = depreciation_per_shift_rub * useful_life_months * productive_shifts_per_month
    return FixedAssetDepreciation(
        name=name,
        initial_cost_rub=initial_cost,
        useful_life_months=useful_life_months,
        productive_shifts_per_month=productive_shifts_per_month,
        depreciation_per_shift_rub=depreciation_per_shift_rub,
    )


DEFAULT_DEPRECIATION_ASSETS: tuple[FixedAssetDepreciation, ...] = (
    _default_asset("Soosan JD-2000", 14_250.0),
    _default_asset("ZEGA D480A", 12_500.0),
    _default_asset("JK 830-3", 11_854.166666666668),
    _default_asset("TM255-T", 7_500.0),
    _default_asset("УРБ-2А2 + компрессор", 3_541.6666666666665),
    _default_asset("УРБ-2А2 + компрессор (2)", 2_291.666666666667),
)


def depreciation_assets_to_records(assets: Iterable[FixedAssetDepreciation]) -> list[dict]:
    return [asdict(asset) for asset in assets]


def depreciation_assets_from_records(records: list[dict]) -> list[FixedAssetDepreciation]:
    assets: list[FixedAssetDepreciation] = []
    for row in records:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        initial_cost_rub = parse_rub_amount(row.get("initial_cost_rub", 0))
        useful_life_months = float(row.get("useful_life_months", 0) or 0)
        productive_shifts_per_month = float(row.get("productive_shifts_per_month", 0) or 0)
        assets.append(
            FixedAssetDepreciation(
                name=name,
                initial_cost_rub=initial_cost_rub,
                useful_life_months=useful_life_months,
                productive_shifts_per_month=productive_shifts_per_month,
                depreciation_per_shift_rub=calculate_depreciation_per_shift_rub(
                    initial_cost_rub,
                    useful_life_months,
                    productive_shifts_per_month,
                ),
            )
        )
    return assets


def find_depreciation_asset(
    name: str,
    assets: Iterable[FixedAssetDepreciation] | None = None,
) -> FixedAssetDepreciation | None:
    source = assets if assets is not None else DEFAULT_DEPRECIATION_ASSETS
    for asset in source:
        if asset.name == name:
            return asset
    return None
