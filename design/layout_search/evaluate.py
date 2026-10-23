"""Оценка одного варианта раскладки: сетка, монтаж, отбраковка и показатели.

Порядок: сетка (`generate_pattern` без ручных скважин) → монтаж «Магистраль +
цепочки» (система и стенки — как в базовой сети) → паспорт варианта → отбраковка
(коды `validate`) и ЛСП вне коридора `[0,8·W₀; 1,03·W₀]` за один расчёт подошвы →
темп отбойки → окно 8 мс. W₀ и шаги для разрыва у подошвы — из базового паспорта
и с перебором a и b не меняются.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from design.analysis import collar_crest_warnings
from design.layout_search.space import Candidate
from design.models import BlastDesign, BlastDomain, Hole, InitiationNetwork
from design.pattern import generate_pattern
from design.relief import RELIEF_MIN_MS_M, burden_relief
from design.spatial.surfaces import SurfaceSet
from design.timing import SYSTEM_TYPES, resolve_times
from design.toe_line import (
    FLOOR_BURDEN_MIN_RATIO,
    TOE_BURDEN_TOLERANCE,
    FloorBurden,
    design_burden_m,
    floor_checks,
)
from design.trunk_network import build_trunk_chains_network

# Виды стенок: если базовая сеть их монтирует, монтаж варианта тоже их включает.
WALL_KINDS = frozenset({"contour", "presplit", "trim"})
# Шаги сетки, которые для проверок подошвы берутся из базы.
STEP_KEYS = ("spacing_a_m", "burden_b_m")
# Коды `validate`, отбраковывающие вариант (`reject_codes_and_lsp` выводит их сам).
REJECT_CODES = ("floor_beyond_toe", "collar_too_close_to_crest", "floor_row_gap_excess")
# Код отбраковки пустой сетки.
EMPTY_CODE = "empty"
# Окно одновременного срабатывания (только показывается), мс.
WINDOW_MS = 8.0
# Шаги округления перед сравнением: доли — 0,01, длина стыков — 0,5 м.
SHARE_STEP = 0.01
LENGTH_STEP_M = 0.5
_EPS = 1e-6


@dataclass(frozen=True)
class SearchContext:
    """Базовый паспорт (контур, поверхности, домены, `pattern_params`), W₀ и границы темпа."""

    design: BlastDesign
    w0_m: float | None
    relief_min_ms_m: float = RELIEF_MIN_MS_M
    relief_max_ms_m: float | None = None

    @classmethod
    def from_design(
        cls,
        design: BlastDesign,
        *,
        relief_min_ms_m: float = RELIEF_MIN_MS_M,
        relief_max_ms_m: float | None = None,
    ) -> SearchContext:
        """W₀ — проектная W базовых параметров (`toe_line.design_burden_m`)."""
        return cls(
            design=design,
            w0_m=design_burden_m(design.pattern_params),
            relief_min_ms_m=relief_min_ms_m,
            relief_max_ms_m=relief_max_ms_m,
        )


@dataclass
class Evaluation:
    """Результат оценки варианта: сетка, сеть и показатели ранжирования."""

    candidate: Candidate
    holes: list[Hole]
    network: InitiationNetwork
    rejected: bool
    reject_codes: list[str]
    lsp_out: int
    fast_share: float
    converging_length_m: float
    outside_share: float
    robust_spread: float | None
    hole_count: int
    window8_max_holes: int
    downhole_ms: float
    warnings: list[str] = field(default_factory=list)

    def rank_key(self) -> tuple:
        """Ключ сравнения, меньше — лучше: отбраковка, ЛСП вне коридора, быстрые
        доли, стыки, доля вне ±25 %, разброс (None — хуже любого числа), число
        скважин. Без статистики темпа (`relief` None) доли и стыки — `inf`.
        Доли и разброс — до 0,01, стыки — до 0,5 м: шум генератора порядок не
        решает. Окно 8 мс и замедление в сравнении не участвуют."""
        spread = math.inf if self.robust_spread is None else _round_step(self.robust_spread, SHARE_STEP)
        return (
            self.rejected,
            self.lsp_out,
            _round_step(self.fast_share, SHARE_STEP),
            _round_step(self.converging_length_m, LENGTH_STEP_M),
            _round_step(self.outside_share, SHARE_STEP),
            spread,
            self.hole_count,
        )


def _round_step(value: float, step: float) -> float:
    if not math.isfinite(value):
        return value
    return round(round(value / step) * step, 6) + 0.0  # + 0.0 убирает «-0.0»


def _surfaces(value: object) -> SurfaceSet | None:
    """Поверхности паспорта как в `design_service`: словарь — в `SurfaceSet`."""
    if value is None or isinstance(value, SurfaceSet):
        return value
    if isinstance(value, dict):
        return SurfaceSet.from_dict(value)
    return value  # type: ignore[return-value]


def _domains(items: list | None) -> list[BlastDomain]:
    return [d if isinstance(d, BlastDomain) else BlastDomain.from_dict(d) for d in items or []]


def _lsp_out(burdens: dict[str, FloorBurden], w0_m: float | None) -> int:
    """Скважины с ЛСП вне коридора `[0,8·W₀; 1,03·W₀]` или за подошвой; без W₀ — 0."""
    if w0_m is None:
        return 0
    low = FLOOR_BURDEN_MIN_RATIO * w0_m - _EPS
    high = (1.0 + TOE_BURDEN_TOLERANCE) * w0_m + _EPS
    return sum(1 for item in burdens.values() if item.beyond_toe or not low <= item.value_m <= high)


def reject_codes_and_lsp(design: BlastDesign, w0_m: float | None) -> tuple[list[str], int]:
    """Коды отбраковки и `lsp_out` за один расчёт подошвы (`floor_checks`).

    Коды выводятся так же, как в `validate`: `floor_beyond_toe` — есть скважины
    за подошвой, `floor_row_gap_excess` — есть разрыв у подошвы с `excess`,
    `collar_too_close_to_crest` — `collar_crest_warnings(force=True)`: в отличие
    от `validate`, отступ устья от кромки проверяется всегда, даже без ключей
    отступа и схемы первого ряда (у выпуклой бровки обычные ряды встают к ней
    вплотную). Полный `validate` не зовётся: остальные его проверки (тайминг,
    ЛНС, заряды) отбраковке не нужны.
    """
    burdens, beyond_toe, row_gaps = floor_checks(design)
    codes: set[str] = set()
    if beyond_toe:
        codes.add("floor_beyond_toe")
    if any(gap.excess for gap in row_gaps.values()):
        codes.add("floor_row_gap_excess")
    if collar_crest_warnings(design, force=True):
        codes.add("collar_too_close_to_crest")
    return sorted(codes), _lsp_out(burdens, w0_m)


def with_base_steps(params: dict, base: dict | None) -> dict:
    """`pattern_params` варианта для проверок подошвы: шаги a и b — базовые.

    Разрыв у подошвы («шаг + 3 %») отсчитывается от исходной сетки, как W₀ для
    ЛСП: иначе вариант с b · 1,03 сам себе расширял бы допуск. Шага нет в базе —
    его нет и здесь (`grid_steps_m` возьмёт то же умолчание, что и для базы).
    """
    base = base or {}
    out = {k: v for k, v in params.items() if k not in STEP_KEYS}
    out.update({k: base[k] for k in STEP_KEYS if k in base})
    return out


def window_max_holes(times: dict[str, float], window_ms: float = WINDOW_MS) -> int:
    """Наибольшее число скважин, срабатывающих в одном окне `window_ms`.

    Окно — как у МИС `analysis.charge_per_delay`: скважины с разницей времён не
    больше `window_ms` — одно окно (скважины ровно через 8 мс, 2·25 против 42 мс,
    в него попадают). Показатель только показывается и в ранжировании не участвует.
    """
    values = sorted(times.values())
    best = left = 0
    for right, t in enumerate(values):
        while t - values[left] > window_ms:
            left += 1
        best = max(best, right - left + 1)
    return best


def network_params(base: BlastDesign) -> dict:
    """Система и стенки монтажа варианта — по базовой сети.

    Система — `network.system` базы (неизвестная — СИНВ). Стенки (контурный,
    предщелевой, оконтуривающий ряд) включаются, если базовая сеть их монтирует:
    у скважин этих видов есть связи или стартовые.
    """
    system = str(getattr(base.network, "system", "") or "nonel")
    if system not in SYSTEM_TYPES:
        system = "nonel"
    return {"system": system, "include_contour": bool(wired_wall_holes(base))}


def wired_wall_holes(base: BlastDesign) -> list[Hole]:
    """Скважины стенок (контурный, предщелевой, оконтуривающий ряд), которые
    монтирует базовая сеть: у них есть связи или они стартовые.

    Фоновый подбор передаёт в дочерний процесс только их, а не все скважины:
    `network_params` по ним даёт тот же ответ, что по полному паспорту.
    """
    network = base.network
    walls = [h for h in base.holes or [] if h.kind in WALL_KINDS]
    if network is None or not walls:
        return []
    wired: set[str] = set(network.starters)
    wired.update(item.hole_id for item in network.starter_items)
    for link in (*network.connectors, *network.surface_connectors):
        wired.update((link.from_hole, link.to_hole))
    return [h for h in walls if h.id in wired]


def _empty(candidate: Candidate, system: str) -> Evaluation:
    return Evaluation(
        candidate=candidate, holes=[], network=InitiationNetwork(system=system), rejected=True,
        reject_codes=[EMPTY_CODE], lsp_out=0, fast_share=math.inf, converging_length_m=math.inf,
        outside_share=math.inf, robust_spread=None, hole_count=0, window8_max_holes=0, downhole_ms=0.0, warnings=[],
    )


def evaluate(ctx: SearchContext, candidate: Candidate) -> Evaluation:
    """Строит вариант и считает показатели ранжирования."""
    base = ctx.design
    # Ручные скважины перебор не использует: сетка без `existing_holes`.
    holes = generate_pattern(
        base.contour, candidate.params, None, _surfaces(base.surfaces), _domains(base.domains)
    )
    mounting = network_params(base)
    if not holes:
        return _empty(candidate, mounting["system"])

    network, warnings = build_trunk_chains_network(holes, {**mounting, "cut_flank": candidate.cut_flank})
    design = replace(base, holes=holes, network=network, pattern_params=dict(candidate.params))

    # Проверки подошвы — на скважинах варианта, но с шагами базы.
    checked = replace(design, pattern_params=with_base_steps(candidate.params, base.pattern_params))
    reject_codes, lsp_out = reject_codes_and_lsp(checked, ctx.w0_m)

    enabled = [h for h in holes if h.enabled]
    times, timing_warnings = resolve_times(network, enabled)
    warnings = [*warnings, *timing_warnings]
    relief = burden_relief(design, times, min_ms_m=ctx.relief_min_ms_m, max_ms_m=ctx.relief_max_ms_m)
    stats = relief.stats if relief is not None else None

    return Evaluation(
        candidate=candidate,
        holes=holes,
        network=network,
        rejected=bool(reject_codes),
        reject_codes=reject_codes,
        lsp_out=lsp_out,
        # Без темпа (мало скважин, все треугольники отброшены) — хуже любого числа.
        fast_share=stats.fast_share if stats else math.inf,
        converging_length_m=stats.converging_length_m if stats else math.inf,
        outside_share=stats.outside_share if stats else math.inf,
        robust_spread=stats.robust_spread if stats else None,
        hole_count=len(holes),
        window8_max_holes=window_max_holes(times),
        downhole_ms=float(network.timing_params.get("downhole_delay_ms", 0.0) or 0.0),
        warnings=warnings,
    )
