"""Построитель кровли: триангуляция Делоне с ограничителями (TASK-013, PR 3).

Интерфейс `SurfaceBuilder` (§3 PR 3, п. 1) и два пути:

- **CDT** — PythonCDT (C++ CDT 2.0.0, MPL-2.0). Пересекающиеся ограничители
  разрешаются вставкой вершины (`TRY_RESOLVE`); откуда она взялась, говорит
  `piece_to_originals`.
- **scipy** — запасной: `scipy.spatial.Delaunay`, затем каждое ребро
  ограничителя, которого нет в триангуляции, делится в точках пересечения с
  мешающими рёбрами, и триангуляция строится заново. Цикл ограничен; не
  сошлось — ошибка с местом.

Выбор — `BLASTEX_SURFACE_BUILDER` (`cdt` или `scipy`); без флага — CDT, а
если PythonCDT не установлен — scipy с предупреждением в журнале.

Построитель получает точки в плане (локальная система) и пары индексов
ограничителей. Возвращает вершины (первые N — входные точки, дальше новые) и
треугольники; у новых вершин — номера ограничителей, на которых они лежат:
по ним вызывающий назначает Z. Точные дубли входа — одна вершина: дубль в
треугольники не попадает.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import shapely
from scipy.spatial import Delaunay, QhullError, cKDTree

from design.spatial.cad.rings import XY

log = logging.getLogger(__name__)

BUILDER_ENV = "BLASTEX_SURFACE_BUILDER"
BUILDER_NAMES = ("cdt", "scipy")
# Раундов исправления рёбер у запасного пути не больше этого.
MAX_ROUNDS = 40
# Новых точек на ограничителях — не больше стольких на одну входную.
MAX_ADDED_PER_POINT = 4
# Точка деления ближе этого к концу ребра или к другой точке деления не вставляется.
MIN_SPLIT_M = 0.005
_ON_SEGMENT_M = 1e-7


class SurfaceBuildError(RuntimeError):
    """Триангуляция не построена — текст для пользователя и место (локальное)."""

    def __init__(self, message: str, point: XY | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.point = point


@dataclass
class BuildResult:
    vertices: np.ndarray
    triangles: np.ndarray
    # Новая вершина → номера ограничителей входа, на которых она лежит.
    origins: dict[int, list[int]] = field(default_factory=dict)


class SurfaceBuilder(Protocol):
    name: str

    def build(self, points: np.ndarray, constraints: np.ndarray) -> BuildResult: ...


def _empty(points: np.ndarray) -> BuildResult:
    return BuildResult(np.asarray(points, dtype=float).reshape(-1, 2).copy(), np.zeros((0, 3), dtype=int))


def _canonical(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Для каждой точки — индекс её первого вхождения; индексы без дублей по порядку."""

    if not len(points):
        return np.zeros(0, dtype=int), np.zeros(0, dtype=int)
    _, first, inverse = np.unique(points, axis=0, return_index=True, return_inverse=True)
    return first[inverse.ravel()], np.sort(first)


def _constraint_rows(constraints: np.ndarray, canonical: np.ndarray) -> list[tuple[int, int, int]]:
    rows = []
    for number, (a, b) in enumerate(np.asarray(constraints, dtype=int).reshape(-1, 2).tolist()):
        ca, cb = int(canonical[a]), int(canonical[b])
        if ca != cb:
            rows.append((ca, cb, number))
    return rows


class CdtBuilder:
    """Основной путь — PythonCDT."""

    name = "cdt"

    def __init__(self) -> None:
        import PythonCDT

        self._cdt = PythonCDT

    def build(self, points: np.ndarray, constraints: np.ndarray) -> BuildResult:
        points = np.asarray(points, dtype=float).reshape(-1, 2)
        n = len(points)
        canonical, keep = _canonical(points)
        if len(keep) < 3:
            return _empty(points)
        position = np.full(n, -1, dtype=int)
        position[keep] = np.arange(len(keep))
        rows = _constraint_rows(constraints, canonical)
        by_pair: dict[tuple[int, int], list[int]] = {}
        for a, b, number in rows:
            pa, pb = int(position[a]), int(position[b])
            by_pair.setdefault((min(pa, pb), max(pa, pb)), []).append(number)
        cdt = self._cdt
        try:
            triangulation = cdt.Triangulation(
                cdt.VertexInsertionOrder.AUTO, cdt.IntersectingConstraintEdges.TRY_RESOLVE, 0.0
            )
            triangulation.insert_vertices(points[keep])
            if by_pair:
                triangulation.insert_edges(np.asarray(list(by_pair), dtype=np.uintc))
            triangulation.erase_super_triangle()
            raw = triangulation.vertices_array()
            triangles = np.asarray(triangulation.triangles_array()["vertices"], dtype=int).reshape(-1, 3)
            pieces = list(triangulation.piece_to_originals_iter())
        except RuntimeError as exc:
            raise SurfaceBuildError(f"Триангуляция CDT не построена: {exc}") from exc
        xy = np.column_stack([raw["x"], raw["y"]]).astype(float)
        m = len(keep)
        mapping = np.concatenate([keep, n + np.arange(len(xy) - m)]).astype(int)
        origins: dict[int, set[int]] = {}
        for piece, originals in pieces:
            for vertex in (piece.v1, piece.v2):
                if vertex < m:
                    continue
                found = origins.setdefault(int(mapping[vertex]), set())
                for edge in originals:
                    found.update(by_pair.get((min(edge.v1, edge.v2), max(edge.v1, edge.v2)), []))
        return BuildResult(
            vertices=np.vstack([points, xy[m:]]),
            triangles=mapping[triangles] if len(triangles) else np.zeros((0, 3), dtype=int),
            origins={vertex: sorted(found) for vertex, found in origins.items()},
        )


