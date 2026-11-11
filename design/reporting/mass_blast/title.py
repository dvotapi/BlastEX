"""Документ 1: титул проекта МВ и его оборот «Состав проекта» (эталон v0.11, стр. 5–6).

Как титул паспорта на бурение ГР.05.01 v0.7 (вариант A): «СОГЛАСОВАНО»
(заказчик) слева, «УТВЕРЖДАЮ» (подрядчик) прижат к правому полю — самая
длинная строка кончается у поля, строки внутри блока — по левому краю.
"""
from __future__ import annotations

from typing import Any, Mapping

from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle

from design.reporting.brand import FONT, FONT_BOLD, GRAPHITE, GREY, ORGANIZATION, RED
from design.reporting.mass_blast.common import (
    DASH,
    cell,
    date,
    grid_style,
    num,
    p,
    rich,
    spacer,
    text,
    value_text,
    width_of,
)

SIGN_LINE = "____________"
DATE_LINE = "«___» ___________ 20__ г."

COMPOSITION = (
    ("1", "Технический расчёт", "прил. 10", "techcalc"),
    ("2", "Таблица параметров взрывных работ", "прил. 11", "table"),
    ("3", "Распорядок проведения массового взрыва", "прил. 12", "schedule"),
    ("Г.1", "Схема расположения скважин (по маркшейдерской съёмке)", "прил. 10", "G1"),
    ("Г.2", "Поперечные профили через заряды", "прил. 10", "G2"),
    ("Г.3", "Схема заряжания, забойки и отвода оборудования", "прил. 10", "G3"),
    ("Г.4", "Схема взрывной сети с интервалами замедления", "прил. 10", "G4"),
    ("Г.5", "Ситуационный план: опасная зона, охраняемые объекты, посты охраны, взрывная станция", "прил. 10, 12", "G5"),
)
COMPOSITION_NOTES = (
    "Графические приложения выполняются по прил. 10 ФНП 494; схема расположения скважин и план блока подписываются "
    "исполнителями маркшейдерской съёмки с указанием должностей. Схема расстановки постов охраны опасной зоны "
    "(п. 16 распорядка) — на ситуационном плане Г.5.",
    "Ознакомление ответственных лиц с проектом — в распорядке (п. 416 ФНП 494).",
)


# Геометрия титула — по эталону v0.11 (стр. 5; пункты от верхнего края листа).
TITLE_LEFT = 60.6
TITLE_RIGHT = 49.6           # от правого края: конец самой длинной строки «УТВЕРЖДАЮ»
SIGNER_TOP = 97.0
SIGNER_STEP = 15.7
TITLE_RED_TOP = 221.0
NUMBER_TOP = 243.0
OBJECT_TOP = 278.0
CUSTOMER_TOP = 299.0
SUMMARY_TOP = 328.0
SUMMARY_STEP = 14.95
SUMMARY_LABEL_RIGHT = 296.0
SUMMARY_VALUE_X = 319.0
AGREEMENT_TOP = 480.0
AGREEMENT_STEP = 22.8
BASIS_TOP = 636.0

_S = {
    "cap": ParagraphStyle("mb_t_cap", fontName=FONT_BOLD, fontSize=10.4, leading=12.4, textColor=GRAPHITE),
    "line": ParagraphStyle("mb_t_line", fontName=FONT, fontSize=9.5, leading=11.5, textColor=GRAPHITE),
    "red": ParagraphStyle("mb_t_red", fontName=FONT_BOLD, fontSize=13.3, leading=16, textColor=RED, alignment=TA_CENTER),
    "number": ParagraphStyle("mb_t_no", fontName=FONT_BOLD, fontSize=22.8, leading=27, textColor=GRAPHITE, alignment=TA_CENTER),
    "object": ParagraphStyle("mb_t_obj", fontName=FONT_BOLD, fontSize=13.3, leading=16, textColor=GRAPHITE, alignment=TA_CENTER),
    "customer": ParagraphStyle("mb_t_cust", fontName=FONT, fontSize=9.5, leading=11.5, textColor=GREY, alignment=TA_CENTER),
    "label": ParagraphStyle("mb_t_label", fontName=FONT, fontSize=9.5, leading=11.5, textColor=GREY, alignment=TA_RIGHT),
    "value": ParagraphStyle("mb_t_value", fontName=FONT_BOLD, fontSize=10.4, leading=12.4, textColor=GRAPHITE),
    "basis": ParagraphStyle("mb_t_basis", fontName=FONT, fontSize=8.6, leading=14.2, textColor=GREY, alignment=TA_CENTER),
}


