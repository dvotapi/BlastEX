"""Лист графической части Г.1–Г.5: поле чертежа, полоса легенды, подпись.

A4 альбомный (TASK-018 §4): поля листа 13,5 мм, поле чертежа 270 × 146 мм
(в эталоне — 270 × 150: блок 66 помещается в 1:500 только с поворотом и
только на таком поле), под ним — полоса легенды 19 мм (масштаб, линейка,
стрелка «С», условные обозначения, примечание), внизу — подпись «Съёмку
выполнил» (Г.1) или «Составил» (Г.2–Г.5). Векторные примитивы ReportLab:
стрелки, пунктиры, кружки скважин.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from reportlab.graphics.shapes import Circle, Drawing, Group, Line, Polygon, Rect, String
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from design.reporting.brand import FONT, FONT_BOLD, GRAPHITE, GREY, LINE, RED, TINT, ZEBRA
from design.reporting.mass_blast.common import person_line, signature_row, text
from design.reporting.mass_blast.frame import Margins, frame_width
from design.reporting.plan_sheet import XY, north_arrow_turned, scale_bar

MARGINS = Margins(left=13.5 * mm, right=13.5 * mm, top=10 * mm, bottom=11 * mm)
FIELD_W_MM = frame_width(True, MARGINS) / mm      # 270 мм
FIELD_H_MM = 146.0
LEGEND_H_MM = 19.0
FIELD_PAD_MM = 1.5       # крайние точки вида — контур блока, подписи скважин внутри него
LEGEND_SIZE = 6.0
LEGEND_SIZES = (6.0, 5.4, 4.8)
LEGEND_ROW_MM = 3.7
SIGNATURE_PT = 8.5
SIGNATURE_TEXT_MM = 152.0   # средняя графа `signature_row` на поле 270 мм
BLUE = HexColor("#1F6FB2")
ORANGE = HexColor("#E07B00")
PURPLE = HexColor("#6A3D9A")
GREEN = HexColor("#2E7D32")
SITUATION = HexColor("#9EA2A8")
STEMMING = HexColor("#D9DBDE")
CONTOUR_DASH = [2.2 * mm, 1.1 * mm]
TOE_DASH = [2 * mm, 1.5 * mm]
SECTION_DASH = [4 * mm, 1 * mm, 0.6 * mm, 1 * mm]
ACTUAL_SIZE_NOTE = "Печатать в масштабе 100 %, без «вписать в страницу»"

__all__ = [
    "ACTUAL_SIZE_NOTE", "BLUE", "CONTOUR_DASH", "FIELD_H_MM", "FIELD_PAD_MM", "FIELD_W_MM", "GREEN", "LEGEND_H_MM",
    "MARGINS", "ORANGE", "PURPLE", "SECTION_DASH", "SITUATION", "STEMMING", "TOE_DASH", "arrow", "fit", "legend_band",
    "pts", "signature", "Margins",
]


def pts(line: Iterable[XY]) -> list[float]:
    """Миллиметры листа → плоский список координат pt."""

    return [value * mm for p in line for value in p]


def arrow(start: XY, end: XY, color: Color, *, width: float = 0.6, head_mm: float = 1.4, shrink_mm: float = 0.0) -> Group:
    """Стрелка из `start` в `end` (мм листа) с залитым наконечником."""

    (x0, y0), (x1, y1) = start, end
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    group = Group()
    if length <= 2 * shrink_mm + 1e-6:
        return group
    ux, uy = dx / length, dy / length
    x0, y0 = x0 + ux * shrink_mm, y0 + uy * shrink_mm
    x1, y1 = x1 - ux * shrink_mm, y1 - uy * shrink_mm
    head = min(head_mm, (length - 2 * shrink_mm) * 0.6)
    bx, by = x1 - ux * head, y1 - uy * head
    px, py = -uy * head * 0.38, ux * head * 0.38
    group.add(Line(x0 * mm, y0 * mm, bx * mm, by * mm, strokeColor=color, strokeWidth=width))
    group.add(Polygon([x1 * mm, y1 * mm, (bx + px) * mm, (by + py) * mm, (bx - px) * mm, (by - py) * mm],
                      fillColor=color, strokeColor=color, strokeWidth=0.1))
    return group


def fit(value: str, size: float, width_pt: float, bold: bool = False) -> str:
    font = FONT_BOLD if bold else FONT
    if pdfmetrics.stringWidth(value, font, size) <= width_pt:
        return value
    while value and pdfmetrics.stringWidth(value + "…", font, size) > width_pt:
        value = value[:-1]
    return value + "…"


def _symbol(kind: str, x: float, y: float, style: Mapping[str, Any]) -> Group:
    """Знак условного обозначения 8 мм шириной, нижний левый угол (x, y) pt."""

    group = Group()
    cy = y + 1.1 * mm
    if kind == "circle":
        group.add(Circle(x + 2 * mm, cy, 0.75 * mm, fillColor=style.get("fill", white),
                         strokeColor=style.get("stroke", GRAPHITE), strokeWidth=0.5))
    elif kind == "arrow":
        group.add(arrow((x / mm, cy / mm), (x / mm + 7, cy / mm), style.get("stroke", GRAPHITE), width=style.get("width", 0.8)))
    elif kind == "box":
        group.add(Rect(x + 1 * mm, y + 0.2 * mm, 5 * mm, 1.8 * mm, fillColor=style.get("fill", white),
                       strokeColor=style.get("stroke", GRAPHITE), strokeWidth=0.5))
    elif kind == "marker":
        group.add(style["draw"](x + 3.5 * mm, cy))
    else:
        group.add(Line(x, cy, x + 7 * mm, cy, strokeColor=style.get("stroke", GRAPHITE), strokeWidth=style.get("width", 0.6),
                       strokeDashArray=style.get("dash")))
    return group


def legend_band(
    *,
    scale: int,
    bar_m: int,
    bar_mm: float,
    items: Sequence[tuple[str, Mapping[str, Any], str]],
    notes: Sequence[tuple[str, Color]] = (),
    north: XY | None = (0.0, 1.0),
    scale_note: str = "",
    width_mm: float = FIELD_W_MM,
    height_mm: float = LEGEND_H_MM,
) -> Drawing:
    """Масштаб, линейка, стрелка «С» справа, условные обозначения в строки, примечания."""

    width, height = width_mm * mm, height_mm * mm
    d = Drawing(width, height)
    arrow_room = 18 * mm if north is not None else 0.0
    if north is not None:
        d.add(north_arrow_turned(width - arrow_room / 2, height / 2 - 1.5 * mm, north, FONT_BOLD, length=8 * mm))
    top = height - 3.2 * mm
    d.add(String(0, top, f"Масштаб 1:{scale:,}".replace(",", " "), fontName=FONT_BOLD, fontSize=8, fillColor=GRAPHITE))
    d.add(scale_bar(bar_m, bar_mm, 30 * mm, top - 0.4 * mm, FONT))
    note = scale_note or ACTUAL_SIZE_NOTE
    d.add(String(30 * mm + bar_mm * mm + 9 * mm, top, note, fontName=FONT, fontSize=LEGEND_SIZE, fillColor=GREY))
    room = width - arrow_room
    # Строки условных обозначений и примечаний должны уместиться в полосу
    # (иначе легли бы на подпись): кегль уменьшается; если и в самом мелком
    # не помещается — лишние обозначения идут одной строкой «также: …», а
    # примечания склеиваются в последнюю строку с обрезкой.
    for size in LEGEND_SIZES:
        row_mm = LEGEND_ROW_MM * size / LEGEND_SIZE
        row_pt = row_mm * mm
        # Строк обозначений — столько, чтобы под ними осталась строка примечаний.
        max_rows = max(1, int((top + 0.2 * mm) // row_pt) - 1) if notes else max(1, int((top - 0.6 * mm) // row_pt))
        placed, rows = _place_items(items, size, room)
        if rows > max_rows and size == LEGEND_SIZES[-1]:
            overflow = [label for _kind, _style, label, _x, row in placed if row >= max_rows]
            placed = [item for item in placed if item[4] < max_rows]
            placed.append(("text", {}, "также: " + "; ".join(overflow), 0.0, max_rows))
            rows = max_rows
        notes_top = top - row_pt * (rows + 1) + 0.2 * mm
        capacity = max(0, int(notes_top // (size * 1.3)) + 1)
        if (rows <= max_rows and len(notes) <= capacity) or size == LEGEND_SIZES[-1]:
            break
    for kind, style, label, x, row in placed:
        y = top - row_mm * mm * row - 0.6 * mm
        if kind == "text":
            d.add(String(x, y + 0.3 * mm, fit(label, size, room), fontName=FONT, fontSize=size, fillColor=GRAPHITE))
            continue
        d.add(_symbol(kind, x, y, style))
        d.add(String(x + 9 * mm, y + 0.3 * mm, label, fontName=FONT, fontSize=size, fillColor=GRAPHITE))
    lines = list(notes)
    if len(lines) > capacity:
        kept = lines[: max(capacity - 1, 0)]
        rest = lines[len(kept):]
        lines = kept + ([(" ".join(value for value, _color in rest), rest[0][1])] if capacity else [])
    y = notes_top
    for value, color in lines:
        d.add(String(0, y, fit(value, size, room), fontName=FONT, fontSize=size, fillColor=color))
        y -= size * 1.3
    return d


def _place_items(items, size: float, room: float) -> tuple[list[tuple], int]:
    placed: list[tuple] = []
    x, row = 0.0, 1
    for kind, style, label in items:
        item_w = 9 * mm + pdfmetrics.stringWidth(label, FONT, size) + 4 * mm
        if x and x + item_w > room:
            x, row = 0.0, row + 1
        placed.append((kind, style, fit(label, size, room - 9 * mm), x, row))
        x += item_w
    return placed, row


def field_frame(d: Drawing) -> None:
    d.add(Rect(0, 0, d.width, d.height, fillColor=None, strokeColor=LINE, strokeWidth=0.6))


def signature(context: Mapping[str, Any], *, surveyor: bool) -> Any:
    """«Съёмку выполнил: маркшейдер …» (Г.1) или «Составил: …» (Г.2–Г.5); пусто — пустая линия."""

    requisites = context.get("requisites") or {}
    width = FIELD_W_MM * mm
    if surveyor:
        name = text(requisites.get("surveyor_name"))
        person = {"position": "маркшейдер" if name else "", "name": name}
        label = "Съёмку выполнил:"
    else:
        person, label = requisites.get("made_by") or {}, "Составил:"
    # Одной строкой: перенос подписи вытолкнул бы её на следующую страницу,
    # и названия листов «Графики» разошлись бы с листами.
    one_line = fit(person_line(person), SIGNATURE_PT, SIGNATURE_TEXT_MM * mm - 8)
    return signature_row(label, {"position": "", "name": one_line}, width)


__all__ += ["field_frame", "person_line", "FONT", "FONT_BOLD", "GRAPHITE", "GREY", "LINE", "RED", "TINT", "ZEBRA"]
