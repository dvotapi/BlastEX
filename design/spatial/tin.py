"""Треугольная сеть (TIN) и операции пересечения с ней.

Сеть строится как 2.5D: триангуляция Делоне в плане, Z интерполируется
барицентрически. Для почти вертикального откоса точки сначала кладутся
на локальную плоскость (длинная горизонталь + Z), затем поднимаются обратно.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from design.models import Point3

_EPS = 1e-12
_LOCATE_EPS = 1e-9
_MAX_TIN_POINTS = 2500


@dataclass
class TIN:
    """Неструктурированная треугольная сеть: вершины + индексы треугольников."""

    vertices: list[Point3] = field(default_factory=list)
    triangles: list[tuple[int, int, int]] = field(default_factory=list)

    _origin: tuple[float, float] = field(default=(0.0, 0.0), repr=False, compare=False)
    _cell: float = field(default=1.0, repr=False, compare=False)
    _cols: int = field(default=0, repr=False, compare=False)
    _rows: int = field(default=0, repr=False, compare=False)
    _buckets: list[list[int]] = field(default_factory=list, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._rebuild_index()

    def to_dict(self) -> dict:
        return {
            "vertices": [v.to_dict() for v in self.vertices],
            "triangles": [list(t) for t in self.triangles],
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> TIN:
        data = data or {}
        triangles: list[tuple[int, int, int]] = []
        for raw in data.get("triangles", []):
            if len(raw) >= 3:
                triangles.append((int(raw[0]), int(raw[1]), int(raw[2])))
        return cls(
            vertices=[Point3.from_dict(v) for v in data.get("vertices", [])],
            triangles=triangles,
        )

    @property
    def is_empty(self) -> bool:
        return not self.vertices or not self.triangles

    def bounds(self) -> tuple[float, float, float, float, float, float] | None:
        if not self.vertices:
            return None
        xs = [v.x for v in self.vertices]
        ys = [v.y for v in self.vertices]
        zs = [v.z for v in self.vertices]
        return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)

    def elevation_at(self, x: float, y: float) -> float | None:
        """Отметка поверхности в (x, y) или None, если точка вне выпуклой оболочки."""
        tri = self._locate_xy(x, y)
        if tri is None:
            return None
        i, j, k = self.triangles[tri]
        return _barycentric_z(self.vertices[i], self.vertices[j], self.vertices[k], x, y)

    def vertical_intersection(self, x: float, y: float) -> Point3 | None:
        z = self.elevation_at(x, y)
        if z is None:
            return None
        return Point3(x=x, y=y, z=z)

    def line_intersection(self, p0: Point3, p1: Point3) -> Point3 | None:
        """Ближайшее к `p0` пересечение отрезка p0→p1 с треугольниками сети."""
        direction = (p1.x - p0.x, p1.y - p0.y, p1.z - p0.z)
        best_t = 1.0 + 1e-9
        best: Point3 | None = None
        for i, j, k in self.triangles:
            hit = _segment_triangle(p0, direction, self.vertices[i], self.vertices[j], self.vertices[k])
            if hit is None:
                continue
            t, point = hit
            if 0.0 <= t <= 1.0 and t < best_t:
                best_t = t
                best = point
        return best

    def distance_to_surface(self, point: Point3) -> float | None:
        """Расстояние до сети. Для 2.5D над треугольником — signed (точка минус поверхность)."""
        z = self.elevation_at(point.x, point.y)
        if z is not None:
            return point.z - z
        if self.is_empty:
            return None
        best: float | None = None
        for i, j, k in self.triangles:
            dist = _point_triangle_distance(point, self.vertices[i], self.vertices[j], self.vertices[k])
            if best is None or dist < best:
                best = dist
        return best

    def sample_line(self, x0: float, y0: float, x1: float, y1: float, count: int = 48) -> list[Point3]:
        """Профиль поверхности вдоль отрезка в плане (пропуски вне TIN отбрасываются)."""
        count = max(2, int(count))
        points: list[Point3] = []
        for i in range(count):
            t = i / (count - 1)
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            hit = self.vertical_intersection(x, y)
            if hit is not None:
                points.append(hit)
        return points

    def _rebuild_index(self) -> None:
        if not self.triangles or not self.vertices:
            self._cols = self._rows = 0
            self._buckets = []
            return
        xs = [v.x for v in self.vertices]
        ys = [v.y for v in self.vertices]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span = max(max_x - min_x, max_y - min_y, 1.0)
        cells = max(4, min(40, int(math.sqrt(len(self.triangles)) * 1.5) or 4))
        self._cell = span / cells
        self._origin = (min_x, min_y)
        self._cols = cells
        self._rows = cells
        self._buckets = [[] for _ in range(cells * cells)]
        for idx, (i, j, k) in enumerate(self.triangles):
            a, b, c = self.vertices[i], self.vertices[j], self.vertices[k]
            tmin_x = min(a.x, b.x, c.x)
            tmax_x = max(a.x, b.x, c.x)
            tmin_y = min(a.y, b.y, c.y)
            tmax_y = max(a.y, b.y, c.y)
            c0, r0 = self._cell_of(tmin_x, tmin_y)
            c1, r1 = self._cell_of(tmax_x, tmax_y)
            for row in range(r0, r1 + 1):
                for col in range(c0, c1 + 1):
                    self._buckets[row * self._cols + col].append(idx)

    def _cell_of(self, x: float, y: float) -> tuple[int, int]:
        col = int((x - self._origin[0]) / self._cell) if self._cell else 0
        row = int((y - self._origin[1]) / self._cell) if self._cell else 0
        return max(0, min(self._cols - 1, col)), max(0, min(self._rows - 1, row))

    def _locate_xy(self, x: float, y: float) -> int | None:
        if not self._buckets:
            return None
        col, row = self._cell_of(x, y)
        for idx in self._buckets[row * self._cols + col]:
            i, j, k = self.triangles[idx]
            if _point_in_triangle_xy(self.vertices[i], self.vertices[j], self.vertices[k], x, y):
                return idx
        # Соседние ячейки — точка на границе ячейки.
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = row + dr, col + dc
                if 0 <= rr < self._rows and 0 <= cc < self._cols:
                    for idx in self._buckets[rr * self._cols + cc]:
                        i, j, k = self.triangles[idx]
                        if _point_in_triangle_xy(self.vertices[i], self.vertices[j], self.vertices[k], x, y):
                            return idx
        return None


def build_tin(points: Iterable[Point3], *, max_points: int = _MAX_TIN_POINTS) -> TIN:
    """Строит TIN по облаку точек. Почти вертикальные наборы кладутся в локальную СК."""
    cleaned = _prepare_points(points, max_points)
    if len(cleaned) < 3:
        return TIN(vertices=cleaned, triangles=[])
    if _is_steep(cleaned):
        return _tin_on_best_plane(cleaned)
    triangles = _delaunay_xy([(p.x, p.y) for p in cleaned])
    return TIN(vertices=cleaned, triangles=triangles)


def loft_polylines(upper: list[Point3], lower: list[Point3], *, samples: int | None = None) -> TIN:
    """Линейчатая поверхность между двумя полилиниями (бровка и подошва откоса)."""
    if len(upper) < 2 or len(lower) < 2:
        return build_tin([*upper, *lower])
    count = samples or max(len(upper), len(lower), 8)
    count = max(2, min(count, 400))
    top = _resample_polyline(upper, count)
    bot = _resample_polyline(lower, count)
    vertices = top + bot
    triangles: list[tuple[int, int, int]] = []
    for i in range(count - 1):
        a, a1 = i, i + 1
        b, b1 = count + i, count + i + 1
        triangles.append(_ccw_xyz(vertices, a, a1, b))
        triangles.append(_ccw_xyz(vertices, a1, b1, b))
    return TIN(vertices=vertices, triangles=triangles)


def _prepare_points(points: Iterable[Point3], max_points: int) -> list[Point3]:
    unique: dict[tuple[int, int], Point3] = {}
    for point in points:
        key = (round(point.x * 1e6), round(point.y * 1e6))
        prev = unique.get(key)
        if prev is None or point.z > prev.z:
            unique[key] = Point3(x=point.x, y=point.y, z=point.z)
    cleaned = list(unique.values())
    if len(cleaned) <= max_points:
        return cleaned
    xs = [p.x for p in cleaned]
    ys = [p.y for p in cleaned]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    side = max(8, int(math.sqrt(max_points)))
    cell_w = max((max_x - min_x) / side, 1e-6)
    cell_h = max((max_y - min_y) / side, 1e-6)
    bins: dict[tuple[int, int], list[Point3]] = {}
    for point in cleaned:
        key = (int((point.x - min_x) / cell_w), int((point.y - min_y) / cell_h))
        bins.setdefault(key, []).append(point)
    reduced: list[Point3] = []
    for group in bins.values():
        n = len(group)
        reduced.append(
            Point3(
                x=sum(p.x for p in group) / n,
                y=sum(p.y for p in group) / n,
                z=sum(p.z for p in group) / n,
            )
        )
    return reduced


def _is_steep(points: list[Point3]) -> bool:
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    xy_span = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    z_span = max(zs) - min(zs)
    return z_span > xy_span * 2.5 and z_span > 1.0


def _tin_on_best_plane(points: list[Point3]) -> TIN:
    """Триангуляция в локальной плоскости: ось вдоль простирания, вторая — по Z."""
    origin = points[0]
    axis = _longest_horizontal_axis(points)
    ux, uy = axis
    local = [((p.x - origin.x) * ux + (p.y - origin.y) * uy, p.z) for p in points]
    triangles = _delaunay_xy(local)
    return TIN(vertices=list(points), triangles=triangles)


def _longest_horizontal_axis(points: list[Point3]) -> tuple[float, float]:
    best = (1.0, 0.0)
    best_len = 0.0
    for i, a in enumerate(points):
        for b in points[i + 1 :]:
            dx, dy = b.x - a.x, b.y - a.y
            length = math.hypot(dx, dy)
            if length > best_len:
                best_len = length
                best = (dx / length, dy / length) if length > _EPS else (1.0, 0.0)
    return best


def _delaunay_xy(pts: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    n = len(pts)
    if n < 3:
        return []
    min_x = min(p[0] for p in pts)
    max_x = max(p[0] for p in pts)
    min_y = min(p[1] for p in pts)
    max_y = max(p[1] for p in pts)
    dx = max(max_x - min_x, 1.0)
    dy = max(max_y - min_y, 1.0)
    d = max(dx, dy) * 20.0
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5
    super_verts = [(cx, cy + 3 * d), (cx - 3 * d, cy - 2 * d), (cx + 3 * d, cy - 2 * d)]
    verts = list(pts) + super_verts
    s0, s1, s2 = n, n + 1, n + 2
    triangles: list[tuple[int, int, int]] = [(s0, s1, s2)]

    for i, point in enumerate(pts):
        bad: list[tuple[int, int, int]] = []
        for tri in triangles:
            if _in_circumcircle(verts[tri[0]], verts[tri[1]], verts[tri[2]], point):
                bad.append(tri)
        edge_count: dict[tuple[int, int], int] = {}
        for a, b, c in bad:
            for edge in ((a, b), (b, c), (c, a)):
                key = (edge[0], edge[1]) if edge[0] < edge[1] else (edge[1], edge[0])
                edge_count[key] = edge_count.get(key, 0) + 1
        bad_set = set(bad)
        triangles = [t for t in triangles if t not in bad_set]
        for (a, b), count in edge_count.items():
            if count == 1:
                triangles.append(_ccw(verts, a, b, i))

    return [t for t in triangles if s0 not in t and s1 not in t and s2 not in t]


def _ccw(
    verts: list[tuple[float, float]], i: int, j: int, k: int
) -> tuple[int, int, int]:
    ax, ay = verts[i]
    bx, by = verts[j]
    cx, cy = verts[k]
    if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0:
        return (i, k, j)
    return (i, j, k)


def _ccw_xyz(verts: list[Point3], i: int, j: int, k: int) -> tuple[int, int, int]:
    return _ccw([(v.x, v.y) for v in verts], i, j, k)


def _in_circumcircle(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    p: tuple[float, float],
) -> bool:
    ax, ay = a[0] - p[0], a[1] - p[1]
    bx, by = b[0] - p[0], b[1] - p[1]
    cx, cy = c[0] - p[0], c[1] - p[1]
    det = (
        (ax * ax + ay * ay) * (bx * cy - by * cx)
        - (bx * bx + by * by) * (ax * cy - ay * cx)
        + (cx * cx + cy * cy) * (ax * by - ay * bx)
    )
    orient = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(orient) < _EPS:
        return False
    return (det > 0) == (orient > 0)


def _point_in_triangle_xy(a: Point3, b: Point3, c: Point3, x: float, y: float) -> bool:
    v0x, v0y = c.x - a.x, c.y - a.y
    v1x, v1y = b.x - a.x, b.y - a.y
    v2x, v2y = x - a.x, y - a.y
    dot00 = v0x * v0x + v0y * v0y
    dot01 = v0x * v1x + v0y * v1y
    dot02 = v0x * v2x + v0y * v2y
    dot11 = v1x * v1x + v1y * v1y
    dot12 = v1x * v2x + v1y * v2y
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < _EPS:
        return False
    u = (dot11 * dot02 - dot01 * dot12) / denom
    v = (dot00 * dot12 - dot01 * dot02) / denom
    return u >= -_LOCATE_EPS and v >= -_LOCATE_EPS and (u + v) <= 1.0 + _LOCATE_EPS


def _barycentric_z(a: Point3, b: Point3, c: Point3, x: float, y: float) -> float:
    v0x, v0y = b.x - a.x, b.y - a.y
    v1x, v1y = c.x - a.x, c.y - a.y
    v2x, v2y = x - a.x, y - a.y
    denom = v0x * v1y - v1x * v0y
    if abs(denom) < _EPS:
        return (a.z + b.z + c.z) / 3.0
    t = (v2x * v1y - v1x * v2y) / denom
    s = (v0x * v2y - v2x * v0y) / denom
    return a.z + t * (b.z - a.z) + s * (c.z - a.z)


def _segment_triangle(
    origin: Point3,
    direction: tuple[float, float, float],
    a: Point3,
    b: Point3,
    c: Point3,
) -> tuple[float, Point3] | None:
    """Möller–Trumbore: пересечение луча с треугольником, параметр t вдоль direction."""
    ax, ay, az = a.x, a.y, a.z
    e1 = (b.x - ax, b.y - ay, b.z - az)
    e2 = (c.x - ax, c.y - ay, c.z - az)
    px = direction[1] * e2[2] - direction[2] * e2[1]
    py = direction[2] * e2[0] - direction[0] * e2[2]
    pz = direction[0] * e2[1] - direction[1] * e2[0]
    det = e1[0] * px + e1[1] * py + e1[2] * pz
    if abs(det) < _EPS:
        return None
    inv = 1.0 / det
    tx, ty, tz = origin.x - ax, origin.y - ay, origin.z - az
    u = (tx * px + ty * py + tz * pz) * inv
    if u < -_LOCATE_EPS or u > 1.0 + _LOCATE_EPS:
        return None
    qx = ty * e1[2] - tz * e1[1]
    qy = tz * e1[0] - tx * e1[2]
    qz = tx * e1[1] - ty * e1[0]
    v = (direction[0] * qx + direction[1] * qy + direction[2] * qz) * inv
    if v < -_LOCATE_EPS or u + v > 1.0 + _LOCATE_EPS:
        return None
    t = (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv
    point = Point3(
        x=origin.x + direction[0] * t,
        y=origin.y + direction[1] * t,
        z=origin.z + direction[2] * t,
    )
    return t, point


def _point_triangle_distance(p: Point3, a: Point3, b: Point3, c: Point3) -> float:
    closest = _closest_on_triangle(p, a, b, c)
    return math.dist((p.x, p.y, p.z), (closest.x, closest.y, closest.z))


def _closest_on_triangle(p: Point3, a: Point3, b: Point3, c: Point3) -> Point3:
    ab = (b.x - a.x, b.y - a.y, b.z - a.z)
    ac = (c.x - a.x, c.y - a.y, c.z - a.z)
    ap = (p.x - a.x, p.y - a.y, p.z - a.z)
    d1 = _dot(ab, ap)
    d2 = _dot(ac, ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return a
    bp = (p.x - b.x, p.y - b.y, p.z - b.z)
    d3 = _dot(ab, bp)
    d4 = _dot(ac, bp)
    if d3 >= 0.0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        v = d1 / (d1 - d3)
        return Point3(x=a.x + ab[0] * v, y=a.y + ab[1] * v, z=a.z + ab[2] * v)
    cp = (p.x - c.x, p.y - c.y, p.z - c.z)
    d5 = _dot(ab, cp)
    d6 = _dot(ac, cp)
    if d6 >= 0.0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        w = d2 / (d2 - d6)
        return Point3(x=a.x + ac[0] * w, y=a.y + ac[1] * w, z=a.z + ac[2] * w)
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return Point3(
            x=b.x + (c.x - b.x) * w,
            y=b.y + (c.y - b.y) * w,
            z=b.z + (c.z - b.z) * w,
        )
    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    return Point3(
        x=a.x + ab[0] * v + ac[0] * w,
        y=a.y + ab[1] * v + ac[1] * w,
        z=a.z + ab[2] * v + ac[2] * w,
    )


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _resample_polyline(points: list[Point3], count: int) -> list[Point3]:
    if len(points) == count:
        return [Point3(x=p.x, y=p.y, z=p.z) for p in points]
    if len(points) == 1:
        return [Point3(x=points[0].x, y=points[0].y, z=points[0].z) for _ in range(count)]
    lengths = [0.0]
    for i in range(1, len(points)):
        lengths.append(
            lengths[-1]
            + math.dist(
                (points[i - 1].x, points[i - 1].y, points[i - 1].z),
                (points[i].x, points[i].y, points[i].z),
            )
        )
    total = lengths[-1] or 1.0
    result: list[Point3] = []
    for i in range(count):
        target = total * i / (count - 1)
        j = 0
        while j + 1 < len(lengths) and lengths[j + 1] < target:
            j += 1
        span = lengths[j + 1] - lengths[j] if j + 1 < len(lengths) else 1.0
        t = 0.0 if span < _EPS else (target - lengths[j]) / span
        a = points[min(j, len(points) - 1)]
        b = points[min(j + 1, len(points) - 1)]
        result.append(
            Point3(
                x=a.x + (b.x - a.x) * t,
                y=a.y + (b.y - a.y) * t,
                z=a.z + (b.z - a.z) * t,
            )
        )
    return result
