"""Кровля блока по чертежу маркшейдера (TASK-013, PR 3).

Порядок построения (§2 «Поверхность и подошва»): отсечение по контуру + 20 м
→ точки → ограничители → исключения пользователя (`surface_data`) → защита
плоских треугольников → граница и предел длины ребра (здесь). Линии без
своей Z получают её с поверхности, построенной без них (как proximity
breakline в Civil 3D), и затем входят ограничителями.

Защита плоских треугольников: треугольник, все три вершины которого —
горизонтали одной отметки, получает точку в центре тяжести, Z — обратными
расстояниями по трём ближайшим вершинам с другой Z; триангуляция строится
заново, до трёх проходов.

Качество (§2): число отметок, покрытие контура кровлей, наибольшее
расстояние от точки контура до ближайшей отметки, выбросы — отклонение
отметки от плоскости по её соседям в TIN больше 1,5 м. Выброс ищется
жадно: самый сильный помечается и выпадает из соседей остальных, иначе
точки рядом с одним «пиком» тоже выглядели бы выбросами.

Объём между кровлей и подошвой в полигоне — точно: треугольники TIN,
обрезанные полигоном, площадь куска × (Z кровли в его центре тяжести −
подошва). Для линейной в треугольнике кровли это точный интеграл;
треугольник, пересекающий подошву, режется по её линии. Часть полигона вне
кровли — по ближайшей вершине кровли, как устья скважин.
"""
from __future__ import annotations

import heapq
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

from design.spatial.cad.model import ROLE_CREST_BOTTOM, ROLE_CREST_TOP, CadEntity, CadWarning, ru_number
from design.spatial.cad.rings import XY, LocalFrame, RingIssue, ring_area, ring_perimeter
from design.spatial.cad.surface_builder import BuildResult, SurfaceBuilder, make_builder
from design.spatial.cad.surface_data import ROLE_PRIORITY, SurfaceData, collect_surface_data
from design.spatial.cad.two_contours import BENCH_HEIGHT_RANGE_M, MAX_RING_SAMPLES

MAX_EDGE_M = 30.0
OUTLIER_M = 1.5
THRESHOLD_M = 0.5
GAP_SAMPLE_M = 1.0
# Кровля тяжелее этого — предупреждение о размере паспорта (прореживания нет:
# отметки маркшейдера не выбрасываются).
SIZE_WARNING_VERTICES = 5000
# Выбросов в списке не больше этого: дальше данные, а не отдельные точки.
MAX_OUTLIERS = 500
# Покрытие ниже этого — предупреждение.
FULL_COVERAGE_PCT = 99.9
IDW_NEIGHBOURS = 3
# Проходов защиты плоских треугольников не больше этого.
FLAT_PASSES = 3
# Соседей центра плоского треугольника сначала берём столько; не хватило
# вершин другой отметки — ищем по дереву других отметок.
IDW_FIRST_K = 32
# Треугольник меньшей площади — вырожденный (три точки на одной прямой).
MIN_FLAT_AREA_M2 = 1e-6
# Нижняя бровка дальше этого от контура объёма — чужой уступ, не порог блока.
THRESHOLD_NEAR_M = 2.0
_SAME_Z_M = 0.001

XYZ = tuple[float, float, float]


@dataclass
class Outlier:
    id: str
    point: XYZ
    deviation_m: float


@dataclass
class Threshold:
    """Участок нижней бровки выше подошвы — возможный порог."""

    segments: list[list[XY]]
    excess_m: float


@dataclass
class VolumeResult:
    # Объём кровля − подошва (ниже подошвы — ноль), с частью вне кровли.
    volume_m3: float
    # Интеграл (кровля − подошва) по покрытой части, со знаком.
    integral_m3: float
    covered_m2: float
    area_m2: float
    # Интеграл со знаком по части вне кровли; None — она не считалась.
    outside_integral_m3: float | None = None

    @property
    def coverage_pct(self) -> float:
        return 100.0 * self.covered_m2 / self.area_m2 if self.area_m2 > 0 else 0.0

    def mean_height_m(self) -> float | None:
        """Средняя высота по контуру, со знаком.

        Часть вне кровли — как в объёме, если она считалась; иначе среднее
        по покрытой части.
        """
        if self.outside_integral_m3 is not None and self.area_m2 > 0:
            return (self.integral_m3 + self.outside_integral_m3) / self.area_m2
        return self.integral_m3 / self.covered_m2 if self.covered_m2 > 0 else None


@dataclass
class Roof:
    frame: LocalFrame
    vertices: np.ndarray
    triangles: np.ndarray
    builder: str
    data: SurfaceData
    plane: bool = False
    flat_fixed: int = 0
    spot_count: int = 0
    coverage_pct: float = 0.0
    max_gap_m: float | None = None
    max_gap_point: XY | None = None
    outliers: list[Outlier] = field(default_factory=list)
    thresholds: list[Threshold] = field(default_factory=list)
    floor_z_m: float | None = None
    mean_height_m: float | None = None
    needs_confirmation: bool = False
    volume_m3: float | None = None
    volume_basis: str = "top"
    area_top_m2: float = 0.0
    area_bottom_m2: float = 0.0
    warnings: list[CadWarning] = field(default_factory=list)
    issues: list[RingIssue] = field(default_factory=list)
    _locator: object = field(default=None, repr=False)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def triangle_count(self) -> int:
        return len(self.triangles)

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def area_mean_m2(self) -> float:
        return (self.area_top_m2 + self.area_bottom_m2) / 2

    @property
    def mean_area_volume_m3(self) -> float | None:
        """S ср × средняя высота — способ горизонтальных сечений."""

        return None if self.mean_height_m is None else self.area_mean_m2 * self.mean_height_m

    @property
    def excluded(self) -> list[str]:
        return self.data.excluded

    def world_vertices(self) -> np.ndarray:
        out = self.vertices.copy()
        out[:, 0] += self.frame.ox
        out[:, 1] += self.frame.oy
        return out

    def elevation_at(self, x: float, y: float) -> float | None:
        if self._locator is None:
            self._locator = _Locator(self.vertices, self.triangles)
        value = self._locator.z(np.array([[x - self.frame.ox, y - self.frame.oy]]))[0]
        return None if math.isnan(value) else float(value)


