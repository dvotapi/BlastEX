"""Кровля блока по чертежу маркшейдера (TASK-013, PR 3).

Порядок построения (§2 «Поверхность и подошва»): отсечение по контуру + 20 м
→ точки → ограничители → исключения пользователя (`surface_data`) → защита
плоских треугольников → граница и предел длины ребра (здесь). Линии без
своей Z получают её с поверхности, построенной без них (как proximity
breakline в Civil 3D), и затем входят ограничителями.

Защита плоских треугольников: треугольник с тремя вершинами одной
горизонтали получает точку в центре тяжести, Z — обратными расстояниями по
трём ближайшим вершинам с другой Z; триангуляция строится заново.

Качество (§2): число отметок, покрытие контура кровлей, наибольшее
расстояние от точки контура до ближайшей отметки, выбросы — отклонение
отметки от плоскости по её соседям в TIN больше 1,5 м. Выброс ищется
жадно: самый сильный помечается и выпадает из соседей остальных, иначе
точки рядом с одним «пиком» тоже выглядели бы выбросами.

Объём между кровлей и подошвой в полигоне — точно: треугольники TIN,
обрезанные полигоном, площадь куска × (Z кровли в его центре тяжести −
подошва). Для линейной в треугольнике кровли это точный интеграл. Часть
полигона вне кровли считается по отметке бровки, если она известна.
"""
from __future__ import annotations

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
    # Объём кровля − подошва (отрицательные куски — ноль), с частью вне кровли.
    volume_m3: float
    # Интеграл (кровля − подошва) по покрытой части, со знаком.
    integral_m3: float
    covered_m2: float
    area_m2: float

    @property
    def coverage_pct(self) -> float:
        return 100.0 * self.covered_m2 / self.area_m2 if self.area_m2 > 0 else 0.0


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


def _volume_local(
    vertices: np.ndarray,
    triangles: np.ndarray,
    polygon: Sequence[XY],
    floor_z: float,
    fallback_z: float | None,
) -> VolumeResult:
    shape = Polygon(polygon).buffer(0)
    area = float(shape.area)
    covered = integral = volume = 0.0
    if len(triangles) and area > 0:
        shapely.prepare(shape)
        tri = vertices[triangles]
        polys = shapely.polygons(tri[:, :, :2])
        mask = shapely.intersects(polys, shape)
        if np.any(mask):
            pieces = shapely.intersection(polys[mask], shape)
            areas = shapely.area(pieces)
            keep = areas > 0
            if np.any(keep):
                centres = shapely.get_coordinates(shapely.centroid(pieces[keep]))
                heights = _plane_z(tri[mask][keep], centres) - floor_z
                covered = float(np.sum(areas[keep]))
                integral = float(np.sum(areas[keep] * heights))
                volume = float(np.sum(areas[keep] * np.maximum(heights, 0.0)))
    uncovered = max(0.0, area - covered)
    if fallback_z is not None:
        volume += uncovered * max(0.0, fallback_z - floor_z)
    return VolumeResult(volume_m3=volume, integral_m3=integral, covered_m2=min(covered, area), area_m2=area)


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


def _flat_triangles(triangles: np.ndarray, line_of: np.ndarray, soft: np.ndarray) -> np.ndarray:
    owners = line_of[triangles]
    same = (owners[:, 0] == owners[:, 1]) & (owners[:, 1] == owners[:, 2]) & (owners[:, 0] >= 0)
    return triangles[same & soft[np.maximum(owners[:, 0], 0)]]


def _idw_centres(vertices: np.ndarray, z: np.ndarray, flat: np.ndarray) -> np.ndarray:
    """Центры плоских треугольников с Z по трём ближайшим вершинам с другой Z."""

    centres = vertices[flat][:, :, :2].mean(axis=1)
    level = z[flat[:, 0]]
    finite = np.flatnonzero(np.isfinite(z))
    tree = cKDTree(vertices[finite, :2])
    k = min(len(finite), 24)
    distances, found = tree.query(centres, k=k)
    distances = np.atleast_2d(distances)
    found = np.atleast_2d(found)
    out = np.full(len(centres), np.nan)
    for row in range(len(centres)):
        picked: list[tuple[float, float]] = []
        for distance, index in zip(distances[row], found[row]):
            if not np.isfinite(distance):
                break
            value = z[finite[index]]
            if abs(value - level[row]) > _SAME_Z_M:
                picked.append((max(float(distance), 1e-9), float(value)))
                if len(picked) == IDW_NEIGHBOURS:
                    break
        if picked:
            weights = np.array([1 / d for d, _ in picked])
            out[row] = float(np.dot(weights, [v for _, v in picked]) / weights.sum())
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

    soft = np.array([line.soft for line in data.lines] or [False], dtype=bool)
    result = builder.build(xy, data.edges)
    full_z = _fill_nearest(result.vertices, _assign_new_z(result, z, data.edges, priority))
    line_of = np.concatenate([data.line_of, np.full(len(result.vertices) - len(xy), -1)])
    vertices = np.column_stack([result.vertices, full_z])
    flat = _flat_triangles(_trim(vertices, result.triangles, data.region), line_of, soft)
    flat_fixed = 0
    source = np.concatenate([np.arange(len(xy)), np.full(len(result.vertices) - len(xy), -1)])
    if len(flat):
        centres = _idw_centres(vertices, full_z, flat)
        centres = centres[np.isfinite(centres[:, 2])]
        if len(centres):
            flat_fixed = len(centres)
            xy2 = np.vstack([xy, centres[:, :2]])
            z2 = np.concatenate([z, centres[:, 2]])
            result = builder.build(xy2, data.edges)
            full_z = _fill_nearest(result.vertices, _assign_new_z(result, z2, data.edges, priority))
            vertices = np.column_stack([result.vertices, full_z])
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


