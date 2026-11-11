"""Охраняемые объекты: «вне зоны / В ЗОНЕ» по четырём типам (решение владельца В11).

Требуемое расстояние по типу: люди — зона для людей; здания — наибольшее из
сейсмики и УВВ; сооружения (ЛЭП, дороги, трубопроводы) — наибольшее из зоны
механизмов и сейсмики; механизмы — зона механизмов. Расстояние до объекта в
PR 1 задаёт вызывающий; по ситуации карьера его посчитает PR 2. Лечебные и
детские учреждения ближе зоны для зданий — ошибка `expert_required` (п. 808).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from design.safety import SafetyIssue, num

__all__ = ["OBJECT_KINDS", "ObjectAssessment", "ProtectedObject", "assess_objects"]

OBJECT_KINDS = ("people", "buildings", "structures", "mechanisms")
OBJECT_KIND_LABELS = {"people": "люди", "buildings": "здания", "structures": "сооружения", "mechanisms": "механизмы"}
INSIDE = "В ЗОНЕ"
OUTSIDE = "вне зоны"


@dataclass(frozen=True)
class ProtectedObject:
    name: str
    kind: str
    distance_m: float
    # Лечебное или детское учреждение, здание с большой площадью застекления (п. 808).
    sensitive: bool = False


@dataclass(frozen=True)
class ObjectAssessment:
    name: str
    kind: str
    distance_m: float
    required_m: float
    factor: str
    position: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "distance_m": self.distance_m,
            "required_m": self.required_m,
            "factor": self.factor,
            "position": self.position,
        }


def assess_objects(
    objects: Sequence[ProtectedObject],
    *,
    people_m: float,
    mechanisms_m: float,
    seismic_m: float,
    airblast_m: float,
) -> tuple[list[ObjectAssessment], list[SafetyIssue]]:
    required = {
        "people": (people_m, "люди"),
        "buildings": max((seismic_m, "сейсмика"), (airblast_m, "УВВ")),
        "structures": max((mechanisms_m, "механизмы"), (seismic_m, "сейсмика")),
        "mechanisms": (mechanisms_m, "механизмы"),
    }
    rows: list[ObjectAssessment] = []
    issues: list[SafetyIssue] = []
    for item in objects:
        if item.kind not in required:
            issues.append(
                SafetyIssue("error", "object_kind_unknown", f"«{item.name}»: тип объекта не из списка (люди, здания, сооружения, механизмы).")
            )
            continue
        need, factor = required[item.kind]
        position = INSIDE if item.distance_m < need else OUTSIDE
        rows.append(ObjectAssessment(item.name, item.kind, item.distance_m, need, factor, position))
        buildings_m = max(seismic_m, airblast_m)
        if item.sensitive and item.distance_m < buildings_m:
            issues.append(
                SafetyIssue(
                    "error",
                    "expert_required",
                    f"«{item.name}» ({num(item.distance_m)} м) — лечебное или детское учреждение ближе "
                    f"{num(buildings_m)} м: безопасные расстояния определяет экспертная организация (п. 808).",
                )
            )
    return rows, issues
