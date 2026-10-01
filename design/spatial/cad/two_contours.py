"""Два контура блока, свободная поверхность, отметки уступа (TASK-013, PR 2).

Блок — контур в плане и две поверхности (§2 «Модель блока и контур»). Для
площадей нужны два контура с общими тылом и флангами:

- по верхней бровке — S верх, внутри него ставятся скважины (это контур
  паспорта);
- по нижней бровке — S низ: фланги продлеваются от верхней бровки до нижней
  по своему направлению, откос между бровками добавляется к блоку.

Рёбра контура, всё лежащие не дальше 1 м от верхней бровки, — свободная
поверхность: эта метка уходит в проектирование сетки для первого ряда.
Направление фланга берётся от вершины тыла не ближе 5 м к концу бровки: у
блока 66 между тылом и бровкой есть ребро 4 м вдоль бровки, и продление по
нему ушло бы внутрь блока.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

import numpy as np
import shapely
from shapely.geometry import LineString, Point

from design.spatial.cad.contour import cut_polyline, project_on_polyline
from design.spatial.cad.model import CadWarning, ru_number
from design.spatial.cad.rings import XY, LocalFrame, check_ring, normalize_ring, point_label, ring_area, ring_perimeter
from design.spatial.cad.stitch import StitchedLine

FREE_FACE_DISTANCE_M = 1.0
FREE_FACE_SAMPLE_M = 1.0
FLANK_BACKSTEP_M = 5.0
FLANK_MAX_EXTENSION_M = 100.0
# Разрыв нижней бровки между флангами до этого закрывается прямой для S низ —
# как подсвеченные разрывы сшивки (stitch.GAP_REPORT_M).
TOE_GAP_BRIDGE_M = 5.0
BENCH_HEIGHT_RANGE_M = (2.0, 25.0)
# Без свободной поверхности отметка бровки берётся по верхним бровкам у контура.
CREST_NEAR_CONTOUR_M = 5.0
# Нижняя бровка для отметки подошвы — не дальше этого от контура.
TOE_NEAR_CONTOUR_M = 50.0


@dataclass
class Flank:
    """Продление фланга: от конца откоса по верхней бровке до нижней бровки."""

    start: XY
    end: XY | None
    length_m: float | None


@dataclass
class TwoContours:
    top: list[XY]
    bottom: list[XY]
    free_faces: list[tuple[int, int]]
    flanks: list[Flank] = field(default_factory=list)
    warnings: list[CadWarning] = field(default_factory=list)

    @property
    def area_top_m2(self) -> float:
        return ring_area(self.top)

    @property
    def area_bottom_m2(self) -> float:
        return ring_area(self.bottom)

    @property
    def area_mean_m2(self) -> float:
        return (self.area_top_m2 + self.area_bottom_m2) / 2

    @property
    def perimeter_top_m(self) -> float:
        return ring_perimeter(self.top)


@dataclass
class BenchLevels:
    crest_z_m: float | None
    toe_z_m: float | None
    crest_source: str = ""
    toe_source: str = ""
    warnings: list[CadWarning] = field(default_factory=list)

    @property
    def height_m(self) -> float | None:
        if self.crest_z_m is None or self.toe_z_m is None:
            return None
        return self.crest_z_m - self.toe_z_m


def _xy(line: StitchedLine) -> list[XY]:
    return [(point[0], point[1]) for point in line.points]


def _union(lines: Sequence[StitchedLine], frame: LocalFrame):
    geoms = [LineString(frame.to_local(_xy(line))) for line in lines if len(line.points) >= 2]
    return shapely.unary_union(geoms) if geoms else None


def free_face_edges(ring: Sequence[XY], top_lines: Sequence[StitchedLine]) -> list[tuple[int, int]]:
    """Рёбра, целиком лежащие не дальше 1 м от верхней бровки."""

    if len(ring) < 3 or not top_lines:
        return []
    frame = LocalFrame.of(ring)
    crest = _union(top_lines, frame)
    if crest is None:
        return []
    local = frame.to_local(ring)
    free: list[tuple[int, int]] = []
    for index in range(len(local)):
        a, b = local[index], local[(index + 1) % len(local)]
        count = max(2, math.ceil(math.dist(a, b) / FREE_FACE_SAMPLE_M) + 1)
        t = np.linspace(0.0, 1.0, count)
        samples = shapely.points(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if float(np.max(shapely.distance(samples, crest))) <= FREE_FACE_DISTANCE_M:
            free.append((index, (index + 1) % len(local)))
    return free


def _runs(count: int, free: set[int]) -> list[tuple[int, int]]:
    """Серии подряд идущих свободных рёбер: (первая вершина, последняя вершина)."""

    start = next(index for index in range(count) if index not in free)
    runs: list[tuple[int, int]] = []
    current: int | None = None
    for step in range(1, count + 1):
        edge = (start + step) % count
        if edge in free:
            if current is None:
                current = edge
        elif current is not None:
            runs.append((current, edge))
            current = None
    return runs


def _flank_direction(local: Sequence[XY], vertex: int, step: int, stop: int) -> XY:
    """Направление фланга к вершине `vertex` от вершины тыла не ближе 5 м."""

    count = len(local)
    anchor = vertex
    for _ in range(count):
        anchor = (anchor + step) % count
        if math.dist(local[anchor], local[vertex]) >= FLANK_BACKSTEP_M or anchor == stop:
            break
    dx, dy = local[vertex][0] - local[anchor][0], local[vertex][1] - local[anchor][1]
    norm = math.hypot(dx, dy) or 1.0
    return (dx / norm, dy / norm)


def _ray_hit(origin: XY, direction: XY, line: LineString) -> XY | None:
    ray = LineString([origin, (origin[0] + direction[0] * FLANK_MAX_EXTENSION_M, origin[1] + direction[1] * FLANK_MAX_EXTENSION_M)])
    hits = [point for point in _points(ray.intersection(line))]
    if not hits:
        return None
    nearest = min(hits, key=lambda point: math.dist(point, origin))
    return nearest


def _points(geometry) -> list[XY]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Point":
        return [(geometry.x, geometry.y)]
    if geometry.geom_type == "LineString":
        return [tuple(coord) for coord in geometry.coords]
    return [point for part in getattr(geometry, "geoms", []) for point in _points(part)]


def _along(line: LineString, start: XY, end: XY) -> list[XY]:
    """Кусок линии от точки `start` до точки `end` (обе на линии), по ходу от start."""

    coords = [(x, y) for x, y in line.coords]
    m_start = project_on_polyline(coords, start)[0]
    m_end = project_on_polyline(coords, end)[0]
    piece = cut_polyline(coords, m_start, m_end)
    if m_start > m_end:
        piece.reverse()
    return piece


def _nearest_hit(origin: XY, direction: XY, lines: Sequence[LineString]) -> tuple[XY, LineString] | None:
    best: tuple[XY, LineString] | None = None
    for line in lines:
        hit = _ray_hit(origin, direction, line)
        if hit is not None and (best is None or math.dist(hit, origin) < math.dist(best[0], origin)):
            best = (hit, line)
    return best


def _join_across_gap(
    hit_first: XY, line_first: LineString, hit_last: XY, line_last: LineString
) -> tuple[list[XY], float, XY] | None:
    """Путь по нижней бровке от фланга до фланга через один разрыв не больше
    `TOE_GAP_BRIDGE_M` между двумя кусками: (путь, длина разрыва, середина разрыва)."""

    first_ends = [tuple(line_first.coords[0])[:2], tuple(line_first.coords[-1])[:2]]
    last_ends = [tuple(line_last.coords[0])[:2], tuple(line_last.coords[-1])[:2]]
    gap, end_first, end_last = min(
        ((math.dist(a, b), a, b) for a in first_ends for b in last_ends), key=lambda item: item[0]
    )
    if gap > TOE_GAP_BRIDGE_M:
        return None
    path = [hit_first, *_along(line_first, hit_first, end_first), *_along(line_last, end_last, hit_last), hit_last]
    return path, gap, ((end_first[0] + end_last[0]) / 2, (end_first[1] + end_last[1]) / 2)


def two_contours(
    ring: Sequence[XY],
    top_lines: Sequence[StitchedLine],
    bottom_lines: Sequence[StitchedLine],
    *,
    face_lines: Sequence[StitchedLine] | None = None,
) -> TwoContours:
    """Контур по нижней бровке с общими тылом и флангами контура `ring`.

    `face_lines` — линии, вдоль которых ищется свободная поверхность (по
    умолчанию все верхние бровки). Серия свободных рёбер, чей фланг не дошёл
    до нижней бровки, остаётся в нижнем контуре как есть — с предупреждением:
    один промах не должен обнулять откосы остальных серий.
    """

    top = list(ring)
    free = free_face_edges(top, top_lines if face_lines is None else face_lines)
    result = TwoContours(top=top, bottom=top, free_faces=free)
    if not free:
        result.warnings.append(
            CadWarning(
                "no_free_face",
                "Верхней бровки вдоль контура нет — свободная поверхность и откос не найдены: S низ = S верх.",
            )
        )
        return result
    if not bottom_lines:
        result.warnings.append(CadWarning("no_toe", "Нижней бровки нет — откос не учтён: S низ = S верх."))
        return result
    if len(free) == len(top):
        result.warnings.append(
            CadWarning("no_flanks", "Весь контур идёт по верхней бровке — флангов нет: S низ = S верх.")
        )
        return result

    frame = LocalFrame.of(top)
    local = frame.to_local(top)
    bottoms = [LineString(frame.to_local(_xy(line))) for line in bottom_lines if len(line.points) >= 2]
    runs = _runs(len(local), {edge for edge, _ in free})

    pieces: list[tuple[int, int, list[XY] | None]] = []
    for number, (first, last) in enumerate(runs):
        previous_end = runs[number - 1][1]
        next_start = runs[(number + 1) % len(runs)][0]
        direction_first = _flank_direction(local, first, -1, previous_end)
        direction_last = _flank_direction(local, last, +1, next_start)
        best: tuple[float, XY, XY, LineString] | None = None
        for line in bottoms:
            hit_first = _ray_hit(local[first], direction_first, line)
            hit_last = _ray_hit(local[last], direction_last, line)
            if hit_first is None or hit_last is None:
                continue
            total = math.dist(hit_first, local[first]) + math.dist(hit_last, local[last])
            if best is None or total < best[0]:
                best = (total, hit_first, hit_last, line)
        if best is None:
            nearest = [
                _nearest_hit(local[vertex], direction, bottoms)
                for vertex, direction in ((first, direction_first), (last, direction_last))
            ]
            for vertex, found in zip((first, last), nearest):
                hit = found[0] if found else None
                result.flanks.append(
                    Flank(
                        frame.point_to_world(local[vertex]),
                        frame.point_to_world(hit) if hit else None,
                        math.dist(hit, local[vertex]) if hit else None,
                    )
                )
            where = frame.point_to_world(local[first])
            if nearest[0] and nearest[1]:
                # Оба фланга дошли, но до разных кусков нижней бровки: она
                # разорвана между ними (разрыв больше 1 м по §2 не сшивается).
                (hit_first, line_first), (hit_last, line_last) = nearest
                joined = _join_across_gap(hit_first, line_first, hit_last, line_last)
                if joined is not None:
                    path, gap_m, gap_at = joined
                    pieces.append((first, last, path))
                    result.warnings.append(
                        CadWarning(
                            "toe_gap",
                            f"Нижняя бровка между флангами разорвана ({ru_number(gap_m, 1)} м у точки "
                            f"{point_label(frame.point_to_world(gap_at))}) — для S низ разрыв закрыт прямой.",
                            level="info",
                        )
                    )
                    continue
                result.warnings.append(
                    CadWarning(
                        "toe_gap",
                        f"Откос у точки {point_label(where)} не учтён: нижняя бровка между флангами разорвана "
                        f"больше чем на {ru_number(TOE_GAP_BRIDGE_M, 0)} м.",
                    )
                )
            else:
                result.warnings.append(
                    CadWarning(
                        "flank_miss",
                        f"Откос у точки {point_label(where)} не учтён: фланг не доходит до нижней бровки "
                        f"(ищем в пределах {ru_number(FLANK_MAX_EXTENSION_M, 0)} м).",
                    )
                )
            pieces.append((first, last, None))
            continue
        _, hit_first, hit_last, line = best
        pieces.append((first, last, [hit_first, *_along(line, hit_first, hit_last), hit_last]))
        for vertex, hit in ((first, hit_first), (last, hit_last)):
            result.flanks.append(
                Flank(frame.point_to_world(local[vertex]), frame.point_to_world(hit), math.dist(hit, local[vertex]))
            )

    if all(piece is None for _, _, piece in pieces):
        return result

    count = len(local)
    bottom_local: list[XY] = []
    for number, (first, last, piece) in enumerate(pieces):
        if piece is None:
            vertex = first
            while vertex != last:
                bottom_local.append(local[vertex])
                vertex = (vertex + 1) % count
            bottom_local.append(local[last])
        else:
            bottom_local.append(local[first])
            bottom_local.extend(piece)
            bottom_local.append(local[last])
        following = pieces[(number + 1) % len(pieces)][0]
        vertex = (last + 1) % count
        while vertex != following:
            bottom_local.append(local[vertex])
            vertex = (vertex + 1) % count

    bottom = normalize_ring(frame.to_world(bottom_local))
    issues = check_ring(bottom)
    if issues:
        result.warnings.append(
            CadWarning("bottom_invalid", f"Контур по нижней бровке не построен: {issues[0].message} S низ = S верх.")
        )
        return result
    result.bottom = bottom
    if ring_area(bottom) < ring_area(top) - 0.01:
        result.warnings.append(
            CadWarning(
                "toe_inside",
                "Контур по нижней бровке меньше верхнего — проверьте, не перепутаны ли верхняя и нижняя бровки.",
            )
        )
    return result


def bench_levels(
    ring: Sequence[XY],
    free_faces: Sequence[tuple[int, int]],
    top_lines: Sequence[StitchedLine],
    bottom_lines: Sequence[StitchedLine],
    floor_z: float | None,
) -> BenchLevels:
    """Отметки уступа для паспорта: бровка — по верхней бровке у откоса,
    подошва — проектная отметка, без неё — по нижней бровке."""

    levels = BenchLevels(crest_z_m=None, toe_z_m=None)
    frame = LocalFrame.of(ring)
    local = frame.to_local(ring)

    # Отметка бровки — по самой бровке у откоса: точки свободных рёбер через
    # 1 м проецируются на ближайшую верхнюю бровку, Z интерполируется по ней.
    crest_z: list[float] = []
    if free_faces and top_lines:
        samples = [point for a, b in free_faces for point in _samples(local[a], local[b])]
        crest_z = _z_at_samples(top_lines, frame, samples, FREE_FACE_DISTANCE_M)
    if not crest_z and top_lines and len(local) >= 3:
        samples = [point for index in range(len(local)) for point in _samples(local[index], local[(index + 1) % len(local)])]
        crest_z = _z_at_samples(top_lines, frame, samples, CREST_NEAR_CONTOUR_M)
    if crest_z:
        levels.crest_z_m, levels.crest_source = float(median(crest_z)), "crest_top"
    else:
        levels.warnings.append(
            CadWarning("crest_z_missing", "Отметка бровки не найдена — оставлена отметка паспорта.")
        )

    if floor_z is not None:
        levels.toe_z_m, levels.toe_source = float(floor_z), "floor"
    else:
        toe_z = (
            _z_near(bottom_lines, frame, shapely.Polygon(local).exterior, TOE_NEAR_CONTOUR_M)
            if bottom_lines and len(local) >= 3
            else []
        )
        if toe_z:
            levels.toe_z_m, levels.toe_source = float(median(toe_z)), "crest_bottom"
        else:
            levels.warnings.append(
                CadWarning("toe_z_missing", "Отметка подошвы не найдена — оставлена отметка паспорта.")
            )

    height = levels.height_m
    low, high = BENCH_HEIGHT_RANGE_M
    if height is not None and not low <= height <= high:
        levels.warnings.append(
            CadWarning(
                "bench_height",
                f"Высота уступа {ru_number(height, 1)} м вне {ru_number(low, 0)}–{ru_number(high, 0)} м — "
                "проверьте подошву и роли бровок.",
            )
        )
    return levels


def _samples(a: XY, b: XY) -> list[XY]:
    count = max(2, math.ceil(math.dist(a, b) / FREE_FACE_SAMPLE_M) + 1)
    return [(a[0] + (b[0] - a[0]) * k / (count - 1), a[1] + (b[1] - a[1]) * k / (count - 1)) for k in range(count)]


def _z_on_line(points: Sequence[tuple[float, float, float]], xy: Sequence[XY], m: float) -> float:
    """Z точки линии на расстоянии `m` от начала (по длине в плане)."""

    walked = 0.0
    last = len(xy) - 2
    for index in range(last + 1):
        length = math.dist(xy[index], xy[index + 1])
        if walked + length >= m or index == last:
            t = 0.0 if not length else max(0.0, min(1.0, (m - walked) / length))
            return points[index][2] + (points[index + 1][2] - points[index][2]) * t
        walked += length
    return points[-1][2]


def _z_at_samples(
    lines: Sequence[StitchedLine], frame: LocalFrame, samples: Sequence[XY], distance_m: float
) -> list[float]:
    prepared = [(line.points, frame.to_local(_xy(line))) for line in lines if len(line.points) >= 2]
    values: list[float] = []
    for sample in samples:
        best: tuple[float, float, int] | None = None
        for number, (_, xy) in enumerate(prepared):
            m, _, distance = project_on_polyline(xy, sample)
            if distance <= distance_m and (best is None or distance < best[0]):
                best = (distance, m, number)
        if best is not None:
            points, xy = prepared[best[2]]
            values.append(_z_on_line(points, xy, best[1]))
    return values


def _z_near(lines: Sequence[StitchedLine], frame: LocalFrame, target, distance_m: float) -> list[float]:
    values: list[float] = []
    for line in lines:
        local = frame.to_local(_xy(line))
        for (x, y), point in zip(local, line.points):
            if target.distance(Point(x, y)) <= distance_m:
                values.append(point[2])
    return values