def _signer_lines(caption: str, signer: Mapping[str, Any], organization: str) -> list[str]:
    name = text(signer.get("name"))
    return [
        caption,
        text(signer.get("position")),
        organization,
        "",
        f"{SIGN_LINE}  {name}" if name else SIGN_LINE,
        DATE_LINE,
    ]


def summary_rows(context: Mapping[str, Any]) -> list[tuple[str, str]]:
    project = context.get("project") or {}
    blocks = list(context.get("blocks") or [])
    totals = context.get("totals") or {}
    tables = [(b.get("parameter_table") or {}).get("totals") or {} for b in context.get("blocks_v2") or []]
    zones = context.get("zones") or {}
    block_text = ", ".join(
        f"{text(b.get('code'))} / {text(b.get('horizon'))} м" if text(b.get("horizon")) else text(b.get("code"))
        for b in blocks
    )
    holes = sum(int(t.get("hole_count") or 0) for t in tables)
    charge = sum(float(t.get("charge_kg") or 0.0) for t in tables)
    volume = totals.get("block_volume_m3")
    return [
        ("Блок / горизонт", block_text or DASH),
        ("Дата взрыва", date(project.get("blast_date"))),
        ("Время взрыва (местное)", text(project.get("blast_time")) or DASH),
        ("Объём взрываемого массива, м³", num(volume, 0) if volume else DASH),
        ("Скважин, шт", str(holes) if holes else DASH),
        ("Масса ВВ по проекту, кг", num(charge, 0) if charge else DASH),
        ("Опасная зона для людей, м", value_text((zones.get("people") or {}).get("value"))),
        ("Опасная зона для механизмов, м", value_text((zones.get("mechanisms") or {}).get("value"))),
    ]


def _year(context: Mapping[str, Any]) -> str:
    requisites = context.get("requisites") or {}
    for value in (requisites.get("project_date"), (context.get("project") or {}).get("blast_date")):
        value = text(value)
        if len(value) >= 4 and value[:4].isdigit():
            return value[:4]
        if len(value) == 10 and value[6:].isdigit():
            return value[6:]
    return "20__"


def _put(canvas, value: str, style: str, x: float, top: float, width: float, page_h: float) -> float:
    """Абзац в заданном месте листа (верх строки — `top` от верхнего края); высота."""

    paragraph = Paragraph(rich(value), _S[style])
    _w, height = paragraph.wrap(width, 400)
    paragraph.drawOn(canvas, x, page_h - top - height)
    return height


