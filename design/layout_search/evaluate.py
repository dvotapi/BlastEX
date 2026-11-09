"""Оценка одного варианта раскладки: сетка, монтаж, отбраковка и показатели.

Порядок: сетка (`generate_pattern` без ручных скважин) → монтаж «Магистраль +
цепочки» (система, контурный ряд и замедление в скважине — как в базовой сети) →
паспорт варианта → отбраковка (коды `validate`) и ЛСП вне коридора
`[0,8·W₀; 1,03·W₀]` за один расчёт подошвы → темп отбойки → окно 8 мс. W₀ и шаги
для разрыва у подошвы — из базового паспорта и с перебором a и b не меняются.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import shapely

from design.analysis import collar_crest_warnings
from design.back_layout import back_boundary, back_offset_m, back_side
from design.geometry import ensure_ccw, offset_polygon
from design.layout_search.space import Candidate
from design.models import (
    BlastDesign,
    BlastDomain,
    BlockContour,
    Hole,
    InitiationNetwork,
    in_main_grid,
    main_grid_kind,
)
from design.pattern import LAYOUT_ANCHOR_BACK, LAYOUT_ANCHOR_PATTERNS, generate_pattern
from design.relief import RELIEF_MIN_MS_M, burden_relief
from design.spatial.surfaces import SurfaceSet
from design.timing import SYSTEM_TYPES, resolve_times
from design.toe_line import (
    FLOOR_BURDEN_MIN_RATIO,
    TOE_BURDEN_TOLERANCE,
    FloorBurden,
    design_burden_m,
    floor_checks,
    grid_steps_m,
)
from design.trunk_network import build_trunk_chains_network

# Вид скважин, который монтаж включает только по флагу `include_contour`
# (`timing._eligible_holes`); предщелевой и оконтуривающий ряды входят всегда.
CONTOUR_KIND = "contour"
# Шаги сетки, которые для проверок подошвы берутся из базы.
STEP_KEYS = ("spacing_a_m", "burden_b_m")
# Коды `validate`, отбраковывающие вариант (`reject_codes_and_lsp` выводит их сам).
# `floor_burden_excess` — ЛСП передней скважины больше W + 3 %: брак, а не
# пометка (решение владельца 09.11.2026); недобор (< 0,8·W) — только `lsp_out`.
REJECT_CODES = ("floor_beyond_toe", "collar_too_close_to_crest", "floor_row_gap_excess", "floor_burden_excess")
# Код отбраковки пустой сетки.
EMPTY_CODE = "empty"
# Метка сеток по параметрам в `seen` (ключи раскладок начинаются с фланга).
PATTERN_KEY = "pattern"
# Окно одновременного срабатывания (только показывается), мс.
WINDOW_MS = 8.0
# Шаги округления перед сравнением: доли — 0,01, длина стыков — 0,5 м.
SHARE_STEP = 0.01
LENGTH_STEP_M = 0.5
# Покрытие блока (решение владельца 08.11.2026): точка не покрыта, если до
# ближайшей скважины дальше ¾ большего шага (центр ячейки a × b — не дальше
# 0,71·max(a, b)); площадь сравнивается в целых ячейках a·b варианта — углы
# зоны (единицы м²) порядок не решают, полоса, куда влез бы эшелон, — решает.
COVER_RADIUS_RATIO = 0.75
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
    # Площадь блока без скважин, м² (`uncovered_area_m2`).
    uncovered_m2: float = 0.0

    def uncovered_cells(self) -> int:
        """Площадь без скважин в целых ячейках a·b варианта."""
        a, b = grid_steps_m(self.candidate.params)
        cell = a * b
        if not math.isfinite(self.uncovered_m2) or cell <= 0:
            return 0
        return int(round(self.uncovered_m2 / cell))

    def rank_key(self, rejected: bool | None = None) -> tuple:
        """Ключ сравнения, меньше — лучше: отбраковка, площадь без скважин
        (решение владельца 08.11.2026: покрытие блока у краёв; в целых ячейках
        a·b), ЛСП вне коридора, быстрые
        доли, стыки, доля вне ±25 %, разброс (None — хуже любого числа), число
        скважин. Без статистики темпа (`relief` None) доли и стыки — `inf`.
        Доли и разброс — до 0,01, стыки — до 0,5 м: шум генератора порядок не
        решает. Окно 8 мс и замедление в сравнении не участвуют.
        `rejected` — подмена флага отбраковки (семена этапа 2, `search._ranked`)."""
        spread = math.inf if self.robust_spread is None else _round_step(self.robust_spread, SHARE_STEP)
        return (
            self.rejected if rejected is None else rejected,
            self.uncovered_cells(),
            self.lsp_out,
            _round_step(self.fast_share, SHARE_STEP),
            _round_step(self.converging_length_m, LENGTH_STEP_M),
            _round_step(self.outside_share, SHARE_STEP),
            spread,
            self.hole_count,
        )


def uncovered_area_m2(contour: BlockContour, params: dict, holes: list[Hole]) -> float:
    """Площадь блока без скважин, м²: часть зоны раскладки дальше
    `COVER_RADIUS_RATIO`·max(a, b) от устьев всех скважин варианта.

    Зона раскладки — граница генератора без полос, которые скважинам заданы
    пустыми: от бровки — контур, сжатый на отступ от контура; «от тыла» —
    сжатый у боковых сторон (`back_boundary`) и без полосы отступа от тыла.
    Одна мера для обоих шаблонов: полоса у фланга, куда влез бы ещё эшелон,
    и недостроенная глубина блока видны одинаково."""
    verts = ensure_ccw(contour.points_xy)
    if len(verts) < 3:
        return 0.0
    try:
        margin = max(float(params.get("edge_margin_m", 0.0) or 0.0), 0.0)
    except (TypeError, ValueError):
        margin = 0.0
    back = None
    if params.get("layout_anchor") == LAYOUT_ANCHOR_BACK and str(params.get("pattern", "square")) in LAYOUT_ANCHOR_PATTERNS:
        back = back_side(contour)
    ring = back_boundary(contour, margin) if back is not None else (offset_polygon(verts, margin) if margin > 0 else verts)
    if len(ring) < 3:
        return 0.0
    zone = shapely.Polygon(ring).buffer(0)
    if back is not None:
        zone = zone.difference(shapely.LineString(back).buffer(back_offset_m(params)))
    a, b = grid_steps_m(params)
    radius = COVER_RADIUS_RATIO * max(a, b)
    if not holes or radius <= 0:
        return float(zone.area)
    covered = shapely.union_all(shapely.buffer(shapely.points([(h.collar.x, h.collar.y) for h in holes]), radius))
    return float(zone.difference(covered).area)


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
    за подошвой, `floor_burden_excess` — у передней скважины ЛСП больше W + 3 %
    (`FloorBurden.excess` не за подошвой; W — b паспорта проверки, в переборе —
    W₀ базы, `with_base_steps`), `floor_row_gap_excess` — есть разрыв у подошвы с `excess`,
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
    if any(item.excess and not item.beyond_toe for item in burdens.values()):
        codes.add("floor_burden_excess")
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
    """Система, вид основной сетки, контурный ряд и замедление в скважине
    монтажа варианта — по базе.

    Система — `network.system` базы (неизвестная — СИНВ). `main_kind` — вид
    основной сетки (`pattern_params.default_kind`): по нему построитель
    отличает основную сетку вида stab/satellite от вставок; ряды решётки
    стеночного вида — члены столбцов при любом виде. Флаг `include_contour`
    управляет только отдельными рядами вида contour (предщелевой и
    оконтуривающий ряды монтаж включает всегда) и ставится, если базовая сеть
    монтирует хотя бы одну контурную скважину (`wired_wall_holes`). У ДШ и
    электронной замедление в скважине — из базовой сети (`base_downhole_ms`);
    у СИНВ его выбирает построитель.
    """
    system = str(getattr(base.network, "system", "") or "nonel")
    if system not in SYSTEM_TYPES:
        system = "nonel"
    params: dict = {
        "system": system,
        "main_kind": main_grid_kind(base.pattern_params),
        "include_contour": bool(wired_wall_holes(base)),
    }
    if system != "nonel":
        downhole_ms = base_downhole_ms(base.network)
        if downhole_ms is not None:
            params["downhole_delay_ms"] = downhole_ms
    return params


def wired_wall_holes(base: BlastDesign) -> list[Hole]:
    """Контурные скважины, которые монтирует базовая сеть. Ряд решётки вида
    contour (`default_kind` или строка `row_params`) — не стенки: его монтирует
    построитель как члены столбцов, в счёт он не идёт.

    Смонтированной считается скважина, которая есть в сети хоть как-то:
    стартовая, конец поверхностной или старой связи, скважина шнура ДШ,
    электронное время или канал.

    Только по ним решается флаг `include_contour` (`network_params`), поэтому
    фоновый подбор передаёт в дочерний процесс лишь их, а не все скважины.
    """
    network = base.network
    walls = [h for h in base.holes or [] if h.kind == CONTOUR_KIND and not in_main_grid(h)]
    if network is None or not walls:
        return []
    return [h for h in walls if h.id in _wired_hole_ids(network)]


def _wired_hole_ids(network: InitiationNetwork) -> set[str]:
    """Скважины, которые сеть монтирует любым способом."""
    wired: set[str] = set(network.starters)
    wired.update(item.hole_id for item in network.starter_items)
    for link in (*network.connectors, *network.surface_connectors):
        wired.update((link.from_hole, link.to_hole))
    for cord in network.detonating_cords:
        wired.update(cord.hole_ids)
    wired.update(network.electronic_times_ms)
    wired.update(channel.hole_id for channel in network.electronic_channels)
    return wired


def base_downhole_ms(network: InitiationNetwork | None) -> float | None:
    """Замедление в скважине базовой сети: поле схемы (`timing_params`), иначе
    первое значение по скважинам (`downhole_delay_ms`), иначе первого детонатора;
    нигде нет — `None` (построитель возьмёт умолчание системы)."""
    if network is None:
        return None
    value = (network.timing_params or {}).get("downhole_delay_ms")
    if value is None and network.downhole_delay_ms:
        value = next(iter(network.downhole_delay_ms.values()))
    if value is None and network.detonators:
        value = network.detonators[0].delay_ms
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _empty(candidate: Candidate, system: str) -> Evaluation:
    return Evaluation(
        candidate=candidate, holes=[], network=InitiationNetwork(system=system), rejected=True,
        reject_codes=[EMPTY_CODE], lsp_out=0, fast_share=math.inf, converging_length_m=math.inf,
        outside_share=math.inf, robust_spread=None, hole_count=0, window8_max_holes=0, downhole_ms=0.0, warnings=[],
    )


def _layout_key(holes: list[Hole], cut_flank: str) -> tuple:
    """Отпечаток раскладки: устья, забои, вид и включение скважин до 1 мм и фланг вруба."""
    return (cut_flank, tuple(
        (h.id, h.kind, h.enabled, round(h.collar.x, 3), round(h.collar.y, 3), round(h.collar.z, 3),
         round(h.toe.x, 3), round(h.toe.y, 3), round(h.toe.z, 3))
        for h in holes
    ))


def evaluate(ctx: SearchContext, candidate: Candidate, seen: dict | None = None) -> Evaluation:
    """Строит вариант и считает показатели ранжирования.

    `seen` — оценки уже построенных раскладок за этот поиск: варианты с теми
    же скважинами и флангом (пара с подъёмом угла даёт одно и то же при разных
    `front_rows_tilt_deg`) берут готовую оценку со своим `candidate`. Там же —
    сетки по параметрам (ключ `(PATTERN_KEY, параметры)`): фланг сетку не
    меняет, и второй фланг того же варианта её не строит заново (генерация
    «от тыла» — основная часть времени оценки). Скважины после генерации
    никто не меняет, поэтому оценки делят их объекты (списки — свои).
    """
    base = ctx.design
    pattern_key = (PATTERN_KEY, candidate.key()[0]) if seen is not None else None
    if pattern_key is not None and pattern_key in seen:
        holes = list(seen[pattern_key])
    else:
        # Ручные скважины перебор не использует: сетка без `existing_holes`.
        holes = generate_pattern(
            base.contour, candidate.params, None, _surfaces(base.surfaces), _domains(base.domains)
        )
        if pattern_key is not None:
            seen[pattern_key] = list(holes)
    mounting = network_params(base)
    if not holes:
        return _empty(candidate, mounting["system"])
    key = _layout_key(holes, candidate.cut_flank) if seen is not None else None
    if key is not None and key in seen:
        return replace(seen[key], candidate=candidate)
    result = _evaluated(ctx, candidate, holes, mounting)
    if key is not None:
        seen[key] = result
    return result


def _evaluated(ctx: SearchContext, candidate: Candidate, holes: list[Hole], mounting: dict) -> Evaluation:
    base = ctx.design

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
        uncovered_m2=uncovered_area_m2(base.contour, candidate.params, holes),
    )
