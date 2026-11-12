"""Планы блока Г.1 (скважины), Г.3 (заряжание и заходки СЗМ), Г.4 (взрывная сеть).

Один вид на три листа блока (`block_view`): масштаб из ряда и поворот по
общему генератору плана (`design/reporting/plan_sheet.py`, TASK-018 §4).
Данные — `blocks_v2[i].graphics` ревизии; здесь только раскладка.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Mapping, Sequence

from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Polygon, PolyLine, String
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from design.reporting import plan_sheet
from design.reporting.mass_blast.common import num, text
from design.reporting.mass_blast.graphics.sheet import (
    BLUE,
    CONTOUR_DASH,
    FIELD_H_MM,
    FIELD_PAD_MM,
    FIELD_W_MM,
    GREEN,
    ORANGE,
    PURPLE,
    SECTION_DASH,
    SITUATION,
    TOE_DASH,
    arrow,
    field_frame,
    legend_band,
    pts,
)
from design.reporting.brand import FONT, FONT_BOLD, GRAPHITE, GREY, RED, ZEBRA
from design.reporting.plan_sheet import XY, PlanView

MIN_HOLE_MM = 1.3
# Допуск смещения устья — условие 2 акта готовности (±0,5 м); тот же, что у факта.
OFFSET_TOLERANCE_M = 0.5
LABEL_SHARE = 0.22
LABEL_PT = (3.0, 5.6)
# Масса у скважины на Г.1 — только при шаге на листе не меньше 6 мм (решение В2).
MASS_MIN_SPACING_MM = 6.0
TIME_STOPS = ("#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725")
GROUP_COLORS = (RED, PURPLE, BLUE, ORANGE, GREEN, GRAPHITE, HexColor("#8C564B"), HexColor("#17BECF"))
TOE_LABELS = {"angle": "нижняя бровка (по углу откоса)", "survey": "нижняя бровка (по съёмке)"}


# --------------------------------------------------------------- вид

def _points(graphics: Mapping[str, Any]) -> list[XY]:
    plan = graphics.get("plan") or {}
    found: list[XY] = []
    for hole in graphics.get("holes") or ():
        p = plan_sheet.point((hole.get("x"), hole.get("y")))
        if p:
            found.append(p)
        toe = plan_sheet.point(hole.get("toe"))
        if toe:
            found.append(toe)
    for ring in _contours(graphics):
        found += ring
    for key in ("crest_top", "crest_toe"):
        for item in plan.get(key) or ():
            found += plan_sheet.line(item)
    # Заходки СЗМ (Г.3) выходят за крайние скважины — за тыльный ряд и на
    # полшага за крайнюю колонку: вид общий на три листа, они должны поместиться.
    for item in (graphics.get("szm") or {}).get("passes") or ():
        found += plan_sheet.line(item.get("points") or ())
    return found


def _contours(graphics: Mapping[str, Any]) -> list[list[XY]]:
    """Кольца контура: все части контура по скважинам, иначе контур плана."""

    rings = [plan_sheet.line(ring) for ring in graphics.get("contours") or ()]
    if not rings:
        rings = [plan_sheet.line((graphics.get("plan") or {}).get("contour") or ())]
    return [ring for ring in rings if len(ring) >= 3]


def block_view(graphics: Mapping[str, Any]) -> PlanView:
    """Масштаб и поворот плана блока — общие для Г.1, Г.3 и Г.4.

    Повёрнутый план кладётся первым рядом вниз (как в эталоне: смотрим с
    откоса): из двух углов с одним размером рамки (α и α + 180°) берётся тот,
    при котором первый ряд ниже середины блока."""

    view = plan_sheet.fit_view(_points(graphics), FIELD_W_MM, FIELD_H_MM, pad_mm=FIELD_PAD_MM)
    if not view.angle_deg:
        return view
    holes = _holes(graphics)
    first = [view.xy(p)[1] for hole, p in holes if hole.get("first_row")]
    every = [view.xy(p)[1] for _hole, p in holes]
    if first and every and sum(first) / len(first) > sum(every) / len(every):
        return replace(view, angle_deg=(view.angle_deg + 180.0) % 360.0, cu=-view.cu, cv=-view.cv)
    return view


def _spacing_mm(holes: Sequence[XY]) -> float:
    """Шаг скважин на листе, мм (точки — уже в миллиметрах листа)."""

    spacing = plan_sheet.median_spacing(holes)
    return 10.0 if spacing is None else spacing


SECTION_LABEL_INSET_MM = 3.0


def _inset(line: Sequence[XY], inset: float) -> list[tuple[XY, ...]]:
    """Части ломаной внутри поля с отступом `inset` мм от края."""

    shifted = [(x - inset, y - inset) for x, y in line]
    parts = plan_sheet.clip(shifted, FIELD_W_MM - 2 * inset, FIELD_H_MM - 2 * inset)
    return [tuple((x + inset, y + inset) for x, y in part) for part in parts]


def _clip(line: Sequence[XY]) -> list[tuple[XY, ...]]:
    return plan_sheet.clip(line, FIELD_W_MM, FIELD_H_MM)


def _base(view: PlanView, graphics: Mapping[str, Any], *, situation: bool, crests: bool) -> Drawing:
    """Поле: ситуация, контур (заливка и штрих), бровки."""

    plan = graphics.get("plan") or {}
    d = Drawing(FIELD_W_MM * mm, FIELD_H_MM * mm)
    if situation:
        for layer in plan.get("situation") or ():
            for item in layer.get("lines") or ():
                for part in _clip(view.line(plan_sheet.line(item.get("points") or ()))):
                    d.add(PolyLine(pts(part), strokeColor=SITUATION, strokeWidth=0.3))
    for contour in _contours(graphics):
        d.add(Polygon(pts(view.line(contour)), fillColor=ZEBRA, strokeColor=GRAPHITE, strokeWidth=0.7,
                      strokeDashArray=CONTOUR_DASH))
    if crests:
        for item in plan.get("crest_top") or ():
            line = plan_sheet.line(item)
            if len(line) >= 2:
                d.add(PolyLine(pts(view.line(line)), strokeColor=GRAPHITE, strokeWidth=1.0))
        for item in plan.get("crest_toe") or ():
            line = plan_sheet.line(item)
            if len(line) >= 2:
                d.add(PolyLine(pts(view.line(line)), strokeColor=GRAPHITE, strokeWidth=0.5, strokeDashArray=TOE_DASH))
    return d


def _holes(graphics: Mapping[str, Any]) -> list[tuple[Mapping[str, Any], XY]]:
    result = []
    for hole in graphics.get("holes") or ():
        p = plan_sheet.point((hole.get("x"), hole.get("y")))
        if p:
            result.append((hole, p))
    return result


def _radius(view: PlanView, hole: Mapping[str, Any]) -> float:
    diameter = float(hole.get("diameter_mm") or 0.0)
    return max(diameter / view.scale, MIN_HOLE_MM) / 2


def _contour_label(graphics: Mapping[str, Any]) -> str:
    return "контур блока" if graphics.get("contour_source") == "design" else "контур блока (по скважинам, отступ 1,9 м)"


def _common_items(graphics: Mapping[str, Any], *, crests: bool) -> list[tuple[str, Mapping[str, Any], str]]:
    plan = graphics.get("plan") or {}
    items: list[tuple[str, Mapping[str, Any], str]] = []
    if _contours(graphics):
        items.append(("line", {"dash": CONTOUR_DASH, "width": 0.7}, _contour_label(graphics)))
    if crests and plan.get("crest_top"):
        items.append(("line", {"width": 1.0}, "верхняя бровка"))
    if crests and plan.get("crest_toe"):
        items.append(("line", {"dash": TOE_DASH, "width": 0.5}, TOE_LABELS.get(str(plan.get("toe_source")), "нижняя бровка")))
    return items


NOT_FITTED = "Блок не помещается на лист и в 1:5000: часть плана — за краем поля."


def _legend(view: PlanView, items, notes) -> Drawing:
    if not view.fits:
        notes = [(NOT_FITTED, RED), *notes]
    bar_m, bar_mm = plan_sheet.bar(view.scale)
    return legend_band(scale=view.scale, bar_m=bar_m, bar_mm=bar_mm, items=items, notes=notes, north=view.north)


def _crs_text(graphics: Mapping[str, Any]) -> str:
    crs = graphics.get("crs") or {}
    name = text(crs.get("name"))
    epsg = crs.get("epsg")
    parts = [name] if name else []
    if epsg:
        parts.append(f"EPSG:{epsg}")
    if text(crs.get("height_system")):
        parts.append(f"высоты — {text(crs.get('height_system'))}")
    return "СК " + ", ".join(parts) if parts else "СК объекта"


# --------------------------------------------------------------- Г.1

def g1_drawings(graphics: Mapping[str, Any], view: PlanView) -> tuple[Drawing, Drawing]:
    d = _base(view, graphics, situation=True, crests=True)
    holes = _holes(graphics)
    sheet = [view.xy(p) for _hole, p in holes]
    spacing = _spacing_mm(sheet)
    size = min(LABEL_PT[1], max(LABEL_PT[0], LABEL_SHARE * spacing * plan_sheet.MM_TO_PT))
    with_mass = spacing >= MASS_MIN_SPACING_MM and any(hole.get("charge_kg") is not None for hole, _p in holes)
    for section in graphics.get("sections") or ():
        line = plan_sheet.line(section.get("line") or ())
        if len(line) != 2:
            continue
        # Линия разреза выходит за крайние скважины на 7 м — в вид блока она не
        # входит и обрезается по полю с отступом под букву.
        inset = _inset(view.line(line), SECTION_LABEL_INSET_MM)
        if not inset:
            continue
        ends = (inset[0][0], inset[-1][-1])
        for part in inset:
            d.add(PolyLine(pts(part), strokeColor=GRAPHITE, strokeWidth=0.6, strokeDashArray=SECTION_DASH))
        for x, y in ends:
            name = text(section.get("name"))
            d.add(Circle(x * mm, y * mm, 2.2 * mm, fillColor=white, strokeColor=None))
            d.add(String(x * mm, y * mm - 2.6, name, fontName=FONT_BOLD, fontSize=8, fillColor=GRAPHITE, textAnchor="middle"))
    for (hole, p), (x, y) in zip(holes, sheet):
        toe = plan_sheet.point(hole.get("toe"))
        if toe:
            tx, ty = view.xy(toe)
            d.add(Line(x * mm, y * mm, tx * mm, ty * mm, strokeColor=GREY, strokeWidth=0.3))
    # Г.1 по исполнительной съёмке (слой «Факт», PR 5): у скважин есть `surveyed`.
    survey = any("surveyed" in hole for hole, _p in holes)
    for (hole, _p), (x, y) in zip(holes, sheet):
        first = bool(hole.get("first_row"))
        r = _radius(view, hole)
        color = RED if first else GRAPHITE
        number_color = color
        if survey and hole.get("surveyed") is False:
            # Без съёмки — по проекту, пустым серым кружком.
            d.add(Circle(x * mm, y * mm, r * mm, fillColor=white, strokeColor=GREY, strokeWidth=0.5,
                         strokeDashArray=(1.2, 0.8)))
            number_color = GREY
        else:
            d.add(Circle(x * mm, y * mm, r * mm, fillColor=RED if first else white, strokeColor=color, strokeWidth=0.5))
        if survey and float(hole.get("offset_m") or 0.0) > OFFSET_TOLERANCE_M:
            number_color = RED
        d.add(String(x * mm, (y + r) * mm + 0.8, text(hole.get("hole_id")),
                     fontName=FONT_BOLD if first or number_color is RED else FONT,
                     fontSize=size, fillColor=number_color, textAnchor="middle"))
        below = (y - r) * mm - 0.6 - size * 0.75
        d.add(String(x * mm, below, num(hole.get("depth_m"), 1), fontName=FONT, fontSize=size * 0.9, fillColor=GREY,
                     textAnchor="middle"))
        if with_mass and hole.get("charge_kg") is not None:
            d.add(String(x * mm, below - size * 0.85, num(hole.get("charge_kg"), 0), fontName=FONT, fontSize=size * 0.8,
                         fillColor=GREY, textAnchor="middle"))
    field_frame(d)
    label = "скважина: № — сверху, глубина L, м — снизу" + (", под ней масса заряда, кг" if with_mass else "")
    if survey:
        label = "скважина по съёмке: № — сверху, фактическая глубина L, м — снизу" + (
            ", под ней масса заряда по факту, кг" if with_mass else "")
    items = [
        ("circle", {}, label),
        ("circle", {"fill": RED, "stroke": RED}, "скважина первого ряда"),
        *_common_items(graphics, crests=True),
    ]
    if survey:
        items.append(("circle", {"stroke": GREY}, "без съёмки — по проекту"))
    if graphics.get("sections"):
        items.append(("line", {"dash": SECTION_DASH, "width": 0.6}, "линия поперечного профиля (Г.2)"))
    # Пометка «тесно» — только когда массу не печатаем из-за шага на листе.
    notes = [(_g1_note(graphics, spacing >= MASS_MIN_SPACING_MM), GREY)]
    if survey:
        notes += _survey_notes(graphics)
    return d, _legend(view, items, notes)


def _survey_notes(graphics: Mapping[str, Any]) -> list[tuple[str, Color]]:
    """Г.1 по съёмке: скважины без съёмки и со смещением устья больше допуска (условие 2 акта готовности)."""

    holes = list(graphics.get("holes") or ())
    missing = [text(hole.get("hole_id")) for hole in holes if hole.get("surveyed") is False]
    moved = [hole for hole in holes if float(hole.get("offset_m") or 0.0) > OFFSET_TOLERANCE_M]
    notes: list[tuple[str, Color]] = []
    if missing:
        notes.append((f"По проекту, без съёмки ({len(missing)}): {_short_list(missing)}.", GREY))
    if moved:
        shown = ", ".join(f"№ {text(h.get('hole_id'))} — {num(h.get('offset_m'), 2)} м" for h in moved[:12])
        more = f" и ещё {len(moved) - 12}" if len(moved) > 12 else ""
        notes.append((f"Смещение устья от проекта больше {num(OFFSET_TOLERANCE_M, 1)} м (№ красным): {shown}{more}.", RED))
    return notes


def _short_list(ids: Sequence[str], limit: int = 20) -> str:
    return ", ".join(ids[:limit]) + (f" и ещё {len(ids) - limit}" if len(ids) > limit else "")


def _g1_note(graphics: Mapping[str, Any], with_mass: bool) -> str:
    holes = list(graphics.get("holes") or ())
    note = f"Скважин {len(holes)}"
    if holes:
        ref = holes[0]
        note += (f". Опорная скважина № {text(ref.get('hole_id'))}: X (восток) = {num(ref.get('x'), 2)}, "
                 f"Y (север) = {num(ref.get('y'), 2)}, Z = {num(ref.get('z'), 2)}")
    note += f"; {_crs_text(graphics)}."
    if not with_mass:
        note += " Масса заряда по скважинам — в таблице параметров (на листе тесно)."
    return note


# --------------------------------------------------------------- Г.3

PASS_MARKER_MM = 1.8


def _pass_marker(x: float, y: float, number: int) -> Group:
    group = Group()
    group.add(Circle(x * mm, y * mm, 1.7 * mm, fillColor=white, strokeColor=BLUE, strokeWidth=0.6))
    group.add(String(x * mm, y * mm - 2.0, str(number), fontName=FONT_BOLD, fontSize=5.6, fillColor=BLUE, textAnchor="middle"))
    return group


def _label(d: Drawing, view: PlanView, point: Any, value: str, color: Color) -> None:
    p = plan_sheet.point(point)
    if p is None:
        return
    x, y = view.xy(p)
    width = pdfmetrics.stringWidth(value, FONT_BOLD, 6.5)
    x = min(max(x * mm, width / 2 + 2), FIELD_W_MM * mm - width / 2 - 2)
    y = min(max(y * mm, 4), FIELD_H_MM * mm - 8)
    d.add(Polygon([x - width / 2 - 1.5, y - 2.5, x + width / 2 + 1.5, y - 2.5, x + width / 2 + 1.5, y + 6.5,
                   x - width / 2 - 1.5, y + 6.5], fillColor=white, strokeColor=None))
    d.add(String(x, y, value, fontName=FONT_BOLD, fontSize=6.5, fillColor=color, textAnchor="middle"))


def g3_drawings(graphics: Mapping[str, Any], view: PlanView, zones: Mapping[str, Any]) -> tuple[Drawing, Drawing]:
    d = _base(view, graphics, situation=False, crests=True)
    for hole, p in _holes(graphics):
        x, y = view.xy(p)
        first = bool(hole.get("first_row"))
        r = _radius(view, hole)
        d.add(Circle(x * mm, y * mm, r * mm, fillColor=RED if first else white, strokeColor=RED if first else GRAPHITE,
                     strokeWidth=0.4))
    szm = graphics.get("szm") or {}
    for item in szm.get("passes") or ():
        line = [view.xy(p) for p in plan_sheet.line(item.get("points") or ())]
        if len(line) < 2:
            continue
        for part in _clip(line[:-1]):
            d.add(PolyLine(pts(part), strokeColor=BLUE, strokeWidth=1.1))
        d.add(arrow(line[-2], line[-1], BLUE, width=1.1, head_mm=1.8))
        # Кружок с номером — целиком в поле (у края центр сдвигается внутрь).
        mx = min(max(line[0][0], PASS_MARKER_MM), FIELD_W_MM - PASS_MARKER_MM)
        my = min(max(line[0][1], PASS_MARKER_MM), FIELD_H_MM - PASS_MARKER_MM)
        d.add(_pass_marker(mx, my, int(item.get("number") or 0)))
    _label(d, view, szm.get("rear_label"), "тыл блока — въезд / выезд СЗМ", GRAPHITE)
    _label(d, view, szm.get("front_label"), "бровка (первый ряд)", RED)
    field_frame(d)
    flank = "левого" if szm.get("start_flank", "left") == "left" else "правого"
    mechanisms = (zones.get("mechanisms") or {}).get("value")
    forbidden = szm.get("forbidden_zone_m") or 20
    items = [
        ("arrow", {"stroke": BLUE, "width": 1.1}, "поперечная заходка СЗМ от тыла к бровке между двумя колонками скважин; № — порядок"),
        ("circle", {"fill": RED, "stroke": RED}, "первый ряд — заряд по ЛСПП"),
        *_common_items(graphics, crests=True),
    ]
    notes = [
        (f"Заходки СЗМ — {len(szm.get('passes') or ())}, нумерация вдоль фронта с {flank} фланга (смотреть с откоса вглубь блока). "
         "Забойка — буровым шламом на всю свободную часть скважины после установки боевика и заполнения ВВ.", GRAPHITE),
        (f"Запретная зона при заряжании — {num(forbidden, 0)} м от заряжаемых скважин (п. 159 ФНП 494), ограждается "
         "на местности; СЗМ после заряжания выводится за её пределы.", GRAPHITE),
        ("Отвод оборудования (экскаваторы, буровые станки, прочая техника) — "
         + (f"не менее {num(mechanisms, 0)} м от ближайшей скважины, " if mechanisms else "")
         + "за пределы опасной зоны для механизмов; оставляемое — укрывается (распорядок, пп. 15, 25).", GRAPHITE),
    ]
    return d, _legend(view, items, notes)


# --------------------------------------------------------------- Г.4

def _time_color(share: float) -> Color:
    share = min(1.0, max(0.0, share))
    stops = [HexColor(value) for value in TIME_STOPS]
    position = share * (len(stops) - 1)
    index = min(int(position), len(stops) - 2)
    t = position - index
    a, b = stops[index], stops[index + 1]
    return Color(a.red + (b.red - a.red) * t, a.green + (b.green - a.green) * t, a.blue + (b.blue - a.blue) * t)


def _ms(value: Any) -> str:
    if value is None:
        return "—"
    number = float(value)
    return str(int(round(number))) if abs(number - round(number)) < 0.05 else num(number, 1)


def _star(x: float, y: float, r: float) -> Polygon:
    points = []
    for index in range(10):
        radius = r if index % 2 == 0 else r * 0.45
        angle = math.radians(90 + index * 36)
        points += [x + radius * math.cos(angle), y + radius * math.sin(angle)]
    return Polygon(points, fillColor=RED, strokeColor=white, strokeWidth=0.4)


def g4_drawings(graphics: Mapping[str, Any], view: PlanView) -> tuple[Drawing, Drawing]:
    d = _base(view, graphics, situation=False, crests=False)
    network = graphics.get("network") or {}
    holes = _holes(graphics)
    sheet = {text(hole.get("hole_id")): view.xy(p) for hole, p in holes}
    spacing = _spacing_mm(list(sheet.values()))
    size = min(4.6, max(2.8, 0.18 * spacing * plan_sheet.MM_TO_PT))
    for cord in network.get("cords") or ():
        line = [sheet[h] for h in cord.get("hole_ids") or () if h in sheet]
        if len(line) >= 2:
            d.add(PolyLine(pts(line), strokeColor=ORANGE, strokeWidth=0.7))
    for link in network.get("links") or ():
        a, b = sheet.get(text(link.get("from"))), sheet.get(text(link.get("to")))
        if a is None or b is None:
            continue
        color = GROUP_COLORS[int(link.get("group") or 0) % len(GROUP_COLORS)]
        d.add(arrow(a, b, color, width=0.5, head_mm=1.1, shrink_mm=MIN_HOLE_MM / 2 + 0.2))
    times = [float(hole["label_ms"]) for hole, _p in holes if hole.get("label_ms") is not None]
    t0, t1 = (min(times), max(times)) if times else (0.0, 1.0)
    span = (t1 - t0) or 1.0
    for hole, _p in holes:
        x, y = sheet[text(hole.get("hole_id"))]
        r = _radius(view, hole)
        label = hole.get("label_ms")
        if label is None:
            d.add(Circle(x * mm, y * mm, r * mm, fillColor=white, strokeColor=RED, strokeWidth=0.5))
            d.add(Line((x - r) * mm, (y - r) * mm, (x + r) * mm, (y + r) * mm, strokeColor=RED, strokeWidth=0.6))
            d.add(Line((x - r) * mm, (y + r) * mm, (x + r) * mm, (y - r) * mm, strokeColor=RED, strokeWidth=0.6))
            continue
        d.add(Circle(x * mm, y * mm, r * mm, fillColor=_time_color((float(label) - t0) / span), strokeColor=GRAPHITE,
                     strokeWidth=0.3))
        d.add(String((x + r) * mm + 0.6, (y - r) * mm - size * 0.6, _ms(label), fontName=FONT, fontSize=size, fillColor=GRAPHITE))
    for hole_id in network.get("starters") or ():
        if hole_id in sheet:
            x, y = sheet[hole_id]
            d.add(_star(x * mm, y * mm, 2.3 * mm))
            d.add(String(x * mm, (y - 2.6) * mm - 6, "СТАРТ", fontName=FONT_BOLD, fontSize=6.5, fillColor=RED,
                         textAnchor="middle"))
    field_frame(d)
    items: list[tuple[str, Mapping[str, Any], str]] = []
    for index, group in enumerate(network.get("groups") or ()):
        items.append(("arrow", {"stroke": GROUP_COLORS[index % len(GROUP_COLORS)], "width": 0.8},
                      f"{text(group.get('label'))} ({group.get('count')} шт.)"))
    if network.get("cords"):
        items.append(("line", {"stroke": ORANGE, "width": 0.7}, "детонирующий шнур"))
    items.append(("marker", {"draw": lambda x, y: _star(x, y, 1.6 * mm)}, "стартер (начало сети)"))
    if network.get("unconnected"):
        items.append(("circle", {"stroke": RED}, "скважина не подключена к сети"))
    notes = _g4_notes(network)
    return d, _legend(view, items, notes)


def _g4_notes(network: Mapping[str, Any]) -> list[tuple[str, Color]]:
    notes: list[tuple[str, Color]] = []
    if network.get("system") == "electronic":
        notes.append(("Электронная система: у скважины — время канала, мс; цвет кружка — по времени.", GRAPHITE))
    elif network.get("label_mode") == "surface":
        notes.append((f"Число у скважины — время поверхностной сети, мс (+{_ms(network.get('downhole_ms'))} мс замедление в скважине); "
                      "цвет кружка — по времени.", GRAPHITE))
    else:
        notes.append(("Число у скважины — время срабатывания с замедлением в скважине, мс; цвет кружка — по времени.", GRAPHITE))
    if network.get("block_ms") is not None:
        window = int(network.get("window_8ms_max") or 0)
        notes.append(
            (f"Время блока {_ms(network.get('block_ms'))} мс; одновременно до {network.get('same_time_max')} скв.; "
             f"в окне 8 мс до {window} скв.", RED if window > 1 else GRAPHITE)
        )
    else:
        notes.append(("Сети инициирования в проекте блока нет: показаны только скважины.", RED))
    return notes


__all__ = ["block_view", "g1_drawings", "g3_drawings", "g4_drawings"]
