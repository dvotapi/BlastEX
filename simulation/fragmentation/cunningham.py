"""Kuz-Ram по Каннингему для подбора удельного расхода на листе «Расчёт».

Формулы — C. V. B. Cunningham, «The Kuz-Ram fragmentation model — 20 years
on», EFEE 2005: фактор породы A = 0,06·(RMD + RDI + HF), средний кусок по
Кузнецову с показателем 19/20 (или 19/30, вариант 1983 года), индекс
равномерности n по варианту 1987 года с диаметром в миллиметрах.

Модуль применяется только к подбору q в Blast.py. Прогнозы вкладки
«Проектирование» по-прежнему считает simulation.fragmentation.kuzram.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from simulation.fragmentation.distributions import (
    rosin_rammler_characteristic_mm,
    rosin_rammler_oversize_pct,
)
from simulation.fragmentation.units import fragment_mm_from_cm

MODEL_VERSION = "kuzram-cunningham-1.0"

ROCK_FACTOR_METHODS = ("rmd50", "rmd10", "joint_factor", "manual")
JOINT_CONDITIONS = (1.0, 1.5, 2.0)
JOINT_ANGLES = (20, 30, 40)
STRENGTH_EXPONENTS = {"19/20": 19.0 / 20.0, "19/30": 19.0 / 30.0}

# Поле настроек → (нижняя граница, верхняя граница, подпись в сообщении).
NUMERIC_BOUNDS: dict[str, tuple[float, float, str]] = {
    "rock_factor_manual": (0.5, 30.0, "Фактор породы A"),
    "rock_factor_correction": (0.1, 10.0, "Поправка C(A)"),
    "drill_deviation_m": (0.0, 2.0, "Отклонение бурения σ, м"),
    "uniformity_correction": (0.5, 2.0, "Поправка C(n)"),
    "q_max_kg_m3": (0.5, 5.0, "Верхняя граница перебора q, кг/м³"),
}

Q_MIN_KG_M3 = 0.10
MIN_UNIFORMITY_N = 0.1
RMD_MASSIVE = 50.0
RMD_FRIABLE = 10.0
# Один заряд в скважине: множитель (|BCL − CCL|/L + 0,1)^0,1 при BCL = 0.
SINGLE_CHARGE_FACTOR = 1.1 ** 0.1


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


@dataclass(frozen=True)
class KuzRamSettings:
    """Настройки модели; умолчания — монолитный массив без поправок."""

    rock_factor_method: str = "rmd50"
    rock_factor_manual: float = 6.0
    joint_condition: float = 1.0
    joint_angle: int = 20
    rock_factor_correction: float = 1.0
    strength_exponent: str = "19/20"
    drill_deviation_m: float = 0.0
    uniformity_correction: float = 1.0
    q_max_kg_m3: float = 2.0

    def __post_init__(self) -> None:
        if self.rock_factor_method not in ROCK_FACTOR_METHODS:
            raise ValueError(f"Неизвестный способ расчёта фактора породы: {self.rock_factor_method}.")
        if self.strength_exponent not in STRENGTH_EXPONENTS:
            raise ValueError("Показатель при силе ВВ — 19/20 или 19/30.")
        if float(self.joint_condition) not in JOINT_CONDITIONS:
            raise ValueError("Состояние трещин JCF — 1; 1,5 или 2.")
        if float(self.joint_angle) not in JOINT_ANGLES:
            raise ValueError("Ориентация трещин JPA — 20, 30 или 40.")
        for name, (low, high, label) in NUMERIC_BOUNDS.items():
            value = float(getattr(self, name))
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{label} — от {_number(low)} до {_number(high)}.")

    @property
    def exponent(self) -> float:
        return STRENGTH_EXPONENTS[self.strength_exponent]


@dataclass(frozen=True)
class RockFactorBreakdown:
    """Состав фактора породы A: слагаемые, сумма до поправки и поправка C(A)."""

    method: str
    rmd: float | None
    rdi: float | None
    hf: float | None
    joint_spacing_m: float | None
    reduced_pattern_m: float | None
    jps: float | None
    base: float
    correction: float

    @property
    def value(self) -> float:
        return self.base * self.correction


def joint_plane_spacing_factor(joint_spacing_m: float, reduced_pattern_m: float) -> float:
    """JPS по Каннингему 2005: шаг трещин относительно приведённой сетки P."""
    if joint_spacing_m < 0.1:
        return 10.0
    if joint_spacing_m < 0.3:
        return 20.0
    if joint_spacing_m < 0.95 * reduced_pattern_m:
        return 80.0
    return 50.0


def rock_factor(
    settings: KuzRamSettings,
    *,
    ucs_mpa: float,
    density_t_m3: float,
    fissuring_per_m: float,
    burden_m: float,
    spacing_m: float,
) -> RockFactorBreakdown:
    """A = 0,06·(RMD + RDI + HF)·C(A); при ручном вводе A = заданное·C(A).

    RDI = 25·ρ − 50 (ρ в т/м³), HF = UCS/5 (модуля упругости в данных нет).
    Для трещиноватого массива RMD заменяет JF = JCF·JPS + JPA; без трещин —
    монолитный массив.
    """
    correction = float(settings.rock_factor_correction)
    if settings.rock_factor_method == "manual":
        return RockFactorBreakdown(
            "manual", None, None, None, None, None, None, float(settings.rock_factor_manual), correction
        )
    rdi = 25.0 * density_t_m3 - 50.0
    hf = ucs_mpa / 5.0
    joint_spacing = reduced_pattern = jps = None
    if settings.rock_factor_method == "rmd10":
        rmd = RMD_FRIABLE
    elif settings.rock_factor_method == "joint_factor" and fissuring_per_m > 0:
        joint_spacing = 1.0 / fissuring_per_m
        reduced_pattern = math.sqrt(burden_m * spacing_m)
        jps = joint_plane_spacing_factor(joint_spacing, reduced_pattern)
        rmd = float(settings.joint_condition) * jps + float(settings.joint_angle)
    else:
        rmd = RMD_MASSIVE
    base = 0.06 * (rmd + rdi + hf)
    if base * correction <= 0:
        raise ValueError(
            f"Фактор породы A = {_number(round(base * correction, 2))} — он должен быть больше нуля. "
            f"При плотности {_number(density_t_m3)} т/м³ и UCS {_number(ucs_mpa)} МПа выбранный способ даёт A ≤ 0: "
            "выберите монолитный массив (RMD 50), способ по трещиноватости или задайте A вручную."
        )
    return RockFactorBreakdown(
        settings.rock_factor_method, rmd, rdi, hf, joint_spacing, reduced_pattern, jps,
        base, correction,
    )


def mean_fragment_mm(
    rock_factor_a: float,
    powder_factor_kg_m3: float,
    charge_mass_kg: float,
    re_weight: float,
    exponent: float,
) -> float:
    """x50 = A·q^−0,8·Q^(1/6)·RE^(−e): формула даёт сантиметры, результат — мм."""
    x50_cm = (
        rock_factor_a
        * powder_factor_kg_m3 ** -0.8
        * charge_mass_kg ** (1.0 / 6.0)
        * re_weight ** (-exponent)
    )
    return fragment_mm_from_cm(x50_cm)


@dataclass(frozen=True)
class Uniformity:
    """Индекс равномерности: по формуле, принятый (не ниже 0,1) и L/H."""

    raw: float
    value: float
    charge_to_bench: float


def uniformity_index(
    *,
    burden_m: float,
    hole_diameter_mm: float,
    spacing_to_burden: float,
    drill_deviation_m: float,
    charge_length_m: float,
    bench_height_m: float,
    correction: float,
) -> Uniformity:
    """n = (2,2 − 14·W/d)·√((1 + a/W)/2)·(1 − σ/W)·1,1^0,1·(L/H)·C(n).

    W, σ, L, H — метры, d — миллиметры (Каннингем 1987). L/H не больше 1.
    """
    charge_to_bench = min(1.0, charge_length_m / bench_height_m)
    raw = (
        (2.2 - 14.0 * burden_m / hole_diameter_mm)
        * math.sqrt((1.0 + spacing_to_burden) / 2.0)
        # Не даём отклонению бурения сделать множитель отрицательным: иначе
        # при (2.2 − 14·W/d) < 0 два минуса дают положительный n (kuzram.py
        # клэмпит этот же член так же).
        * max(0.0, 1.0 - drill_deviation_m / burden_m)
        * SINGLE_CHARGE_FACTOR
        * charge_to_bench
        * correction
    )
    return Uniformity(raw=raw, value=max(MIN_UNIFORMITY_N, raw), charge_to_bench=charge_to_bench)


def oversize(x50_mm: float, n: float, lump_size_mm: float) -> tuple[float, float]:
    """Характерный размер xc (мм) и доля кусков крупнее кондиционного, % (Розин–Раммлер)."""
    return (
        rosin_rammler_characteristic_mm(x50_mm, n),
        rosin_rammler_oversize_pct(x50_mm, n, lump_size_mm),
    )


def solve_rock_factor_correction(
    oversize_at: Callable[[float], float],
    target_pct: float,
    *,
    iterations: int = 80,
) -> float | None:
    """C(A), при котором oversize_at(C(A)) равен target_pct; None — если вне 0,1–10.

    Негабарит растёт с C(A) (средний кусок крупнее), поэтому достаточно
    бисекции по ln C(A) в границах поправки из настроек.
    """
    low, high, _label = NUMERIC_BOUNDS["rock_factor_correction"]
    if oversize_at(low) > target_pct or oversize_at(high) < target_pct:
        return None
    lo, hi = math.log(low), math.log(high)
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        # exp(mid) у самой границы может дать 10.000000000000002 —
        # зажимаем каждое пробное значение, иначе replace(...) на входе
        # в тест не пройдёт валидацию границ настройки.
        trial = min(high, max(low, math.exp(mid)))
        if oversize_at(trial) > target_pct:
            hi = mid
        else:
            lo = mid
    return min(high, max(low, math.exp((lo + hi) / 2.0)))
