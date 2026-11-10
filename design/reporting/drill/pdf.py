"""PDF паспорта на бурение по форме v0.7 (ReportLab, как паспорт массового взрыва).

Рисует раскладку `layout.build_layout` и ничего не считает. Каждая страница
раскладки — ровно одна страница PDF (`KeepInFrame` ужимает, а не переносит),
поэтому «стр. N из M» и чётная страница плана не зависят от длины текстов.
`invariant=1` убирает время и случайный идентификатор: та же ревизия — те
же байты.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Mapping
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepInFrame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from design.reporting.drill import plan_drawing, rig_scheme
from design.reporting.drill.layout import DepthPage, PassportLayout, build_layout

ASSETS = Path(__file__).with_name("assets")
FONT = "BlastEXRoboto"
FONT_BOLD = "BlastEXRoboto-Bold"

GRAPHITE = HexColor("#2E3237")
RED = HexColor("#B71C1C")
TINT = HexColor("#FCEDEE")
ZEBRA = HexColor("#F3F4F5")
LINE = HexColor("#C9CCD0")
GREY = HexColor("#6B7075")

FOOTER = "ООО «Комплексные решения» · Паспорт на бурение · стр. {page} из {total}"
TITLE_SAFETY = "Меры безопасности. Порядок работ. Установка станка"
TITLE_DEPTHS = "Паспорт на бурение взрывных скважин (ФНП 505 п. 989)"
TITLE_DEPTHS_MORE = "Паспорт на бурение взрывных скважин (продолжение)"
TITLE_BLANK = ""
TITLE_PLAN = "Графическая часть. План расположения скважин"

PAGE_W, PAGE_H = A4
MARGIN_X = 15 * mm
TOP = 24 * mm       # шапка: логотип и красная линия
BOTTOM = 14 * mm    # подвал
FRAME_W = PAGE_W - 2 * MARGIN_X
FRAME_H = PAGE_H - TOP - BOTTOM
CELL_PAD_X = 4
CELL_PAD_Y = 2
ACQUAINTANCE_ROW_H = 7.2 * mm
LOGO_W = 34 * mm


def _register_fonts() -> None:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(ASSETS / "Roboto-Regular.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(ASSETS / "Roboto-Bold.ttf")))
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)


def _style(name: str, size: float, *, bold: bool = False, color=GRAPHITE, align=TA_LEFT, leading: float | None = None,
           space_after: float = 0) -> ParagraphStyle:
    return ParagraphStyle(
        name, fontName=FONT_BOLD if bold else FONT, fontSize=size, leading=leading or size * 1.25,
        textColor=color, alignment=align, spaceAfter=space_after,
    )


S = {
    "body": _style("body", 8.5),
    "body_r": _style("body_r", 8.5, align=TA_RIGHT),
    "grey": _style("grey", 8.5, color=GREY),
    "grey_r": _style("grey_r", 8.5, color=GREY, align=TA_RIGHT),
    "bold": _style("bold", 8.5, bold=True),
    "small": _style("small", 7, color=GREY),
    "small_c": _style("small_c", 7, color=GREY, align=TA_CENTER),
    "h2": _style("h2", 10.5, bold=True, space_after=3),
    "cap": _style("cap", 9, bold=True),
    "title_red": _style("title_red", 13, bold=True, color=RED, align=TA_CENTER),
    "number": _style("number", 26, bold=True, align=TA_CENTER, leading=32),
    "object": _style("object", 12.5, bold=True, align=TA_CENTER),
    "customer": _style("customer", 8.5, color=GREY, align=TA_CENTER),
    "basis_c": _style("basis_c", 8, color=GREY, align=TA_CENTER),
    "s_label": _style("s_label", 9.5),
    "s_value": _style("s_value", 20, bold=True, color=RED, align=TA_CENTER, leading=26),
    "th": _style("th", 7, bold=True, color=white, align=TA_CENTER),
    "td": _style("td", 7.5),
    "safety_no": _style("safety_no", 8.5, bold=True, color=RED, align=TA_RIGHT),
    "blank": _style("blank", 10, color=GREY, align=TA_CENTER),
}


def _p(text: str, style: str) -> Paragraph:
    """Пользовательский текст не становится разметкой ReportLab."""

    return Paragraph(escape(text), S[style])


def _pb(label: str, value: str, style: str = "bold") -> Paragraph:
    return Paragraph(f"{escape(label)}<b>{escape(value)}</b>", S[style])


# --- страница 1 ----------------------------------------------------------

def _signer_cell(caption: str, signer: tuple[str, str, str]) -> list:
    position, organization, name = signer
    return [
        _p(caption, "cap"),
        _p(position or " ", "body"),
        _p(organization or " ", "body"),
        Spacer(1, 4 * mm),
        _p(f"___________  {name}", "body"),
        _p("«___» ___________ 20__ г.", "body"),
    ]


def _title_page(layout: PassportLayout) -> list:
    title = layout.title
    signers = Table(
        [[_signer_cell("СОГЛАСОВАНО", title.agreed), _signer_cell("УТВЕРЖДАЮ", title.approved)]],
        colWidths=[FRAME_W / 2] * 2,
    )
    signers.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    half = FRAME_W / 2
    summary = Table(
        [[_p(label, "grey_r"), _p(value, "bold")] for label, value in title.summary],
        colWidths=[half - 2 * mm, half - 2 * mm],
    )
    summary.setStyle(TableStyle([
        ("LEFTPADDING", (1, 0), (1, -1), 4 * mm), ("TOPPADDING", (0, 0), (-1, -1), 0.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story: list = [signers, Spacer(1, 10 * mm), _p("ПАСПОРТ НА БУРЕНИЕ ВЗРЫВНЫХ СКВАЖИН", "title_red"),
                   Spacer(1, 2 * mm), _p(f"№ {title.passport_no}", "number"), Spacer(1, 1 * mm)]
    if title.object_name:
        story.append(_p(title.object_name, "object"))
    if title.customer:
        story.append(_p(f"Заказчик: {title.customer}", "customer"))
    story += [Spacer(1, 6 * mm), summary]
    if title.approvals:
        approvals = Table(
            [[_p("Согласовано:", "grey_r"), _p(line, "body"), ""] for line in title.approvals],
            colWidths=[half - 2 * mm, half - 32 * mm, 30 * mm],
        )
        approvals.setStyle(TableStyle([
            ("LEFTPADDING", (1, 0), (1, -1), 4 * mm), ("LINEBELOW", (2, 0), (2, -1), 0.6, GRAPHITE),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [Spacer(1, 5 * mm), approvals]
    story += [Spacer(1, 7 * mm), _p("С паспортом ознакомлены", "h2"), _people_table(title), Spacer(1, 8 * mm),
              _p(title.basis, "basis_c"), _p(title.org_year, "basis_c")]
    return story


def _people_table(title) -> Table:
    """Таблица ознакомления: строка не ниже 7,2 мм и растёт под длинную должность."""

    rows = [[_p(h, "th") for h in ("№", "Фамилия И. О.", "Должность", "Дата", "Подпись")]]
    rows += [
        [_p(str(index), "td"), _p(name, "td"), _p(position, "td"), "", ""]
        for index, (name, position) in enumerate(title.acquaintance, start=1)
    ]
    widths = [8 * mm, 46 * mm, 72 * mm, 24 * mm]
    widths.append(FRAME_W - sum(widths))
    heights: list[float | None] = [None]
    for row in rows[1:]:
        needed = max(cell.wrap(widths[col] - 2 * CELL_PAD_X, PAGE_H)[1] for col, cell in enumerate(row[:3]))
        heights.append(max(ACQUAINTANCE_ROW_H, needed + 2 * CELL_PAD_Y))
    people = Table(rows, colWidths=widths, rowHeights=heights, repeatRows=1)
    people.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRAPHITE), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD_X), ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD_X),
        ("TOPPADDING", (0, 0), (-1, -1), CELL_PAD_Y), ("BOTTOMPADDING", (0, 0), (-1, -1), CELL_PAD_Y),
    ]))
    return people


def fit_text(text: str, font: str, size: float, width: float) -> str:
    """Строка, обрезанная с «…» по ширине; помещается — как есть."""

    if pdfmetrics.stringWidth(text, font, size) <= width:
        return text
    while text and pdfmetrics.stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def fit_font_size(text: str, font: str, size: float, width: float, min_size: float = 4.5) -> float:
    """Кегль, при котором строка помещается по ширине (не меньше `min_size`)."""

    actual = pdfmetrics.stringWidth(text, font, size)
    if actual <= width:
        return size
    return max(min_size, size * width / actual)


# --- страница 2 ----------------------------------------------------------

def _safety_page(layout: PassportLayout) -> list:
    safety = layout.safety
    items = Table(
        [[_p(str(number), "safety_no"), _p(text, "body")] for number, text in enumerate(safety.items, start=1)],
        colWidths=[7 * mm, FRAME_W - 7 * mm],
    )
    items.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 0.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8),
    ]))
    order = Table(
        [[_p(label, "grey"), _p(value, "body")] for label, value in safety.work_order],
        colWidths=[38 * mm, FRAME_W - 38 * mm],
    )
    order.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.6),
    ]))
    scheme_w, scheme_h = 105 * mm, 112 * mm
    s_box = Table([[_p(safety.s_text, "s_value")]], colWidths=[52 * mm])
    s_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("TOPPADDING", (0, 0), (-1, -1), 3),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    right = [
        _p("От верхней бровки до ближайшей точки опоры станка (гусениц) — не менее", "s_label"),
        Spacer(1, 2 * mm), s_box, Spacer(1, 2 * mm),
        _p("Ось станка — перпендикулярно бровке.", "body"),
    ]
    scheme = Table(
        [[rig_scheme.drawing(scheme_w, scheme_h, font=FONT, bold_font=FONT_BOLD), right]],
        colWidths=[scheme_w + 4 * mm, FRAME_W - scheme_w - 4 * mm],
    )
    scheme.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return [
        _p("Основные меры безопасности", "h2"), items, Spacer(1, 1 * mm),
        _p(safety.basis, "small"), Spacer(1, 3 * mm),
        _p("Порядок работ", "h2"), order, Spacer(1, 3 * mm),
        _p("Установка буровой установки на первом ряду", "h2"), scheme,
    ]


# --- страницы таблицы глубин ---------------------------------------------

DEPTH_HEAD = ("№", "Глуб.", "Угол", "Азим.", "Факт")
DEPTH_WIDTHS = (8.5 * mm, 10 * mm, 7.5 * mm, 8.5 * mm, 9.5 * mm)


def _params_table(page: DepthPage) -> Table:
    pairs = list(page.params or ())
    rows = []
    for index in range(0, len(pairs), 2):
        left = pairs[index]
        right = pairs[index + 1] if index + 1 < len(pairs) else ("", "")
        rows.append([_p(left[0], "grey"), _p(left[1], "bold"), _p(right[0], "grey"), _p(right[1], "bold")])
    rows.append([_p("Допустимые отклонения", "grey"), _p(page.tolerances or "", "bold"), "", ""])
    rows.append([_p("Технология бурения", "grey"), _p(page.technology or "", "body"), "", ""])
    widths = [48 * mm, 42 * mm, 46 * mm]
    widths.append(FRAME_W - sum(widths))
    table = Table(rows, colWidths=widths)
    last = len(rows) - 1
    table.setStyle(TableStyle([
        ("SPAN", (1, last - 1), (3, last - 1)), ("SPAN", (1, last), (3, last)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
    ]))
    return table


def _depth_table(page: DepthPage, rows_per_column: int) -> Table:
    groups = 4
    head = [_p(h, "th") for _ in range(groups) for h in DEPTH_HEAD]
    data = [head]
    style = [
        ("FONTNAME", (0, 1), (-1, -1), FONT), ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("TEXTCOLOR", (0, 1), (-1, -1), GRAPHITE),
        ("BACKGROUND", (0, 0), (-1, 0), GRAPHITE), ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 1), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9),
        ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]
    for row in range(rows_per_column):
        line: list[str] = []
        if row % 2 == 1:
            style.append(("BACKGROUND", (0, row + 1), (-1, row + 1), ZEBRA))
        for group in range(groups):
            column = page.columns[group] if group < len(page.columns) else ()
            if row < len(column):
                cell = column[row]
                line += [cell.number, cell.depth, cell.angle, cell.azimuth, ""]
                # Длинный номер («R10-150») уменьшается, а не вылезает из ячейки.
                number_font = FONT_BOLD if cell.first_row else FONT
                size = fit_font_size(cell.number, number_font, 7, DEPTH_WIDTHS[0] - 2)
                if size < 7:
                    style.append(("FONTSIZE", (group * 5, row + 1), (group * 5, row + 1), size))
                if cell.first_row:
                    first, last = group * 5, group * 5 + 3
                    style += [
                        ("BACKGROUND", (first, row + 1), (last, row + 1), TINT),
                        ("TEXTCOLOR", (first, row + 1), (last, row + 1), RED),
                        ("FONTNAME", (first, row + 1), (last, row + 1), FONT_BOLD),
                    ]
            else:
                line += [""] * 5
        data.append(line)
    widths = [w for _ in range(groups) for w in DEPTH_WIDTHS]
    # Пустой просвет между группами — левой рамкой каждой группы.
    for group in range(1, groups):
        style.append(("LINEBEFORE", (group * 5, 0), (group * 5, -1), 1.2, GRAPHITE))
    table = Table(data, colWidths=widths, rowHeights=[None] + [10.0] * rows_per_column, repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def _depth_page(page: DepthPage, first: bool, rows_per_column: int) -> list:
    story: list = []
    if first:
        story += [_p("1. Параметры бурения", "h2"), _params_table(page), Spacer(1, 4 * mm),
                  _p("2. Глубины скважин", "h2")]
    else:
        story.append(_p("2. Глубины скважин (продолжение)", "h2"))
    story += [
        _p("Глубина — проектная, с перебуром. Угол наклона и азимут — только для наклонных скважин. "
           "Первый ряд выделен. Графу «Факт» заполняет машинист.", "small"),
        # На странице продолжения — только занятые строки.
        Spacer(1, 1.5 * mm),
        _depth_table(page, rows_per_column if first else max(len(column) for column in page.columns)),
    ]
    if page.total:
        story += [Spacer(1, 1.5 * mm), _p(f"{page.total}. Координаты устьев — в ведомости маркшейдера.", "small")]
    if page.compiled_by is not None:
        sign = Table(
            [[_p("Паспорт составил:", "body"), "", _p(page.compiled_by, "body")],
             ["", _p("подпись", "small_c"), ""]],
            colWidths=[35 * mm, 45 * mm, FRAME_W - 80 * mm],
        )
        sign.setStyle(TableStyle([
            ("LINEBELOW", (1, 0), (1, 0), 0.6, GRAPHITE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (2, 0), (2, 0), 4 * mm), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("TOPPADDING", (0, 1), (-1, 1), 0),
        ]))
        story += [Spacer(1, 6 * mm), sign]
    return story


def _plan_page(layout: PassportLayout) -> list:
    """План расположения скважин (PR 3): поле плана и легенда с масштабом под ним."""

    sheet = layout.plan
    return [
        plan_drawing.drawing(sheet, font=FONT, bold_font=FONT_BOLD),
        Spacer(1, 2 * mm),
        plan_drawing.legend(sheet, FRAME_W, font=FONT, bold_font=FONT_BOLD),
    ]


# --- сборка ----------------------------------------------------------------

def _page_titles(layout: PassportLayout) -> list[str]:
    titles = ["", TITLE_SAFETY, TITLE_DEPTHS]
    titles += [TITLE_DEPTHS_MORE] * (len(layout.depth_pages) - 1)
    if layout.blank_before_plan:
        titles.append(TITLE_BLANK)
    titles.append(TITLE_PLAN)
    return titles


def draw_page_frame(
    canvas, *, page_w: float, page_h: float, margin_x: float, header: str, title: str, footer: str
) -> None:
    """Оформление листа документов паспорта: логотип, красная линия, справа
    шапка (серым, обрезается по ширине) и название листа, подвал по центру.
    Пустая шапка или название не рисуются. Общее для паспорта и ведомости."""

    canvas.saveState()
    logo = str(ASSETS / "logo.png")
    canvas.drawImage(logo, margin_x, page_h - 17 * mm, width=LOGO_W, height=LOGO_W * 738 / 2400, mask="auto")
    canvas.setStrokeColor(RED)
    canvas.setLineWidth(1.2)
    canvas.line(margin_x, page_h - 20 * mm, page_w - margin_x, page_h - 20 * mm)
    if header:
        canvas.setFillColor(GREY)
        canvas.setFont(FONT, 7.5)
        header_w = page_w - 2 * margin_x - LOGO_W - 8 * mm
        canvas.drawRightString(page_w - margin_x, page_h - 11.5 * mm, fit_text(header, FONT, 7.5, header_w))
    if title:
        canvas.setFillColor(GRAPHITE)
        canvas.setFont(FONT_BOLD, 8.5)
        canvas.drawRightString(page_w - margin_x, page_h - 16.5 * mm, title)
    canvas.setFillColor(GREY)
    canvas.setFont(FONT, 7)
    canvas.drawCentredString(page_w / 2, 8 * mm, footer)
    canvas.restoreState()


# Пометка PDF черновика (предпросмотр PR 6): на каждой странице по диагонали.
DRAFT_MARK = "ЧЕРНОВИК — не для работы"


def _draw_draft_mark(canvas) -> None:
    canvas.saveState()
    canvas.setFillColor(RED, alpha=0.18)
    canvas.setFont(FONT_BOLD, 40)
    canvas.translate(PAGE_W / 2, PAGE_H / 2)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, DRAFT_MARK)
    canvas.restoreState()


def _decorate(layout: PassportLayout, titles: list[str]):
    def on_page(canvas, _doc) -> None:
        number = canvas.getPageNumber()
        # Шапка и название — со стр. 2: на титуле их нет.
        title = titles[number - 1] if 1 < number <= len(titles) else ""
        draw_page_frame(
            canvas, page_w=PAGE_W, page_h=PAGE_H, margin_x=MARGIN_X,
            header=layout.header if number > 1 else "", title=title,
            footer=FOOTER.format(page=number, total=layout.page_count),
        )

    return on_page


def _fit(story: list) -> KeepInFrame:
    # Одна страница раскладки — одна страница PDF: длинный текст ужимается.
    return KeepInFrame(FRAME_W, FRAME_H, story, mode="shrink")


def render_layout_pdf(
    layout: PassportLayout, *, title: str, rows_per_column: int = 50, draft: bool = False
) -> bytes:
    _register_fonts()
    output = BytesIO()
    doc = BaseDocTemplate(
        output, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=TOP, bottomMargin=BOTTOM,
        title=title, author="BlastEX", subject="Паспорт на бурение", creator="BlastEX", producer="BlastEX",
        invariant=1,
    )
    frame = Frame(MARGIN_X, BOTTOM, FRAME_W, FRAME_H, id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    # Пометка черновика — после содержимого страницы (`onPageEnd`), иначе её
    # закрывают заливки таблиц и схема станка. У ревизии её нет — байты прежние.
    template = PageTemplate(id="page", frames=[frame], onPage=_decorate(layout, _page_titles(layout)))
    if draft:
        template.onPageEnd = lambda canvas, _doc: _draw_draft_mark(canvas)
    doc.addPageTemplates([template])
    pages = [_title_page(layout), _safety_page(layout)]
    pages += [_depth_page(page, index == 0, rows_per_column) for index, page in enumerate(layout.depth_pages)]
    if layout.blank_before_plan:
        pages.append([Spacer(1, FRAME_H / 2 - 10 * mm), _p("Страница оставлена пустой", "blank")])
    pages.append(_plan_page(layout))
    story: list = []
    for index, page in enumerate(pages):
        if index:
            story.append(PageBreak())
        story.append(_fit(page))
    doc.build(story)
    return output.getvalue()


def render_passport_pdf(
    context: Mapping[str, Any], *, revision_no: int | None = None, draft: bool = False
) -> bytes:
    """PDF паспорта на бурение из снимка ревизии (`drilling_passport_revisions.context`).

    `draft` — предпросмотр черновика (PR 6): на каждой странице пометка
    `DRAFT_MARK`; PDF ревизии строится без неё, байты прежние.
    """

    layout = build_layout(context)
    passport_no = str((context.get("passport") or {}).get("passport_no") or "")
    title = f"Паспорт на бурение № {passport_no}"
    if revision_no is not None:
        title += f", ревизия {revision_no}"
    elif draft:
        title += ", черновик"
    return render_layout_pdf(layout, title=title, draft=draft)
