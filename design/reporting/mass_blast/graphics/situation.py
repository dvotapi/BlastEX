"""Г.5 — ситуационный план (форма v0.8, TASK-018 §4).

Слева — карта, север вверх, без поворота: блоки, кольца опасных зон, ситуация
TASK-013 по видам, охраняемые объекты с номером и линией до блока, точки
постов, взрывной станции, укрытия и места сбора (`layout_points`). Справа —
зоны, охраняемые объекты, посты, станция. Масштаб — ряд Г.5 1:2000 / 1:5000 /
1:10 000 / 1:25 000 (решение владельца В4), самый крупный, при котором зона
для людей (и большие зоны), объекты и точки помещаются. Данные — `context["graphics"]`.
"""
from __future__ import annotations

from typing import Any, Mapping

import shapely
from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Polygon, PolyLine, Rect, String
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle
from shapely.geometry import Polygon as ShapelyPolygon

from design.reporting import plan_sheet
from design.reporting.brand import FONT, FONT_BOLD, GRAPHITE, GREY, LINE, RED
from design.reporting.mass_blast.common import cell, grid_style, num, p, rich, spacer, text
from design.reporting.mass_blast.graphics.sheet import FIELD_H_MM, FIELD_W_MM, LEGEND_H_MM, ORANGE, SITUATION, fit, pts
from design.reporting.plan_sheet import PlanView

SITUATION_SCALES = (2000, 5000, 10000, 25000)
MAP_W_MM = 165.0
MAP_H_MM = FIELD_H_MM + LEGEND_H_MM
PANEL_W_MM = FIELD_W_MM - MAP_W_MM - 4.0
MAP_PAD_MM = 6.0
MAX_OBJECT_ROWS = 14
MAX_POST_ROWS = 10
ROAD = HexColor("#8C6D46")
POWER = HexColor("#1F6FB2")
ZONE_STYLE = {
    "people": dict(strokeColor=RED, strokeWidth=1.0),
    "mechanisms": dict(strokeColor=ORANGE, strokeWidth=0.9, strokeDashArray=[2.5 * mm, 1.2 * mm]),
    "buildings": dict(strokeColor=GRAPHITE, strokeWidth=0.7, strokeDashArray=[0.8 * mm, 0.8 * mm]),
}
ZONE_LABELS = {"people": "опасная зона для людей", "mechanisms": "для механизмов", "buildings": "здания и сооружения"}
LAYER_STYLE = {
    "building": dict(strokeColor=GRAPHITE, strokeWidth=0.6),
    "road": dict(strokeColor=ROAD, strokeWidth=0.8),
    "power_line": dict(strokeColor=POWER, strokeWidth=0.6, strokeDashArray=[1.5 * mm, 0.8 * mm]),
}
POINT_CODES = {"guard_post": "П", "blast_station": "ВС", "shelter": "У", "gather": "МС"}
POINT_TITLES = {"blast_station": "Взрывная станция", "shelter": "Укрытие", "gather": "Место сбора"}
SCHEDULE_KEYS = {"blast_station": "station", "shelter": "shelter", "gather": "gather"}
NO_SITUATION = "Ситуации карьера нет: объекты, посты и дороги привязать по плану карьера."
NOT_FITTED = "План не помещается в масштаб 1:25 000: часть зон, объектов и постов — за краем листа (см. таблицы справа)."


