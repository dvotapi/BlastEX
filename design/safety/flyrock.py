"""Разлёт отдельных кусков породы: пп. 784–786 и прил. 21 ФНП 494.

Формула (1): r_разл = 1250·η_з·√(f/(1 + η_заб)·d/a).
Для серии зарядов одного диаметра с переменными параметрами расчёт идёт по
наименьшим η_заб и a и наибольшим η_з и f серии (п. 784, решение владельца
В2) — это не максимум r по скважинам. По скважинам r_разл считается для
таблицы параметров. Рельеф — формулы (2)–(4) п. 785.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from design.safety import SafetyIssue, SafetyValue, num

__all__ = ["FlyrockResult", "flyrock_r", "flyrock_series", "relief_factor"]

FLYROCK_FORMULA = "r_разл = 1250·η_з·√(f/(1 + η_заб)·d/a)"
BASIS_FLYROCK = "ФНП 494 п. 784, формула (1)"
# Порог превышения блока над границей опасной зоны, п. 785.
RELIEF_HEIGHT_LIMIT_M = 30.0


def flyrock_r(eta_charge: float, eta_stemming: float, hardness_f: float, diameter_m: float, distance_m: float) -> float:
    """Формула (1) п. 784, м."""

    if distance_m <= 0 or diameter_m <= 0 or hardness_f <= 0:
        return 0.0
    return 1250.0 * eta_charge * math.sqrt(hardness_f / (1.0 + eta_stemming) * diameter_m / distance_m)


def _substitution(eta_charge: float, eta_stemming: float, f: float, d: float, a: float, r: float) -> str:
    return (
        f"1250·{num(eta_charge, 3)}·√({num(f, 1 if f % 1 else 0)}/(1 + {num(eta_stemming, 2)})·"
        f"{num(d, 3)}/{num(a, 2)}) = {num(r)}"
    )


@dataclass(frozen=True)
class FlyrockResult:
    """Разлёт по серии: расчёт, поправка на рельеф и вклад каждого параметра."""

    series: SafetyValue           # r_разл серии по формуле (1)
    relief: SafetyValue           # K_р
    with_relief: SafetyValue      # R_разл = r·K_р
    eta_charge: float
    eta_stemming: float
    hardness_f: float
    diameter_m: float
    distance_m: float
    per_hole: dict[str, float]    # r_разл по скважине (для таблицы параметров)
    issues: tuple[SafetyIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": self.series.to_dict(),
            "relief": self.relief.to_dict(),
            "with_relief": self.with_relief.to_dict(),
            "eta_charge": round(self.eta_charge, 4),
            "eta_stemming": round(self.eta_stemming, 4),
            "hardness_f": self.hardness_f,
            "diameter_m": round(self.diameter_m, 4),
            "distance_m": round(self.distance_m, 3),
            "per_hole": {key: round(value, 1) for key, value in self.per_hole.items()},
            "issues": [issue.to_dict() for issue in self.issues],
        }


def relief_factor(
    r_m: float,
    *,
    relief_height_m: float | None,
    slope_angle_deg: float | None,
) -> tuple[SafetyValue, list[SafetyIssue]]:
    """K_р по п. 785: (3) — косогор, (4) — превышение более 30 м; иначе 1.

    Задано и то и другое — берётся большее. Ничего не задано — K_р = 1 и
    предупреждение `relief_unknown`: проект не знает, нужен ли учёт рельефа.
    """

    issues: list[SafetyIssue] = []
    candidates: list[SafetyValue] = []
    if slope_angle_deg is not None and slope_angle_deg > 0:
        k = 1.0 + math.tan(math.radians(slope_angle_deg))
        candidates.append(
            SafetyValue(k, "—", "K_р = 1 + tg β", f"1 + tg {num(slope_angle_deg, 1)}° = {num(k, 2)}", "ФНП 494 п. 785, формула (3)", "REFERENCE")
        )
    if relief_height_m is not None and relief_height_m > RELIEF_HEIGHT_LIMIT_M and r_m > 0:
        k = 0.5 * (1.0 + math.sqrt(1.0 + 4.0 * relief_height_m / r_m))
        candidates.append(
            SafetyValue(
                k,
                "—",
                "K_р = 0,5·(1 + √(1 + 4H/r_разл))",
                f"0,5·(1 + √(1 + 4·{num(relief_height_m, 1)}/{num(r_m)})) = {num(k, 2)}",
                "ФНП 494 п. 785, формула (4)",
                "REFERENCE",
            )
        )
    if candidates:
        return max(candidates, key=lambda item: item.value or 0.0), issues
    if relief_height_m is None and slope_angle_deg is None:
        issues.append(
            SafetyIssue(
                "warning",
                "relief_unknown",
                "Не заданы ни угол косогора, ни превышение блока над границей опасной зоны: рельеф (п. 785) не учтён.",
            )
        )
        return SafetyValue(1.0, "—", "K_р = 1", "рельеф не задан", "ФНП 494 п. 785", "REFERENCE"), issues
    return SafetyValue(1.0, "—", "K_р = 1", "косогора нет, превышение не более 30 м", "ФНП 494 п. 785", "REFERENCE"), issues


def flyrock_series(
    holes: Sequence[Any],
    *,
    hardness_f: float,
    relief_height_m: float | None = None,
    slope_angle_deg: float | None = None,
) -> FlyrockResult:
    """Разлёт по серии скважин (`SafetyHole` или любые объекты с теми же свойствами)."""

    issues: list[SafetyIssue] = []
    usable = [hole for hole in holes if hole.distance_m is not None]
    if len(usable) < len(holes):
        issues.append(
            SafetyIssue(
                "warning",
                "flyrock_distance_unknown",
                f"У {len(holes) - len(usable)} скв. нет соседей в ряду и между рядами: в серию для разлёта они "
                "не вошли.",
            )
        )
    per_hole = {
        hole.hole_id: flyrock_r(hole.eta_charge, hole.eta_stemming, hardness_f, hole.diameter_m, hole.distance_m)
        for hole in usable
    }
    if not usable:
        empty = SafetyValue(None, "м", FLYROCK_FORMULA, "нет скважин с зарядом и соседями", BASIS_FLYROCK)
        relief, relief_issues = relief_factor(0.0, relief_height_m=relief_height_m, slope_angle_deg=slope_angle_deg)
        return FlyrockResult(empty, relief, empty, 0.0, 0.0, hardness_f, 0.0, 0.0, {}, tuple(issues + relief_issues))

    eta_charge = max(hole.eta_charge for hole in usable)
    eta_stemming = min(hole.eta_stemming for hole in usable)
    distance = min(hole.distance_m for hole in usable)
    diameters = {round(hole.diameter_m, 4) for hole in usable}
    diameter = max(diameters)
    if len(diameters) > 1:
        issues.append(
            SafetyIssue(
                "warning",
                "flyrock_mixed_diameter",
                "В серии скважины разного диаметра: разлёт посчитан по наибольшему диаметру.",
            )
        )
    r = flyrock_r(eta_charge, eta_stemming, hardness_f, diameter, distance)
    series = SafetyValue(
        r,
        "м",
        FLYROCK_FORMULA,
        _substitution(eta_charge, eta_stemming, hardness_f, diameter, distance, r),
        f"{BASIS_FLYROCK}; серия — наименьшие η_заб и a, наибольшие η_з и f",
    )
    relief, relief_issues = relief_factor(r, relief_height_m=relief_height_m, slope_angle_deg=slope_angle_deg)
    issues.extend(relief_issues)
    k = relief.value or 1.0
    with_relief = SafetyValue(
        r * k,
        "м",
        "R_разл = r_разл·K_р",
        f"{num(r)}·{num(k, 2)} = {num(r * k)}",
        "ФНП 494 п. 785, формула (2)",
    )
    return FlyrockResult(series, relief, with_relief, eta_charge, eta_stemming, hardness_f, diameter, distance, per_hole, tuple(issues))
