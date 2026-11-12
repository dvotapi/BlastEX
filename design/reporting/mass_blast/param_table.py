"""Документ 3: таблица параметров взрывных работ (прил. 11 ФНП 494, эталон v0.11, стр. 9–11).

Книжный A4, вписан по ширине; разрывы страниц — строго по `FIRST_PAGE_ROWS` /
`NEXT_PAGE_ROWS` скважин (63 / 73, TASK-018 §3.2), заголовок таблицы (2 строки,
группы граф Р / Ф) повторяется на каждой странице. «Общая запись» (прил. 11,
прим. 3): диаметр, перебур Р, забойка Р и ПД печатаются в первой строке
страницы и там, где значение меняется. Графы Ф проекта — пустые белые клетки;
исполнительная таблица слоя «Факт» (PR 5, `fact=`) печатает в них факт и
итог Ф. Данные — `blocks_v2[i].parameter_table` (PR 2) или ревизия слоя
«Факт», рендер ничего не считает.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from reportlab.lib.colors import white
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import PageBreak, Paragraph, Table, TableStyle

from design.reporting.brand import FONT, FONT_BOLD, GRAPHITE, LINE, RED, ZEBRA
from design.reporting.mass_blast.common import DASH, S, cell, date, num, p, person_line, rich, short, spacer, text
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
    "depth_fact_m": 1, "subdrill_fact_m": 1, "lspp_fact_m": 2, "spacing_fact_m": 2, "burden_fact_m": 2,
    "charge_fact_kg": 0, "stemming_fact_m": 1,
}
NOTE_TEXT = (
    "Р — расчётная, Ф — фактическая величина (Ф заполняется при заряжании или после него). Повторяющиеся значения — "
    "общей записью: показаны в первой строке страницы и там, где меняются. Красный № — скважина первого ряда "
    "(ЛСПП указана). Масса заряда Р — по декам проекта, кратно {round_kg} кг."
)


FACT_NOTE_TEXT = (
    "Р — по проекту (ревизия проекта массового взрыва), Ф — по факту: глубина, перебур, ЛСПП и расстояния — по "
    "исполнительной съёмке (те же правила расчёта, что у Р), масса и забойка — по записям заряжания; масса Р — "
    "кратно {round_kg} кг, Ф — до 1 кг. Пустая клетка Ф — факта нет. Итог Ф — когда факт есть у всех скважин. "
    "Красный № — скважина первого ряда."
)
FACT_TOTALS = (
    ("depth_fact_m", "depth_fact_m", 1), ("subdrill_fact_m", "subdrill_fact_mean_m", 1),
    ("spacing_fact_m", "spacing_fact_mean_m", 2), ("burden_fact_m", "burden_fact_mean_m", 2),
    ("charge_fact_kg", "charge_fact_kg", 0), ("stemming_fact_m", "stemming_fact_min_m", 1),
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


NOTE_FONT = 7.0
NOTE_PREVIEW_CHARS = 60   # две строки узкой графы мелким шрифтом — заведомо меньше
NOTE_SMALL = ParagraphStyle("mb_table_note", fontName=FONT, fontSize=4.8, leading=4.9, textColor=GRAPHITE)


def _note_cell(hole_id: str, note: str, width: float, overflow: list[tuple[str, str]]) -> Any:
    """Примечание в узкой графе: строкой 7 pt, иначе двумя строками мелко; не
    помещается и так — начало с «…*», полный текст — под таблицей (`overflow`)."""

    inner = width - 2.4
    if not note or pdfmetrics.stringWidth(note, FONT, NOTE_FONT) <= inner:
        return note
    paragraph = Paragraph(rich(note), NOTE_SMALL)
    if paragraph.wrap(inner, ROW_H)[1] <= ROW_H - 1:
        return paragraph
    overflow.append((hole_id, note))
    # В графе — только начало (полный текст — под таблицей): потолок длины,
    # чтобы подбор не перебирал тысячи знаков длинного примечания.
    cut = note[:NOTE_PREVIEW_CHARS]
    while cut and Paragraph(rich(cut + "…*"), NOTE_SMALL).wrap(inner, ROW_H)[1] > ROW_H - 1:
        cut = cut[:-1]
    return Paragraph(rich(cut.rstrip() + "…*"), NOTE_SMALL)


def _page_table(
    rows: Sequence[Mapping[str, Any]],
    widths: Sequence[float],
    totals: Mapping[str, Any] | None,
    overflow: list[tuple[str, str]] | None = None,
    *,
    fact: bool = False,
) -> Table:
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
            if key == "note":
                value = _note_cell(text(row.get("hole_id")), value, widths[-1], overflow if overflow is not None else [])
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
        if fact:
            for key, total, digits in FACT_TOTALS:
                value = totals.get(total)
                line[KEYS.index(key)] = "" if value is None else num(value, digits)
        data.append(line)
        heights.append(ROW_H + 2)
        style += [
            ("SPAN", (0, index), (2, index)), ("FONTNAME", (0, index), (-1, index), FONT_BOLD),
            ("LINEABOVE", (0, index), (-1, index), 0.9, GRAPHITE), ("ALIGN", (0, index), (0, index), "LEFT"),
        ]
    table = Table(data, colWidths=list(widths), rowHeights=heights)
    table.setStyle(TableStyle(style))
    return table


SUMMARY_MAX_LINES = 2   # строка «Объект; ВВ; P; ПД; f; общее…» над таблицей — не выше двух строк


def _summary_line(context: Mapping[str, Any], block: Mapping[str, Any], *, common: bool = True) -> str:
    project = context.get("project") or {}
    consumption = list((block.get("consumption") or []))
    explosives = ", ".join(dict.fromkeys(text(line.get("name")) for line in consumption if line.get("kind") == "explosive"))
    primers = ", ".join(dict.fromkeys(text(line.get("name")) for line in consumption if line.get("kind") == "primer"))
    p_kg_m = next(
        (section.get("p_kg_m") for section in block.get("technical_calculation") or [] if section.get("number") == "4"),
        None,
    )
    hardness = ((block.get("safety") or {}).get("params") or {}).get("hardness_f")
    common_note = text((block.get("parameter_table") or {}).get("common_note"))
    parts = [
        f"Объект: {text(project.get('object_name'))}" if text(project.get("object_name")) else "",
        f"ВВ: {explosives}" if explosives else "",
        f"P = {short(p_kg_m, 2)} кг/м" if p_kg_m else "",
        f"ПД: {primers}" if primers else "",
        f"f = {short(hardness, 1)}" if hardness is not None else "",
        (f"общее для всех скважин: {common_note}" if common else "общее для всех скважин: см. под таблицей")
        if common_note else "",
    ]
    return ";  ".join(part for part in parts if part)


def table_story(
    context: Mapping[str, Any], block_index: int, width: float, *, fact: Mapping[str, Any] | None = None
) -> list:
    """Таблица блока. `fact` — исполнительная таблица слоя «Факт» (PR 5):
    `{"blast_date", "blast_time"}` по факту; без него — таблица проекта."""

    block = (context.get("blocks_v2") or [])[block_index]
    table = block.get("parameter_table") or {}
    rows = list(table.get("rows") or [])
    totals = table.get("totals") or {}
    project = context.get("project") or {}
    requisites = context.get("requisites") or {}
    widths = [width * c[3] / sum(c[3] for c in COLUMNS) for c in COLUMNS]
    horizon = text(block.get("horizon"))
    title = " · ".join(filter(None, (
        "ТАБЛИЦА ПАРАМЕТРОВ ВЗРЫВНЫХ РАБОТ (ФАКТ)" if fact is not None else "ТАБЛИЦА ПАРАМЕТРОВ ВЗРЫВНЫХ РАБОТ",
        f"блок № {text(block.get('code'))}" if text(block.get("code")) else "",
        f"гор. {horizon} м" if horizon else "",
    )))
    # Значения проекта — экранированными (`rich`): текст пользователя не становится разметкой.
    when = (f"взрыв  <b>{rich(date(project.get('blast_date')))}</b>    "
            f"<b>{rich(text(project.get('blast_time')) or DASH)}</b>")
    if fact is not None and (text(fact.get("blast_date")) or text(fact.get("blast_time"))):
        when = (f"взрыв по факту  <b>{rich(date(text(fact.get('blast_date')) or project.get('blast_date')))}</b>    "
                f"<b>{rich(text(fact.get('blast_time')) or DASH)}</b>")
    head = Table([[p(title, "doc_red"), p("", "grey_r", markup=when)]], colWidths=[width * 0.68, width * 0.32])
    head.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    # Строка шапки не выше двух строк: длинное общее примечание — под таблицей,
    # иначе первая страница не вместит 63 скважины.
    summary = p(_summary_line(context, block), "note")
    common_below = False
    if summary.wrap(width, 1000)[1] > SUMMARY_MAX_LINES * S["note"].leading + 0.5:
        summary = p(_summary_line(context, block, common=False), "note")
        common_below = True
    story: list = [head, summary, spacer(1)]
    pages = paginate(len(rows))
    overflow: list[tuple[str, str]] = []
    for number, (start, end) in enumerate(pages):
        last = number == len(pages) - 1
        if number:
            story.append(PageBreak())
        # Итог — строкой под последней скважиной, если помещается на странице.
        capacity = FIRST_PAGE_ROWS if number == 0 else NEXT_PAGE_ROWS
        tail_fits = (capacity - (end - start)) * ROW_H >= TAIL_H
        story.append(_page_table(rows[start:end], widths, totals if last and tail_fits else None, overflow,
                                 fact=fact is not None))
        if last and not tail_fits:
            story += [PageBreak(), _page_table([], widths, totals, fact=fact is not None)]
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
    if fact is None:
        story += [spacer(1), p(NOTE_TEXT.format(round_kg=round_kg), "small")]
    else:
        count = int(totals.get("hole_count") or 0)
        done = (f"Факт: бурение — {int(totals.get('drilled_count') or 0)} из {count} скв., заряжание — "
                f"{int(totals.get('charged_count') or 0)} из {count} скв.; отказов — {int(totals.get('misfired_count') or 0)}.")
        story += [spacer(1), p(done + " " + FACT_NOTE_TEXT.format(round_kg=round_kg), "small")]
    if common_below:
        story.append(p(f"Общее для всех скважин: {text(table.get('common_note'))}.", "small"))
    if overflow:
        full = "; ".join(f"№ {hole} — {note}" for hole, note in overflow)
        story.append(p(f"* Примечания к скважинам полностью: {full}.", "small"))
    story += [spacer(3), sign]
    return story


__all__ = ["FIRST_PAGE_ROWS", "MARGINS", "NEXT_PAGE_ROWS", "paginate", "table_story"]
