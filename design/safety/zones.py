"""Сводка опасных зон: пп. 779, 783, 786 ФНП 494.

Люди — наибольшее по факторам, опасным для людей: разлёт с рельефом,
вверх до 50 м, не меньше прил. 21 (скважинные заряды — 200 м, на косогоре
вниз по склону — 300 м). Механизмы — доля зоны людей, вверх до 50 м,
«принято проектом» (п. 779 расстояние для механизмов не задаёт). Здания —
наибольшее из сейсмики и УВВ. Ручной ввод — только `MANUAL_OVERRIDE` с
причиной и не меньше расчётного.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from design.safety import SafetyIssue, SafetyValue, ceil_to, num

__all__ = ["SLOPE_PEOPLE_MIN_M", "Zones", "apply_manual", "danger_zones"]

# Прил. 21, п. 1.5: скважинные заряды — не менее 200 м, на косогоре вниз по
# склону — не менее 300 м. Пол 200 м действует при любом параметре объекта.
PEOPLE_MIN_FNP_M = 200.0
SLOPE_PEOPLE_MIN_M = 300.0
ZONE_LABELS = {"people": "для людей", "mechanisms": "для механизмов", "buildings": "для зданий и сооружений"}


@dataclass(frozen=True)
class Zones:
    people: SafetyValue
    people_factor: str          # определяющий фактор: «разлёт» или «прил. 21»
    mechanisms: SafetyValue
    buildings: SafetyValue
    buildings_factor: str       # «сейсмика» или «УВВ»
    issues: tuple[SafetyIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "people": self.people.to_dict(),
            "people_factor": self.people_factor,
            "mechanisms": self.mechanisms.to_dict(),
            "buildings": self.buildings.to_dict(),
            "buildings_factor": self.buildings_factor,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def apply_manual(kind: str, calculated: SafetyValue, manual: tuple[float, str] | None) -> tuple[SafetyValue, list[SafetyIssue]]:
    """Ручное значение зоны: с причиной и не меньше расчётного, иначе — ошибка и расчётное."""

    if manual is None:
        return calculated, []
    value, reason = float(manual[0]), str(manual[1] or "").strip()
    label = ZONE_LABELS.get(kind, kind)
    if not reason:
        return calculated, [
            SafetyIssue("error", "manual_reason_missing", f"Опасная зона {label} задана вручную без причины: принята расчётная.")
        ]
    if calculated.value is not None and value < calculated.value:
        return calculated, [
            SafetyIssue(
                "error",
                "manual_below_calculated",
                f"Опасная зона {label} {num(value)} м меньше расчётной {num(calculated.value)} м: принята расчётная.",
            )
        ]
    return (
        SafetyValue(value, "м", calculated.formula, f"задано вручную: {reason}", calculated.basis, "MANUAL_OVERRIDE"),
        [],
    )


def danger_zones(
    *,
    flyrock_m: float | None,
    people_min_m: float,
    on_slope: bool,
    k_mech: float,
    seismic_m: float | None,
    airblast_m: float | None,
    manual: dict[str, tuple[float, str]] | None = None,
) -> Zones:
    """Зоны по принятым расстояниям факторов (уже вверх до 50 м у r_с и r_в)."""

    manual = manual or {}
    issues: list[SafetyIssue] = []
    minimum = max(people_min_m, PEOPLE_MIN_FNP_M, SLOPE_PEOPLE_MIN_M if on_slope else 0.0)
    rounded = ceil_to(flyrock_m) if flyrock_m else 0.0
    if rounded >= minimum:
        people_value, factor = rounded, "разлёт"
        sub = f"{num(flyrock_m or 0)} → {num(rounded)} (не меньше {num(minimum)} по прил. 21)"
    else:
        people_value, factor = minimum, "прил. 21"
        sub = f"разлёт {num(flyrock_m or 0)} → {num(rounded)} меньше минимума прил. 21 — {num(minimum)}"
    people = SafetyValue(
        people_value,
        "м",
        "max(⌈R_разл⌉₅₀; минимум прил. 21)",
        sub,
        "ФНП 494 пп. 779, 783, 786, прил. 21",
    )
    people, manual_issues = apply_manual("people", people, manual.get("people"))
    issues.extend(manual_issues)

    # Доля зоны людей — до целого метра, затем вверх до 50: 0,667 значит
    # «две трети», и 0,667·750 = 500,25 не должно давать 550 м.
    mech_raw = round(k_mech * (people.value or 0.0))
    mechanisms = SafetyValue(
        ceil_to(mech_raw),
        "м",
        "⌈k_мех·зона людей⌉₅₀",
        f"{num(k_mech, 3)}·{num(people.value or 0)} = {num(mech_raw)} → {num(ceil_to(mech_raw))}",
        "принято проектом (п. 779)",
    )
    mechanisms, manual_issues = apply_manual("mechanisms", mechanisms, manual.get("mechanisms"))
    issues.extend(manual_issues)

    seismic, airblast = seismic_m or 0.0, airblast_m or 0.0
    buildings_factor = "сейсмика" if seismic >= airblast else "УВВ"
    buildings = SafetyValue(
        max(seismic, airblast),
        "м",
        "max(r_с; r_в)",
        f"max({num(seismic)}; {num(airblast)}) = {num(max(seismic, airblast))}",
        "ФНП 494 пп. 779, 794, 804",
    )
    buildings, manual_issues = apply_manual("buildings", buildings, manual.get("buildings"))
    issues.extend(manual_issues)
    return Zones(people, factor, mechanisms, buildings, buildings_factor, tuple(issues))