def _neighbours(triangles: np.ndarray, count: int) -> list[np.ndarray]:
    if not len(triangles):
        return [np.zeros(0, dtype=int) for _ in range(count)]
    edges = np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    both = np.vstack([edges, edges[:, ::-1]])
    order = np.argsort(both[:, 0], kind="stable")
    both = both[order]
    starts = np.searchsorted(both[:, 0], np.arange(count + 1))
    return [both[starts[v] : starts[v + 1], 1] for v in range(count)]


def _fit_deviation(vertices: np.ndarray, vertex: int, around: np.ndarray) -> float | None:
    """Отклонение Z вершины от плоскости по её соседям (среднее, если соседи на одной прямой)."""

    if not len(around):
        return None
    d = vertices[around, :2] - vertices[vertex, :2]
    zs = vertices[around, 2]
    if len(around) >= 3:
        matrix = np.column_stack([np.ones(len(around)), d])
        if np.linalg.matrix_rank(matrix, tol=1e-6 * max(1.0, float(np.abs(d).max()))) == 3:
            coef, *_ = np.linalg.lstsq(matrix, zs, rcond=None)
            return float(vertices[vertex, 2] - coef[0])
    return float(vertices[vertex, 2] - zs.mean())


def _outliers(vertices: np.ndarray, triangles: np.ndarray, ids: list[str]) -> list[tuple[int, float]]:
    """Жадно: самый сильный выброс помечается и выпадает из соседей остальных."""

    candidates = [i for i, item in enumerate(ids) if item]
    if not candidates:
        return []
    around = _neighbours(triangles, len(vertices))
    deviation = {i: _fit_deviation(vertices, i, around[i]) for i in candidates}
    flagged: list[tuple[int, float]] = []
    removed: set[int] = set()
    while len(flagged) < MAX_OUTLIERS:
        live = [(abs(value), i) for i, value in deviation.items() if value is not None and i not in removed]
        if not live:
            break
        size, worst = max(live)
        if size <= OUTLIER_M:
            break
        flagged.append((worst, float(deviation[worst])))
        removed.add(worst)
        for other in around[worst].tolist():
            if other in deviation and other not in removed:
                keep = np.array([n for n in around[other].tolist() if n not in removed], dtype=int)
                deviation[other] = _fit_deviation(vertices, other, keep)
    return flagged


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


def _thresholds(data: SurfaceData, floor_z: float) -> list[Threshold]:
    """Участки нижней бровки выше подошвы больше чем на 0,5 м (§2)."""

    if not len(data.edges):
        return []
    picked = []
    for (a, b), number in zip(data.edges.tolist(), data.edge_line.tolist()):
        if data.lines[number].role != ROLE_CREST_BOTTOM:
            continue
        za, zb = data.z[a], data.z[b]
        if np.isfinite(za) and np.isfinite(zb) and max(za, zb) > floor_z + THRESHOLD_M:
            picked.append((a, b))
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
    marks = len(data.mass) + int(np.sum([data.lines[i].soft for i in data.line_of.tolist() if i >= 0]))
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
    roof.outliers = [
        Outlier(ids[i], (*frame.point_to_world((float(vertices[i, 0]), float(vertices[i, 1]))), float(vertices[i, 2])), value)
        for i, value in _outliers(vertices, triangles, ids)
    ]

    polygon = bottom_local or top_local
    if floor_z is None:
        roof.coverage_pct = _volume_local(vertices, triangles, polygon, 0.0, None).coverage_pct
        warnings.append(CadWarning("floor_missing", "Подошва не задана — высота уступа и объём не считаются."))
    else:
        roof.thresholds = _thresholds(data, floor_z)
        top_volume = _volume_local(vertices, triangles, top_local, floor_z, None)
        if top_volume.covered_m2 > 0:
            roof.mean_height_m = top_volume.integral_m3 / top_volume.covered_m2
        block = _volume_local(vertices, triangles, polygon, floor_z, crest_z)
        roof.coverage_pct = block.coverage_pct
        roof.volume_m3 = block.volume_m3
        _check_height(roof)
    if roof.triangle_count and roof.coverage_pct < FULL_COVERAGE_PCT:
        warnings.append(
            CadWarning(
                "coverage",
                f"Кровля покрывает {ru_number(roof.coverage_pct, 1)} % контура"
                + (": остальное посчитано по отметке бровки." if crest_z is not None else "."),
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
