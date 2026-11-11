"""Документ 3: таблица параметров взрывных работ (прил. 11 ФНП 494, эталон v0.11, стр. 9–11).

Книжный A4, вписан по ширине; разрывы страниц — строго по `FIRST_PAGE_ROWS` /
`NEXT_PAGE_ROWS` скважин (63 / 73, TASK-018 §3.2), заголовок таблицы (2 строки,
группы граф Р / Ф) повторяется на каждой странице. «Общая запись» (прил. 11,
прим. 3): диаметр, перебур Р, забойка Р и ПД печатаются в первой строке
страницы и там, где значение меняется. Графы Ф — пустые белые клетки (PR 5
заполнит их фактом). Данные — `blocks_v2[i].parameter_table` (PR 2), рендер
ничего не считает.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from reportlab.lib.colors import white
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Table, TableStyle

from design.reporting.brand import FONT, FONT_BOLD, GRAPHITE, LINE, RED, ZEBRA
from design.reporting.mass_blast.common import DASH, cell, date, num, p, person_line, short, spacer, text
from design.reporting.mass_blast.frame import Margins

FIRST_PAGE_ROWS = 63
NEXT_PAGE_ROWS = 73
ROW_H = 10.28          # пт — шаг строки эталона (63 / 73 строки заполняют страницу)
HEAD_H = (15.0, 9.0)   # две строки заголовка таблицы
MARGINS = Margins(left=10 * mm, right=10 * mm, top=10 * mm, bottom=13 * mm)
TAIL_H = 30 * mm       # итог, примечание и подписи под последней строкой

# (ключ, заголовок группы, подзаголовок, ширина — доли ширины таблицы)
COLUMNS: tuple[tuple[str, str, str, float], ...] = (
    ("hole_id", "№ скв.", "", 5.2),
    ("diameter_mm", "Диаметр, мм", "", 4.6),
    ("bench_height_m", "Высота уступа, м", "", 5.0),
    ("depth_m", "Глубина скважины, м", "Р", 4.9),
    ("depth_fact_m", "", "Ф", 4.9),
    ("subdrill_m", "Перебур, м", "Р", 4.4),
    ("subdrill_fact_m", "", "Ф", 4.4),
    ("water_m", "Столб воды, м", "", 4.6),
    ("lspp_m", "ЛСПП, м", "Р", 4.6),
    ("lspp_fact_m", "", "Ф", 4.6),
    ("spacing_m", "Между скв., м", "Р", 4.6),
    ("spacing_fact_m", "", "Ф", 4.6),
    ("burden_m", "Между рядами, м", "Р", 4.6),
    ("burden_fact_m", "", "Ф", 4.6),
    ("charge_kg", "Масса заряда, кг", "Р", 6.0),
    ("charge_fact_kg", "", "Ф", 6.0),
    ("stemming_m", "Забойка, м", "Р", 4.4),
    ("stemming_fact_m", "", "Ф", 4.4),
    ("primers_pcs", "ПД, шт", "", 3.4),
    ("note", "Примечание", "", 11.5),
)
KEYS = [c[0] for c in COLUMNS]
FACT_COLUMNS = [index for index, column in enumerate(COLUMNS) if column[2] == "Ф"]
COMMON_ENTRY = ("diameter_mm", "subdrill_m", "stemming_m", "primers_pcs")   # «общая запись»
DIGITS = {
    "diameter_mm": 0, "bench_height_m": 1, "depth_m": 1, "subdrill_m": 1, "water_m": 1, "lspp_m": 2,
    "spacing_m": 2, "burden_m": 2, "charge_kg": 0, "stemming_m": 1, "primers_pcs": 0,
}
NOTE_TEXT = (
    "Р — расчётная, Ф — фактическая величина (Ф заполняется при заряжании или после него). Повторяющиеся значения — "
    "общей записью: показаны в первой строке страницы и там, где меняются. Красный № — скважина первого ряда "
    "(ЛСПП указана). Масса заряда Р — по декам проекта, кратно {round_kg} кг."
)


def paginate(count: int) -> list[tuple[int, int]]:
    """Границы строк по страницам: 63 на первой, 73 на следующих."""

    pages, start, size = [], 0, FIRST_PAGE_ROWS
    while start < count:
        pages.append((start, min(count, start + size)))
        start, size = start + size, NEXT_PAGE_ROWS
    return pages or [(0, 0)]


def _value(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if key == "hole_id" or key == "note":
        return text(value)
    if value is None or value == "":
        return ""
    return num(value, DIGITS.get(key, 1))


def _head() -> tuple[list[list], list[tuple]]:
    top, bottom, style = [], [], []
    for index, (_key, title, sub, _w) in enumerate(COLUMNS):
        if sub == "Р":
            top.append(cell(title, "th"))
            style.append(("SPAN", (index, 0), (index + 1, 0)))
        elif sub == "Ф":
            top.append("")
        else:
            top.append(cell(title, "th"))
            style.append(("SPAN", (index, 0), (index, 1)))
        bottom.append(cell(sub, "th") if sub else "")
    return [top, bottom], style


def _base_style(rows: int) -> list[tuple]:
    style: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 1), GRAPHITE),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 2), (-1, -1), FONT), ("FONTSIZE", (0, 2), (-1, -1), 7),
        ("TEXTCOLOR", (0, 2), (-1, -1), GRAPHITE),
        ("ALIGN", (0, 2), (-2, -1), "CENTER"), ("ALIGN", (-1, 2), (-1, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.2), ("RIGHTPADDING", (0, 0), (-1, -1), 1.2),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
        ("FONTNAME", (KEYS.index("charge_kg"), 2), (KEYS.index("charge_kg"), -1), FONT_BOLD),
    ]
    for offset in range(rows):
        row = offset + 2
        if offset % 2 == 1:
            style.append(("BACKGROUND", (0, row), (-1, row), ZEBRA))
            # Графы Ф — белые клетки для записи от руки.
            style += [("BACKGROUND", (col, row), (col, row), white) for col in FACT_COLUMNS]
    return style


def _page_table(rows: Sequence[Mapping[str, Any]], widths: Sequence[float], totals: Mapping[str, Any] | None) -> Table:
    head, head_style = _head()
    data = list(head)
    style = _base_style(len(rows)) + head_style
    previous: dict[str, str] = {}
    for offset, row in enumerate(rows):
        line = []
        for key in KEYS:
            value = _value(row, key)
            if key in COMMON_ENTRY:
                # Общая запись: значение — в первой строке страницы и там, где меняется.
                shown = value if previous.get(key) != value else ""
                previous[key] = value
                value = shown
            line.append(value)
        data.append(line)
        if row.get("first_row"):
            style += [
                ("TEXTCOLOR", (0, offset + 2), (0, offset + 2), RED),
                ("FONTNAME", (0, offset + 2), (0, offset + 2), FONT_BOLD),
            ]
    heights = list(HEAD_H) + [ROW_H] * len(rows)
    if totals is not None:
        index = len(data)
        line = [""] * len(KEYS)
        line[0] = "Итого / среднее"
        line[KEYS.index("depth_m")] = num(totals.get("depth_m"), 1)
        line[KEYS.index("subdrill_m")] = num(totals.get("subdrill_mean_m"), 1)
        line[KEYS.index("spacing_m")] = num(totals.get("spacing_mean_m"), 2)
        line[KEYS.index("burden_m")] = num(totals.get("burden_mean_m"), 2)
        line[KEYS.index("charge_kg")] = num(totals.get("charge_kg"), 0)
        line[KEYS.index("stemming_m")] = num(totals.get("stemming_min_m"), 1)
        line[KEYS.index("primers_pcs")] = num(totals.get("primers_pcs"), 0)
        line[KEYS.index("note")] = f"скважин: {int(totals.get('hole_count') or 0)}"
        data.append(line)
        heights.append(ROW_H + 2)
        style += [
            ("SPAN", (0, index), (2, index)), ("FONTNAME", (0, index), (-1, index), FONT_BOLD),
            ("LINEABOVE", (0, index), (-1, index), 0.9, GRAPHITE), ("ALIGN", (0, index), (0, index), "LEFT"),
        ]
    table = Table(data, colWidths=list(widths), rowHeights=heights)
    table.setStyle(TableStyle(style))
    return table


def _summary_line(context: Mapping[str, Any], block: Mapping[str, Any]) -> str:
    project = context.get("project") or {}
    consumption = list((block.get("consumption") or []))
    explosives = ", ".join(dict.fromkeys(text(line.get("name")) for line in consumption if line.get("kind") == "explosive"))
    primers = ", ".join(dict.fromkeys(text(line.get("name")) for line in consumption if line.get("kind") == "primer"))
    p_kg_m = next(
        (section.get("p_kg_m") for section in block.get("technical_calculation") or [] if section.get("number") == "4"),
        None,
    )
    hardness = ((block.get("safety") or {}).get("params") or {}).get("hardness_f")
    common = text((block.get("parameter_table") or {}).get("common_note"))
    parts = [
        f"Объект: {text(project.get('object_name'))}" if text(project.get("object_name")) else "",
        f"ВВ: {explosives}" if explosives else "",
        f"P = {short(p_kg_m, 2)} кг/м" if p_kg_m else "",
        f"ПД: {primers}" if primers else "",
        f"f = {short(hardness, 1)}" if hardness is not None else "",
        f"общее для всех скважин: {common}" if common else "",
    ]
    return ";  ".join(part for part in parts if part)


def table_story(context: Mapping[str, Any], block_index: int, width: float) -> list:
    block = (context.get("blocks_v2") or [])[block_index]
    table = block.get("parameter_table") or {}
    rows = list(table.get("rows") or [])
    totals = table.get("totals") or {}
    project = context.get("project") or {}
    requisites = context.get("requisites") or {}
    widths = [width * c[3] / sum(c[3] for c in COLUMNS) for c in COLUMNS]
    horizon = text(block.get("horizon"))
    title = " · ".join(filter(None, (
        "ТАБЛИЦА ПАРАМЕТРОВ ВЗРЫВНЫХ РАБОТ",
        f"блок № {text(block.get('code'))}" if text(block.get("code")) else "",
        f"гор. {horizon} м" if horizon else "",
    )))
    when = f"взрыв  <b>{date(project.get('blast_date'))}</b>    <b>{text(project.get('blast_time')) or DASH}</b>"
    head = Table([[p(title, "doc_red"), p("", "grey_r", markup=when)]], colWidths=[width * 0.68, width * 0.32])
    head.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    story: list = [head, p(_summary_line(context, block), "note"), spacer(1)]
    pages = paginate(len(rows))
    for number, (start, end) in enumerate(pages):
        last = number == len(pages) - 1
        if number:
            story.append(PageBreak())
        # Итог — строкой под последней скважиной, если помещается на странице.
        capacity = FIRST_PAGE_ROWS if number == 0 else NEXT_PAGE_ROWS
        tail_fits = (capacity - (end - start)) * ROW_H >= TAIL_H
        story.append(_page_table(rows[start:end], widths, totals if last and tail_fits else None))
        if last and not tail_fits:
            story += [PageBreak(), _page_table([], widths, totals)]
    round_kg = short(table.get("charge_round_kg") or 5, 1)
    sign = Table(
        [[p("Составил:", "body"), p(person_line(requisites.get("made_by")), "body"), "",
          p("Проверил:", "body"), p(person_line(requisites.get("checked_by")), "body"), ""]],
        colWidths=[16 * mm, width / 2 - 16 * mm - 30 * mm, 28 * mm, 16 * mm, width / 2 - 16 * mm - 30 * mm, 28 * mm],
    )
    sign.setStyle(TableStyle([
        ("LINEBELOW", (2, 0), (2, 0), 0.5, LINE), ("LINEBELOW", (5, 0), (5, 0), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [spacer(1), p(NOTE_TEXT.format(round_kg=round_kg), "small"), spacer(3), sign]
    return story


__all__ = ["FIRST_PAGE_ROWS", "MARGINS", "NEXT_PAGE_ROWS", "paginate", "table_story"]
