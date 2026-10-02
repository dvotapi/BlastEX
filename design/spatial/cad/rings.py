"""Кольцо контура блока: нормализация и проверки (TASK-013, PR 2).

Контур блока — простой замкнутый полигон в плане. Перед проверкой кольцо
нормализуется (§2 «Модель блока и контур»): обход против часовой стрелки,
без повтора первой точки, без дублей и коллинеарных вершин в пределах 1 см.
Проверки дают тексты для пользователя: «Построить блок» неактивна, пока есть
хоть одна ошибка.

Координаты МСК — миллионы метров. Проверки shapely идут в локальной системе
(сдвиг к левому нижнему углу), а места ошибок возвращаются в координатах
чертежа.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import shapely

from design.spatial.cad.model import ru_number

XY = tuple[float, float]

# Дубли и коллинеарные вершины ближе этого — одна вершина (§2).
DEDUP_TOLERANCE_M = 0.01
# Ребро короче — ошибка: такие рёбра ломают сетку и разметку откосов (§2).
MIN_EDGE_M = 0.05
# Площадь меньше — точки контура лежат на одной линии.
MIN_AREA_M2 = 1e-6


@dataclass
class RingIssue:
    """Ошибка контура: код, текст для пользователя и место на чертеже."""

    code: str
    message: str
    point: XY | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "point": list(self.point) if self.point else None}


@dataclass(frozen=True)
class LocalFrame:
    """Локальная система координат: начало — левый нижний угол точек."""

    ox: float = 0.0
    oy: float = 0.0

    @classmethod
    def of(cls, points: Iterable[XY]) -> LocalFrame:
        xs: list[float] = []
        ys: list[float] = []
        for x, y in points:
            xs.append(x)
            ys.append(y)
        if not xs:
            return cls()
        return cls(min(xs), min(ys))

    def to_local(self, points: Iterable[XY]) -> list[XY]:
        return [(x - self.ox, y - self.oy) for x, y in points]

    def to_world(self, points: Iterable[XY]) -> list[XY]:
        return [(x + self.ox, y + self.oy) for x, y in points]

    def point_to_world(self, point: XY) -> XY:
        return (point[0] + self.ox, point[1] + self.oy)


def point_label(point: XY) -> str:
    """«(12,34; 56,78)» — место на чертеже для текстов ошибок."""

    return f"({ru_number(point[0], 2)}; {ru_number(point[1], 2)})"


def signed_area(points: Sequence[XY]) -> float:
    if len(points) < 3:
        return 0.0
    ox, oy = points[0]
    total = 0.0
    for (ax, ay), (bx, by) in zip(points, [*points[1:], points[0]]):
        total += (ax - ox) * (by - oy) - (bx - ox) * (ay - oy)
    return total / 2


def ring_area(points: Sequence[XY]) -> float:
    return abs(signed_area(points))


def ring_perimeter(points: Sequence[XY]) -> float:
    if len(points) < 2:
        return 0.0
    return sum(math.dist(a, b) for a, b in zip(points, [*points[1:], points[0]]))


def _drop_duplicates(points: Sequence[XY]) -> list[XY]:
    clean: list[XY] = []
    for point in points:
        if not clean or math.dist(clean[-1], point) > DEDUP_TOLERANCE_M:
            clean.append((float(point[0]), float(point[1])))
    while len(clean) > 1 and math.dist(clean[0], clean[-1]) <= DEDUP_TOLERANCE_M:
        clean.pop()
    return clean


def _between(prev: XY, point: XY, nxt: XY) -> bool:
    """Вершина лежит на отрезке prev–next не дальше 1 см: она лишняя.

    Вершина на продолжении отрезка («шип» назад вдоль ребра) не лишняя: её
    удаление молча изменило бы форму, пусть ошибку покажет проверка.
    """

    dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return False
    t = ((point[0] - prev[0]) * dx + (point[1] - prev[1]) * dy) / length2
    if t < 0 or t > 1:
        return False
    distance = abs((point[0] - prev[0]) * dy - (point[1] - prev[1]) * dx) / math.sqrt(length2)
    return distance <= DEDUP_TOLERANCE_M


def _drop_collinear(points: list[XY]) -> list[XY]:
    """Вершины на прямой в пределах 1 см — прочь, за линейное время.

    Убирать можно, только пока все исходные точки остаются в 1 см от новой
    хорды. Сравнение вершины лишь с текущими соседями копит сдвиг: на дуге с
    частыми вершинами каждая «на прямой» со своими соседями, а круг R = 100 м
    с шагом 0,25 м уходил внутрь на 8 см и терял 0,1 % площади.
    """

    count = len(points)
    if count <= 3:
        return list(points)
    # Начало — крайняя точка: она на выпуклой оболочке, шов реже приходится на прямую.
    first = min(range(count), key=lambda index: points[index])
    order = [*points[first:], *points[:first], points[first]]
    ring: list[XY] = [order[0]]
    # gaps[i] — исходные точки, убранные между ring[i] и ring[i + 1] (по кругу).
    gaps: list[list[XY]] = []
    anchor = 0
    while anchor < count:
        end = _furthest_end(order, anchor)
        ring.append(order[end])
        gaps.append(order[anchor + 1 : end])
        anchor = end
    ring.pop()  # последняя — снова первая точка
    if len(ring) < 3:
        # Все точки на одной прямой: проверка контура скажет «площадь 0».
        return list(points)

    # Шов: первая точка не проверялась, а убранная на шве меняет соседей у
    # новых крайних — проверяем их, пока убирается.
    changed = True
    while changed and len(ring) > 3:
        changed = False
        for index in (0, len(ring) - 1):
            inner = [*gaps[index - 1], ring[index], *gaps[index]]
            if all(_between(ring[index - 1], item, ring[(index + 1) % len(ring)]) for item in inner):
                gaps[index - 1] = inner
                del ring[index]
                del gaps[index]
                changed = True
                break
    return ring


def _furthest_end(order: Sequence[XY], anchor: int) -> int:
    """Самая дальняя вершина, до которой хорда от `anchor` проходит не дальше
    1 см от всех промежуточных точек (как `_between`).

    Допустимые направления хорды — пересечение «конусов» промежуточных точек:
    точка на расстоянии r от начала допускает отклонение asin(1 см / r).
    """

    ax, ay = order[anchor]
    base: float | None = None
    low, high = -math.pi, math.pi
    farthest = 0.0
    end = anchor + 1
    for candidate in range(anchor + 2, len(order)):
        px, py = order[candidate - 1][0] - ax, order[candidate - 1][1] - ay
        radius = math.hypot(px, py)
        if base is None:
            base = math.atan2(py, px)
        angle = _turn(math.atan2(py, px) - base)
        spread = math.pi / 2 if radius <= DEDUP_TOLERANCE_M else math.asin(DEDUP_TOLERANCE_M / radius)
        low, high = max(low, angle - spread), min(high, angle + spread)
        farthest = max(farthest, radius)
        qx, qy = order[candidate][0] - ax, order[candidate][1] - ay
        reach = math.hypot(qx, qy)
        if low > high or reach == 0 or not low <= _turn(math.atan2(qy, qx) - base) <= high:
            break
        # Хорда короче самой дальней точки — путь вернулся назад: проверяем точно.
        if reach < farthest and not all(
            _between(order[anchor], order[index], order[candidate]) for index in range(anchor + 1, candidate)
        ):
            break
        end = candidate
    return end


def _turn(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def normalize_ring(points: Sequence[XY]) -> list[XY]:
    """Кольцо против часовой стрелки, без повтора первой точки и лишних вершин."""

    ring = _drop_collinear(_drop_duplicates(points))
    if signed_area(ring) < 0:
        ring.reverse()
    return ring


_REASON_POINT = re.compile(r"\[\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]")


def _validity_issue(reason: str, frame: LocalFrame) -> RingIssue:
    """Перевод `explain_validity` shapely на язык пользователя."""

    match = _REASON_POINT.search(reason)
    point = frame.point_to_world((float(match.group(1)), float(match.group(2)))) if match else None
    if "Self-intersection" in reason:
        where = f" в точке {point_label(point)}" if point else ""
        return RingIssue(
            "self_intersection",
            f"Контур пересекает сам себя{where}. Проверьте порядок и направление участков.",
            point,
        )
    if "Too few points" in reason:
        return RingIssue("too_few_points", "В контуре меньше трёх различных точек.", point)
    if "Invalid Coordinate" in reason:
        return RingIssue("invalid", "В контуре есть точка без координат.", point)
    where = f" у точки {point_label(point)}" if point else ""
    return RingIssue("invalid", f"Контур некорректен{where} ({reason.split('[')[0].strip()}).", point)


def check_ring(points: Sequence[XY]) -> list[RingIssue]:
    """Ошибки кольца: мало точек, нулевая площадь, самопересечение, короткие рёбра."""

    ring = [(float(x), float(y)) for x, y in points]
    if len(ring) < 3:
        return [RingIssue("too_few_points", "В контуре меньше трёх различных точек.")]
    frame = LocalFrame.of(ring)
    polygon = shapely.Polygon(frame.to_local(ring))
    # Нулевая площадь «восьмёрки» — не вырожденность, а самопересечение:
    # вырожден контур, у которого все точки на одной линии.
    if polygon.convex_hull.area <= MIN_AREA_M2:
        return [RingIssue("zero_area", "Площадь контура равна нулю: точки лежат на одной линии.")]

    issues: list[RingIssue] = []
    reason = shapely.is_valid_reason(polygon)
    if reason != "Valid Geometry":
        issues.append(_validity_issue(reason, frame))
    for index, (a, b) in enumerate(zip(ring, [*ring[1:], ring[0]])):
        length = math.dist(a, b)
        if length < MIN_EDGE_M:
            issues.append(
                RingIssue(
                    "short_edge",
                    f"Ребро {index + 1} короче {ru_number(MIN_EDGE_M, 2)} м ({ru_number(length, 2)} м) "
                    f"у точки {point_label(a)}.",
                    a,
                )
            )
    return issues
