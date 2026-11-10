"""Ведомость координат скважин — PDF, альбомный A4, по эталону v0.6 (TASK-015, PR 5).

Лист для выноса и съёмки в поле: проектные значения и пустые графы факта.
Числа — с точкой, как у маркшейдера (решение владельца 10.11.2026 для DXF):
координаты и отметки — 3 знака, как в файле выноса, глубины — 1 знак, углы —
целые. Шрифт, цвета и логотип — как у паспорта (`pdf.py`); `invariant=1`:
повтор ревизии — те же байты.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Mapping
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, KeepInFrame, PageBreak, PageTemplate, Paragraph, Table, TableStyle

from design.drilling_passport import DEFAULT_TOLERANCE_M
from design.reporting.drill.coords import CoordsRow, coords_header, coords_pages, coords_rows
from design.reporting.drill.pdf import ASSETS, FONT, FONT_BOLD, GRAPHITE, GREY, LINE, RED, _register_fonts, fit_text

__all__ = ["render_coords_pdf"]

PAGE_W, PAGE_H = landscape(A4)
MARGIN_X = 12 * mm
TOP = 24 * mm
BOTTOM = 14 * mm
FRAME_W = PAGE_W - 2 * MARGIN_X
FRAME_H = PAGE_H - TOP - BOTTOM
LOGO_W = 34 * mm
HEADER_W = FRAME_W - LOGO_W - 8 * mm
HEAD_ROW_H = 9 * mm
ROW_H = 5 * mm
FIELD = HexColor("#FFF6D6")   # графы, которые заполняют в поле
HEAD = HexColor("#2E3237")

TITLE = "Ведомость координат скважин"
SUBTITLE = "Ведомость координат скважин — для маркшейдерской службы (вынос и съёмка)"
FOOTER = "ООО «Комплексные решения» · Ведомость координат скважин · стр. {page} из {total}"
COLUMNS = (
    ("№", 11), ("Ряд", 7), ("X (восток)", 20), ("Y (север)", 20), ("Z устья", 14), ("H уст., м", 11),
    ("Глубина Р, м", 13), ("Перебур, м", 12), ("Z забоя Р", 14), ("X ф", 20), ("Y ф", 20), ("Z ф", 14),
    ("Глубина Ф, м", 13), ("Вода, м", 11), ("Δ глуб., м", 12), ("Смещ., м", 11), ("Вывод", 17),
    ("Угол β, °", 12), ("Азимут, °", 12),
)
# Графы факта: X ф … Вода.
FIELD_COLUMNS = (9, 13)

_STYLES = {
    "h1": ParagraphStyle("h1", fontName=FONT_BOLD, fontSize=12, leading=15, textColor=GRAPHITE, spaceAfter=2),
    "note": ParagraphStyle("note", fontName=FONT, fontSize=7, leading=8.6, textColor=GREY, spaceAfter=2),
    "crs": ParagraphStyle("crs", fontName=FONT_BOLD, fontSize=7.5, leading=9, textColor=GRAPHITE, spaceAfter=4),
    "th": ParagraphStyle("th", fontName=FONT_BOLD, fontSize=6.5, leading=7.6, textColor=white, alignment=TA_CENTER),
}


def _tolerance(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    number = float(value) if isinstance(value, (int, float)) and value > 0 else DEFAULT_TOLERANCE_M
    return f"{number:g}".replace(".", ",")


def _note(context: Mapping[str, Any]) -> str:
    payload = (context.get("passport") or {}).get("payload") or {}
    return (
        "Р — проект (вынос), Ф — факт (съёмка после бурения). Ряд 1 — первый от откоса, 2 — остальные. "
        "Δ — факт минус проект; «Вывод»: ОК — в допуске (глубина ±"
        f"{_tolerance(payload, 'tol_depth_m')} м, устье {_tolerance(payload, 'tol_collar_m')} м от выноски), "
        "ДОБУРИТЬ / ПЕРЕБУР — глубина вне допуска, СМЕЩЕНИЕ — устье дальше допуска; такие скважины до "
        "заряжания исправляются или учитываются в проекте МВ. Угол β и азимут — только у наклонных скважин."
    )


def _angle(value: float | None) -> str:
    return "" if value is None else str(round(value) % 360)


def _cells(row: CoordsRow) -> list[str]:
    return [
        row.number, str(row.row), f"{row.x:.3f}", f"{row.y:.3f}", f"{row.z_collar:.3f}", f"{row.bench_m:.1f}",
        f"{row.depth_m:.1f}", f"{row.subdrill_m:.1f}", f"{row.z_toe:.3f}", "", "", "", "", "", "", "", "",
        _angle(row.dip_deg), _angle(row.azimuth_deg),
    ]


def _table(rows: list[CoordsRow]) -> Table:
    head = [Paragraph(escape(title), _STYLES["th"]) for title, _ in COLUMNS]
    data = [head, *(_cells(row) for row in rows)]
    widths = [width * mm for _, width in COLUMNS]
    scale = FRAME_W / sum(widths)
    table = Table(data, colWidths=[w * scale for w in widths], rowHeights=[HEAD_ROW_H] + [ROW_H] * len(rows))
    first, last = FIELD_COLUMNS
    commands = [
        ("FONT", (0, 1), (-1, -1), FONT, 7.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), GRAPHITE),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("ALIGN", (0, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]
    if rows:
        commands.append(("BACKGROUND", (first, 1), (last, -1), FIELD))
    for index, row in enumerate(rows, start=1):
        if row.row == 1:
            commands.append(("TEXTCOLOR", (0, index), (1, index), RED))
    table.setStyle(TableStyle(commands))
    return table


def _decorate(header: str, total: int):
    logo = str(ASSETS / "logo.png")

    def on_page(canvas, _doc) -> None:
        number = canvas.getPageNumber()
        canvas.saveState()
        canvas.drawImage(logo, MARGIN_X, PAGE_H - 17 * mm, width=LOGO_W, height=LOGO_W * 738 / 2400, mask="auto")
        canvas.setStrokeColor(RED)
        canvas.setLineWidth(1.2)
        canvas.line(MARGIN_X, PAGE_H - 20 * mm, PAGE_W - MARGIN_X, PAGE_H - 20 * mm)
        canvas.setFillColor(GREY)
        canvas.setFont(FONT, 7.5)
        canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 11.5 * mm, fit_text(header, FONT, 7.5, HEADER_W))
        canvas.setFillColor(GRAPHITE)
        canvas.setFont(FONT_BOLD, 8.5)
        canvas.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 16.5 * mm, SUBTITLE)
        canvas.setFillColor(GREY)
        canvas.setFont(FONT, 7)
        canvas.drawCentredString(PAGE_W / 2, 8 * mm, FOOTER.format(page=number, total=total))
        canvas.restoreState()

    return on_page


def render_coords_pdf(context: Mapping[str, Any], *, revision_no: int | None = None) -> bytes:
    """Ведомость координат из снимка ревизии: один кусок `coords_pages` — один лист."""

    _register_fonts()
    header, crs = coords_header(context)
    pages = coords_pages(coords_rows(context))
    passport_no = str((context.get("passport") or {}).get("passport_no") or "")
    title = f"Ведомость координат скважин — паспорт на бурение № {passport_no}"
    if revision_no is not None:
        title += f", ревизия {revision_no}"
    output = BytesIO()
    doc = BaseDocTemplate(
        output, pagesize=(PAGE_W, PAGE_H), leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=TOP,
        bottomMargin=BOTTOM, title=title, author="BlastEX", subject="Ведомость координат скважин",
        creator="BlastEX", producer="BlastEX", invariant=1,
    )
    frame = Frame(MARGIN_X, BOTTOM, FRAME_W, FRAME_H, id="body", leftPadding=0, rightPadding=0, topPadding=0,
                  bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=_decorate(header, len(pages)))])
    story: list = []
    for index, rows in enumerate(pages):
        page: list = []
        if index == 0:
            page += [
                Paragraph(TITLE, _STYLES["h1"]),
                Paragraph(escape(_note(context)), _STYLES["note"]),
                Paragraph(escape(f"{crs}. X — восток, Y — север; координаты в СК объекта без пересчёта."), _STYLES["crs"]),
            ]
        else:
            story.append(PageBreak())
        page.append(_table(rows))
        # Один кусок — один лист: страница не переносится, «стр. N из M» верно.
        story.append(KeepInFrame(FRAME_W, FRAME_H, page, mode="shrink"))
    doc.build(story)
    return output.getvalue()