class ScipyBuilder:
    """Запасной путь — scipy Delaunay с исправлением рёбер ограничителей."""

    name = "scipy"

    def build(self, points: np.ndarray, constraints: np.ndarray) -> BuildResult:
        points = np.asarray(points, dtype=float).reshape(-1, 2)
        n = len(points)
        canonical, keep = _canonical(points)
        if len(keep) < 3:
            return _empty(points)
        state = _ScipyState(points, keep)
        chains = [[a, b] for a, b, _ in _constraint_rows(constraints, canonical)]
        owners = [[number] for _, _, number in _constraint_rows(constraints, canonical)]
        state.split_crossings(chains, owners)
        state.split_at_vertices(chains)
        limit = n * MAX_ADDED_PER_POINT + 1000
        for _ in range(MAX_ROUNDS):
            triangles = state.triangulate()
            if triangles is None:
                return BuildResult(state.array(), np.zeros((0, 3), dtype=int), state.origins)
            edges = {tuple(sorted(edge)) for edge in _edges(triangles)}
            missing = [
                (chain, k)
                for chain in chains
                for k in range(len(chain) - 1)
                if tuple(sorted((chain[k], chain[k + 1]))) not in edges
            ]
            if not missing:
                return BuildResult(state.array(), triangles, state.origins)
            state.split_missing(missing, triangles, owners, chains)
            if len(state.points) - n > limit:
                break
        chain, k = missing[0]
        a, b = state.points[chain[k]], state.points[chain[k + 1]]
        point = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        raise SurfaceBuildError(
            "Запасной построитель не провёл ребро ограничителя — проверьте линии у этого места.", point
        )


