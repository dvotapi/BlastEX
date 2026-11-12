"""Стили, форматирование чисел и мелкие строительные блоки документов проекта МВ."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence
from xml.sax.saxutils import escape

from reportlab.lib.colors import white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from design.reporting.brand import (
    FONT,
    FONT_BOLD,
    FONT_FALLBACK,
    GRAPHITE,
    GREY,
    LINE,
    RED,
    TINT,
    ZEBRA,
    register_fallback_font,
    register_fonts,
)
from design.reporting.drill.fmt import DASH, NBSP, date, num, short

__all__ = [
    "DASH",
    "NBSP",
    "S",
    "blank_line",
    "cell",
    "date",
    "date_short",
    "grid_style",
    "num",
    "p",
    "rich",
    "short",
    "signature_row",
    "text",
    "value_text",
]

RED_HEX = "#B71C1C"
GREY_HEX = "#6B7075"


def _style(name: str, size: float, *, bold: bool = False, color=GRAPHITE, align=TA_LEFT, leading: float | None = None,
           space_after: float = 0, space_before: float = 0) -> ParagraphStyle:
    return ParagraphStyle(
        name, fontName=FONT_BOLD if bold else FONT, fontSize=size, leading=leading or size * 1.22,
        textColor=color, alignment=align, spaceAfter=space_after, spaceBefore=space_before,
    )


S: dict[str, ParagraphStyle] = {
    "body": _style("mb_body", 8.5),
    "body_c": _style("mb_body_c", 8.5, align=TA_CENTER),
    "body_r": _style("mb_body_r", 8.5, align=TA_RIGHT),
    "bold": _style("mb_bold", 8.5, bold=True),
    "bold_c": _style("mb_bold_c", 8.5, bold=True, align=TA_CENTER),
    "bold_r": _style("mb_bold_r", 8.5, bold=True, align=TA_RIGHT),
    "grey": _style("mb_grey", 8.5, color=GREY),
    "grey_r": _style("mb_grey_r", 8.5, color=GREY, align=TA_RIGHT),
    "grey_c": _style("mb_grey_c", 8.5, color=GREY, align=TA_CENTER),
    "small": _style("mb_small", 6.5, color=GREY),
    "small_c": _style("mb_small_c", 6.5, color=GREY, align=TA_CENTER),
    "note": _style("mb_note", 6.5, color=GREY, leading=7.6),
    "item": _style("mb_item", 8, leading=9.6),
    "item_b": _style("mb_item_b", 8, bold=True, leading=9.6),
    "item_br": _style("mb_item_br", 8, bold=True, align=TA_RIGHT, leading=9.6),
    "item_grey": _style("mb_item_grey", 8, color=GREY, leading=9.6),
    "cons_label": _style("mb_cons_label", 7, color=GREY, leading=8.4),
    "cons_value": _style("mb_cons_value", 7, bold=True, leading=8.4),
    "cap": _style("mb_cap", 9, bold=True),
    "h2": _style("mb_h2", 10, bold=True, space_after=2),
    "section": _style("mb_section", 8.5, bold=True),
    "doc_red": _style("mb_doc_red", 10, bold=True, color=RED),
    "title_red": _style("mb_title_red", 13, bold=True, color=RED, align=TA_CENTER),
    "act_red": _style("mb_act_red", 14, bold=True, color=RED, align=TA_CENTER),
    "number": _style("mb_number", 24, bold=True, align=TA_CENTER, leading=30),
    "object": _style("mb_object", 12, bold=True, align=TA_CENTER),
    "label_grey_r": _style("mb_label_grey_r", 9.5, color=GREY, align=TA_RIGHT),
    "summary_value": _style("mb_summary_value", 9.5, bold=True),
    "th": _style("mb_th", 6.5, bold=True, color=white, align=TA_CENTER, leading=7.6),
    "th_l": _style("mb_th_l", 7, bold=True, color=white, leading=8.4),
    "td": _style("mb_td", 7, leading=8.4),
    "td_br": _style("mb_td_br", 7, bold=True, align=TA_RIGHT, leading=8.4),
    "td_c": _style("mb_td_c", 7, align=TA_CENTER, leading=8.4),
    "td_r": _style("mb_td_r", 7, align=TA_RIGHT, leading=8.4),
    "td_b": _style("mb_td_b", 7, bold=True, leading=8.4),
    "td_bc": _style("mb_td_bc", 7, bold=True, align=TA_CENTER, leading=8.4),
    "td_red": _style("mb_td_red", 7, bold=True, color=RED, align=TA_CENTER, leading=8.4),
    "blank": _style("mb_blank", 10, color=GREY, align=TA_CENTER),
}

# «H_у», «l_заб», «K_р», «r_разл» в подписях данных — подстрочным индексом.
_SUBSCRIPT = re.compile(r"(?<![\w])([A-Za-zηαΔΣρ])_\{?([0-9A-Za-zА-Яа-яЁё]+)\}?")


def text(value: Any) -> str:
    """Пусто — «» (не «None»); число — как есть."""

    if value is None:
        return ""
    return str(value).strip()


@lru_cache(maxsize=1)
def _roboto_chars() -> frozenset[int]:
    register_fonts()
    register_fallback_font()
    return frozenset(pdfmetrics.getFont(FONT).face.charToGlyph)


def _with_fallback(markup: str) -> str:
    """Знаки, которых нет в Roboto, — шрифтом DejaVu (иначе печатается пусто)."""

    known = _roboto_chars()
    out: list[str] = []
    for char in markup:
        if ord(char) > 127 and ord(char) not in known:
            out.append(f'<font name="{FONT_FALLBACK}">{char}</font>')
        else:
            out.append(char)
    return "".join(out)


def rich(value: Any) -> str:
    """Экранированный текст с подстрочными индексами: пользовательский текст
    не становится разметкой ReportLab."""

    markup = _SUBSCRIPT.sub(r'\1<sub rise="20%" size="75%">\2</sub>', escape(text(value)))
    return _with_fallback(markup.replace("\n", "<br/>"))


def p(value: Any, style: str = "body", *, markup: str | None = None) -> Paragraph:
    """Абзац: `markup` — уже готовая разметка (только из кода рендера)."""

    return Paragraph(_with_fallback(markup) if markup is not None else rich(value), S[style])


def cell(value: Any, style: str = "td") -> Paragraph:
    return p(value, style)


def date_short(value: str | None) -> str:
    """ISO «2026-10-13» → «13.10.26» (как в п. 4 распорядка эталона)."""

    full = date(value)
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", full):
        return full[:6] + full[8:]
    return full


def value_text(value: Any) -> str:
    """Число техрасчёта для печати: ≥ 100 — целое, ≥ 1 — до сотых, меньше — до
    тысячных, без лишних нулей. Строка — как есть. Округления расчёта (5 кг,
    кратно 50 м) уже в данных; здесь только запись."""

    if value is None or value == "":
        return DASH
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float)):
        magnitude = abs(float(value))
        if magnitude >= 100:
            return num(value, 0)
        if magnitude >= 1:
            return short(value, 2)
        return short(value, 3)
    return text(value)


def blank_line(width: float, label: str = "") -> Table:
    """Место для записи от руки: линия и подпись под ней мелко."""

    rows = [[""]] + ([[p(label, "small_c")]] if label else [])
    table = Table(rows, colWidths=[width], rowHeights=[5 * mm] + ([None] if label else []))
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (0, 0), 0.6, GRAPHITE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def person_line(person: Mapping[str, Any] | None) -> str:
    person = person or {}
    return " ".join(part for part in (text(person.get("position")), text(person.get("name"))) if part)


def signature_row(label: str, person: Mapping[str, Any] | None, width: float) -> Table:
    """«Расчёт составил: | должность ФИО | ________ | «__» ____ 20__» — у каждого своя линия."""

    widths = [45 * mm, width - 45 * mm - 45 * mm - 28 * mm, 45 * mm, 28 * mm]
    table = Table(
        [[p(label, "body"), p(person_line(person), "body"), "", p("«__» ____ 20__", "small_c")]],
        colWidths=widths,
    )
    table.setStyle(TableStyle([
        ("LINEBELOW", (2, 0), (2, 0), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def grid_style(header_rows: int = 1, *, zebra: bool = True, rows: int = 0, padding: float = 1.5) -> list[tuple]:
    """Таблица фирменного стиля: графитовая шапка, тонкая сетка, зебра."""

    style: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), GRAPHITE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), padding), ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
    ]
    if zebra:
        for row in range(header_rows, header_rows + rows):
            if (row - header_rows) % 2 == 1:
                style.append(("BACKGROUND", (0, row), (-1, row), ZEBRA))
    return style


def header_line(context: Mapping[str, Any]) -> str:
    """Шапка листа: «Проект массового взрыва № … · блок № … · гор. …»."""

    number = text((context.get("requisites") or {}).get("project_no"))
    blocks = [b for b in context.get("blocks") or []]
    codes = ", ".join(text(b.get("code")) for b in blocks if text(b.get("code")))
    horizons = ", ".join(dict.fromkeys(text(b.get("horizon")) for b in blocks if text(b.get("horizon"))))
    parts = ["Проект массового взрыва" + (f" № {number}" if number else "")]
    if codes:
        parts.append(f"блок № {codes}")
    if horizons:
        parts.append(f"гор. {horizons}")
    return " · ".join(parts)


def width_of(value: str, size: float, bold: bool = False) -> float:
    return pdfmetrics.stringWidth(value, FONT_BOLD if bold else FONT, size)


def spacer(height_mm: float) -> Spacer:
    return Spacer(1, height_mm * mm)


def nonempty(values: Iterable[Any]) -> list[str]:
    return [text(v) for v in values if text(v)]


def first(items: Sequence[Mapping[str, Any]], **match: Any) -> Mapping[str, Any] | None:
    for item in items:
        if all(item.get(key) == value for key, value in match.items()):
            return item
    return None


__all__ += ["GREY_HEX", "RED_HEX", "TINT", "header_line", "nonempty", "person_line", "spacer", "width_of", "first"]