class _Locator:
    """Z кровли в точках плана: треугольник через STRtree, барицентрически."""

    def __init__(self, vertices: np.ndarray, triangles: np.ndarray) -> None:
        self.vertices = vertices
        self.triangles = triangles
        self.tree = shapely.STRtree(shapely.polygons(vertices[triangles][:, :, :2])) if len(triangles) else None

    def z(self, points: np.ndarray) -> np.ndarray:
        out = np.full(len(points), np.nan)
        if self.tree is None or not len(points):
            return out
        where, which = self.tree.query(shapely.points(points), predicate="intersects")
        if not len(where):
            return out
        _, first = np.unique(where, return_index=True)
        where, which = where[first], which[first]
        out[where] = _plane_z(self.vertices[self.triangles[which]], points[where])
        return out


def _plane_z(tri: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Z плоскости треугольников (K, 3, 3) в точках (K, 2)."""

    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    v0 = b[:, :2] - a[:, :2]
    v1 = c[:, :2] - a[:, :2]
    v2 = points - a[:, :2]
    denom = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    safe = np.where(np.abs(denom) < 1e-15, 1.0, denom)
    u = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / safe
    v = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / safe
    z = a[:, 2] + u * (b[:, 2] - a[:, 2]) + v * (c[:, 2] - a[:, 2])
    return np.where(np.abs(denom) < 1e-15, (a[:, 2] + b[:, 2] + c[:, 2]) / 3, z)


# --- объём ------------------------------------------------------------------


def volume_in_polygon(
    vertices: np.ndarray,
    triangles: np.ndarray,
    polygon: Sequence[XY],
    floor_z: float,
    fallback_z: float | None = None,
) -> VolumeResult:
    """Объём между TIN (мировые координаты) и плоскостью подошвы в полигоне."""

    frame = LocalFrame.of(polygon)
    local = np.asarray(vertices, dtype=float).reshape(-1, 3).copy()
    local[:, 0] -= frame.ox
    local[:, 1] -= frame.oy
    return _volume_local(local, np.asarray(triangles, dtype=int).reshape(-1, 3), frame.to_local(polygon), floor_z, fallback_z)


def tin_volume_in_polygon(
    tin: object, polygon: Sequence[XY], floor_z: float, fallback_z: float | None = None
) -> VolumeResult:
    """`volume_in_polygon` для TIN паспорта (`design.spatial.tin.TIN`)."""

    vertices = np.array([(v.x, v.y, v.z) for v in tin.vertices], dtype=float).reshape(-1, 3)
    triangles = np.asarray(tin.triangles, dtype=int).reshape(-1, 3)
    return volume_in_polygon(vertices, triangles, polygon, floor_z, fallback_z)


def _volume_local(
    vertices: np.ndarray,
    triangles: np.ndarray,
    polygon: Sequence[XY],
    floor_z: float,
    fallback_z: float | None,
) -> VolumeResult:
    """Объём в полигоне; `fallback_z` — считать и часть вне кровли.

    Часть вне кровли берёт Z ближайшей вершины TIN (как устья скважин,
    `geometry.collar_on_roof`); без треугольников — `fallback_z` (бровка).
    """
    shape = Polygon(polygon).buffer(0)
    area = float(shape.area)
    covered = integral = volume = 0.0
    triangles = _unique_triangles(triangles, len(vertices))
    if len(triangles) and area > 0:
        shapely.prepare(shape)
        tri = vertices[triangles]
        polys = shapely.polygons(tri[:, :, :2])
        above, crossing = _above_floor(tri, floor_z)
        # Треугольник целиком внутри — площадь и Z центра тяжести напрямую;
        # обрезаются только пересекающие границу.
        inside = shapely.contains_properly(shape, polys)
        if np.any(inside):
            whole = tri[inside]
            d1 = whole[:, 1, :2] - whole[:, 0, :2]
            d2 = whole[:, 2, :2] - whole[:, 0, :2]
            areas = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / 2
            heights = whole[:, :, 2].mean(axis=1) - floor_z
            covered += float(np.sum(areas))
            integral += float(np.sum(areas * heights))
            volume += _piece_volume(tri[inside], above[inside], floor_z)
        mask = ~inside & shapely.intersects(shape, polys)
        if np.any(mask):
            pieces = shapely.intersection(polys[mask], shape)
            areas = shapely.area(pieces)
            keep = areas > 0
            if np.any(keep):
                cut = tri[mask][keep]
                centres = shapely.get_coordinates(shapely.centroid(pieces[keep]))
                heights = _plane_z(cut, centres) - floor_z
                covered += float(np.sum(areas[keep]))
                integral += float(np.sum(areas[keep] * heights))
                # Кусок целиком выше подошвы — сам кусок: пересечение почти
                # совпадающих полигонов в GEOS бывает пустым.
                lifted = pieces[keep].copy()
                cross = crossing[mask][keep]
                lifted[cross] = shapely.intersection(above[mask][keep][cross], lifted[cross])
                volume += _piece_volume(cut, lifted, floor_z)
    covered = min(covered, area)
    outside: float | None = None
    if fallback_z is not None:
        outside = _outside_integral(vertices, triangles, shape, area - covered, floor_z, fallback_z)
        volume += max(0.0, outside[1])
        outside = outside[0]
    return VolumeResult(
        volume_m3=volume, integral_m3=integral, covered_m2=covered, area_m2=area, outside_integral_m3=outside
    )


def _unique_triangles(triangles: np.ndarray, vertex_count: int) -> np.ndarray:
    """Треугольники без повторов (в любом порядке вершин).

    Повтор считал бы площадь и объём дважды и стирал бы границу сети.
    """
    if not len(triangles):
        return triangles
    n = np.int64(max(vertex_count, 1))
    rows = np.sort(triangles, axis=1).astype(np.int64)
    _, first = np.unique((rows[:, 0] * n + rows[:, 1]) * n + rows[:, 2], return_index=True)
    return triangles[np.sort(first)]


def _above_floor(tri: np.ndarray, floor_z: float) -> tuple[np.ndarray, np.ndarray]:
    """Часть каждого треугольника выше подошвы (полигоны shapely, пустые — ниже)
    и признак «пересекает подошву».

    Кровля в треугольнике линейна, линия подошвы режет его по прямой: выше
    подошвы — треугольник или четырёхугольник. Режется только тот, что
    пересекает подошву (подножие откоса).
    """
    h = tri[:, :, 2] - floor_z
    out = shapely.polygons(tri[:, :, :2])
    below = np.all(h <= 0, axis=1)
    out[below] = shapely.Polygon()
    crossing = ~below & np.any(h < 0, axis=1)
    for k in np.flatnonzero(crossing).tolist():
        ring: list[tuple[float, float]] = []
        for i in range(3):
            j = (i + 1) % 3
            hi, hj = h[k, i], h[k, j]
            if hi >= 0:
                ring.append((float(tri[k, i, 0]), float(tri[k, i, 1])))
            if (hi < 0) != (hj < 0):
                t = hi / (hi - hj)
                ring.append(
                    (
                        float(tri[k, i, 0] + t * (tri[k, j, 0] - tri[k, i, 0])),
                        float(tri[k, i, 1] + t * (tri[k, j, 1] - tri[k, i, 1])),
                    )
                )
        out[k] = Polygon(ring) if len(ring) >= 3 else shapely.Polygon()
    return out, crossing


def _piece_volume(tri: np.ndarray, pieces: np.ndarray, floor_z: float) -> float:
    """Σ площадь куска × (Z плоскости его треугольника в центре тяжести − подошва).

    Куски лежат выше подошвы, кровля в них линейна — интеграл точный.
    """
    areas = shapely.area(pieces)
    keep = areas > 0
    if not np.any(keep):
        return 0.0
    centres = shapely.get_coordinates(shapely.centroid(pieces[keep]))
    heights = np.maximum(_plane_z(tri[keep], centres) - floor_z, 0.0)
    return float(np.sum(areas[keep] * heights))


TIN_BORDER_EDGES_MAX = 10_000


def _tin_area(vertices: np.ndarray, triangles: np.ndarray) -> shapely.Geometry | None:
    """Область TIN в плане — по рёбрам границы (ребро одного треугольника).

    Объединение всех треугольников на 100 000 треугольников — секунды, сборка
    области по границе — миллисекунды. Повторы треугольников сняты в
    `_volume_local`.
    Граница не собралась (сеть с наложениями) или в ней больше
    `TIN_BORDER_EDGES_MAX` рёбер (сеть в дырах: сборка растёт быстрее числа
    рёбер, 28 000 рёбер — около секунды) — None: часть вне кровли тогда по
    бровке, объединять сотни тысяч присланных треугольников на каждый
    пересчёт нельзя. У кровли из чертежа граница — сотни рёбер.
    """
    edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    keys, count = np.unique(edges[:, 0].astype(np.int64) * len(vertices) + edges[:, 1], return_counts=True)
    border = np.stack(np.divmod(keys[count == 1], len(vertices)), axis=1)
    if not len(border) or len(border) > TIN_BORDER_EDGES_MAX:
        return None
    area = shapely.build_area(shapely.multilinestrings(shapely.linestrings(vertices[border][:, :, :2])))
    return area if area.is_valid and not area.is_empty else None


# Часть вне кровли режется на ячейки: около 4000 на её площадь, не мельче
# 0,05 м. Ячейки ставятся только над частью вне кровли — полосами по строкам,
# не сеткой над габаритом: у тонкой рамки габарит — весь блок. Работа
# ограничена: ячеек не больше 50 000, а сумма «пересечение × вершины куска» —
# не больше 2 млн, иначе шаг удваивается; не уложились и одной строкой —
# каждый кусок остатка — одна ячейка. Щели склейки треугольников (площадь
# меньше 1e-6 м²) — шум, не часть вне кровли.
OUTSIDE_CELLS = 4_000
OUTSIDE_CELL_MIN_M = 0.05
OUTSIDE_CELLS_MAX = 50_000
OUTSIDE_WORK_MAX = 2_000_000
OUTSIDE_SLIVER_M2 = 1e-6


def outside_cells(parts: np.ndarray) -> np.ndarray:
    """Куски ячеек над частью вне кровли (полигоны `parts`), в сумме — она же."""

    if len(parts) > OUTSIDE_CELLS_MAX:
        return parts
    bounds = shapely.total_bounds(parts)
    extent = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
    step = max(OUTSIDE_CELL_MIN_M, math.sqrt(float(np.sum(shapely.area(parts))) / OUTSIDE_CELLS))
    tree = shapely.STRtree(parts)
    while step <= 2 * extent:
        cells = _strip_cells(parts, tree, bounds, step)
        if cells is not None:
            return cells
        step *= 2
    return parts


def _strip_cells(parts: np.ndarray, tree: shapely.STRtree, bounds: np.ndarray, step: float) -> np.ndarray | None:
    """Ячейки шага `step`: строка режется по кускам, ячейки — над её кусками.

    None — вышло бы больше `OUTSIDE_CELLS_MAX` ячеек или `OUTSIDE_WORK_MAX` работы.
    """
    min_x, min_y, max_x, max_y = bounds
    ys = np.arange(min_y, max_y, step)
    if len(ys) > OUTSIDE_CELLS_MAX:
        return None
    # Работа оценивается по габаритам кусков — до любой геометрической операции:
    # кусок пересекается со строками над своим габаритом (и соседней по краю).
    part_bounds = shapely.bounds(parts)
    spans = np.floor((part_bounds[:, 3] - min_y) / step) - np.floor((part_bounds[:, 1] - min_y) / step) + 2
    if spans.sum() > OUTSIDE_CELLS_MAX or np.sum(spans * shapely.get_num_coordinates(parts)) > OUTSIDE_WORK_MAX:
        return None
    rows = shapely.box(min_x, ys, max_x, ys + step)
    # Без предиката — только пересечение габаритов; пустые пересечения отсеются ниже.
    row, part = tree.query(rows)
    # Пересечение бывает и коллекцией (полигоны, отрезки) — части в два прохода.
    pieces = shapely.get_parts(shapely.get_parts(shapely.intersection(rows[row], parts[part])))
    pieces = pieces[(shapely.get_type_id(pieces) == 3) & (shapely.area(pieces) > 0)]
    if not len(pieces):
        return pieces
    edges = shapely.bounds(pieces)
    counts = np.maximum(np.ceil((edges[:, 2] - edges[:, 0]) / step), 1).astype(int)
    if int(counts.sum()) > OUTSIDE_CELLS_MAX:
        return None
    if int(np.sum(counts * shapely.get_num_coordinates(pieces))) > OUTSIDE_WORK_MAX:
        return None
    owner = np.repeat(np.arange(len(pieces)), counts)
    offset = np.arange(len(owner)) - np.repeat(np.cumsum(counts) - counts, counts)
    x0 = edges[owner, 0] + offset * step
    cells = shapely.intersection(shapely.box(x0, edges[owner, 1], x0 + step, edges[owner, 3]), pieces[owner])
    return cells[shapely.area(cells) > 0]


def _outside_integral(
    vertices: np.ndarray,
    triangles: np.ndarray,
    shape: Polygon,
    uncovered_m2: float,
    floor_z: float,
    fallback_z: float,
) -> tuple[float, float]:
    """(Интеграл со знаком, объём) части полигона вне кровли.

    Ячейка берёт Z ближайшей к её точке вершины сети; без треугольников или
    с сетью, граница которой не собирается, вся часть — по `fallback_z`.
    """
    if uncovered_m2 <= max(1e-9, 1e-9 * float(shape.area)):
        return 0.0, 0.0
    covered_area = _tin_area(vertices, triangles)
    if covered_area is None:
        # Сеть с наложениями: часть вне кровли — по бровке, как без сети.
        height = fallback_z - floor_z
        return uncovered_m2 * height, uncovered_m2 * max(0.0, height)
    rest = shapely.difference(shape, covered_area)
    parts = shapely.get_parts(shapely.get_parts(rest))
    parts = parts[(shapely.get_type_id(parts) == 3) & (shapely.area(parts) > OUTSIDE_SLIVER_M2)]
    if not len(parts):
        return 0.0, 0.0
    # Ближайшая из всех вершин сети с отметкой — как у устья (`TIN.nearest_vertex`).
    marked = np.flatnonzero(np.isfinite(vertices[:, 2]))
    if not len(marked):
        height = fallback_z - floor_z
        return uncovered_m2 * height, uncovered_m2 * max(0.0, height)
    pieces = outside_cells(parts)
    if not len(pieces):
        return 0.0, 0.0
    areas = shapely.area(pieces)
    centres = shapely.get_coordinates(shapely.point_on_surface(pieces))
    _, nearest = cKDTree(vertices[marked, :2]).query(centres)
    heights = vertices[marked[nearest], 2] - floor_z
    return float(np.sum(areas * heights)), float(np.sum(areas * np.maximum(heights, 0.0)))


# --- построение ---------------------------------------------------------------


def _edge_priority(data: SurfaceData, edge_line: np.ndarray) -> np.ndarray:
    return np.array([ROLE_PRIORITY[data.lines[number].role] for number in edge_line.tolist()], dtype=int)


def _assign_new_z(result: BuildResult, z: np.ndarray, edges: np.ndarray, priority: np.ndarray) -> np.ndarray:
    """Z новых вершин построителя — по ограничителю, на котором она лежит (по приоритету)."""

    full = np.concatenate([z, np.full(len(result.vertices) - len(z), np.nan)])
    for vertex, origins in result.origins.items():
        best: int | None = None
        values: list[float] = []
        for number in origins:
            a, b = int(edges[number, 0]), int(edges[number, 1])
            if not (np.isfinite(z[a]) and np.isfinite(z[b])):
                continue
            pa, pb = result.vertices[a], result.vertices[b]
            d = pb - pa
            length2 = float(np.dot(d, d))
            t = 0.0 if length2 == 0 else float(np.dot(result.vertices[vertex] - pa, d)) / length2
            value = float(z[a] + (z[b] - z[a]) * min(1.0, max(0.0, t)))
            rank = int(priority[number])
            if best is None or rank > best:
                best, values = rank, [value]
            elif rank == best:
                values.append(value)
        if values:
            full[vertex] = float(np.mean(values))
    return full


def _fill_nearest(xy: np.ndarray, z: np.ndarray) -> np.ndarray:
    missing = ~np.isfinite(z)
    if not np.any(missing) or np.all(missing):
        return z
    known = np.flatnonzero(~missing)
    _, nearest = cKDTree(xy[known]).query(xy[missing])
    z = z.copy()
    z[missing] = z[known[nearest]]
    return z


def _trim(vertices: np.ndarray, triangles: np.ndarray, region: Polygon) -> np.ndarray:
    """Треугольники внутри границы (контур + буфер) и без рёбер длиннее 30 м."""

    if not len(triangles):
        return triangles
    tri = vertices[triangles][:, :, :2]
    lengths = np.linalg.norm(tri - np.roll(tri, -1, axis=1), axis=2)
    centres = tri.mean(axis=1)
    inside = shapely.contains_xy(region, centres[:, 0], centres[:, 1])
    return triangles[inside & (lengths.max(axis=1) <= MAX_EDGE_M)]


def _flat_triangles(triangles: np.ndarray, soft: np.ndarray, z: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """Треугольники, все три вершины которых — горизонтали одной отметки.

    Отметка, а не номер линии: куски одной горизонтали, разрезанные буфером,
    дают те же плоские треугольники. Вырожденные (три точки на одной прямой у
    границы) не в счёт: их центр лёг бы на сам ограничитель.
    """

    if not len(triangles):
        return triangles
    levels = z[triangles]
    same = (np.abs(levels[:, 0] - levels[:, 1]) <= _SAME_Z_M) & (np.abs(levels[:, 1] - levels[:, 2]) <= _SAME_Z_M)
    tri = xy[triangles]
    d1 = tri[:, 1] - tri[:, 0]
    d2 = tri[:, 2] - tri[:, 0]
    area = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / 2
    return triangles[soft[triangles].all(axis=1) & same & (area > MIN_FLAT_AREA_M2)]


def _idw(distances: np.ndarray, values: np.ndarray) -> np.ndarray:
    weights = 1.0 / np.maximum(distances, 1e-9)
    return (weights * values).sum(axis=1) / weights.sum(axis=1)


def _idw_centres(vertices: np.ndarray, z: np.ndarray, flat: np.ndarray) -> np.ndarray:
    """Центры плоских треугольников с Z по трём ближайшим вершинам с другой Z.

    Сначала — среди ближайших вершин вообще; где их не хватило (горизонталь
    уплотнена через 2 м, и десятки ближайших — той же отметки), — по дереву
    вершин других отметок, своему для каждой отметки. Память — линейная.
    """

    centres = vertices[flat][:, :, :2].mean(axis=1)
    level = z[flat[:, 0]]
    out = np.full(len(centres), np.nan)
    finite = np.flatnonzero(np.isfinite(z))
    if not len(finite) or not len(centres):
        return np.column_stack([centres, out])
    k = min(IDW_FIRST_K, len(finite))
    distances, found = cKDTree(vertices[finite, :2]).query(centres, k=k)
    distances = np.asarray(distances).reshape(len(centres), k)
    values = z[finite[np.asarray(found).reshape(len(centres), k)]]
    other = np.abs(values - level[:, None]) > _SAME_Z_M
    count = np.cumsum(other, axis=1)
    done = count[:, -1] >= IDW_NEIGHBOURS
    use = other & (count <= IDW_NEIGHBOURS)
    weights = np.where(use, 1.0 / np.maximum(distances, 1e-9), 0.0)
    out[done] = (weights * values).sum(axis=1)[done] / weights.sum(axis=1)[done]
    rest = np.flatnonzero(~done)
    for value in np.unique(np.round(level[rest], 3)).tolist():
        rows = rest[np.abs(level[rest] - value) <= _SAME_Z_M]
        others = finite[np.abs(z[finite] - value) > _SAME_Z_M]
        if not len(others):
            continue
        kk = min(IDW_NEIGHBOURS, len(others))
        near, index = cKDTree(vertices[others, :2]).query(centres[rows], k=kk)
        near = np.asarray(near).reshape(len(rows), kk)
        out[rows] = _idw(near, z[others[np.asarray(index).reshape(len(rows), kk)]])
    return np.column_stack([centres, out])


def _triangulate(data: SurfaceData, builder: SurfaceBuilder) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """TIN кровли: вершины (локальные XYZ), треугольники, исходный индекс вершины, сколько плоских исправлено."""

    xy = data.xy
    z = data.z.copy()
    priority = _edge_priority(data, data.edge_line)
    missing = ~np.isfinite(z)
    if np.any(missing):
        known = np.flatnonzero(~missing)
        position = np.full(len(xy), -1)
        position[known] = np.arange(len(known))
        both = (position[data.edges[:, 0]] >= 0) & (position[data.edges[:, 1]] >= 0) if len(data.edges) else np.zeros(0, bool)
        edges = position[data.edges[both]] if len(data.edges) else np.zeros((0, 2), dtype=int)
        first = builder.build(xy[known], edges)
        first_z = _fill_nearest(first.vertices, _assign_new_z(first, z[known], edges, priority[both]))
        trimmed = _trim(np.column_stack([first.vertices, first_z]), first.triangles, data.region)
        filled = _Locator(np.column_stack([first.vertices, first_z]), trimmed).z(xy[missing])
        z[missing] = filled
        z = _fill_nearest(xy, z)

    soft_lines = np.array([line.soft for line in data.lines] or [False], dtype=bool)
    soft = (data.line_of >= 0) & soft_lines[np.maximum(data.line_of, 0)]
    # Защита плоских треугольников: центры получают Z по соседям другой
    # отметки, TIN строится заново — до FLAT_PASSES раз, пока плоские остаются.
    points, levels, flat_fixed, passes = xy, z, 0, 0
    while True:
        result = builder.build(points, data.edges)
        full_z = _fill_nearest(result.vertices, _assign_new_z(result, levels, data.edges, priority))
        vertices = np.column_stack([result.vertices, full_z])
        if passes == FLAT_PASSES:
            break
        is_soft = np.concatenate([soft, np.zeros(len(result.vertices) - len(soft), dtype=bool)])
        flat = _flat_triangles(_trim(vertices, result.triangles, data.region), is_soft, full_z, result.vertices)
        centres = _idw_centres(vertices, full_z, flat) if len(flat) else np.zeros((0, 3))
        centres = centres[np.isfinite(centres[:, 2])]
        if not len(centres):
            break
        flat_fixed += len(centres)
        points = np.vstack([points, centres[:, :2]])
        levels = np.concatenate([levels, centres[:, 2]])
        passes += 1
    source = np.concatenate([np.arange(len(xy)), np.full(len(result.vertices) - len(xy), -1)])
    triangles = _trim(vertices, result.triangles, data.region)
    used = np.unique(triangles.ravel()) if len(triangles) else np.zeros(0, dtype=int)
    remap = np.full(len(vertices), -1)
    remap[used] = np.arange(len(used))
    return vertices[used], remap[triangles] if len(triangles) else triangles.reshape(-1, 3), source[used], flat_fixed


def _plane(data: SurfaceData, crest_z: float | None) -> tuple[np.ndarray, np.ndarray, float | None]:
    crest = [
        float(data.z[i])
        for i in range(len(data.xy))
        if data.line_of[i] >= 0 and data.lines[data.line_of[i]].role == ROLE_CREST_TOP and np.isfinite(data.z[i])
    ]
    level = float(np.mean(crest)) if crest else crest_z
    if level is None:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=int), None
    min_x, min_y, max_x, max_y = data.region.bounds
    vertices = np.array([[min_x, min_y, level], [max_x, min_y, level], [max_x, max_y, level], [min_x, max_y, level]])
    return vertices, np.array([[0, 1, 2], [0, 2, 3]]), level


# --- качество -------------------------------------------------------------------


class _PlaneFits:
    """Плоскости МНК по соседям вершин TIN — суммами, чтобы исключение вершины
    обновляло подгонку её соседей за O(1), а не заново по всем отметкам.

    Для вершины v: z ≈ c0 + c1·dx + c2·dy по соседям (dx, dy — от v), оценка
    в самой v — c0. Соседи на одной прямой — среднее их Z.
    """

    def __init__(self, vertices: np.ndarray, triangles: np.ndarray) -> None:
        self.xy = vertices[:, :2]
        self.z = vertices[:, 2]
        count = len(vertices)
        edges = np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]) if len(triangles) else np.zeros((0, 2), int)
        edges = np.unique(np.sort(edges, axis=1), axis=0)
        src = np.concatenate([edges[:, 0], edges[:, 1]])
        dst = np.concatenate([edges[:, 1], edges[:, 0]])
        order = np.argsort(src, kind="stable")
        self.dst = dst[order]
        self.starts = np.searchsorted(src[order], np.arange(count + 1))
        self.sums = np.zeros((count, 9))
        np.add.at(self.sums, src, self._terms(src, dst))

    def _terms(self, at: np.ndarray, other: np.ndarray) -> np.ndarray:
        d = self.xy[other] - self.xy[at]
        z = self.z[other]
        dx, dy = d[:, 0], d[:, 1]
        return np.column_stack([np.ones(len(at)), dx, dy, dx * dx, dx * dy, dy * dy, z, z * dx, z * dy])

    def neighbours(self, vertex: int) -> np.ndarray:
        return self.dst[self.starts[vertex] : self.starts[vertex + 1]]

    def remove(self, removed: int, vertex: int) -> None:
        self.sums[vertex] -= self._terms(np.array([vertex]), np.array([removed]))[0]

    def deviation(self, vertices: np.ndarray) -> np.ndarray:
        """Отклонение Z вершин от плоскости по соседям; без соседей — NaN."""

        n, sx, sy, sxx, sxy, syy, sz, szx, szy = self.sums[vertices].T
        matrix = np.stack(
            [np.stack([n, sx, sy], axis=-1), np.stack([sx, sxx, sxy], axis=-1), np.stack([sy, sxy, syy], axis=-1)],
            axis=1,
        )
        det = np.linalg.det(matrix)
        spread = np.maximum(sxx * syy, 1e-12)
        solvable = (n >= 3) & (np.abs(det) > 1e-9 * n * spread)
        estimate = np.divide(sz, n, out=np.full(len(vertices), np.nan), where=n > 0)
        if np.any(solvable):
            rhs = np.stack([sz, szx, szy], axis=-1)[solvable]
            estimate[solvable] = np.linalg.solve(matrix[solvable], rhs[..., None])[:, 0, 0]
        return self.z[vertices] - estimate


def _outliers(vertices: np.ndarray, triangles: np.ndarray, ids: list[str]) -> tuple[list[tuple[int, float]], bool]:
    """Жадно: самый сильный выброс помечается и выпадает из соседей остальных.

    Возвращает выбросы (вершина, отклонение) и признак, что список обрезан
    пределом `MAX_OUTLIERS`.
    """

    candidates = np.array([i for i, item in enumerate(ids) if item], dtype=int)
    if not len(candidates) or not len(triangles):
        return [], False
    fits = _PlaneFits(vertices, triangles)
    deviation = np.full(len(vertices), np.nan)
    deviation[candidates] = fits.deviation(candidates)
    is_candidate = np.zeros(len(vertices), dtype=bool)
    is_candidate[candidates] = True
    version = np.zeros(len(vertices), dtype=int)
    heap = [(-abs(value), 0, int(v)) for v, value in zip(candidates.tolist(), deviation[candidates].tolist()) if np.isfinite(value)]
    heapq.heapify(heap)
    removed = np.zeros(len(vertices), dtype=bool)
    flagged: list[tuple[int, float]] = []
    while heap:
        size, stamp, vertex = heapq.heappop(heap)
        if removed[vertex] or stamp != version[vertex]:
            continue
        if -size <= OUTLIER_M:
            break
        if len(flagged) == MAX_OUTLIERS:
            return flagged, True
        flagged.append((vertex, float(deviation[vertex])))
        removed[vertex] = True
        around = [int(v) for v in fits.neighbours(vertex).tolist() if not removed[v]]
        for other in around:
            fits.remove(vertex, other)
        changed = np.array([v for v in around if is_candidate[v]], dtype=int)
        if len(changed):
            deviation[changed] = fits.deviation(changed)
            for v, value in zip(changed.tolist(), deviation[changed].tolist()):
                version[v] += 1
                if np.isfinite(value):
                    heapq.heappush(heap, (-abs(value), int(version[v]), v))
    return flagged, False


def _ring_samples(local: Sequence[XY]) -> np.ndarray:
    step = max(GAP_SAMPLE_M, ring_perimeter(local) / MAX_RING_SAMPLES)
    out: list[XY] = []
    for a, b in zip(local, [*local[1:], local[0]]):
        count = max(1, math.ceil(math.dist(a, b) / step))
        out.extend((a[0] + (b[0] - a[0]) * k / count, a[1] + (b[1] - a[1]) * k / count) for k in range(count))
    return np.asarray(out, dtype=float).reshape(-1, 2)


def _max_gap(data: SurfaceData, rings: list[list[XY]]) -> tuple[float | None, XY | None]:
    """Наибольшее расстояние от точки контура (через 1 м) до ближайшей отметки."""

    known = np.flatnonzero(np.isfinite(data.z))
    if not len(known):
        return None, None
    samples = np.vstack([_ring_samples(ring) for ring in rings])
    distances, _ = cKDTree(data.xy[known]).query(samples)
    worst = int(np.argmax(distances))
    return float(distances[worst]), data.frame.point_to_world((float(samples[worst, 0]), float(samples[worst, 1])))


def _thresholds(data: SurfaceData, floor_z: float, polygon: Sequence[XY], reach_m: float) -> list[Threshold]:
    """Участки нижней бровки у контура объёма выше подошвы больше чем на 0,5 м (§2).

    Нижние бровки соседних уступов в буфере 20 м — не пороги этого блока:
    берутся только рёбра не дальше `reach_m` от контура объёма.
    """

    if not len(data.edges):
        return []
    picked = []
    for (a, b), number in zip(data.edges.tolist(), data.edge_line.tolist()):
        if data.lines[number].role != ROLE_CREST_BOTTOM:
            continue
        za, zb = data.z[a], data.z[b]
        if np.isfinite(za) and np.isfinite(zb) and max(za, zb) > floor_z + THRESHOLD_M:
            picked.append((a, b))
    if picked:
        near = shapely.distance(
            shapely.linestrings(np.stack([data.xy[[a for a, _ in picked]], data.xy[[b for _, b in picked]]], axis=1)),
            Polygon(polygon).buffer(0),
        )
        picked = [edge for edge, distance in zip(picked, near.tolist()) if distance <= reach_m]
    if not picked:
        return []
    parent: dict[int, int] = {}

    def find(item: int) -> int:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for a, b in picked:
        parent[find(a)] = find(b)
    groups: dict[int, list[tuple[int, int]]] = {}
    for a, b in picked:
        groups.setdefault(find(a), []).append((a, b))
    out = []
    for segments in groups.values():
        excess = max(max(data.z[a], data.z[b]) for a, b in segments) - floor_z
        out.append(Threshold([[data.to_world(a), data.to_world(b)] for a, b in segments], float(excess)))
    return sorted(out, key=lambda item: -item.excess_m)


# --- кровля целиком ------------------------------------------------------------


def build_roof(
    entities: Iterable[CadEntity],
    top: Sequence[XY],
    bottom: Sequence[XY] | None,
    *,
    roles: Iterable[str] | None = None,
    excluded: Iterable[str] | None = None,
    floor_z: float | None = None,
    crest_z: float | None = None,
    builder: SurfaceBuilder | None = None,
) -> Roof:
    """Кровля блока, её качество, отметки уступа и объём (§2, §3 PR 3)."""

    builder = builder or make_builder()
    data = collect_surface_data(entities, top, bottom, roles=roles, excluded=excluded)
    frame = data.frame
    warnings = list(data.warnings)
    issues: list[RingIssue] = []
    # Отметки — точки и горизонтали со своей отметкой: 2D-горизонтали (Z = 0) отметок не дают.
    soft_marks = [i for i, line in enumerate(data.line_of.tolist()) if line >= 0 and data.lines[line].soft and np.isfinite(data.z[i])]
    marks = len(data.mass) + len(soft_marks)
    plane = marks == 0
    flat_fixed = 0
    if plane:
        vertices, triangles, level = _plane(data, crest_z)
        source = np.full(len(vertices), -1)
        if level is None:
            issues.append(RingIssue("no_marks", "Отметок и верхней бровки нет — кровлю не из чего построить."))
        else:
            warnings.append(
                CadWarning(
                    "no_marks",
                    f"Отметок нет — кровля плоскостью {ru_number(level, 2)} м по средней Z верхней бровки.",
                )
            )
    else:
        vertices, triangles, source, flat_fixed = _triangulate(data, builder)
        if not len(triangles):
            issues.append(
                RingIssue(
                    "no_triangles",
                    "Треугольников нет: отметок меньше трёх, они на одной прямой или дальше 30 м друг от друга — "
                    "кровля не построена.",
                )
            )

    roof = Roof(
        frame=frame,
        vertices=vertices,
        triangles=triangles,
        builder=builder.name,
        data=data,
        plane=plane,
        flat_fixed=flat_fixed,
        spot_count=data.spot_count,
        warnings=warnings,
        issues=issues,
        floor_z_m=floor_z,
    )
    top_local = frame.to_local(top)
    bottom_local = frame.to_local(bottom) if bottom and len(bottom) >= 3 else None
    roof.area_top_m2 = ring_area(top_local)
    roof.area_bottom_m2 = ring_area(bottom_local) if bottom_local else roof.area_top_m2
    roof.volume_basis = "bottom" if bottom_local else "top"
    roof.max_gap_m, roof.max_gap_point = _max_gap(data, [top_local, *([bottom_local] if bottom_local else [])])

    ids = [data.point_id[i] if i >= 0 else "" for i in source.tolist()]
    found, capped = _outliers(vertices, triangles, ids)
    roof.outliers = [
        Outlier(ids[i], (*frame.point_to_world((float(vertices[i, 0]), float(vertices[i, 1]))), float(vertices[i, 2])), value)
        for i, value in found
    ]
    if capped:
        warnings.append(
            CadWarning(
                "outliers_capped",
                f"Выбросов больше {MAX_OUTLIERS}: в списке — самые сильные. Проверьте отметки: похоже, шум данных, а не отдельные точки.",
            )
        )

    polygon = bottom_local or top_local
    if floor_z is None:
        roof.coverage_pct = _volume_local(vertices, triangles, polygon, 0.0, None).coverage_pct
        warnings.append(CadWarning("floor_missing", "Подошва не задана — высота уступа и объём не считаются."))
    else:
        top_volume = _volume_local(vertices, triangles, top_local, floor_z, crest_z)
        roof.mean_height_m = top_volume.mean_height_m()
        # Нижний контур идёт по нижней бровке; без него подножие откоса —
        # в H·ctg α от контура блока, не дальше H при откосе круче 45°.
        reach = THRESHOLD_NEAR_M + (0.0 if bottom_local else max(0.0, roof.mean_height_m or 0.0))
        roof.thresholds = _thresholds(data, floor_z, polygon, reach)
        block = _volume_local(vertices, triangles, polygon, floor_z, crest_z)
        roof.coverage_pct = block.coverage_pct
        roof.volume_m3 = block.volume_m3
        if plane and roof.mean_height_m is not None:
            # Плоскость не описывает откос: объём по нижнему контуру завысил бы
            # его на (S низ − S верх)·H/2 — S ср × H.
            roof.volume_basis = "mean"
            roof.volume_m3 = roof.area_mean_m2 * max(0.0, roof.mean_height_m)
        _check_height(roof)
    if roof.triangle_count and roof.coverage_pct < FULL_COVERAGE_PCT:
        warnings.append(
            CadWarning(
                "coverage",
                f"Кровля покрывает {ru_number(roof.coverage_pct, 1)} % контура"
                + (": остальное посчитано по ближайшей отметке кровли." if crest_z is not None else "."),
            )
        )
    if roof.vertex_count > SIZE_WARNING_VERTICES:
        warnings.append(
            CadWarning(
                "surface_size",
                f"Кровля — {roof.vertex_count} вершин: паспорт станет тяжелее. Снимите лишние роли в поверхности.",
                "info",
            )
        )
    return roof


def _check_height(roof: Roof) -> None:
    height = roof.mean_height_m
    if height is None:
        return
    low, high = BENCH_HEIGHT_RANGE_M
    if height <= 0:
        roof.issues.append(
            RingIssue(
                "bench_inverted",
                f"Подошва {ru_number(roof.floor_z_m, 1)} м не ниже кровли: средняя высота уступа "
                f"{ru_number(height, 1)} м — проверьте подошву.",
            )
        )
        roof.needs_confirmation = True
    elif not low <= height <= high:
        roof.needs_confirmation = True
        roof.warnings.append(
            CadWarning(
                "bench_height",
                f"Средняя высота уступа {ru_number(height, 1)} м вне {ru_number(low, 0)}–{ru_number(high, 0)} м — "
                "подтвердите её на шаге «Итог».",
            )
        )
