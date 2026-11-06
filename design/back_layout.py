"""Шаблон раскладки «от тыла» (`pattern_params.layout_anchor = "back"`).

Владелец раскладывает блок от тыла: приконтурный ряд — параллельно линии
отрыва (наиболее длинной несвободной стороне контура) на 0,5–0,8·b от неё,
эшелоны (столбцы) — перпендикулярно ей к свободной поверхности с шагом b, у
бровки каждый эшелон заканчивается по ЛСП: ничего, наклон к откосу или
скважина на остатке. Сетка одна, прямоугольная; на дуге тыла приконтурный ряд
выходит лесенкой. Подробности — `Docs/FRONT_ROWS_TILT.md`, «Шаблон «от тыла»».
"""
from __future__ import annotations

import math

from design.models import BlockContour

Point2 = tuple[float, float]

# Излом между соседними несвободными рёбрами больше этого делит стороны
# контура; дуга из мелких рёбер остаётся одной стороной, °.
BACK_SPLIT_TURN_DEG = 45.0


def _free_edge_indices(contour: BlockContour) -> set[int]:
    """Номера свободных рёбер кольца: ребро k — от вершины k к k + 1 (по модулю n)."""
    n = len(contour.vertices)
    free: set[int] = set()
    for chain in contour.free_faces:
        for i, j in zip(chain, chain[1:]):
            if not (0 <= i < n and 0 <= j < n):
                continue
            if j == (i + 1) % n:
                free.add(i)
            elif i == (j + 1) % n:
                free.add(j)
    return free


def _turn_deg(a: Point2, b: Point2) -> float:
    """Угол между направлениями двух рёбер, °."""
    cross = a[0] * b[1] - a[1] * b[0]
    dot = a[0] * b[0] + a[1] * b[1]
    return abs(math.degrees(math.atan2(cross, dot)))


def back_side(contour: BlockContour) -> list[Point2] | None:
    """Тыл блока — вершины наиболее длинной несвободной стороны по обходу контура.

    Сторона — серия подряд идущих несвободных рёбер, излом между соседними
    больше `BACK_SPLIT_TURN_DEG` её делит. Длина стороны — сумма длин рёбер.
    None — несвободных рёбер нет (или у контура меньше трёх вершин).
    """
    pts = contour.points_xy
    n = len(pts)
    if n < 3:
        return None
    free = _free_edge_indices(contour)
    vectors = [(pts[(k + 1) % n][0] - pts[k][0], pts[(k + 1) % n][1] - pts[k][1]) for k in range(n)]
    lengths = [math.hypot(*v) for v in vectors]
    edges = [k for k in range(n) if k not in free and lengths[k] > 1e-9]
    if not edges:
        return None

    def joins(prev: int, nxt: int) -> bool:
        # Между рёбрами допускаются только вырожденные несвободные (повтор вершины).
        k = (prev + 1) % n
        while k != nxt:
            if k in free or lengths[k] > 1e-9:
                return False
            k = (k + 1) % n
        return _turn_deg(vectors[prev], vectors[nxt]) <= BACK_SPLIT_TURN_DEG

    # Начало обхода — ребро, которое не продолжает предыдущее: так серия,
    # проходящая через вершину 0, не рвётся. Замкнутая серия (всё кольцо
    # без изломов) начинается с первого ребра.
    start = next(
        (pos for pos, k in enumerate(edges) if not joins(edges[pos - 1], k) or len(edges) == 1),
        0,
    )
    ordered = edges[start:] + edges[:start]
    sides: list[list[int]] = []
    for k in ordered:
        if sides and joins(sides[-1][-1], k):
            sides[-1].append(k)
        else:
            sides.append([k])
    best = max(sides, key=lambda side: sum(lengths[k] for k in side))
    return [pts[best[0]]] + [pts[(k + 1) % n] for k in best]


def back_azimuth_deg(contour: BlockContour) -> float | None:
    """Азимут хорды тыла в [0, 180): 0° = +Y, по часовой (как `geometry.crest_azimuth_deg`)."""
    side = back_side(contour)
    if side is None:
        return None
    dx, dy = side[-1][0] - side[0][0], side[-1][1] - side[0][1]
    if math.hypot(dx, dy) < 1e-9:
        return None
    return (math.degrees(math.atan2(dx, dy)) % 180.0) % 180.0
