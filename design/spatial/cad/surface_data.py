"""Данные кровли блока по ролям линий чертежа (TASK-013, PR 3).

Кровля — одна TIN с ограничениями (§2 «Поверхность и подошва»). Здесь
собирается то, что в неё идёт:

| Роль | Как входит |
| --- | --- |
| бровки верхняя и нижняя | жёсткий ограничитель, вершины через ≤ 1 м |
| характерная линия с Z | жёсткий ограничитель |
| линия без Z (2D-бровка, характерная) | ограничитель, Z — с поверхности без неё |
| горизонталь | точки через 2 м и мягкий ограничитель |
| отметки поверхности | массовые точки: точки, знаки, вершины 3D-съёмки |

Z = 0 у линии чертежа — отметки нет (2D), а не «0 м». Всё дальше 20 м от
контура (по верхней и нижней бровке) отсекается до триангуляции, поэтому
горизонтали всего карьера не тормозят предпросмотр. Пересечения
ограничителей вставляются вершиной в обе линии, Z — по приоритету «верхняя
бровка > нижняя > характерная > горизонталь > точка»; расхождение больше
0,2 м — в списке качества. Точка ближе 0,1 м к ограничителю с другой Z берёт
его Z и помечается.

Координаты МСК — миллионы метров: всё считается в локальной системе
(`LocalFrame`), места для пользователя возвращаются в координатах чертежа.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Polygon

from design.spatial.cad.contour import MAX_CROSSING_PAIRS
from design.spatial.cad.model import (
    ROLE_CONTOUR_LINE,
    ROLE_CREST_BOTTOM,
    ROLE_CREST_TOP,
    ROLE_FEATURE_LINE,
    ROLE_SPOT_HEIGHTS,
    ZERO_Z_TOLERANCE_M,
    CadEntity,
    CadWarning,
)
from design.spatial.cad.rings import XY, LocalFrame

SURFACE_BUFFER_M = 20.0
CREST_STEP_M = 1.0
CONTOUR_STEP_M = 2.0
# Характерные линии и линии без Z уплотняются как горизонтали: иначе длинный
# отрезок дал бы рёбра длиннее предела и дыру в кровле вдоль линии.
FEATURE_STEP_M = 2.0
CONFLICT_REPORT_M = 0.2
SNAP_TO_CONSTRAINT_M = 0.1
# Точки ближе этого — одна вершина.
MERGE_M = 0.001
# Разница Z меньше этого — та же отметка (точка не помечается).
SAME_Z_M = 0.001
MAX_SURFACE_POINTS = 50_000
MAX_CONSTRAINT_SEGMENTS = 20_000
_QUERY_CHUNK = 256

SURFACE_ROLES: tuple[str, ...] = (
    ROLE_CREST_TOP,
    ROLE_CREST_BOTTOM,
    ROLE_FEATURE_LINE,
    ROLE_CONTOUR_LINE,
    ROLE_SPOT_HEIGHTS,
)
LINE_SURFACE_ROLES = frozenset({ROLE_CREST_TOP, ROLE_CREST_BOTTOM, ROLE_FEATURE_LINE, ROLE_CONTOUR_LINE})
# Приоритет Z на пересечении ограничителей (§2).
ROLE_PRIORITY: dict[str, int] = {
    ROLE_CREST_TOP: 4,
    ROLE_CREST_BOTTOM: 3,
    ROLE_FEATURE_LINE: 2,
    ROLE_CONTOUR_LINE: 1,
    ROLE_SPOT_HEIGHTS: 0,
}


class SurfaceInputError(ValueError):
    """Данные не годятся для кровли (пределы, нет контура) — текст для пользователя."""


@dataclass
class SurfaceLine:
    """Линия-ограничитель после отсечения и уплотнения."""

    role: str
    handle: str
    has_z: bool
    # Горизонталь: мягкий ограничитель, защита от плоских треугольников.
    soft: bool = False


@dataclass
class ConflictValue:
    role: str
    handle: str
    z: float


@dataclass
class Conflict:
    """Разные Z в одном месте: пересечение ограничителей или дубль точки."""

    kind: str
    point: XY
    values: list[ConflictValue]
    accepted_z: float


@dataclass
class Snapped:
    """Точка у ограничителя взяла его Z."""

    id: str
    point: XY
    from_z: float
    to_z: float


@dataclass
class SurfaceData:
    """Вершины (локальная система) и рёбра-ограничители кровли.

    `z` — NaN у вершин линий без отметки: Z им даст поверхность без них.
    `point_id` — у массовых точек их id (handle точки или «handle:вершина»
    линии съёмки), у вершин линий — пустая строка.
    """

    frame: LocalFrame
    region: Polygon
    xy: np.ndarray
    z: np.ndarray
    priority: np.ndarray
    line_of: np.ndarray
    point_id: list[str]
    edges: np.ndarray
    edge_line: np.ndarray
    lines: list[SurfaceLine]
    conflicts: list[Conflict] = field(default_factory=list)
    snapped: list[Snapped] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    warnings: list[CadWarning] = field(default_factory=list)
    # Отметок у контура без исключённых — и тех, что слились с вершиной линии.
    spot_count: int = 0

    @property
    def mass(self) -> np.ndarray:
        """Индексы массовых точек (отметок)."""

        return np.array([i for i, item in enumerate(self.point_id) if item], dtype=int)

    def to_world(self, index: int) -> XY:
        return self.frame.point_to_world((float(self.xy[index, 0]), float(self.xy[index, 1])))


def _has_z(z: float) -> bool:
    return abs(z) > ZERO_Z_TOLERANCE_M


def _local_z(points: Sequence[Sequence[float]], frame: LocalFrame) -> np.ndarray:
    array = np.asarray(points, dtype=float).reshape(-1, 3).copy()
    array[:, 0] -= frame.ox
    array[:, 1] -= frame.oy
    array[np.abs(array[:, 2]) <= ZERO_Z_TOLERANCE_M, 2] = np.nan
    return array


def _region(top: Sequence[XY], bottom: Sequence[XY] | None, frame: LocalFrame) -> Polygon:
    rings = [frame.to_local(top)]
    if bottom and len(bottom) >= 3:
        rings.append(frame.to_local(bottom))
    shapes = [Polygon(ring).buffer(0) for ring in rings]
    region = shapely.union_all(shapes).buffer(SURFACE_BUFFER_M)
    if region.geom_type != "Polygon":
        region = region.convex_hull
    return region


# --- отсечение и уплотнение ------------------------------------------------


def _clip_runs(points: np.ndarray, region: Polygon) -> list[np.ndarray]:
    """Куски линии внутри области: Z на границе — по отрезку."""

    if len(points) < 2:
        return []
    starts, ends = points[:-1], points[1:]
    segments = shapely.linestrings(np.stack([starts[:, :2], ends[:, :2]], axis=1))
    hits = shapely.intersects(segments, region)
    runs: list[np.ndarray] = []
    current: list[np.ndarray] = []
    last_end: tuple[int, float] | None = None
    for k in np.flatnonzero(hits).tolist():
        a, b = starts[k], ends[k]
        length2 = float(np.dot(b[:2] - a[:2], b[:2] - a[:2]))
        pieces = []
        if length2 == 0:
            # Отрезок нулевой длины (ограничитель из одной точки): его отметка
            # остаётся вершиной без рёбер.
            pieces.append((0.0, 1.0))
        for part in _linear_parts(shapely.intersection(segments[k], region)) if length2 else []:
            coords = np.asarray(part.coords)[:, :2]
            ts = sorted(float(np.dot(c - a[:2], b[:2] - a[:2]) / length2) for c in (coords[0], coords[-1]))
            pieces.append((max(0.0, ts[0]), min(1.0, ts[1])))
        for t0, t1 in sorted(pieces):
            p0 = a + (b - a) * t0
            p1 = a + (b - a) * t1
            continues = last_end is not None and last_end[0] == k - 1 and last_end[1] >= 1.0 - 1e-9 and t0 <= 1e-9
            if continues and current:
                current.append(p1)
            else:
                if len(current) >= 2:
                    runs.append(np.array(current))
                current = [p0, p1]
            last_end = (k, t1)
    if len(current) >= 2:
        runs.append(np.array(current))
    return runs


def _linear_parts(geometry) -> list[LineString]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [part for item in geometry.geoms for part in _linear_parts(item)]
    return []


def _densify_count(run: np.ndarray, step: float) -> int:
    lengths = np.hypot(*(run[1:, :2] - run[:-1, :2]).T)
    return int(np.sum(np.maximum(1, np.ceil(lengths / step))))


def _densify(run: np.ndarray, step: float) -> np.ndarray:
    out = [run[0]]
    for a, b in zip(run[:-1], run[1:]):
        count = max(1, math.ceil(math.hypot(*(b[:2] - a[:2])) / step))
        for k in range(1, count + 1):
            out.append(a + (b - a) * (k / count))
    return np.array(out)


def _step(role: str) -> float:
    if role in (ROLE_CREST_TOP, ROLE_CREST_BOTTOM):
        return CREST_STEP_M
    if role == ROLE_CONTOUR_LINE:
        return CONTOUR_STEP_M
    return FEATURE_STEP_M


# --- пересечения ограничителей ----------------------------------------------


def _crossings(runs: list[np.ndarray]) -> list[list[tuple[int, float]]]:
    """Куда вставить вершины: для каждой линии — (отрезок, параметр t)."""

    starts, ends, owner, index = [], [], [], []
    for number, run in enumerate(runs):
        for k in range(len(run) - 1):
            starts.append(run[k, :2])
            ends.append(run[k + 1, :2])
            owner.append(number)
            index.append(k)
    inserts: list[list[tuple[int, float]]] = [[] for _ in runs]
    if not starts:
        return inserts
    a = np.asarray(starts)
    b = np.asarray(ends)
    owners = np.asarray(owner)
    orders = np.asarray(index)
    last = np.asarray([len(run) - 2 for run in runs])[owners]
    closed = np.asarray([len(run) > 3 and np.allclose(run[0, :2], run[-1, :2]) for run in runs])[owners]
    segments = shapely.linestrings(np.stack([a, b], axis=1))
    tree = shapely.STRtree(segments)
    pairs = 0
    for begin in range(0, len(segments), _QUERY_CHUNK):
        left, right = tree.query(segments[begin : begin + _QUERY_CHUNK], predicate="intersects")
        left = left + begin
        step = np.abs(orders[left] - orders[right])
        neighbours = (owners[left] == owners[right]) & ((step == 1) | (closed[left] & (step == last[left])))
        keep = (left < right) & ~neighbours
        pairs += int(np.count_nonzero(keep))
        if pairs > MAX_CROSSING_PAIRS:
            raise SurfaceInputError(
                f"Пересечений линий поверхности слишком много: больше {MAX_CROSSING_PAIRS} пар отрезков. "
                "Снимите лишние роли в поверхности."
            )
        for i, j in zip(left[keep].tolist(), right[keep].tolist()):
            for (seg, t), (seg2, u) in _segment_crossings(a[i], b[i], a[j], b[j], i, j):
                for number, at in ((seg, t), (seg2, u)):
                    if 1e-9 < at < 1.0 - 1e-9:
                        inserts[int(owners[number])].append((int(orders[number]), at))
    return inserts


def _segment_crossings(p, p2, q, q2, i: int, j: int) -> list[tuple[tuple[int, float], tuple[int, float]]]:
    r = p2 - p
    s = q2 - q
    denom = r[0] * s[1] - r[1] * s[0]
    qp = q - p
    rr = float(np.dot(r, r))
    ss = float(np.dot(s, s))
    if abs(denom) > 1e-12 * max(rr, ss, 1e-12):
        t = (qp[0] * s[1] - qp[1] * s[0]) / denom
        u = (qp[0] * r[1] - qp[1] * r[0]) / denom
        if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
            return [((i, min(1.0, max(0.0, t))), (j, min(1.0, max(0.0, u))))]
        return []
    # Параллельные: у наложения концы одного отрезка вставляются в другой.
    found = []
    if rr > 0:
        for end, u in ((q, 0.0), (q2, 1.0)):
            t = float(np.dot(end - p, r) / rr)
            if 0 < t < 1 and _dist_to_line(end, p, r) <= 1e-9 * max(1.0, math.sqrt(rr)):
                found.append(((i, t), (j, u)))
    if ss > 0:
        for end, t in ((p, 0.0), (p2, 1.0)):
            u = float(np.dot(end - q, s) / ss)
            if 0 < u < 1 and _dist_to_line(end, q, s) <= 1e-9 * max(1.0, math.sqrt(ss)):
                found.append(((i, t), (j, u)))
    return found


def _dist_to_line(point, origin, direction) -> float:
    d = point - origin
    length = math.hypot(direction[0], direction[1])
    return abs(d[0] * direction[1] - d[1] * direction[0]) / length if length else math.hypot(*d)


def _insert(run: np.ndarray, inserts: list[tuple[int, float]]) -> np.ndarray:
    if not inserts:
        return run
    by_segment: dict[int, list[float]] = {}
    for seg, t in inserts:
        by_segment.setdefault(seg, []).append(t)
    out = [run[0]]
    for k in range(len(run) - 1):
        a, b = run[k], run[k + 1]
        for t in sorted(set(by_segment.get(k, []))):
            out.append(a + (b - a) * t)
        out.append(b)
    return np.array(out)


# --- сборка и слияние вершин ------------------------------------------------


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def collect_surface_data(
    entities: Iterable[CadEntity],
    top: Sequence[XY],
    bottom: Sequence[XY] | None,
    *,
    roles: Iterable[str] | None = None,
    excluded: Iterable[str] | None = None,
) -> SurfaceData:
    """Вершины и ограничители кровли в контуре + 20 м."""

    if len(top) < 3:
        raise SurfaceInputError("Контур блока не задан — постройте его на шаге «Контур».")
    used = set(SURFACE_ROLES) if roles is None else set(roles) & set(SURFACE_ROLES)
    skip = set(excluded or ())
    frame = LocalFrame.of([*top, *(bottom or [])])
    region = _region(top, bottom, frame)
    shapely.prepare(region)
    min_x, min_y, max_x, max_y = region.bounds
    warnings: list[CadWarning] = []

    # Отметки поверхности — массовые точки.
    mass_xyz: list[tuple[float, float, float]] = []
    mass_ids: list[str] = []
    line_entities: list[CadEntity] = []
    for entity in entities:
        if entity.role not in used:
            continue
        if entity.role == ROLE_SPOT_HEIGHTS:
            if entity.geometry_type == "text":
                continue
            single = entity.geometry_type == "point"
            for number, (x, y, z) in enumerate(entity.points):
                if _has_z(z):
                    mass_xyz.append((x - frame.ox, y - frame.oy, z))
                    mass_ids.append(entity.handle if single else f"{entity.handle}:{number}")
        elif entity.geometry_type == "line" and len(entity.points) >= 2:
            line_entities.append(entity)

    mass = np.asarray(mass_xyz, dtype=float).reshape(-1, 3)
    inside = shapely.contains_xy(region, mass[:, 0], mass[:, 1]) if len(mass) else np.zeros(0, dtype=bool)
    mass = mass[inside]
    mass_ids = [item for item, keep in zip(mass_ids, inside.tolist()) if keep]
    if len(mass) > MAX_SURFACE_POINTS:
        raise SurfaceInputError(
            f"Отметок у контура слишком много: {len(mass)} точек, предел {MAX_SURFACE_POINTS}. "
            "Снимите роль «Отметки поверхности» у лишних слоёв."
        )
    found_excluded = sorted({item for item in mass_ids if item in skip})
    keep = [item not in skip for item in mass_ids]
    mass = mass[np.asarray(keep, dtype=bool)] if len(mass) else mass
    mass_ids = [item for item, ok in zip(mass_ids, keep) if ok]

    # Линии: отсечение, оценка размера, уплотнение.
    clipped: list[tuple[CadEntity, np.ndarray]] = []
    segments = 0
    vertices = len(mass)
    for entity in line_entities:
        xs = [p[0] - frame.ox for p in entity.points]
        ys = [p[1] - frame.oy for p in entity.points]
        if max(xs) < min_x or min(xs) > max_x or max(ys) < min_y or min(ys) > max_y:
            continue
        for run in _clip_runs(_local_z(entity.points, frame), region):
            count = _densify_count(run, _step(entity.role))
            segments += count
            vertices += count + 1
            clipped.append((entity, run))
    if segments > MAX_CONSTRAINT_SEGMENTS:
        raise SurfaceInputError(
            f"Линий поверхности у контура слишком много: {segments} отрезков, предел {MAX_CONSTRAINT_SEGMENTS}. "
            "Снимите лишние роли в поверхности."
        )
    if vertices > MAX_SURFACE_POINTS:
        raise SurfaceInputError(
            f"Данных поверхности у контура слишком много: {vertices} точек, предел {MAX_SURFACE_POINTS}. "
            "Снимите лишние роли в поверхности."
        )

    lines: list[SurfaceLine] = []
    runs: list[np.ndarray] = []
    for entity, run in clipped:
        dense = _densify(run, _step(entity.role))
        lines.append(
            SurfaceLine(
                role=entity.role,
                handle=entity.handle,
                has_z=bool(np.any(np.isfinite(dense[:, 2]))),
                soft=entity.role == ROLE_CONTOUR_LINE,
            )
        )
        runs.append(dense)
    for number, inserts in enumerate(_crossings(runs)):
        runs[number] = _insert(runs[number], inserts)

    if not any(line.role == ROLE_CREST_TOP for line in lines):
        warnings.append(
            CadWarning(
                "no_crest_top",
                "Верхней бровки нет — первый ряд без бровки: устья у откоса могут лечь ниже площадки.",
            )
        )

    data = _assemble(frame, region, runs, lines, mass, mass_ids)
    data.excluded = found_excluded
    data.spot_count = len(mass)
    data.warnings = warnings
    _snap_points(data)
    return data


def _assemble(
    frame: LocalFrame,
    region: Polygon,
    runs: list[np.ndarray],
    lines: list[SurfaceLine],
    mass: np.ndarray,
    mass_ids: list[str],
) -> SurfaceData:
    xyz = np.concatenate([*runs, mass]).reshape(-1, 3)
    line_of = np.concatenate([np.full(len(run), number) for number, run in enumerate(runs)] + [np.full(len(mass), -1)]).astype(int)
    priority = np.array([ROLE_PRIORITY[lines[i].role] if i >= 0 else 0 for i in line_of.tolist()], dtype=int)
    point_id = [""] * (len(xyz) - len(mass)) + list(mass_ids)
    edges: list[tuple[int, int]] = []
    edge_line: list[int] = []
    offset = 0
    for number, run in enumerate(runs):
        for k in range(len(run) - 1):
            edges.append((offset + k, offset + k + 1))
            edge_line.append(number)
        offset += len(run)

    # Слияние вершин ближе 1 мм: Z по приоритету, расхождения — в конфликты.
    union = _UnionFind(len(xyz))
    if len(xyz) > 1:
        for a, b in cKDTree(xyz[:, :2]).query_pairs(MERGE_M):
            union.union(int(a), int(b))
    groups: dict[int, list[int]] = {}
    for index in range(len(xyz)):
        groups.setdefault(union.find(index), []).append(index)

    new_index = np.empty(len(xyz), dtype=int)
    out_xy: list[tuple[float, float]] = []
    out_z: list[float] = []
    out_priority: list[int] = []
    out_line: list[int] = []
    out_id: list[str] = []
    conflicts: list[Conflict] = []
    snapped: list[Snapped] = []
    for members in groups.values():
        number = len(out_xy)
        for member in members:
            new_index[member] = number
        line_members = [m for m in members if line_of[m] >= 0]
        point_members = [m for m in members if line_of[m] < 0]
        rep = max(line_members or members, key=lambda m: (priority[m], np.isfinite(xyz[m, 2]), -m))
        with_z = [m for m in members if np.isfinite(xyz[m, 2])]
        line_with_z = [m for m in line_members if np.isfinite(xyz[m, 2])]
        z = math.nan
        if line_with_z:
            best = max(priority[m] for m in line_with_z)
            z = float(np.mean([xyz[m, 2] for m in line_with_z if priority[m] == best]))
            values = sorted({(lines[line_of[m]].role, lines[line_of[m]].handle, float(xyz[m, 2])) for m in line_with_z})
            spread = max(v[2] for v in values) - min(v[2] for v in values)
            if len({(role, handle) for role, handle, _ in values}) > 1 and spread > CONFLICT_REPORT_M:
                conflicts.append(
                    Conflict(
                        "crossing",
                        frame.point_to_world((float(xyz[rep, 0]), float(xyz[rep, 1]))),
                        [ConflictValue(role, handle, value) for role, handle, value in values],
                        z,
                    )
                )
        elif with_z:
            z = float(np.mean([xyz[m, 2] for m in with_z]))
            spread = max(xyz[m, 2] for m in with_z) - min(xyz[m, 2] for m in with_z)
            if len(point_members) > 1 and spread > CONFLICT_REPORT_M:
                conflicts.append(
                    Conflict(
                        "duplicate",
                        frame.point_to_world((float(xyz[rep, 0]), float(xyz[rep, 1]))),
                        [ConflictValue(ROLE_SPOT_HEIGHTS, point_id[m], float(xyz[m, 2])) for m in point_members],
                        z,
                    )
                )
        if line_with_z:
            for m in point_members:
                if abs(xyz[m, 2] - z) > SAME_Z_M:
                    snapped.append(
                        Snapped(point_id[m], frame.point_to_world((float(xyz[m, 0]), float(xyz[m, 1]))), float(xyz[m, 2]), z)
                    )
        out_xy.append((float(xyz[rep, 0]), float(xyz[rep, 1])))
        out_z.append(z)
        out_priority.append(int(max(priority[m] for m in members)))
        out_line.append(int(line_of[rep]))
        out_id.append("" if line_members else point_id[rep])

    remapped: dict[tuple[int, int], int] = {}
    for (a, b), number in zip(edges, edge_line):
        na, nb = int(new_index[a]), int(new_index[b])
        if na == nb:
            continue
        key = (min(na, nb), max(na, nb))
        remapped.setdefault(key, number)
    return SurfaceData(
        frame=frame,
        region=region,
        xy=np.asarray(out_xy, dtype=float).reshape(-1, 2),
        z=np.asarray(out_z, dtype=float),
        priority=np.asarray(out_priority, dtype=int),
        line_of=np.asarray(out_line, dtype=int),
        point_id=out_id,
        edges=np.asarray(list(remapped), dtype=int).reshape(-1, 2),
        edge_line=np.asarray(list(remapped.values()), dtype=int),
        lines=lines,
        conflicts=conflicts,
        snapped=snapped,
    )


def _snap_points(data: SurfaceData) -> None:
    """Точка ближе 0,1 м к ограничителю с Z берёт его Z (§2) и помечается."""

    mass = data.mass
    if not len(mass) or not len(data.edges):
        return
    a = data.xy[data.edges[:, 0]]
    b = data.xy[data.edges[:, 1]]
    za = data.z[data.edges[:, 0]]
    zb = data.z[data.edges[:, 1]]
    usable = np.isfinite(za) & np.isfinite(zb)
    if not np.any(usable):
        return
    a, b, za, zb = a[usable], b[usable], za[usable], zb[usable]
    tree = shapely.STRtree(shapely.linestrings(np.stack([a, b], axis=1)))
    points = shapely.points(data.xy[mass])
    found, distances = tree.query_nearest(points, max_distance=SNAP_TO_CONSTRAINT_M, return_distance=True, all_matches=False)
    for (where, segment), _ in zip(found.T.tolist(), distances.tolist()):
        index = int(mass[where])
        p = data.xy[index]
        d = b[segment] - a[segment]
        length2 = float(np.dot(d, d))
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, float(np.dot(p - a[segment], d)) / length2))
        z = float(za[segment] + (zb[segment] - za[segment]) * t)
        if abs(data.z[index] - z) > SAME_Z_M:
            data.snapped.append(Snapped(data.point_id[index], data.to_world(index), float(data.z[index]), z))
            data.z[index] = z
