"""Линия подошвы откоса: от неё считается ЛСП первого ряда скважин.

Если у контура есть съёмка нижней бровки (`cad.bottom`, контур не правили) —
берутся её рёбра у свободных поверхностей; иначе линия строится смещением
верхней бровки наружу на проекцию откоса в плане.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon

from design.geometry import drawing_bottom
from design.models import BenchSurface, BlockContour

# Запас к проекции откоса при поиске рёбер съёмки у свободной поверхности, м.
TOE_SEARCH_MARGIN_M = 1.0

Polyline = list[tuple[float, float]]


@dataclass(frozen=True)
class ToeLine:
    polylines: list[Polyline]
    source: str  # "survey" — по съёмке нижней бровки, "built" — построена от верхней


def slope_offset_m(bench: BenchSurface) -> float:
    """Смещение подошвы от верхней бровки в плане: H · tan(90° − угол откоса)."""
    return max(0.0, bench.height_m * math.tan(math.radians(90.0 - bench.face_angle_deg)))


def _free_polylines(contour: BlockContour) -> list[Polyline]:
    pts = contour.points_xy
    lines = []
    for face in contour.free_faces:
        line = [pts[i] for i in face if 0 <= i < len(pts)]
        if len(line) >= 2:
            lines.append(line)
    return lines


def _built(contour: BlockContour, free: list[Polyline], offset: float) -> list[Polyline]:
    if offset <= 0:
        return [list(line) for line in free]
    polygon = Polygon(contour.points_xy)
    result: list[Polyline] = []
    for line in free:
        base = LineString(line)
        best = None
        for sign in (offset, -offset):
            shifted = base.offset_curve(sign)
            if shifted.is_empty:
                continue
            geoms = list(shifted.geoms) if hasattr(shifted, "geoms") else [shifted]
            if not polygon.contains(geoms[0].interpolate(0.5, normalized=True)):
                best = geoms
                break
        if best is None:
            best = [base]
        result.extend([(float(x), float(y)) for x, y in g.coords] for g in best)
    return result


def _survey(ring: list[tuple[float, float]], free: list[Polyline], reach: float) -> list[Polyline]:
    lines = [LineString(line) for line in free]
    n = len(ring)
    near = []
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        mid = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        near.append(any(line.distance(mid) <= reach for line in lines))
    if not any(near):
        return []
    if all(near):
        return [list(ring) + [ring[0]]]
    # Начинаем обход с ребра после первого «дальнего», чтобы серии не рвались на стыке кольца.
    start = (near.index(False) + 1) % n
    polylines: list[Polyline] = []
    current: Polyline = []
    for k in range(n):
        i = (start + k) % n
        if near[i]:
            if not current:
                current = [ring[i]]
            current.append(ring[(i + 1) % n])
        elif current:
            polylines.append(current)
            current = []
    if current:
        polylines.append(current)
    return polylines


def toe_line(contour: BlockContour) -> ToeLine | None:
    """Линия подошвы вдоль свободных поверхностей; None, если их нет."""
    free = _free_polylines(contour)
    if not free:
        return None
    offset = slope_offset_m(contour.bench)
    ring = drawing_bottom(contour)
    if ring is not None:
        polylines = _survey(ring, free, offset + TOE_SEARCH_MARGIN_M)
        if polylines:
            return ToeLine(polylines=polylines, source="survey")
    return ToeLine(polylines=_built(contour, free, offset), source="built")
