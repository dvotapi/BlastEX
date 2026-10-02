"""Сшивка фрагментов линий в непрерывные линии (TASK-013, PR 2).

Маркшейдер присылает бровку кусками: у блока 66 на слое «Горизонт +410» их
23. Перед построением контура фрагменты одной роли сшиваются (§2 «Модель
блока и контур»): концы ближе 1 м, и следующий фрагмент продолжает
направление предыдущего — поворот не больше 60°. Совпадающие концы (до 1 см)
сшиваются при любом повороте, если в этой точке сходятся ровно два конца:
это угол одной линии, а не встреча разных (у блока 66 нижняя бровка 733 → 73B
поворачивает на 95°). Больший разрыв остаётся разрывом и подсвечивается.
Концы с перепадом отметок больше 1 м не сшиваются: это бровки разных уступов,
сошедшиеся в плане (линия без отметок, Z = 0, отметкой не мешает).

Сшитая линия помнит свои фрагменты и где каждый начинается по её длине: так
участок сшитой линии переводится обратно в участки исходных объектов.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

from design.spatial.cad.model import ZERO_Z_TOLERANCE_M, CadEntity

XY = tuple[float, float]
XYZ = tuple[float, float, float]

STITCH_GAP_M = 1.0
STITCH_MAX_TURN_DEG = 60.0
COINCIDENT_M = 0.01
# Разрывы между концами линий до этого расстояния показываются пользователю.
GAP_REPORT_M = 5.0
# Перепад отметок на стыке больше этого — бровки разных уступов (высота
# уступа не меньше 2 м), а не дрожь съёмки.
STITCH_MAX_DZ_M = 1.0
# Кандидатов у конца — не больше стольких ближайших: в пятне из тысяч обрывков
# все пары концов дали бы миллионы кортежей (сшивка идёт в каждом предпросмотре).
NEAREST_ENDS = 8
# Направление конца линии — по её последним метрам, а не по последнему
# звену: съёмка дрожит на сантиметрах.
TANGENT_WINDOW_M = 2.0


@dataclass
class StitchPart:
    """Фрагмент в составе сшитой линии."""

    handle: str
    reversed: bool
    length_m: float
    # Где фрагмент начинается по длине сшитой линии (в плане).
    chain_start_m: float

    def entity_m(self, chain_m: float) -> float:
        """Расстояние по самому фрагменту для точки на `chain_m` сшитой линии."""

        local = min(max(chain_m - self.chain_start_m, 0.0), self.length_m)
        return self.length_m - local if self.reversed else local


@dataclass
class StitchedLine:
    points: list[XYZ]
    parts: list[StitchPart] = field(default_factory=list)

    @property
    def length_m(self) -> float:
        return _length(self.points)

    @property
    def handles(self) -> list[str]:
        return [part.handle for part in self.parts]


@dataclass
class StitchGap:
    """Несшитый стык: `gap` — разрыв больше 1 м, `turn` — излом больше 60°."""

    a: XY
    b: XY
    distance_m: float
    reason: str


def _length(points: Sequence[Sequence[float]]) -> float:
    return sum(math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:]))


def _outward(points: Sequence[XYZ], side: int) -> XY:
    """Единичное направление «наружу» у начала (0) или конца (1) линии."""

    ordered = points if side == 1 else list(reversed(points))
    end = ordered[-1]
    walked = 0.0
    anchor = ordered[-2]
    for index in range(len(ordered) - 2, -1, -1):
        anchor = ordered[index]
        walked += math.dist(ordered[index][:2], ordered[index + 1][:2])
        if walked >= TANGENT_WINDOW_M:
            break
    dx, dy = end[0] - anchor[0], end[1] - anchor[1]
    norm = math.hypot(dx, dy)
    return (dx / norm, dy / norm) if norm else (0.0, 0.0)


def _turn_deg(out_a: XY, out_b: XY) -> float:
    """Поворот при переходе с линии A на B: из A выходим по out_a, в B входим против out_b."""

    cos = -(out_a[0] * out_b[0] + out_a[1] * out_b[1])
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _near_pairs(points: Sequence[Sequence[float]], radius: float) -> list[tuple[int, int]]:
    """Пары точек (i < j) ближе `radius` в плане: у каждой — не больше NEAREST_ENDS ближайших."""

    if len(points) < 2:
        return []
    xy = np.asarray([(point[0], point[1]) for point in points], dtype=float)
    count = min(NEAREST_ENDS + 1, len(points))
    # Граница с запасом на округление: расстояние ровно `radius` — тоже пара.
    _, neighbours = cKDTree(xy).query(xy, k=list(range(1, count + 1)), distance_upper_bound=radius * (1 + 1e-9) + 1e-12)
    found: set[tuple[int, int]] = set()
    for a, row in enumerate(neighbours.tolist()):
        for b in row:
            if b < len(points) and b != a:
                found.add((min(a, b), max(a, b)))
    return sorted(found)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[ra] = rb
        return True


def stitch_lines(lines: Sequence[CadEntity]) -> tuple[list[StitchedLine], list[StitchGap]]:
    """Сшивает линии одной роли. Результат не зависит от порядка входа."""

    # Порядок по handle: одинаковый результат при любом порядке чтения файла.
    usable = sorted((item for item in lines if len(item.points) >= 2), key=lambda item: item.handle)
    closed = [item for item in usable if item.closed]
    open_lines = [item for item in usable if not item.closed]

    # Концы: индекс конца = 2 * линия + сторона (0 — начало, 1 — конец).
    end_points: list[XYZ] = []
    outward: list[XY] = []
    flat: list[bool] = []
    for item in open_lines:
        end_points.extend((item.points[0], item.points[-1]))
        outward.extend((_outward(item.points, 0), _outward(item.points, 1)))
        flat.append(item.z_kind == "zero")

    # Сколько концов совпадает с каждым (вместе с ним самим) — один раз: в узле
    # из k концов пересчёт для каждой пары давал бы k³ сравнений.
    degree: list[int] = []
    if end_points:
        xy = np.asarray([(point[0], point[1]) for point in end_points], dtype=float)
        degree = cKDTree(xy).query_ball_point(xy, r=COINCIDENT_M, return_length=True).tolist()

    accepted: list[tuple[float, float, int, int]] = []
    for a, b in _near_pairs(end_points, STITCH_GAP_M):
        if a // 2 == b // 2:
            continue
        distance = math.dist(end_points[a][:2], end_points[b][:2])
        if distance > STITCH_GAP_M:
            continue
        if not (flat[a // 2] or flat[b // 2]) and abs(end_points[a][2] - end_points[b][2]) > STITCH_MAX_DZ_M:
            continue
        turn = _turn_deg(outward[a], outward[b])
        corner = distance <= COINCIDENT_M and degree[a] == 2 and degree[b] == 2
        if turn <= STITCH_MAX_TURN_DEG or corner:
            accepted.append((distance if distance > COINCIDENT_M else 0.0, turn, a, b))

    joins: dict[int, int] = {}
    components = _UnionFind(len(open_lines))
    for _, _, a, b in sorted(accepted):
        if a in joins or b in joins:
            continue
        # Оба конца одной цепочки не сшиваются: бровка не замыкается в кольцо.
        if not components.union(a // 2, b // 2):
            continue
        joins[a] = b
        joins[b] = a

    stitched: list[StitchedLine] = []
    visited: set[int] = set()
    for start in range(len(open_lines)):
        if start in visited:
            continue
        # Идём к свободному концу цепочки.
        line_index, back_side = start, 0
        seen = {start}
        while 2 * line_index + back_side in joins:
            other = joins[2 * line_index + back_side]
            if other // 2 in seen:
                break
            seen.add(other // 2)
            line_index, back_side = other // 2, 1 - other % 2
        stitched.append(_build_chain(open_lines, joins, line_index, back_side, visited))

    for item in closed:
        points = [*item.points, item.points[0]]
        stitched.append(StitchedLine(points=points, parts=[StitchPart(item.handle, False, item.length_m, 0.0)]))

    return stitched, _report_gaps(stitched)


def _build_chain(
    open_lines: Sequence[CadEntity], joins: dict[int, int], line_index: int, start_side: int, visited: set[int]
) -> StitchedLine:
    points: list[XYZ] = []
    parts: list[StitchPart] = []
    while True:
        visited.add(line_index)
        item = open_lines[line_index]
        reversed_ = start_side == 1
        oriented = list(reversed(item.points)) if reversed_ else list(item.points)
        chain_start = _length(points)
        if points:
            chain_start += math.dist(points[-1][:2], oriented[0][:2])
            if math.dist(points[-1][:2], oriented[0][:2]) <= COINCIDENT_M:
                # На стыке остаётся точка с отметкой: Z = 0 у 2D-линии — отметки нет.
                if abs(points[-1][2]) <= ZERO_Z_TOLERANCE_M < abs(oriented[0][2]):
                    points[-1] = oriented[0]
                oriented = oriented[1:]
        points.extend(oriented)
        parts.append(StitchPart(item.handle, reversed_, item.length_m, chain_start))
        exit_end = 2 * line_index + (1 - start_side)
        if exit_end not in joins:
            break
        other = joins[exit_end]
        if other // 2 in visited:
            break
        line_index, start_side = other // 2, other % 2
    return StitchedLine(points=points, parts=parts)


def _report_gaps(stitched: Sequence[StitchedLine]) -> list[StitchGap]:
    """Свободные концы разных линий ближе 5 м: разрыв или излом, который не сшит."""

    ends: list[tuple[XY, int]] = []
    for number, item in enumerate(stitched):
        if item.points[0][:2] == item.points[-1][:2] and len(item.points) > 2:
            continue
        ends.append(((item.points[0][0], item.points[0][1]), number))
        ends.append(((item.points[-1][0], item.points[-1][1]), number))

    pairs: list[tuple[float, int, int]] = []
    for a, b in _near_pairs([point for point, _ in ends], GAP_REPORT_M):
        if ends[a][1] == ends[b][1]:
            continue
        distance = math.dist(ends[a][0], ends[b][0])
        if distance <= GAP_REPORT_M:
            pairs.append((distance, a, b))

    gaps: list[StitchGap] = []
    used: set[int] = set()
    for distance, a, b in sorted(pairs):
        if a in used or b in used:
            continue
        used.update((a, b))
        gaps.append(StitchGap(ends[a][0], ends[b][0], distance, "turn" if distance <= STITCH_GAP_M else "gap"))
    return gaps
