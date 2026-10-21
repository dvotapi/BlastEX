"""Темп отбойки: время замедления в мс на метр кажущегося сопротивления.

Устья скважин сетки триангулируются по Делоне; по трём временам срабатывания
треугольника строится плоскость t = αx + βy + γ, темп — |∇t| (мс/м).
Сводка ровности: главный показатель — доля площади вне коридора ±25 % вокруг
медианы, второй — устойчивый разброс (межквартильный размах к медиане); cv —
справочный, его раздувают единичные выбросы.

Рабочий диапазон: темп ниже нижней границы (3 мс/м по умолчанию) — дефект
варианта, доля такой площади — первый показатель оценки. Стык сходящихся
фронтов — общее ребро соседних треугольников, где порода с двух сторон
движется навстречу.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.spatial import Delaunay, QhullError

from design.models import BlastDesign, Hole, row_family

# Предел ребра — тот же, что соседство в timing_diagnostics.
RELIEF_EDGE_FACTOR = 1.6
# Коридор вокруг медианы, доля от медианы.
RELIEF_CORRIDOR = 0.25
# Меньшие по площади треугольники вырождены, м².
_MIN_AREA_M2 = 1e-6
# Темп ниже порога — шум float от сложения задержек разными путями
# (17,6 × 3 ≠ 52,8): такие скважины срабатывают одновременно, темп ровно 0.
RELIEF_ZERO_MS_M = 1e-6
# Нижняя граница рабочего диапазона темпа по умолчанию, мс/м: быстрее — дефект.
RELIEF_MIN_MS_M = 3.0
# Наименьший угол подхода движения к линии стыка с каждой стороны, градусы:
# движение почти вдоль ребра стыком не считается.
CONVERGING_MIN_APPROACH_DEG = 10.0

Point2 = tuple[float, float]
Segment = tuple[Point2, Point2]


@dataclass(frozen=True)
class ReliefTriangle:
    hole_ids: tuple[str, str, str]
    points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    relief_ms_m: float
    area_m2: float
    # ∇t плоскости, мс/м по x и y; при нулевом темпе — (0, 0). В ответ не идёт.
    gradient: tuple[float, float] = (0.0, 0.0)

    def to_dict(self, min_bound_ms_m: float = RELIEF_MIN_MS_M) -> dict[str, Any]:
        # Округление для ответа API — только здесь. «Быстрее нижней границы»
        # решается по точному темпу, как в fast_share, а не по округлённому.
        return {
            "hole_ids": list(self.hole_ids),
            "points": [[round(x, 3), round(y, 3)] for x, y in self.points],
            "relief_ms_m": round(self.relief_ms_m, 2),
            "area_m2": round(self.area_m2, 2),
            "fast": self.relief_ms_m < min_bound_ms_m,
        }


@dataclass(frozen=True)
class ReliefStats:
    triangles: int
    median_ms_m: float
    mean_ms_m: float
    min_ms_m: float
    max_ms_m: float
    cv: float | None
    outside_share: float
    robust_spread: float | None
    min_bound_ms_m: float = RELIEF_MIN_MS_M
    max_bound_ms_m: float | None = None
    # Доли площади быстрее нижней и медленнее верхней границы (0 без верхней).
    fast_share: float = 0.0
    slow_share: float = 0.0
    converging_length_m: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "triangles": self.triangles,
            "median_ms_m": round(self.median_ms_m, 2),
            "mean_ms_m": round(self.mean_ms_m, 2),
            "min_ms_m": round(self.min_ms_m, 2),
            "max_ms_m": round(self.max_ms_m, 2),
            "cv": None if self.cv is None else round(self.cv, 4),
            "outside_share": round(self.outside_share, 4),
            "robust_spread": None if self.robust_spread is None else round(self.robust_spread, 4),
            "min_bound_ms_m": round(self.min_bound_ms_m, 2),
            "max_bound_ms_m": (
                None if self.max_bound_ms_m is None else round(self.max_bound_ms_m, 2)
            ),
            "fast_share": round(self.fast_share, 4),
            "slow_share": round(self.slow_share, 4),
            "converging_length_m": round(self.converging_length_m, 2),
        }


@dataclass(frozen=True)
class BurdenRelief:
    triangles: list[ReliefTriangle]
    stats: ReliefStats | None
    # Стыки сходящихся фронтов — отрезки общих рёбер.
    converging: list[Segment] = field(default_factory=list)
    # Нижняя граница темпа этого расчёта — по ней треугольник помечается «быстрым».
    min_bound_ms_m: float = RELIEF_MIN_MS_M

    def to_dict(self) -> dict[str, Any]:
        return {
            "triangles": [t.to_dict(self.min_bound_ms_m) for t in self.triangles],
            "stats": self.stats.to_dict() if self.stats else None,
            "converging": [
                [[round(x, 3), round(y, 3)] for x, y in segment] for segment in self.converging
            ],
        }


def relief_triangles(
    holes: list[Hole], times: dict[str, float], max_edge_m: float
) -> list[ReliefTriangle]:
    """Треугольники Делоне по устьям сетки со временем; темп — |∇t| плоскости."""
    used = [
        h for h in holes
        if h.enabled and row_family(h.kind) == "grid" and h.id in times
    ]
    if len(used) < 3:
        return []
    xy = np.array([[h.collar.x, h.collar.y] for h in used], dtype=float)
    try:
        simplices = Delaunay(xy).simplices
    except QhullError:
        return []  # все точки на одной прямой

    result: list[ReliefTriangle] = []
    for simplex in simplices:
        idx = [int(i) for i in simplex]
        pts = [(float(xy[i, 0]), float(xy[i, 1])) for i in idx]
        edges = [math.dist(pts[k], pts[(k + 1) % 3]) for k in range(3)]
        if max(edges) > max_edge_m:
            continue
        (x0, y0), (x1, y1), (x2, y2) = pts
        det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        area = abs(det) / 2.0
        if area < _MIN_AREA_M2:
            continue
        t0, t1, t2 = (float(times[used[i].id]) for i in idx)
        dt1, dt2 = t1 - t0, t2 - t0
        # Система 2×2 на разностях: α·dx + β·dy = dt.
        alpha = (dt1 * (y2 - y0) - dt2 * (y1 - y0)) / det
        beta = ((x1 - x0) * dt2 - (x2 - x0) * dt1) / det
        relief = math.hypot(alpha, beta)
        if relief < RELIEF_ZERO_MS_M:
            relief, alpha, beta = 0.0, 0.0, 0.0
        result.append(
            ReliefTriangle(
                hole_ids=(used[idx[0]].id, used[idx[1]].id, used[idx[2]].id),
                points=(pts[0], pts[1], pts[2]),
                relief_ms_m=relief,
                area_m2=area,
                gradient=(alpha, beta),
            )
        )
    return result


def _movement(tri: ReliefTriangle) -> tuple[float, float] | None:
    """Направление движения породы m = −∇t/|∇t| (к скважинам, сработавшим раньше)."""
    gx, gy = tri.gradient
    norm = math.hypot(gx, gy)
    if tri.relief_ms_m == 0.0 or norm == 0.0:
        return None  # одновременное срабатывание — направления нет
    return (-gx / norm, -gy / norm)


def _is_converging(first: ReliefTriangle, second: ReliefTriangle, edge: frozenset[str]) -> Segment | None:
    """Отрезок общего ребра, если фронты двух треугольников идут навстречу."""
    m1, m2 = _movement(first), _movement(second)
    if m1 is None or m2 is None:
        return None
    on_edge = [k for k, hid in enumerate(first.hole_ids) if hid in edge]
    opposite = next(k for k in range(3) if k not in on_edge)
    p, q = first.points[on_edge[0]], first.points[on_edge[1]]
    o = first.points[opposite]
    # Нормаль к ребру, направленная от первого треугольника ко второму.
    nx, ny = -(q[1] - p[1]), q[0] - p[0]
    if nx * (o[0] - p[0]) + ny * (o[1] - p[1]) > 0:
        nx, ny = -nx, -ny
    norm = math.hypot(nx, ny)
    nx, ny = nx / norm, ny / norm
    # Обе стороны подходят к ребру: m1·n > sin(угла), m2·n < −sin(угла).
    approach = math.sin(math.radians(CONVERGING_MIN_APPROACH_DEG))
    if m1[0] * nx + m1[1] * ny <= approach or m2[0] * nx + m2[1] * ny >= -approach:
        return None
    return (p, q)


def converging_edges(triangles: list[ReliefTriangle]) -> list[Segment]:
    """Стыки сходящихся фронтов: общие рёбра соседей, где порода идёт навстречу."""
    by_edge: dict[frozenset[str], list[ReliefTriangle]] = {}
    for tri in triangles:
        ids = tri.hole_ids
        for k in range(3):
            key = frozenset((ids[k], ids[(k + 1) % 3]))
            by_edge.setdefault(key, []).append(tri)
    result: list[Segment] = []
    for key, pair in by_edge.items():
        if len(key) != 2 or len(pair) != 2:
            continue  # ребро на краю сетки или вырожденный набор
        segment = _is_converging(pair[0], pair[1], key)
        if segment is not None:
            result.append(segment)
    return result


def _weighted_quantile(sorted_values: np.ndarray, cumulative: np.ndarray, q: float) -> float:
    """Первое значение, на котором накопленная площадь доходит до доли q."""
    pos = int(np.searchsorted(cumulative, q * cumulative[-1] - 1e-12))
    return float(sorted_values[min(pos, len(sorted_values) - 1)])


def relief_stats(
    triangles: list[ReliefTriangle],
    min_ms_m: float = RELIEF_MIN_MS_M,
    max_ms_m: float | None = None,
) -> ReliefStats | None:
    """Сводка ровности: среднее, σ, квантили, доли вне коридора и вне границ — по площади."""
    if not triangles:
        return None
    values = np.array([t.relief_ms_m for t in triangles], dtype=float)
    weights = np.array([t.area_m2 for t in triangles], dtype=float)
    total = float(weights.sum())

    mean = float((values * weights).sum() / total)
    sigma = math.sqrt(float((weights * (values - mean) ** 2).sum() / total))

    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    cumulative = np.cumsum(weights[order])
    median = _weighted_quantile(sorted_values, cumulative, 0.5)
    q25 = _weighted_quantile(sorted_values, cumulative, 0.25)
    q75 = _weighted_quantile(sorted_values, cumulative, 0.75)

    if median > 0:
        outside = np.abs(values - median) > RELIEF_CORRIDOR * median
    else:
        outside = values > 0
    share = float(weights[outside].sum() / total)
    fast = float(weights[values < min_ms_m].sum() / total)
    slow = 0.0 if max_ms_m is None else float(weights[values > max_ms_m].sum() / total)
    converging = sum(math.dist(p, q) for p, q in converging_edges(triangles))

    return ReliefStats(
        triangles=len(triangles),
        median_ms_m=median,
        mean_ms_m=mean,
        min_ms_m=float(values.min()),
        max_ms_m=float(values.max()),
        cv=sigma / mean if mean > 0 else None,
        outside_share=share,
        robust_spread=(q75 - q25) / median if median > 0 else None,
        min_bound_ms_m=min_ms_m,
        max_bound_ms_m=max_ms_m,
        fast_share=fast,
        slow_share=slow,
        converging_length_m=converging,
    )


def burden_relief(
    design: BlastDesign,
    times: dict[str, float],
    *,
    min_ms_m: float = RELIEF_MIN_MS_M,
    max_ms_m: float | None = None,
) -> BurdenRelief | None:
    """Темп отбойки блока; None, если треугольников нет."""
    params = design.pattern_params or {}
    a = float(params.get("spacing_a_m") or 5.0)
    b = float(params.get("burden_b_m") or 4.0)
    triangles = relief_triangles(design.holes, times, RELIEF_EDGE_FACTOR * max(a, b))
    if not triangles:
        return None
    return BurdenRelief(
        triangles=triangles,
        stats=relief_stats(triangles, min_ms_m=min_ms_m, max_ms_m=max_ms_m),
        converging=converging_edges(triangles),
        min_bound_ms_m=min_ms_m,
    )
