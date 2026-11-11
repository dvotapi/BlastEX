"""Сейсмически безопасное расстояние: пп. 792–795 ФНП 494.

Заряды — по моментам срабатывания сети BlastEX (`resolve_network`). Группа
зарядов с замедлением между ними меньше 20 мс — один заряд с общей массой,
N — число групп (п. 794, решение владельца В1). Соседние моменты разнесены
меньше порога — одна группа, поэтому внутри группы интервалы меньше порога,
а между группами — не меньше: разбиение однозначно.

r_с = K_г·K_с·α·∛Q/⁴√N — формула (8); одна группа — формула (5).
Q — ВВ и ПД (решение В4). Правило п. 794 «можно не учитывать заряды в 3 раза
и более меньше максимального» — расчёт с ним и без него, принимается
большее. Повреждения зданий — не менее ×2 (п. 795).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from design.safety import SafetyValue, ceil_to, num

__all__ = ["Charge", "DelayGroup", "SeismicResult", "delay_groups", "seismic_r", "seismic_safety"]

# Правило п. 794: заряд в 3 раза и более меньше максимального можно не учитывать.
SMALL_CHARGE_RATIO = 3.0


@dataclass(frozen=True)
class Charge:
    """Заряд со своим моментом срабатывания: дека, а у проекта без дек — скважина."""

    hole_id: str
    time_ms: float
    mass_kg: float


@dataclass(frozen=True)
class DelayGroup:
    """Заряды, разнесённые меньше порога: при расчёте — один заряд."""

    start_ms: float | None  # None — заряды без момента (не получают сигнал сети)
    end_ms: float | None
    charges: tuple[Charge, ...]

    @property
    def mass_kg(self) -> float:
        return sum(charge.mass_kg for charge in self.charges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_ms": None if self.start_ms is None else round(self.start_ms, 3),
            "end_ms": None if self.end_ms is None else round(self.end_ms, 3),
            "charge_count": len(self.charges),
            "mass_kg": round(self.mass_kg, 3),
            "hole_ids": sorted({charge.hole_id for charge in self.charges}),
        }


def delay_groups(charges: Sequence[Charge], threshold_ms: float) -> list[DelayGroup]:
    """Разбить заряды на группы: соседние по времени ближе `threshold_ms` — в одной."""

    ordered = sorted(charges, key=lambda charge: (charge.time_ms, charge.hole_id))
    groups: list[list[Charge]] = []
    for charge in ordered:
        if groups and charge.time_ms - groups[-1][-1].time_ms < threshold_ms:
            groups[-1].append(charge)
        else:
            groups.append([charge])
    return [DelayGroup(group[0].time_ms, group[-1].time_ms, tuple(group)) for group in groups]


def seismic_r(q_kg: float, n: int, k_ground: float, k_structure: float, alpha: float) -> float:
    """Формула (8): K_г·K_с·α·∛Q/⁴√N; при N = 1 — формула (5)."""

    if q_kg <= 0 or n <= 0:
        return 0.0
    return k_ground * k_structure * alpha * q_kg ** (1.0 / 3.0) / n ** 0.25


@dataclass(frozen=True)
class SeismicVariant:
    """Один вариант Q и N: все группы или без малых по правилу п. 794."""

    rule: str        # "all" | "small_dropped"
    q_kg: float
    n: int
    r_m: float

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "q_kg": round(self.q_kg, 3), "n": self.n, "r_m": round(self.r_m, 2)}


@dataclass(frozen=True)
class SeismicResult:
    groups: tuple[DelayGroup, ...]
    variants: tuple[SeismicVariant, ...]
    chosen: SeismicVariant
    calculated: SafetyValue   # r_с принятого варианта с ×2 п. 795
    accepted: SafetyValue     # вверх до 50 м

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": [group.to_dict() for group in self.groups],
            "group_count": len(self.groups),
            "variants": [variant.to_dict() for variant in self.variants],
            "chosen": self.chosen.to_dict(),
            "calculated": self.calculated.to_dict(),
            "accepted": self.accepted.to_dict(),
        }


def seismic_safety(
    groups: Sequence[DelayGroup],
    *,
    k_ground: float,
    k_structure: float,
    alpha: float,
    buildings_damaged: bool = False,
) -> SeismicResult:
    """r_с по группам. Варианты «все группы» и «без малых» — принимается больший."""

    masses = [group.mass_kg for group in groups if group.mass_kg > 0]
    variants = [SeismicVariant("all", sum(masses), len(masses), seismic_r(sum(masses), len(masses), k_ground, k_structure, alpha))]
    if masses:
        limit = max(masses) / SMALL_CHARGE_RATIO
        kept = [mass for mass in masses if mass > limit]
        if len(kept) < len(masses):
            variants.append(
                SeismicVariant("small_dropped", sum(kept), len(kept), seismic_r(sum(kept), len(kept), k_ground, k_structure, alpha))
            )
    chosen = max(variants, key=lambda item: item.r_m)
    factor = 2.0 if buildings_damaged else 1.0
    r = chosen.r_m * factor
    single = chosen.n == 1
    formula = "r_с = K_г·K_с·α·∛Q" if single else "r_с = K_г·K_с·α·∛Q/⁴√N"
    head = (
        f"{num(k_ground, 1 if k_ground % 1 else 0)}·{num(k_structure, 1 if k_structure % 1 else 0)}·"
        f"{num(alpha, 1 if alpha % 1 else 0)}·∛{num(chosen.q_kg)}"
    )
    substitution = head if single else f"{head}/⁴√{chosen.n}"
    basis = "ФНП 494 п. 792, формула (5)" if single else "ФНП 494 п. 794, формула (8)"
    if chosen.rule == "small_dropped":
        basis += "; заряды в 3 раза и более меньше максимального не учтены"
    if buildings_damaged:
        formula += "·2"
        substitution += "·2"
        basis += "; п. 795 — повреждения зданий, ×2"
    calculated = SafetyValue(r, "м", formula, f"{substitution} = {num(r)}", basis, "CALCULATED")
    rounded = ceil_to(r)
    accepted = SafetyValue(
        rounded,
        "м",
        "вверх до кратного 50 м",
        f"{num(r)} → {num(rounded)}",
        "принято проектом",
    )
    return SeismicResult(tuple(groups), tuple(variants), chosen, calculated, accepted)
