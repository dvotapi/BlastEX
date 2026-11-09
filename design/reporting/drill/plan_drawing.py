"""Вектор плана расположения скважин (стр. 4) из раскладки `plan.build_plan`.

Ничего не считает: переводит миллиметры листа в pt ReportLab и рисует слои
снизу вверх — ситуация, контур блока, бровки, отрезки наклонных, кружки с
номером и глубиной. Легенда с масштабом, линейкой и стрелкой «С» — отдельный
рисунок под полем плана: на поле стрелка легла бы на скважины.
"""
from __future__ import annotations

from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Polygon, PolyLine, Rect, String
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from design.reporting.drill.plan import PLAN_H_MM, PLAN_W_MM, PlanSheet

GRAPHITE = HexColor("#2E3237")
RED = HexColor("#B71C1C")
GREY = HexColor("#6B7075")
LINE = HexColor("#C9CCD0")
SITUATION = HexColor("#9EA2A8")
TOE_DASH = (2 * mm, 1.5 * mm)
TOE_SOURCE_LABELS = {"angle": "нижняя бровка (по углу откоса)", "survey": "нижняя бровка (по съёмке)"}


def _pts(line) -> list[float]:
    return [value * mm for point in line for value in point]


def _north_arrow(x: float, y: float, font: str) -> Group:
    """Стрелка «С» с вершиной в (x, y), pt."""

    w, h = 4 * mm, 9 * mm
    group = Group(
        Polygon([x, y, x - w, y - h * 0.55, x - w * 0.35, y - h * 0.55, x - w * 0.35, y - h,
                 x + w * 0.35, y - h, x + w * 0.35, y - h * 0.55, x + w, y - h * 0.55],
                fillColor=white, strokeColor=GRAPHITE, strokeWidth=0.6),
    )
    group.add(String(x, y - h - 4 * mm, "С", fontName=font, fontSize=10, fillColor=GRAPHITE, textAnchor="middle"))
    return group


def drawing(sheet: PlanSheet, *, font: str, bold_font: str) -> Drawing:
    width, height = PLAN_W_MM * mm, PLAN_H_MM * mm
    d = Drawing(width, height)
    for line in sheet.situation:
        d.add(PolyLine(_pts(line), strokeColor=SITUATION, strokeWidth=0.3))
    if sheet.contour:
        d.add(Polygon(_pts(sheet.contour), fillColor=None, strokeColor=GRAPHITE, strokeWidth=0.6))
    for line in sheet.crest_top:
        d.add(PolyLine(_pts(line), strokeColor=GRAPHITE, strokeWidth=1.0))
    for line in sheet.crest_toe:
        d.add(PolyLine(_pts(line), strokeColor=GRAPHITE, strokeWidth=0.6, strokeDashArray=list(TOE_DASH)))
    for hole in sheet.holes:
        if hole.toe is not None:
            d.add(PolyLine(_pts(((hole.x, hole.y), hole.toe)), strokeColor=GREY, strokeWidth=0.3))
    size = sheet.label_pt
    for hole in sheet.holes:
        color = RED if hole.first_row else GRAPHITE
        label_font = bold_font if hole.first_row else font
        x, y, r = hole.x * mm, hole.y * mm, hole.r * mm
        d.add(Circle(x, y, r, fillColor=white, strokeColor=color, strokeWidth=0.5))
        # Номер — справа сверху, глубина — справа снизу, как в SHOTPlus.
        d.add(String(x + r + 0.3, y + 0.4, hole.number, fontName=label_font, fontSize=size, fillColor=color))
        d.add(String(x + r + 0.3, y - size * 0.85, hole.depth, fontName=font, fontSize=size, fillColor=color))
    d.add(Rect(0, 0, width, height, fillColor=None, strokeColor=LINE, strokeWidth=0.6))
    return d


LEGEND_ROW = 5.5 * mm
LEGEND_SIZE = 7.5
# Справа в легенде — стрелка «С» (вершина вверху, буква снизу).
ARROW_W = 14 * mm
ARROW_H = 16 * mm


