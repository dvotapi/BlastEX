"""Темп отбойки: время замедления в мс на метр кажущегося сопротивления.

Устья скважин сетки триангулируются по Делоне; по трём временам срабатывания
треугольника строится плоскость t = αx + βy + γ, темп — |∇t| (мс/м).
Сводка ровности — разброс темпа по площади и доля площади вне коридора
вокруг медианы.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ReliefTriangle:
    hole_ids: tuple[str, str, str]
    points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    relief_ms_m: float
    area_m2: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_ids": list(self.hole_ids),
            "points": [[x, y] for x, y in self.points],
            "relief_ms_m": self.relief_ms_m,
            "area_m2": self.area_m2,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "triangles": self.triangles,
            "median_ms_m": self.median_ms_m,
            "mean_ms_m": self.mean_ms_m,
            "min_ms_m": self.min_ms_m,
            "max_ms_m": self.max_ms_m,
            "cv": self.cv,
            "outside_share": self.outside_share,
        }


@dataclass(frozen=True)
class BurdenRelief:
    triangles: list[ReliefTriangle]
    stats: ReliefStats | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "triangles": [t.to_dict() for t in self.triangles],
            "stats": self.stats.to_dict() if self.stats else None,
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
        result.append(
            ReliefTriangle(
                hole_ids=(used[idx[0]].id, used[idx[1]].id, used[idx[2]].id),
                points=(pts[0], pts[1], pts[2]),
                relief_ms_m=math.hypot(alpha, beta),
                area_m2=area,
            )
        )
    return result


def relief_stats(triangles: list[ReliefTriangle]) -> ReliefStats | None:
    """Сводка ровности: среднее, σ, медиана и доля вне коридора — по площади."""
    if not triangles:
        return None
    values = np.array([t.relief_ms_m for t in triangles], dtype=float)
    weights = np.array([t.area_m2 for t in triangles], dtype=float)
    total = float(weights.sum())

    mean = float((values * weights).sum() / total)
    sigma = math.sqrt(float((weights * (values - mean) ** 2).sum() / total))

    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    pos = int(np.searchsorted(cumulative, total / 2.0 - 1e-12))
    median = float(values[order][min(pos, len(order) - 1)])

    if median > 0:
        outside = np.abs(values - median) > RELIEF_CORRIDOR * median
    else:
        outside = values > 0
    share = float(weights[outside].sum() / total)

    return ReliefStats(
        triangles=len(triangles),
        median_ms_m=median,
        mean_ms_m=mean,
        min_ms_m=float(values.min()),
        max_ms_m=float(values.max()),
        cv=sigma / mean if mean > 0 else None,
        outside_share=share,
    )


def burden_relief(design: BlastDesign, times: dict[str, float]) -> BurdenRelief | None:
    """Темп отбойки блока; None, если треугольников нет."""
    params = design.pattern_params or {}
    a = float(params.get("spacing_a_m") or 5.0)
    b = float(params.get("burden_b_m") or 4.0)
    triangles = relief_triangles(design.holes, times, RELIEF_EDGE_FACTOR * max(a, b))
    if not triangles:
        return None
    return BurdenRelief(triangles=triangles, stats=relief_stats(triangles))
