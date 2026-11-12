"""Сборка PDF из документов: шапка, подвал, двусторонняя печать (логика `duplex_mv.py`).

Документ (`Part`) — фабрика содержимого и оформление страниц. Сборка идёт в два
шага: сначала каждый документ раскладывается отдельно (ReportLab повторяем,
число страниц известно), затем всё собирается одним проходом с пустыми
оборотами и номерами страниц. Данные при этом не пересчитываются.

Правила комплекта (TASK-018 §2, эталон v0.11):
- каждый документ начинается с лицевой: после документа с нечётным числом
  страниц — пустой оборот «Страница оставлена пустой» с подвалом документа;
- документы проекта (`numbering="project"`) — сквозная «Стр. N из M» с учётом
  пустых оборотов; документы дня взрыва (`"own"`) — у каждого своя, пустой
  оборот — без номера.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Callable, Sequence

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate, Spacer

from design.reporting.brand import (
    FONT,
    FONT_BOLD,
    GREY,
    LOGO,
    ORGANIZATION,
    RED,
    register_fonts,
)
from design.reporting.brand import draw_header as draw_brand_header

DRAFT_MARK = "ЧЕРНОВИК — не для работы"
BLANK_TEXT = "Страница оставлена пустой"
FOOTER_LEFT = f"{ORGANIZATION} · Проект массового взрыва · {{label}}"
HEADER_H = 22 * mm        # логотип, шапка, название листа, красная линия
FOOTER_Y = 8 * mm


@dataclass(frozen=True)
class Margins:
    left: float = 15 * mm
    right: float = 15 * mm
    top: float = 10 * mm          # сверху на страницах без шапки
    bottom: float = 13 * mm


@dataclass
class Part:
    """Один документ комплекта.

    `story` — фабрика содержимого (ReportLab расходует flowables при сборке,
    поэтому их строят заново на каждый проход). `header_pages` — на каких
    страницах документа рисовать шапку с логотипом: `"first"` — только на
    первой (как в эталоне: на продолжениях таблица занимает весь лист),
    `"all"` — на каждой, `"none"` — нигде (бланк формы 4: наряд-путёвка).
    """

    key: str
    label: str
    title: str
    story: Callable[[], list]
    header: str = ""
    numbering: str = "project"
    landscape: bool = False
    header_pages: str = "first"
    margins: Margins = field(default_factory=Margins)
    page_titles: tuple[str, ...] | None = None    # название листа по страницам (иначе `title`)
    page_headers: tuple[str, ...] | None = None   # шапка по страницам (иначе `header`)
    draw_extra: Callable | None = None   # (canvas, part, logo, page_index) — поверх страницы
    # Чертёж в масштабе (графика Г.1–Г.5): PDF просит просмотрщик печатать в
    # фактическом размере (`/PrintScaling /None`), а не «вписать в страницу».
    actual_size: bool = False
    # Страница = лист с названием из `page_titles` (графика): иное число
    # страниц — ошибка раскладки, а не перенос листа на следующую страницу.
    one_page_per_title: bool = False

    @property
    def pagesize(self) -> tuple[float, float]:
        return landscape(A4) if self.landscape else A4


def _logo() -> ImageReader:
    # Картинка из байтов: имя XObject в PDF — по содержимому, а не по пути к
    # файлу, поэтому байты документа не зависят от каталога установки.
    return ImageReader(io.BytesIO(LOGO.read_bytes()))


def _frames(part: Part) -> tuple[Frame, Frame]:
    page_w, page_h = part.pagesize
    m = part.margins
    width = page_w - m.left - m.right
    first = Frame(m.left, m.bottom, width, page_h - HEADER_H - 3 * mm - m.bottom, id="first",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    top = HEADER_H + 3 * mm if part.header_pages == "all" else m.top
    if part.header_pages == "none":
        first = Frame(m.left, m.bottom, width, page_h - m.top - m.bottom, id="first",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    rest = Frame(m.left, m.bottom, width, page_h - top - m.bottom, id="rest",
                 leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    return first, rest


def frame_width(part_landscape: bool = False, margins: Margins | None = None) -> float:
    margins = margins or Margins()
    page_w = (landscape(A4) if part_landscape else A4)[0]
    return page_w - margins.left - margins.right


def _per_page(values: tuple[str, ...] | None, default: str, page: int) -> str:
    if not values:
        return default
    return values[min(page, len(values) - 1)]


def _draw_header(canvas, part: Part, logo: ImageReader, page: int, *, top: float | None = None,
                 header: str | None = None, title: str | None = None) -> None:
    page_w, page_h = part.pagesize
    draw_brand_header(
        canvas, page_w=page_w, page_h=page_h if top is None else top, margin_x=part.margins.left,
        margin_right=part.margins.right, logo=logo,
        header=_per_page(part.page_headers, part.header, page) if header is None else header,
        title=_per_page(part.page_titles, part.title, page) if title is None else title,
    )


def _draw_footer(canvas, part: Part, number: str, *, blank: bool) -> None:
    page_w, _ = part.pagesize
    canvas.setFillColor(GREY)
    canvas.setFont(FONT, 7)
    if number:
        canvas.drawRightString(page_w - part.margins.right, FOOTER_Y, number)
    if blank:
        canvas.drawString(part.margins.left, FOOTER_Y, FOOTER_LEFT.format(label=part.label))


def _draw_blank(canvas, part: Part) -> None:
    page_w, page_h = part.pagesize
    canvas.setFillColor(GREY)
    canvas.setFont(FONT, 10)
    canvas.drawCentredString(page_w / 2, page_h / 2, BLANK_TEXT)


def _draw_draft(canvas, part: Part) -> None:
    page_w, page_h = part.pagesize
    canvas.saveState()
    canvas.setFillColor(RED, alpha=0.18)
    canvas.setFont(FONT_BOLD, 40)
    canvas.translate(page_w / 2, page_h / 2)
    canvas.rotate(35 if not part.landscape else 20)
    canvas.drawCentredString(0, 0, DRAFT_MARK)
    canvas.restoreState()


def _document(buffer: io.BytesIO, title: str) -> BaseDocTemplate:
    return BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
        title=title, author="BlastEX", subject="Проект массового взрыва", creator="BlastEX", producer="BlastEX",
        invariant=1,
    )


def _templates(index: int, part: Part, on_page: Callable, on_page_end: Callable) -> list[PageTemplate]:
    first, rest = _frames(part)
    return [
        PageTemplate(id=f"F{index}", frames=[first], pagesize=part.pagesize, onPage=on_page, onPageEnd=on_page_end,
                     autoNextPageTemplate=f"R{index}"),
        PageTemplate(id=f"R{index}", frames=[rest], pagesize=part.pagesize, onPage=on_page, onPageEnd=on_page_end),
        PageTemplate(id=f"B{index}", frames=[rest], pagesize=part.pagesize, onPage=on_page, onPageEnd=on_page_end),
    ]


def count_pages(part: Part) -> int:
    """Число страниц документа (раскладка без подвала — от номеров она не зависит).

    Запоминается в самой части: комплект раскладывает документ один раз."""

    cached = getattr(part, "_page_count", None)
    if cached is not None:
        return cached
    register_fonts()
    buffer = io.BytesIO()
    doc = _document(buffer, part.label)
    doc.addPageTemplates(_templates(0, part, lambda c, d: None, lambda c, d: None))
    doc.build(list(part.story()))
    if part.one_page_per_title and doc.page != len(part.page_titles or ()):
        raise RuntimeError(
            f"«{part.label}»: {doc.page} стр. на {len(part.page_titles or ())} листов — лист не поместился на страницу."
        )
    part._page_count = doc.page
    return doc.page


@dataclass(frozen=True)
class PageSlot:
    part: int
    page: int | None        # None — пустой оборот
    number: str


def plan_pages(parts: Sequence[Part], counts: Sequence[int], *, duplex: bool) -> list[PageSlot]:
    """Порядок страниц и их номера (без отрисовки — проверяется тестами)."""

    raw: list[tuple[int, int | None]] = []
    for index, count in enumerate(counts):
        raw += [(index, page) for page in range(count)]
        if duplex and count % 2:
            raw.append((index, None))
    project = [k for k, (index, _page) in enumerate(raw) if parts[index].numbering == "project"]
    numbers: dict[int, str] = {k: f"Стр. {n} из {len(project)}" for n, k in enumerate(project, start=1)}
    # Своя нумерация — у каждого документа (`"own"`); части одного документа
    # слоя (`"group:<ключ>"`, исполнительная таблица и Г.1 слоя «Факт») — общая.
    groups: dict[str, list[int]] = {}
    for index, part in enumerate(parts):
        if part.numbering == "project":
            continue
        key = part.numbering if part.numbering.startswith("group:") else f"own:{index}"
        groups.setdefault(key, []).append(index)
    for members in groups.values():
        own = [k for k, (i, page) in enumerate(raw) if i in members and page is not None]
        numbers.update({k: f"Стр. {n} из {len(own)}" for n, k in enumerate(own, start=1)})
        numbers.update({k: "" for k, (i, page) in enumerate(raw) if i in members and page is None})
    return [PageSlot(index, page, numbers[k]) for k, (index, page) in enumerate(raw)]


def render(parts: Sequence[Part], *, title: str, duplex: bool, draft: bool = False) -> bytes:
    """PDF из документов `parts` подряд (с пустыми оборотами при `duplex`)."""

    if not parts:
        raise ValueError("Нет документов для печати.")
    register_fonts()
    counts = [count_pages(part) for part in parts]
    slots = plan_pages(parts, counts, duplex=duplex)
    logo = _logo()

    actual_size = any(part.actual_size for part in parts)

    def on_page(canvas, _doc) -> None:
        if actual_size and canvas.getPageNumber() == 1:
            canvas.setViewerPreference("PrintScaling", "None")
        slot = slots[canvas.getPageNumber() - 1]
        part = parts[slot.part]
        canvas.saveState()
        if slot.page is None:
            _draw_blank(canvas, part)
        elif part.header_pages != "none" and (slot.page == 0 or part.header_pages == "all"):
            _draw_header(canvas, part, logo, slot.page)
        _draw_footer(canvas, part, slot.number, blank=slot.page is None)
        canvas.restoreState()

    def on_page_end(canvas, _doc) -> None:
        slot = slots[canvas.getPageNumber() - 1]
        part = parts[slot.part]
        if part.draw_extra is not None and slot.page is not None:
            canvas.saveState()
            part.draw_extra(canvas, part, logo, slot.page)
            canvas.restoreState()
        if draft:
            _draw_draft(canvas, part)

    buffer = io.BytesIO()
    doc = _document(buffer, title)
    templates: list[PageTemplate] = []
    for index, part in enumerate(parts):
        templates += _templates(index, part, on_page, on_page_end)
    doc.addPageTemplates(templates)
    story: list = []
    for index, part in enumerate(parts):
        if index:
            story += [NextPageTemplate(f"F{index}"), PageBreak()]
        story += list(part.story())
        if duplex and counts[index] % 2:
            story += [NextPageTemplate(f"B{index}"), PageBreak(), Spacer(1, 1)]
    doc.build(story)
    data = buffer.getvalue()
    if doc.page != len(slots):  # pragma: no cover — раскладка повторяема, это страховка
        raise RuntimeError(f"Страниц {doc.page}, а по раскладке {len(slots)}: документы разошлись при сборке.")
    return data


# Шапка листа с заданной верхней кромкой (вторая половина талона-допуска).
draw_header = _draw_header
