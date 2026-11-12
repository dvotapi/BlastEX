"""«Предложить посты» на ситуационном плане Г.5 (TASK-018, PR 6, §14, В6).

Посты охраны — там, где дороги ситуации карьера пересекают границу опасной
зоны для людей: по ним в зону въезжают люди и техника. Взрывная станция и
укрытие — за зоной, на дороге (если есть) с отступом от границы. Это только
предложение: окно ставит точки в форму, пользователь их правит.
Данные — проектная `graphics` контекста v2 (`design/mass_blast_graphics.py`).
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from design.spatial.cad.model import SITUATION_KIND_ROAD

__all__ = ["POST_MERGE_M", "STATION_OFFSET_M", "suggest_layout"]

# Пересечения дорог с границей ближе этого — один пост.
POST_MERGE_M = 50.0
# Станция и укрытие — за границей зоны для людей на столько метров.
STATION_OFFSET_M = 60.0
SHELTER_OFFSET_M = 120.0
# Шаг и предел поиска точки вне всех зон по лучу от блока.
RAY_STEP_M = 25.0
RAY_LIMIT_M = 50_000.0


def _outside_on_ray(zone, center: Point, ux: float, uy: float, start: float, offset: float) -> Point:
    """Точка на луче от блока: дальше всей геометрии зоны (у проекта из нескольких
    блоков зоны бывают несвязными) и ещё на `offset` за её последней границей."""

    distance = start
    while distance < RAY_LIMIT_M:
        point = Point(center.x + ux * distance, center.y + uy * distance)
        if not zone.covers(point):
            beyond = Point(center.x + ux * (distance + offset), center.y + uy * (distance + offset))
            # За границей может начаться соседняя зона — тогда ищем дальше.
            if not zone.covers(beyond):
                return beyond
        distance += RAY_STEP_M
    return Point(center.x + ux * distance, center.y + uy * distance)


def _zone(graphics: Mapping[str, Any]) -> tuple[Polygon | None, float]:
    zones = [zone for zone in graphics.get("zones") or [] if zone.get("kind") == "people"]
    if not zones:
        return None, 0.0
    zone = zones[0]
    polygons = [Polygon(ring) for ring in zone.get("rings") or [] if len(ring) >= 3]
    shape = unary_union(polygons) if polygons else None
    return (shape if shape is not None and not shape.is_empty else None), float(zone.get("value_m") or 0.0)


def _block_center(graphics: Mapping[str, Any]) -> Point | None:
    polygons = [Polygon(ring) for ring in graphics.get("outlines") or [] if len(ring) >= 3]
    if not polygons:
        return None
    return unary_union(polygons).centroid


def suggest_layout(graphics: Mapping[str, Any]) -> dict[str, Any]:
    """Посты на пересечениях дорог с границей зоны для людей, станция и укрытие за зоной.

    Без ситуации карьера или зоны — пусто (`reason` — почему).
    """

    if not graphics.get("has_situation"):
        return {"posts": [], "points": [], "reason": "Нет ситуации карьера: дороги, на которых ставятся посты, неизвестны."}
    zone, radius = _zone(graphics)
    center = _block_center(graphics)
    if zone is None or center is None:
        return {"posts": [], "points": [], "reason": "Опасная зона для людей не рассчитана: проверьте проект."}
    boundary = zone.boundary
    crossings: list[tuple[Point, str]] = []
    road_lines: list[LineString] = []
    for layer in graphics.get("situation") or []:
        if layer.get("kind") != SITUATION_KIND_ROAD:
            continue
        for line in layer.get("lines") or []:
            if len(line) < 2:
                continue
            road = LineString(line)
            road_lines.append(road)
            hit = road.intersection(boundary)
            points = [hit] if isinstance(hit, Point) else list(getattr(hit, "geoms", []))
            crossings += [(point, str(layer.get("name") or "дорога")) for point in points if isinstance(point, Point)]
    merged: list[tuple[Point, str]] = []
    for point, name in crossings:
        if all(point.distance(other) > POST_MERGE_M for other, _ in merged):
            merged.append((point, name))
    # Посты — по часовой стрелке от севера: так их нумерует и Г.5.
    merged.sort(key=lambda item: math.atan2(item[0].x - center.x, item[0].y - center.y) % (2 * math.pi))
    posts = [
        {"code": str(number), "location": f"{name}, на границе опасной зоны ({round(radius)} м)"}
        for number, (_, name) in enumerate(merged, start=1)
    ]
    points = [
        {"kind": "guard_post", "ref": str(number), "x": round(point.x, 1), "y": round(point.y, 1), "label": ""}
        for number, (point, _) in enumerate(merged, start=1)
    ]
    # Станция и укрытие — по направлению первого поста (въезд), за границей зоны.
    anchor = merged[0][0] if merged else Point(center.x - radius, center.y)
    dx, dy = anchor.x - center.x, anchor.y - center.y
    length = math.hypot(dx, dy) or 1.0
    for kind, offset in (("blast_station", STATION_OFFSET_M), ("shelter", SHELTER_OFFSET_M)):
        target = _outside_on_ray(zone, center, dx / length, dy / length, length, offset)
        points.append({"kind": kind, "ref": "", "x": round(target.x, 1), "y": round(target.y, 1), "label": ""})
    return {"posts": posts, "points": points, "reason": "" if posts else "Дороги ситуации не пересекают границу зоны для людей."}