def _edges(triangles: np.ndarray) -> list[tuple[int, int]]:
    tri = np.asarray(triangles, dtype=int)
    stacked = np.vstack([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    stacked.sort(axis=1)
    return [tuple(row) for row in np.unique(stacked, axis=0).tolist()]


class _ScipyState:
    """Точки запасного пути: входные (с дублями) и новые на ограничителях."""

    def __init__(self, points: np.ndarray, keep: np.ndarray) -> None:
        self.points: list[np.ndarray] = [row for row in points]
        self.n = len(points)
        self.keep = keep
        self.origins: dict[int, list[int]] = {}

    def array(self) -> np.ndarray:
        return np.asarray(self.points, dtype=float).reshape(-1, 2)

    def add(self, point: np.ndarray, owners: list[int]) -> int:
        self.points.append(np.asarray(point, dtype=float))
        index = len(self.points) - 1
        self.origins[index] = sorted(set(owners))
        return index

    def active(self) -> np.ndarray:
        return np.concatenate([self.keep, np.arange(self.n, len(self.points))]).astype(int)

    def triangulate(self) -> np.ndarray | None:
        active = self.active()
        try:
            simplices = Delaunay(self.array()[active]).simplices
        except QhullError:
            return None
        return active[simplices]

    def split_crossings(self, chains: list[list[int]], owners: list[list[int]]) -> None:
        """Ограничители, пересекающие друг друга, получают общую вершину."""

        if len(chains) < 2:
            return
        array = self.array()
        segments = shapely.linestrings(np.stack([array[[c[0] for c in chains]], array[[c[1] for c in chains]]], axis=1))
        left, right = shapely.STRtree(segments).query(segments, predicate="intersects")
        inserts: dict[int, list[tuple[float, int]]] = {}
        for i, j in zip(left.tolist(), right.tolist()):
            if i >= j or set(chains[i]) & set(chains[j]):
                continue
            hit = _crossing(array[chains[i][0]], array[chains[i][1]], array[chains[j][0]], array[chains[j][1]])
            if hit is None:
                continue
            t, u, point = hit
            vertex = self.add(point, owners[i] + owners[j])
            inserts.setdefault(i, []).append((t, vertex))
            inserts.setdefault(j, []).append((u, vertex))
        for number, items in inserts.items():
            chains[number][1:1] = [vertex for _, vertex in sorted(items)]

    def split_at_vertices(self, chains: list[list[int]]) -> None:
        """Вершина, лежащая на ограничителе, делит его."""

        if not chains:
            return
        array = self.array()
        active = self.active()
        tree = shapely.STRtree(shapely.points(array[active]))
        for chain in chains:
            a, b = array[chain[0]], array[chain[-1]]
            segment = shapely.linestrings([a, b])
            found = []
            for hit in tree.query(segment, predicate="dwithin", distance=_ON_SEGMENT_M).tolist():
                vertex = int(active[hit])
                if vertex in chain:
                    continue
                t = _param(a, b, array[vertex])
                if 0.0 < t < 1.0:
                    found.append((t, vertex))
            if found:
                inner = [(_param(a, b, array[v]), v) for v in chain[1:-1]]
                chain[:] = [chain[0], *[v for _, v in sorted(inner + found)], chain[-1]]

    def split_missing(
        self,
        missing: list[tuple[list[int], int]],
        triangles: np.ndarray,
        owners: list[list[int]],
        chains: list[list[int]],
    ) -> None:
        """Каждое отсутствующее ребро делится в точках пересечения с мешающими рёбрами."""

        array = self.array()
        edges = np.asarray(_edges(triangles), dtype=int)
        tree = shapely.STRtree(shapely.linestrings(np.stack([array[edges[:, 0]], array[edges[:, 1]]], axis=1)))
        snap = cKDTree(array)
        owner_of = {id(chain): owners[number] for number, chain in enumerate(chains)}
        plan: dict[int, list[tuple[int, list[np.ndarray]]]] = {}
        for chain, k in missing:
            a_index, b_index = chain[k], chain[k + 1]
            a, b = array[a_index], array[b_index]
            length = math.dist(a, b)
            ts: list[float] = []
            for hit in tree.query(shapely.linestrings([a, b]), predicate="intersects").tolist():
                p_index, q_index = edges[hit]
                if p_index in (a_index, b_index) or q_index in (a_index, b_index):
                    continue
                crossing = _crossing(a, b, array[p_index], array[q_index])
                if crossing is not None:
                    ts.append(crossing[0])
            chosen: list[float] = []
            for t in sorted(ts):
                if t * length < MIN_SPLIT_M or (1 - t) * length < MIN_SPLIT_M:
                    continue
                if chosen and (t - chosen[-1]) * length < MIN_SPLIT_M:
                    continue
                chosen.append(t)
            if not chosen:
                chosen = [0.5]
            plan.setdefault(id(chain), []).append((k, [a + (b - a) * t for t in chosen]))
        for chain in chains:
            steps = plan.get(id(chain))
            if not steps:
                continue
            for k, new_points in sorted(steps, key=lambda item: item[0], reverse=True):
                vertices = []
                for point in new_points:
                    distance, nearest = snap.query(point)
                    if distance <= _ON_SEGMENT_M and nearest not in chain:
                        vertices.append(int(nearest))
                    else:
                        vertices.append(self.add(point, owner_of[id(chain)]))
                chain[k + 1 : k + 1] = vertices


def _param(a: np.ndarray, b: np.ndarray, point: np.ndarray) -> float:
    d = b - a
    length2 = float(np.dot(d, d))
    return 0.0 if length2 == 0 else float(np.dot(point - a, d)) / length2


def _crossing(p, p2, q, q2) -> tuple[float, float, np.ndarray] | None:
    """Пересечение отрезков внутри обоих (не в концах): параметры и точка."""

    r = p2 - p
    s = q2 - q
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) <= 1e-12 * max(float(np.dot(r, r)), float(np.dot(s, s)), 1e-12):
        return None
    qp = q - p
    t = (qp[0] * s[1] - qp[1] * s[0]) / denom
    u = (qp[0] * r[1] - qp[1] * r[0]) / denom
    if 0.0 < t < 1.0 and 0.0 < u < 1.0:
        return float(t), float(u), p + r * t
    return None


def make_builder() -> SurfaceBuilder:
    """Построитель по флагу `BLASTEX_SURFACE_BUILDER`; без флага — CDT, если он есть."""

    name = os.environ.get(BUILDER_ENV, "").strip().lower()
    if name and name not in BUILDER_NAMES:
        raise SurfaceBuildError(
            f"{BUILDER_ENV}={name}: неизвестный построитель, допустимы {', '.join(BUILDER_NAMES)}."
        )
    if name == "scipy":
        return ScipyBuilder()
    try:
        return CdtBuilder()
    except ImportError:
        if name == "cdt":
            raise SurfaceBuildError(f"{BUILDER_ENV}=cdt, но PythonCDT не установлен.") from None
        log.warning("PythonCDT не установлен — кровля строится запасным путём scipy.")
        return ScipyBuilder()
