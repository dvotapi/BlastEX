"""Плоская и пространственная геометрия контура блока и скважин.

Никаких внешних зависимостей — только stdlib `math`. Полигональные операции
(`point_in_polygon`, `polygon_area`, `offset_polygon`) реализованы «в лоб»:
точны для выпуклых и умеренно невыпуклых контуров, на острых вогнутых углах
при большом смещении возможны самопересечения — это ограничение сознательное
(проект не тянет shapely ради него) и проверяется в `design.analysis.validate`.
"""
from __future__ import annotations

import math

from design.models import BlockContour, Hole, Point3

Point2 = tuple[float, float]


def point_in_polygon(p: Point2, poly: list[Point2]) -> bool:
    """Чётность пересечений луча (ray casting). Точки на ребре считаются внутри."""
    x, y = p
    n = len(poly)
    if n < 3:
        return False
    inside = False
    x1, y1 = poly[-1]
    for x2, y2 in poly:
        # На самом ребре — точка внутри контура.
        if _point_on_segment((x, y), (x1, y1), (x2, y2)):
            return True
        if (y1 > y) != (y2 > y):
            x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_intersect:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def _point_on_segment(p: Point2, a: Point2, b: Point2, eps: float = 1e-9) -> bool:
    px, py = p
    ax, ay = a
    bx, by = b
    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if abs(cross) > eps:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dot < -eps:
        return False
    length_sq = (bx - ax) ** 2 + (by - ay) ** 2
    return dot <= length_sq + eps


def polygon_signed_area(poly: list[Point2]) -> float:
    """Формула Гаусса (шнурования). Положительна для CCW-обхода."""
    n = len(poly)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def polygon_area(poly: list[Point2]) -> float:
    return abs(polygon_signed_area(poly))


def ensure_ccw(poly: list[Point2]) -> list[Point2]:
    """Возвращает полигон в порядке против часовой стрелки."""
    if polygon_signed_area(poly) < 0:
        return list(reversed(poly))
    return list(poly)


def polygon_centroid(poly: list[Point2]) -> Point2:
    area = polygon_signed_area(poly)
    n = len(poly)
    if n < 3 or area == 0:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return (sum(xs) / max(1, len(xs)), sum(ys) / max(1, len(ys)))
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    factor = 1.0 / (6.0 * area)
    return (cx * factor, cy * factor)


def _line_intersection(
    p1: Point2, d1: Point2, p2: Point2, d2: Point2
) -> Point2 | None:
    """Пересечение двух прямых, заданных точкой и направлением."""
    x1, y1 = p1
    dx1, dy1 = d1
    x2, y2 = p2
    dx2, dy2 = d2
    denom = dx1 * dy2 - dy1 * dx2
    if abs(denom) < 1e-12:
        return None
    t = ((x2 - x1) * dy2 - (y2 - y1) * dx2) / denom
    return (x1 + dx1 * t, y1 + dy1 * t)


def offset_polygon(poly: list[Point2], distance_m: float) -> list[Point2]:
    """Сдвигает контур внутрь (distance_m > 0) на заданное расстояние по нормалям.

    Реализация — классическое пересечение смещённых рёберных прямых. Для
    сильно невыпуклых контуров и больших смещений соседние прямые могут
    давать вырожденное или "вывернутое" пересечение — в этом случае вершина
    просто сдвигается вдоль биссектрисы на distance_m без строгого пересечения.
    """
    ring = ensure_ccw(poly)
    n = len(ring)
    if n < 3 or distance_m == 0.0:
        return list(ring)

    offset_lines: list[tuple[Point2, Point2]] = []
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            offset_lines.append(((x1, y1), (1.0, 0.0)))
            continue
        dx, dy = dx / length, dy / length
        # Внутренняя нормаль для CCW-контура — поворот направления на +90°
        # (интерьер лежит слева от направленного ребра при обходе против часовой).
        nx, ny = -dy, dx
        offset_lines.append(((x1 + nx * distance_m, y1 + ny * distance_m), (dx, dy)))

    new_vertices: list[Point2] = []
    for i in range(n):
        prev_point, prev_dir = offset_lines[i - 1]
        curr_point, curr_dir = offset_lines[i]
        intersection = _line_intersection(prev_point, prev_dir, curr_point, curr_dir)
        if intersection is None:
            # Рёбра почти параллельны — сдвигаем вершину вдоль средней нормали.
            intersection = curr_point
        new_vertices.append(intersection)
    return new_vertices