def draw_title_page(canvas, context: Mapping[str, Any], page_w: float, page_h: float) -> None:
    """Титул целиком (стр. 1 документа) — по координатам эталона: форма постоянная."""

    requisites = context.get("requisites") or {}
    project = context.get("project") or {}
    customer = text(requisites.get("customer_name"))
    contractor = text(requisites.get("contractor_name")) or ORGANIZATION
    right_edge = page_w - TITLE_RIGHT
    left = _signer_lines("СОГЛАСОВАНО", requisites.get("customer_approver") or {}, customer)
    right = _signer_lines("УТВЕРЖДАЮ", requisites.get("contractor_approver") or {}, contractor)
    half = (right_edge - TITLE_LEFT) / 2
    right_w = min(half, max(width_of(line, 10.4 if i == 0 else 9.5, bold=i == 0) for i, line in enumerate(right)) + 1)
    for lines, x, width in ((left, TITLE_LEFT, half - 6), (right, right_edge - right_w, right_w)):
        for index, line in enumerate(lines):
            if line:
                _put(canvas, line, "cap" if index == 0 else "line", x, SIGNER_TOP + index * SIGNER_STEP + 1.0, width, page_h)
    body_w = right_edge - TITLE_LEFT
    number = text(requisites.get("project_no"))
    _put(canvas, "ПРОЕКТ МАССОВОГО ВЗРЫВА", "red", TITLE_LEFT, TITLE_RED_TOP + 0.5, body_w, page_h)
    _put(canvas, f"№ {number}" if number else "№ ________", "number", TITLE_LEFT, NUMBER_TOP + 0.5, body_w, page_h)
    if text(project.get("object_name")):
        _put(canvas, project.get("object_name"), "object", TITLE_LEFT, OBJECT_TOP + 0.5, body_w, page_h)
    if customer:
        _put(canvas, f"Заказчик: {customer}", "customer", TITLE_LEFT, CUSTOMER_TOP + 1.0, body_w, page_h)
    # Строки сводки — с шагом эталона; длинное значение (много блоков)
    # переносится и сдвигает следующие строки вниз, а не наезжает на них.
    top = SUMMARY_TOP
    line_h = _S["value"].leading
    for label, value in summary_rows(context):
        label_h = _put(canvas, label, "label", TITLE_LEFT, top + 1.0, SUMMARY_LABEL_RIGHT - TITLE_LEFT, page_h)
        value_h = _put(canvas, value, "value", SUMMARY_VALUE_X, top + 0.5, right_edge - SUMMARY_VALUE_X, page_h)
        top += SUMMARY_STEP + max(0.0, max(label_h, value_h) - line_h)
    agreements = [a for a in requisites.get("agreements") or [] if text(a.get("name")) or text(a.get("position"))]
    agreement_top = max(AGREEMENT_TOP, top + (AGREEMENT_TOP - SUMMARY_TOP - 8 * SUMMARY_STEP))
    for index, item in enumerate(agreements):
        top = agreement_top + index * AGREEMENT_STEP
        _put(canvas, "Согласовано:", "label", TITLE_LEFT, top + 1.0, SUMMARY_LABEL_RIGHT - TITLE_LEFT, page_h)
        who = " ".join(filter(None, (text(item.get("position")), text(item.get("name")))))
        _put(canvas, who, "line", SUMMARY_VALUE_X, top + 1.0, 160, page_h)
        canvas.setStrokeColor(GRAPHITE)
        canvas.setLineWidth(0.6)
        canvas.line(right_edge - 62, page_h - top - 16, right_edge, page_h - top - 16)
    basis = text(requisites.get("tp_basis"))
    lines = [f"Составлен на основании: {basis}" if basis else "Составлен на основании: ________________",
             f"{ORGANIZATION}, {_year(context)} г."]
    _put(canvas, "\n".join(lines), "basis", TITLE_LEFT, BASIS_TOP + 0.5, body_w, page_h)


def title_story(context: Mapping[str, Any], width: float, counts: Mapping[str, int | None]) -> list:
    """Стр. 1 — титул (рисуется `draw_title_page` поверх пустой страницы), стр. 2 — «Состав проекта»."""

    return [Spacer(1, 1), PageBreak()] + composition_story(width, counts)


def composition_story(width: float, counts: Mapping[str, int | None]) -> list:
    rows = [[cell(h, "th") for h in ("№", "Документ", "Основание", "Листов")]]
    for number, name, basis, key in COMPOSITION:
        sheets = counts.get(key)
        rows.append([
            cell(number, "td_red"), cell(name), cell(basis, "td_c"), cell(str(sheets) if sheets else DASH, "td_c"),
        ])
    widths = [12 * mm, width - 12 * mm - 30 * mm - 20 * mm, 30 * mm, 20 * mm]
    table = Table(rows, colWidths=widths, rowHeights=[None] + [9 * mm] * len(COMPOSITION))
    table.setStyle(TableStyle(grid_style(rows=len(COMPOSITION), padding=2) + [("ALIGN", (0, 1), (0, -1), "CENTER")]))
    return [
        spacer(4), p("Состав проекта", "h2"), spacer(1), table, spacer(5),
        p(COMPOSITION_NOTES[0], "note"), spacer(6), p(COMPOSITION_NOTES[1], "note"),
    ]


__all__ = ["COMPOSITION", "composition_story", "draw_title_page", "summary_rows", "title_story"]