def _scale_bar(sheet: PlanSheet, x: float, y: float, font: str) -> Group:
    group = Group()
    length = sheet.bar_mm * mm
    half = length / 2
    for index, fill in enumerate((GRAPHITE, white)):
        group.add(Rect(x + index * half, y, half, 1.4 * mm, fillColor=fill, strokeColor=GRAPHITE, strokeWidth=0.4))
    for offset, text in ((0, "0"), (half, _bar_text(sheet.bar_m / 2)), (length, f"{sheet.bar_m} м")):
        group.add(String(x + offset, y + 2.2 * mm, text, fontName=font, fontSize=6.5, fillColor=GRAPHITE,
                         textAnchor="middle"))
    return group


def _bar_text(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value).replace(".", ",")


def _legend_items(sheet: PlanSheet) -> list[tuple[str, str]]:
    items = [("hole", "№ скважины и глубина, м"), ("first", "первый ряд")]
    if sheet.contour:
        items.append(("contour", "контур блока"))
    if sheet.crest_top:
        items.append(("top", "верхняя бровка"))
    if sheet.crest_toe:
        items.append(("toe", TOE_SOURCE_LABELS.get(sheet.toe_source, "нижняя бровка")))
    if sheet.situation:
        items.append(("situation", "ситуация"))
    return items


def _symbol(kind: str, x: float, y: float, font: str) -> Group:
    group = Group()
    if kind in ("hole", "first"):
        color = RED if kind == "first" else GRAPHITE
        group.add(Circle(x + 1.2 * mm, y + 1 * mm, 0.7 * mm, fillColor=white, strokeColor=color, strokeWidth=0.5))
        if kind == "hole":
            group.add(String(x + 2.3 * mm, y + 1.6 * mm, "48", fontName=font, fontSize=5, fillColor=GRAPHITE))
            group.add(String(x + 2.3 * mm, y - 0.4 * mm, "11,6", fontName=font, fontSize=5, fillColor=GRAPHITE))
        return group
    styles = {
        "contour": dict(strokeColor=GRAPHITE, strokeWidth=0.6),
        "top": dict(strokeColor=GRAPHITE, strokeWidth=1.0),
        "toe": dict(strokeColor=GRAPHITE, strokeWidth=0.6, strokeDashArray=list(TOE_DASH)),
        "situation": dict(strokeColor=SITUATION, strokeWidth=0.6),
    }
    group.add(Line(x, y + 1 * mm, x + 7 * mm, y + 1 * mm, **styles[kind]))
    return group


def legend(sheet: PlanSheet, width: float, *, font: str, bold_font: str) -> Drawing:
    """Масштаб, линейка, условные обозначения и пометка — под полем плана (pt)."""

    items = _legend_items(sheet)
    rows: list[list[tuple[str, str, float]]] = [[]]
    x = 0.0
    room = width - ARROW_W
    for kind, text in items:
        symbol_w = 8.5 * mm if kind == "hole" else 8 * mm
        item_w = symbol_w + pdfmetrics.stringWidth(text, font, LEGEND_SIZE) + 5 * mm
        if rows[-1] and x + item_w > room:
            rows.append([])
            x = 0.0
        rows[-1].append((kind, text, x))
        x += item_w
    height = max(LEGEND_ROW * (len(rows) + 1) + 1 * mm, ARROW_H)
    d = Drawing(width, height)
    d.add(_north_arrow(width - ARROW_W / 2, height - 0.5 * mm, bold_font))
    top = height - LEGEND_ROW
    d.add(String(0, top + 1 * mm, f"Масштаб 1:{sheet.scale}", fontName=bold_font, fontSize=8.5, fillColor=GRAPHITE))
    d.add(_scale_bar(sheet, 32 * mm, top + 0.6 * mm, font))
    if sheet.note:
        d.add(String(width - ARROW_W, top + 1 * mm, sheet.note, fontName=font, fontSize=LEGEND_SIZE, fillColor=GREY,
                     textAnchor="end"))
    for index, row in enumerate(rows, start=1):
        y = top - LEGEND_ROW * index
        for kind, text, x in row:
            d.add(_symbol(kind, x, y, font))
            symbol_w = 8.5 * mm if kind == "hole" else 8 * mm
            d.add(String(x + symbol_w, y + 0.2 * mm, text, fontName=font, fontSize=LEGEND_SIZE, fillColor=GRAPHITE))
    return d