def block_volume(contour: BlockContour) -> float:
    """Объём блока: площадь контура × высота уступа."""
    return polygon_area(contour.points_xy) * contour.bench.height_m


def hole_from_collar(
    collar: Point3, depth_m: float, angle_deg: float, azimuth_deg: float
) -> Point3:
    """Забой скважины по устью, глубине вдоль оси, углу от вертикали и азимуту."""
    angle_rad = math.radians(angle_deg)
    azimuth_rad = math.radians(azimuth_deg)
    horizontal = depth_m * math.sin(angle_rad)
    vertical = depth_m * math.cos(angle_rad)
    dx = horizontal * math.sin(azimuth_rad)
    dy = horizontal * math.cos(azimuth_rad)
    return Point3(x=collar.x + dx, y=collar.y + dy, z=collar.z - vertical)


def angle_azimuth(collar: Point3, toe: Point3) -> tuple[float, float]:
    """Обратная задача: угол от вертикали и азимут по устью и забою."""
    horizontal = math.hypot(toe.x - collar.x, toe.y - collar.y)
    vertical = collar.z - toe.z
    angle_deg = math.degrees(math.atan2(horizontal, vertical)) if (horizontal or vertical) else 0.0
    dx, dy = toe.x - collar.x, toe.y - collar.y
    azimuth_deg = math.degrees(math.atan2(dx, dy)) % 360.0 if (dx or dy) else 0.0
    return angle_deg, azimuth_deg


def point_to_segment_distance(p: Point2, a: Point2, b: Point2) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def distance_to_free_faces(point_xy: Point2, contour: BlockContour) -> float | None:
    """Минимальное расстояние от точки до ближайшего открытого откоса блока."""
    verts = contour.points_xy
    if not verts or not contour.free_faces:
        return None
    best: float | None = None
    for edge in contour.free_faces:
        for i in range(len(edge) - 1):
            a = verts[edge[i]]
            b = verts[edge[i + 1]]
            dist = point_to_segment_distance(point_xy, a, b)
            if best is None or dist < best:
                best = dist
    return best


def true_burden(hole: Hole, contour: BlockContour) -> float | None:
    """ЛНС по забою (учитывает наклон скважины) до ближайшего открытого откоса."""
    return distance_to_free_faces((hole.toe.x, hole.toe.y), contour)


def local_basis(row_azimuth_deg: float) -> tuple[Point2, Point2]:
    """Базис раскладки: направление вдоль ряда и направление продвижения рядов."""
    az = math.radians(row_azimuth_deg)
    row_dir = (math.sin(az), math.cos(az))
    advance_dir = (row_dir[1], -row_dir[0])
    return row_dir, advance_dir


def _face_reference_point(contour: BlockContour) -> Point2 | None:
    verts = contour.points_xy
    if not verts or not contour.free_faces:
        return None
    pts: list[Point2] = []
    for edge in contour.free_faces:
        for idx in edge:
            if 0 <= idx < len(verts):
                pts.append(verts[idx])
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def pattern_origin(
    contour: BlockContour, row_dir: Point2, advance_dir: Point2
) -> tuple[Point2, Point2]:
    """Начало отсчёта раскладки и направление продвижения рядов «вглубь» блока.

    Если у контура заданы открытые откосы (`free_faces`), отсчёт ведётся от их
    средней точки, а направление продвижения разворачивается в сторону центра
    масс контура. Иначе — от вершины с минимальной проекцией на направление
    продвижения (устойчивый детерминированный выбор без открытого откоса).
    """
    verts = contour.points_xy
    face_ref = _face_reference_point(contour)
    if face_ref is not None:
        centroid = polygon_centroid(verts) if verts else face_ref
        to_centroid = (centroid[0] - face_ref[0], centroid[1] - face_ref[1])
        dot = to_centroid[0] * advance_dir[0] + to_centroid[1] * advance_dir[1]
        if dot < 0:
            advance_dir = (-advance_dir[0], -advance_dir[1])
        return face_ref, advance_dir

    if not verts:
        return (0.0, 0.0), advance_dir
    origin = min(verts, key=lambda p: p[0] * advance_dir[0] + p[1] * advance_dir[1])
    return origin, advance_dir