def _extent(graphics: Mapping[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    # Все кольца зон: зона для механизмов или зданий бывает больше зоны для людей.
    for zone in graphics.get("zones") or ():
        for ring in zone.get("rings") or ():
            points += plan_sheet.line(ring)
    for ring in graphics.get("outlines") or ():
        points += plan_sheet.line(ring)
    for item in graphics.get("points") or ():
        point = plan_sheet.point((item.get("x"), item.get("y")))
        if point:
            points.append(point)
    for item in graphics.get("objects") or ():
        points += plan_sheet.line(item.get("link") or ())
    if len(points) < 3 and points:
        x, y = points[0]
        points += [(x - 100, y - 100), (x + 100, y + 100)]
    return points


def situation_view(graphics: Mapping[str, Any]) -> PlanView:
    return plan_sheet.fit_view(_extent(graphics), MAP_W_MM, MAP_H_MM, pad_mm=MAP_PAD_MM, series=SITUATION_SCALES,
                               rotate_from=None)


def _clip(line) -> list[tuple]:
    return plan_sheet.clip(line, MAP_W_MM, MAP_H_MM)


def _marker(kind: str, x: float, y: float, label: str) -> Group:
    group = Group()
    size = 1.8 * mm
    if kind == "guard_post":
        group.add(Polygon([x, y + size, x - size, y - size * 0.8, x + size, y - size * 0.8], fillColor=GRAPHITE,
                          strokeColor=white, strokeWidth=0.4))
    elif kind == "gather":
        group.add(Circle(x, y, size * 0.9, fillColor=HexColor("#2E7D32"), strokeColor=white, strokeWidth=0.4))
    else:
        group.add(Rect(x - size * 0.9, y - size * 0.9, size * 1.8, size * 1.8, fillColor=RED if kind == "blast_station" else GRAPHITE,
                       strokeColor=white, strokeWidth=0.4))
    if label:
        group.add(String(x + size + 1, y - 2, label, fontName=FONT_BOLD, fontSize=6, fillColor=GRAPHITE))
    return group


def map_drawing(context: Mapping[str, Any], view: PlanView) -> Drawing:
    graphics = context.get("graphics") or {}
    d = Drawing(MAP_W_MM * mm, MAP_H_MM * mm)
    for layer in graphics.get("situation") or ():
        style = LAYER_STYLE.get(str(layer.get("kind")), dict(strokeColor=SITUATION, strokeWidth=0.3))
        for item in layer.get("lines") or ():
            for part in _clip(view.line(plan_sheet.line(item))):
                d.add(PolyLine(pts(part), **style))
    for zone in graphics.get("zones") or ():
        kind = str(zone.get("kind"))
        style = ZONE_STYLE.get(kind, ZONE_STYLE["buildings"])
        best = None
        for ring in zone.get("rings") or ():
            line = view.line(plan_sheet.line(ring))
            if len(line) < 3:
                continue
            for part in _clip(line + line[:1]):
                d.add(PolyLine(pts(part), **style))
            inside = [q for q in line if 2 < q[0] < MAP_W_MM - 40 and 4 < q[1] < MAP_H_MM - 4]
            if inside:
                candidate = max(inside, key=lambda q: q[0] + q[1])
                best = candidate if best is None or candidate[0] + candidate[1] > best[0] + best[1] else best
        if best is not None:
            label = f"{ZONE_LABELS.get(kind, kind)} {num(zone.get('value_m'), 0)} м"
            d.add(String(best[0] * mm + 2, best[1] * mm + 1, label, fontName=FONT, fontSize=6,
                         fillColor=style["strokeColor"]))
    for ring in graphics.get("outlines") or ():
        line = view.line(plan_sheet.line(ring))
        if len(line) < 3:
            continue
        # Блок за краем карты (план не поместился) не рисуется поверх таблиц справа.
        clipped = shapely.clip_by_rect(ShapelyPolygon(line).buffer(0), 0.0, 0.0, MAP_W_MM, MAP_H_MM)
        for part in getattr(clipped, "geoms", [clipped]):
            if part.geom_type == "Polygon" and not part.is_empty:
                d.add(Polygon(pts(list(part.exterior.coords)[:-1]), fillColor=RED, strokeColor=RED, strokeWidth=0.6))
    objects = {str(item.get("key")): item for item in context.get("protected_objects") or ()}
    for item in graphics.get("objects") or ():
        link = plan_sheet.line(item.get("link") or ())
        if len(link) != 2 or str(item.get("key")) not in objects:
            continue
        (x0, y0), (x1, y1) = view.line(link)
        d.add(Line(x0 * mm, y0 * mm, x1 * mm, y1 * mm, strokeColor=GREY, strokeWidth=0.4, strokeDashArray=[1, 1.5]))
        d.add(Circle(x1 * mm, y1 * mm, 1.9 * mm, fillColor=white, strokeColor=GRAPHITE, strokeWidth=0.5))
        d.add(String(x1 * mm, y1 * mm - 2.1, str(item.get("number")), fontName=FONT_BOLD, fontSize=5.8, fillColor=GRAPHITE,
                     textAnchor="middle"))
    for item in graphics.get("points") or ():
        point = plan_sheet.point((item.get("x"), item.get("y")))
        if point is None:
            continue
        x, y = view.xy(point)
        if not (0 <= x <= MAP_W_MM and 0 <= y <= MAP_H_MM):
            continue
        kind = str(item.get("kind"))
        code = POINT_CODES.get(kind, "")
        label = f"{code}{item.get('number')}" if kind == "guard_post" else code
        d.add(_marker(kind, x * mm, y * mm, label))
    notes = ([] if graphics.get("has_situation") else [NO_SITUATION]) + ([] if view.fits else [NOT_FITTED])
    for index, note in enumerate(notes):
        d.add(String(3 * mm, (MAP_H_MM - 6 - 4 * index) * mm, fit(note, 6.5, (MAP_W_MM - 6) * mm, bold=True),
                     fontName=FONT_BOLD, fontSize=6.5, fillColor=RED))
    d.add(plan_sheet.north_arrow(9 * mm, (MAP_H_MM - 10) * mm, FONT_BOLD))
    bar_m, bar_mm = plan_sheet.bar(view.scale, steps=(50, 100, 200, 250, 500, 1000, 2000), target_mm=45.0)
    d.add(String(3 * mm, 9 * mm, f"Масштаб 1:{view.scale:,}".replace(",", " "), fontName=FONT_BOLD, fontSize=8,
                 fillColor=GRAPHITE))
    d.add(plan_sheet.scale_bar(bar_m, bar_mm, 3 * mm, 3 * mm, FONT))
    d.add(String((3 + bar_mm + 6) * mm, 3.6 * mm, "печатать в масштабе 100 %", fontName=FONT, fontSize=5.5, fillColor=GREY))
    d.add(Rect(0, 0, d.width, d.height, fillColor=None, strokeColor=LINE, strokeWidth=0.6))
    return d


def _table(rows: list[list[Any]], widths: list[float]) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(grid_style(rows=len(rows) - 1, padding=1)))
    return table


def panel(context: Mapping[str, Any]) -> list[Any]:
    graphics = context.get("graphics") or {}
    zones = context.get("zones") or {}
    width = PANEL_W_MM * mm
    story: list[Any] = [p("Опасные зоны (расчёт — технический расчёт, разд. 13–15)", "cap")]
    zone_text = "; ".join(
        f"{ZONE_LABELS[kind]} — {num((zones.get(kind) or {}).get('value'), 0)} м"
        for kind in ("people", "mechanisms", "buildings")
        if (zones.get(kind) or {}).get("value")
    )
    story += [p(zone_text or "не рассчитаны", "item"), spacer(2.5)]
    story.append(p("Охраняемые объекты (расстояние от блока)", "cap"))
    objects = list(context.get("protected_objects") or ())
    if objects:
        rows = [[cell(h, "th") for h in ("№", "Объект", "До блока, м", "Безопасно, м", "")]]
        for number, item in enumerate(objects[:MAX_OBJECT_ROWS], start=1):
            inside = item.get("position") == "В ЗОНЕ"
            rows.append([
                cell(str(number), "td_c"),
                cell(f"{text(item.get('name'))} ({text(item.get('kind_label'))})"),
                cell(num(item.get("distance_m"), 0), "td_c"),
                cell(num(item.get("required_m"), 0), "td_c"),
                cell(text(item.get("position")), "td_red" if inside else "td_c"),
            ])
        story.append(_table(rows, [6 * mm, width - 6 * mm - 15 * mm - 15 * mm - 14 * mm, 15 * mm, 15 * mm, 14 * mm]))
        if len(objects) > MAX_OBJECT_ROWS:
            story.append(p(f"… и ещё {len(objects) - MAX_OBJECT_ROWS} — в техническом расчёте, разд. 17.", "note"))
    else:
        story.append(p("Охраняемых объектов ближе наибольшей опасной зоны нет.", "item"))
    story += [spacer(2.5), p("Посты охраны опасной зоны (распорядок, п. 35)", "cap")]
    placed = {str(item.get("ref")): item for item in graphics.get("points") or () if item.get("kind") == "guard_post"}
    posts = list(context.get("guard_posts") or ())
    if posts:
        rows = [[cell(h, "th") for h in ("№", "Место", "От блока, м")]]
        for number, post in enumerate(posts[:MAX_POST_ROWS], start=1):
            point = placed.get(str(post.get("code")))
            rows.append([
                cell(f"П{number}", "td_c"),
                cell(text(post.get("location"))),
                cell(num(point.get("distance_m"), 0) if point else "нет точки", "td_c"),
            ])
        story.append(_table(rows, [8 * mm, width - 8 * mm - 17 * mm, 17 * mm]))
        if len(posts) > MAX_POST_ROWS:
            story.append(p(f"… и ещё {len(posts) - MAX_POST_ROWS} — в распорядке, п. 35.", "note"))
    else:
        story.append(p("Посты не заданы.", "item"))
    story += [spacer(2.5)]
    schedule = context.get("schedule_input") or {}
    for kind, title in POINT_TITLES.items():
        point = next((item for item in graphics.get("points") or () if item.get("kind") == kind), None)
        where = text(point.get("label")) if point else ""
        where = where or text(schedule.get(SCHEDULE_KEYS[kind]))
        distance = f"{num(point.get('distance_m'), 0)} м от блока" if point and point.get("distance_m") is not None else ""
        if not point:
            distance = "нет точки на плане"
        details = " — ".join(part for part in (rich(where), distance) if part) or "—"
        story.append(p(None, "item", markup=f"<b>{title}</b> ({POINT_CODES[kind]}): {details}"))
    return story


__all__ = ["MAP_H_MM", "MAP_W_MM", "PANEL_W_MM", "map_drawing", "panel", "situation_view"]
