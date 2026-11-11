"""Ударная воздушная волна: на застекление (пп. 803–807) и на здания (пп. 796–801).

Застекление. Эквивалентная масса Q_э — формулы (15)–(17) п. 804 с K_з (две
таблицы п. 803: по l_заб/d, без забойки — по l_св/d; ближайшая меньшая
точка, без интерполяции) и K_н наружных зарядов. При короткозамедленном
взрывании Q_э и N — по группе с наибольшим Q_э (п. 806); заряды с разницей
моментов меньше 10 мс — одна группа (решение владельца В1). r_в — формулы
(12)–(14) ФНП (решение В3): 65·∛Q_э² при Q_э ≤ 2 кг; 65·√Q_э при 2…1000 кг;
200·∛Q_э при 1000…5000 кг. Поправки: интервал между группами (п. 806),
IX группа ×1,5 / V группа ÷2 (п. 804), мороз ×1,5 (п. 807).

Здания и сооружения: формулы (10) r_в = K_в·∛Q и (11) r_в = k_в·√Q п. 796
(коэффициенты прил. 23 выбирает проект), поправки пп. 798–801. Без
охраняемых зданий раздел в проект не выводится.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from design.safety import SafetyIssue, SafetyValue, ceil_to, chain_by_time, num

__all__ = [
    "AirblastCharge",
    "AirblastGroup",
    "AirblastResult",
    "airblast_glazing",
    "airblast_groups",
    "airblast_on_buildings",
    "delay_factor",
    "kz_lookup",
    "qe_external",
    "rv_glazing",
]

# Заряд длиннее 12 своих диаметров считается по (17), короче — по (16).
LONG_CHARGE_DIAMETERS = 12.0
# Верхняя граница формулы (12), кг.
QE_MAX_KG = 5000.0


def kz_lookup(ratio: float, table: Sequence[tuple[float, float]]) -> float:
    """Коэффициент по таблице п. 803: ближайшая меньшая (или равная) точка."""

    points = sorted(table)
    value = points[0][1]
    for x, k in points:
        if ratio + 1e-9 >= x:
            value = k
    return value


@dataclass(frozen=True)
class AirblastCharge:
    """Скважинный заряд для Q_э: P, l_зар, d и K_з его скважины."""

    hole_id: str
    time_ms: float
    capacity_kg_m: float
    charge_length_m: float
    diameter_m: float
    kz: float
    kz_by_free: bool = False  # K_з по свободной части l_св/d — скважина без забойки

    @property
    def long(self) -> bool:
        return self.charge_length_m > LONG_CHARGE_DIAMETERS * self.diameter_m

    @property
    def qe_base(self) -> float:
        """12·P·d по (17) или P·l_зар по (16) — без K_з."""
        if self.long:
            return LONG_CHARGE_DIAMETERS * self.capacity_kg_m * self.diameter_m
        return self.capacity_kg_m * self.charge_length_m


@dataclass(frozen=True)
class AirblastGroup:
    charges: tuple[AirblastCharge, ...]

    @property
    def start_ms(self) -> float:
        return self.charges[0].time_ms

    @property
    def end_ms(self) -> float:
        return self.charges[-1].time_ms

    @property
    def kz(self) -> float:
        return max(charge.kz for charge in self.charges)

    @property
    def qe_kg(self) -> float:
        return self.kz * sum(charge.qe_base for charge in self.charges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_ms": round(self.start_ms, 3),
            "end_ms": round(self.end_ms, 3),
            "n": len(self.charges),
            "kz": self.kz,
            "qe_kg": round(self.qe_kg, 4),
        }


def airblast_groups(charges: Sequence[AirblastCharge], threshold_ms: float) -> list[AirblastGroup]:
    groups = chain_by_time(sorted(charges, key=lambda charge: charge.hole_id), lambda charge: charge.time_ms, threshold_ms)
    return [AirblastGroup(tuple(group)) for group in groups]


def delay_factor(groups: Sequence[AirblastGroup]) -> tuple[float, float | None]:
    """Поправка п. 806 по наименьшему интервалу между соседними группами.

    ≥ 50 мс — 1; 30–50 — 1,2; 20–30 — 1,5; 10–20 — 2. Одна группа — взрыв
    одновременный, поправки нет.
    """

    gaps = [later.start_ms - earlier.end_ms for earlier, later in zip(groups, groups[1:])]
    if not gaps:
        return 1.0, None
    gap = min(gaps)
    if gap >= 50:
        return 1.0, gap
    if gap >= 30:
        return 1.2, gap
    if gap >= 20:
        return 1.5, gap
    return 2.0, gap


def rv_glazing(qe_kg: float) -> tuple[float, str, str]:
    """r_в по (12)–(14), м: значение, формула, номер формулы."""

    if qe_kg <= 0:
        return 0.0, "r_в = 65·∛Q_э²", "(14)"
    if qe_kg <= 2.0:
        return 65.0 * qe_kg ** (2.0 / 3.0), "r_в = 65·∛Q_э²", "(14)"
    if qe_kg < 1000.0:
        return 65.0 * math.sqrt(qe_kg), "r_в = 65·√Q_э", "(13)"
    return 200.0 * qe_kg ** (1.0 / 3.0), "r_в = 200·∛Q_э", "(12)"


def qe_external(mass_kg: float, h_cover_m: float, h_charge_m: float, table: Sequence[tuple[float, float]]) -> float:
    """Формула (15): Q_э = K_н·Q для наружных зарядов, засыпанных грунтом."""

    ratio = h_cover_m / h_charge_m if h_charge_m > 0 else 0.0
    return kz_lookup(ratio, table) * mass_kg


@dataclass(frozen=True)
class AirblastResult:
    groups: tuple[AirblastGroup, ...]
    group: AirblastGroup | None
    kz: SafetyValue
    qe: SafetyValue
    factors: SafetyValue      # произведение поправок
    base: SafetyValue         # r_в по (12)–(14) без поправок
    calculated: SafetyValue   # с поправками
    accepted: SafetyValue     # вверх до 50 м
    issues: tuple[SafetyIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_count": len(self.groups),
            "group": self.group.to_dict() if self.group else None,
            "kz": self.kz.to_dict(),
            "qe": self.qe.to_dict(),
            "factors": self.factors.to_dict(),
            "base": self.base.to_dict(),
            "calculated": self.calculated.to_dict(),
            "accepted": self.accepted.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def airblast_glazing(
    groups: Sequence[AirblastGroup],
    *,
    rock_group_ix: bool,
    rock_group_v_reduce: bool,
    frost: bool,
    detcord_kg: float = 0.0,
    interval_unknown: bool = False,
) -> AirblastResult:
    """r_в на застекление по группе с наибольшим Q_э и поправкам пп. 804, 806, 807.

    `interval_unknown` — последняя группа без моментов (заряды не получают
    сигнал сети): интервал до неё неизвестен, поправка за замедление — 2,
    как при наименьшем интервале п. 806.
    """

    issues: list[SafetyIssue] = []
    group = max(groups, key=lambda item: item.qe_kg) if groups else None
    qe = (group.qe_kg if group else 0.0) + detcord_kg
    n = len(group.charges) if group else 0
    kz = group.kz if group else 0.0
    kinds = {charge.long for charge in group.charges} if group else set()
    if kinds == {True}:
        qe_formula, qe_basis = "Q_э = 12·P·d·K_з·N", "ФНП 494 п. 804, формула (17)"
    elif kinds == {False}:
        qe_formula, qe_basis = "Q_э = P·l_зар·K_з·N", "ФНП 494 п. 804, формула (16)"
    else:
        qe_formula, qe_basis = "Q_э = K_з·Σ(12·P·d | P·l_зар)", "ФНП 494 п. 804, формулы (16), (17)"
    qe_basis += "; группа с наибольшим Q_э — п. 806"
    if group and kinds == {True} and len({(c.capacity_kg_m, c.diameter_m) for c in group.charges}) == 1:
        sample = group.charges[0]
        qe_sub = (
            f"12·{num(sample.capacity_kg_m, 2)}·{num(sample.diameter_m, 3)}·{num(kz, 3)}·{n}"
            f" = {num(qe, 3)}"
        )
    else:
        qe_sub = f"K_з = {num(kz, 3)}, N = {n} → {num(qe, 3)}"
    if detcord_kg > 0:
        qe_formula += " + Q_ДШ"
        qe_basis += "; масса ДШ — п. 805"
        qe_sub += f" (в т. ч. ДШ {num(detcord_kg, 2)} кг)"
    if qe >= QE_MAX_KG:
        issues.append(
            SafetyIssue(
                "warning",
                "qe_out_of_range",
                f"Q_э = {num(qe)} кг — вне области формул (12)–(14) (до 5000 кг): r_в посчитан по (12).",
            )
        )

    base_r, rv_formula, rv_number = rv_glazing(qe)
    if interval_unknown and len(groups) > 1:
        delay, gap = 2.0, None
    else:
        delay, gap = delay_factor(groups)
    rock = 1.5 if rock_group_ix else 0.5 if rock_group_v_reduce else 1.0
    frost_k = 1.5 if frost else 1.0
    product = delay * rock * frost_k
    factor_parts = [
        f"замедление {num(delay, 1)}" + (
            f" (интервал {num(gap)} мс)" if gap is not None
            else " (интервал неизвестен)" if len(groups) > 1 else " (одна группа)"
        ),
        f"порода {num(rock, 1)}",
        f"мороз {num(frost_k, 1)}",
    ]
    factors = SafetyValue(
        product,
        "—",
        "K = K_замедл·K_порода·K_мороз",
        "; ".join(factor_parts) + f" → {num(product, 3)}",
        "ФНП 494 пп. 804, 806, 807",
    )
    r = base_r * product
    rounded = ceil_to(r)
    return AirblastResult(
        groups=tuple(groups),
        group=group,
        kz=SafetyValue(kz, "—", _kz_formula(group), f"K_з = {num(kz, 3)}", "ФНП 494 п. 804, таблица K_з"),
        qe=SafetyValue(qe, "кг", qe_formula, qe_sub, qe_basis),
        factors=factors,
        base=SafetyValue(base_r, "м", rv_formula, f"по Q_э = {num(qe, 3)} → {num(base_r, 1)}", f"ФНП 494 п. 804, формула {rv_number}"),
        calculated=SafetyValue(r, "м", f"{rv_formula}·K", f"{num(base_r, 1)}·{num(product, 3)} = {num(r)}", "ФНП 494 пп. 804, 806, 807"),
        accepted=SafetyValue(rounded, "м", "вверх до кратного 50 м", f"{num(r)} → {num(rounded)}", "принято проектом"),
        issues=tuple(issues),
    )


def _kz_formula(group: AirblastGroup | None) -> str:
    """По какой таблице п. 803 взят наибольший K_з группы."""

    if group is None:
        return "K_з по l_заб/d (п. 803)"
    worst = max(group.charges, key=lambda charge: charge.kz)
    return "K_з по l_св/d — без забойки (п. 803)" if worst.kz_by_free else "K_з по l_заб/d (п. 803)"


# Поправки пп. 798–801 к расстоянию по (10) / (11).
_BARRIER_BEHIND = {"10": 1.3, "11": 1.4}


def airblast_on_buildings(
    mass_kg: float,
    *,
    coefficient: float,
    formula: str,
    behind_barrier: bool = False,
    narrow_valley: bool = False,
    barrier_behind_blast: bool = False,
    covered: bool = False,
) -> SafetyValue:
    """r_в для зданий и сооружений, п. 796: (10) K_в·∛Q или (11) k_в·√Q.

    Коэффициент — из прил. 23 по степени допустимых повреждений, выбирает
    проект (п. 797). Поправки: объект за преградой — ÷2 (п. 798), узкая
    долина или улица — ×2 (п. 799), прочные преграды за местом взрыва — ×1,3
    к (10) и ×1,4 к (11) (п. 800), засыпка не менее пяти высот заряда — ÷4
    (п. 801а).
    """

    if formula not in _BARRIER_BEHIND:
        raise ValueError("формула (10) или (11)")
    if formula == "10":
        base = coefficient * mass_kg ** (1.0 / 3.0)
        text, sub = "r_в = K_в·∛Q", f"{num(coefficient, 1)}·∛{num(mass_kg)}"
    else:
        base = coefficient * math.sqrt(mass_kg)
        text, sub = "r_в = k_в·√Q", f"{num(coefficient, 1)}·√{num(mass_kg)}"
    factor, notes = 1.0, []
    for flag, k, note in (
        (behind_barrier, 0.5, "за преградой ÷2 (п. 798)"),
        (narrow_valley, 2.0, "узкая долина ×2 (п. 799)"),
        (barrier_behind_blast, _BARRIER_BEHIND[formula], f"преграды за местом взрыва ×{num(_BARRIER_BEHIND[formula], 1)} (п. 800)"),
        (covered, 0.25, "засыпка ÷4 (п. 801а)"),
    ):
        if flag:
            factor *= k
            notes.append(note)
    r = base * factor
    suffix = f"; {', '.join(notes)}" if notes else ""
    return SafetyValue(r, "м", text, f"{sub}·{num(factor, 2)} = {num(r)}", f"ФНП 494 п. 796, формула ({formula}){suffix}")
