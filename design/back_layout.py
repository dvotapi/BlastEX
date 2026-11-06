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
from dataclasses import dataclass, field
from typing import Any

import shapely

from design.geometry import local_basis, point_in_polygon, polygon_centroid, polygon_signed_area
from design.models import BlockContour

Point2 = tuple[float, float]

# Излом между соседними несвободными рёбрами больше этого делит стороны
# контура; дуга из мелких рёбер остаётся одной стороной, °.
BACK_SPLIT_TURN_DEG = 45.0
# Отступ приконтурного ряда от тыла — доля шага b: без ключа `back_offset_m`
# 0,65·b, допустимый диапазон 0,5–0,8·b (решение владельца 06.11.2026).
BACK_OFFSET_DEFAULT_RATIO = 0.65
BACK_OFFSET_RANGE = (0.5, 0.8)


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


def back_offset_m(params: dict[str, Any], burden_b: float) -> float:
    """Отступ приконтурного ряда от тыла: `back_offset_m`, без него (или при
    неверном, не положительном значении) — `BACK_OFFSET_DEFAULT_RATIO`·b."""
    raw = (params or {}).get("back_offset_m")
    try:
        value = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        value = None
    if value is None or not math.isfinite(value) or value <= 0:
        return BACK_OFFSET_DEFAULT_RATIO * burden_b
    return value


@dataclass
class BackColumn:
    """Эшелон (столбец) решётки от тыла.

    `nodes` — регулярные узлы от тыла к бровке с шагом b; `rows` — номер ряда
    решётки у каждого узла (один на всю сетку: узлы на одной линии ряда — один
    номер, первый ряд решётки — 0); `index` — номер столбца решётки по оси ряда.
    """

    index: int
    nodes: list[Point2] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)


def _toward_face(contour: BlockContour, back: list[Point2], advance: Point2) -> Point2:
    """`advance` или обратное ему — направление от тыла к свободной поверхности
    (без неё — к центру масс контура)."""
    mid = (0.5 * (back[0][0] + back[-1][0]), 0.5 * (back[0][1] + back[-1][1]))
    pts = contour.points_xy
    free = sorted({i for chain in contour.free_faces for i in chain if 0 <= i < len(pts)})
    if free:
        target = (sum(pts[i][0] for i in free) / len(free), sum(pts[i][1] for i in free) / len(free))
    else:
        target = polygon_centroid(pts)
    dot = (target[0] - mid[0]) * advance[0] + (target[1] - mid[1]) * advance[1]
    return advance if dot >= 0 else (-advance[0], -advance[1])


def back_columns(
    contour: BlockContour,
    boundary: list[Point2],
    row_azimuth_deg: float,
    spacing_a: float,
    burden_b: float,
    back_offset: float,
    shift_along: float,
) -> list[BackColumn]:
    """Эшелоны решётки от тыла: узлы каждого от приконтурного ряда к бровке.

    Решётка одна: ряды — по `row_azimuth_deg` (`local_basis`), столбцы
    перпендикулярно; начало по v — хорда тыла, сдвинутая к бровке на
    `back_offset`, по u — середина хорды плюс `shift_along` (по модулю a).
    Первый узел эшелона — узел решётки внутри `boundary`, расстояние которого
    до тыла в `BACK_OFFSET_RANGE`·b, ближайший по эшелону к линии отступа (тыл,
    смещённый внутрь на `back_offset`); такого нет — узел, ближайший к
    диапазону (при равенстве — дальше от тыла). Расстояние до тыла — до
    ломаной тыла, если эшелон её пересекает, иначе — по эшелону от входа в
    контур. Дальше — узлы внутри `boundary` с шагом b к бровке. Пустые эшелоны
    не возвращаются; без тыла — пусто.
    """
    back = back_side(contour)
    if back is None or spacing_a <= 0 or burden_b <= 0 or len(boundary) < 3:
        return []
    row_dir, advance = local_basis(row_azimuth_deg)
    advance = _toward_face(contour, back, advance)
    origin = (0.5 * (back[0][0] + back[-1][0]), 0.5 * (back[0][1] + back[-1][1]))

    def world(u: float, v: float) -> Point2:
        return (origin[0] + u * row_dir[0] + v * advance[0], origin[1] + u * row_dir[1] + v * advance[1])

    def local(p: Point2) -> tuple[float, float]:
        dx, dy = p[0] - origin[0], p[1] - origin[1]
        return dx * row_dir[0] + dy * row_dir[1], dx * advance[0] + dy * advance[1]

    ring = list(boundary) + [boundary[0]]
    outline = shapely.LineString(ring)
    back_line = shapely.LineString(back)
    # Тыл, смещённый внутрь: внутренность кольца против часовой — слева от обхода.
    ccw = polygon_signed_area(contour.points_xy) > 0
    offset_line = shapely.offset_curve(back_line, back_offset if ccw else -back_offset)
    uv = [local(p) for p in boundary]
    u_lo, u_hi = min(u for u, _ in uv), max(u for u, _ in uv)
    v_lo, v_hi = min(v for _, v in uv), max(v for _, v in uv)
    lo_range, hi_range = BACK_OFFSET_RANGE[0] * burden_b, BACK_OFFSET_RANGE[1] * burden_b
    phase = shift_along % spacing_a
    k_lo = math.floor((u_lo - phase) / spacing_a)
    k_hi = math.ceil((u_hi - phase) / spacing_a)
    j_lo = math.floor((v_lo - back_offset) / burden_b) - 1
    j_hi = math.ceil((v_hi - back_offset) / burden_b) + 1

    def crossings(geom: object, u: float) -> list[float]:
        line = shapely.LineString([world(u, v_lo - burden_b), world(u, v_hi + burden_b)])
        hit = shapely.intersection(line, geom)
        pts = [q for q in shapely.get_coordinates(hit)] if not hit.is_empty else []
        return sorted(local((float(q[0]), float(q[1])))[1] for q in pts)

    columns: list[BackColumn] = []
    for k in range(k_lo, k_hi + 1):
        u = phase + k * spacing_a
        inside = [
            j for j in range(j_lo, j_hi + 1) if point_in_polygon(world(u, back_offset + j * burden_b), boundary)
        ]
        if not inside:
            continue
        crosses_back = bool(crossings(back_line, u))
        if crosses_back:
            nodes = [world(u, back_offset + j * burden_b) for j in inside]
            dist = [float(d) for d in shapely.distance(shapely.points(nodes), back_line)]
        else:
            entry = crossings(outline, u)
            start = entry[0] if entry else v_lo
            dist = [back_offset + j * burden_b - start for j in inside]
        target_hits = crossings(offset_line, u) if crosses_back else []
        target = target_hits[0] if target_hits else None

        def gap(n: int) -> float:
            return max(lo_range - dist[n], dist[n] - hi_range, 0.0)

        def key(n: int) -> tuple[float, float]:
            if gap(n) > 0:
                return (gap(n), -dist[n])
            v = back_offset + inside[n] * burden_b
            return (0.0, abs(v - target) if target is not None else abs(dist[n] - back_offset))

        first = min(range(len(inside)), key=key)
        picked = inside[first:]
        columns.append(
            BackColumn(index=k, nodes=[world(u, back_offset + j * burden_b) for j in picked], rows=list(picked))
        )
    if columns:
        base = min(r for col in columns for r in col.rows)
        for col in columns:
            col.rows = [r - base for r in col.rows]
    return columns
