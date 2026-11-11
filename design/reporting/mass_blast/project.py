"""Документы 1–4 проекта МВ по контексту ревизии v2: части комплекта и PDF.

`project_parts` — титул (с оборотом «Состав проекта»), техрасчёт и таблица
параметров по каждому блоку, распорядок. «Листов» в «Составе проекта» —
число страниц документа без пустых оборотов (решение владельца 11.11.2026,
В7); у графики Г.1–Г.5 до PR 4 — «—».
"""
from __future__ import annotations

from typing import Any, Mapping

from design.reporting.mass_blast import frame
from design.reporting.mass_blast.common import header_line, text
from design.reporting.mass_blast.frame import Margins, Part
from design.reporting.mass_blast.param_table import MARGINS as TABLE_MARGINS
from design.reporting.mass_blast.param_table import table_story
from design.reporting.mass_blast.schedule import schedule_story
from design.reporting.mass_blast.techcalc import techcalc_story
from design.reporting.mass_blast.title import draw_title_page, title_story

DOCUMENTS = ("title", "technical-calculation", "parameter-table", "schedule")
TITLE_LABEL = "Титул"
TECHCALC_TITLE = "Технический расчёт массового взрыва (приложение № 10 к ФНП 494)"
TABLE_TITLE = "Таблица параметров взрывных работ (приложение № 11 к ФНП 494)"
SCHEDULE_TITLE = "Распорядок проведения массового взрыва (приложение № 12 к ФНП 494)"


def _block_suffix(context: Mapping[str, Any], index: int) -> str:
    blocks = context.get("blocks_v2") or []
    if len(blocks) < 2:
        return ""
    return f" · блок {text(blocks[index].get('code'))}"


def project_parts(context: Mapping[str, Any], documents: tuple[str, ...] = DOCUMENTS) -> list[Part]:
    """Части документов проекта в порядке комплекта (TASK-018 §2)."""

    header = header_line(context)
    width = frame.frame_width()
    table_width = frame.frame_width(margins=TABLE_MARGINS)
    blocks = range(len(context.get("blocks_v2") or []))
    techcalc = [
        Part(key=f"techcalc:{i}", label="Технический расчёт" + _block_suffix(context, i), title=TECHCALC_TITLE,
             header=header, story=lambda i=i: techcalc_story(context, i, width))
        for i in blocks
    ]
    tables = [
        Part(key=f"table:{i}", label="Таблица параметров" + _block_suffix(context, i), title=TABLE_TITLE,
             header=header, story=lambda i=i: table_story(context, i, table_width), margins=TABLE_MARGINS)
        for i in blocks
    ]
    schedule = Part(key="schedule", label="Распорядок", title=SCHEDULE_TITLE, header=header,
                    story=lambda: schedule_story(context, width))
    # «Листов» в составе проекта — по раскладке самих документов; считаются,
    # только когда титул печатается (раскладка запоминается в части).
    counts: dict[str, int | None] = {}
    if "title" in documents:
        counts = {
            "techcalc": sum(frame.count_pages(part) for part in techcalc) or None,
            "table": sum(frame.count_pages(part) for part in tables) or None,
            "schedule": frame.count_pages(schedule),
        }
    title = Part(
        key="title", label=TITLE_LABEL, title="", header="", story=lambda: title_story(context, width, counts),
        header_pages="all", page_titles=("", "Состав проекта"), page_headers=("", header),
        draw_extra=lambda canvas, part, _logo, page: draw_title_page(canvas, context, *part.pagesize) if page == 0 else None,
    )
    selected: list[Part] = []
    if "title" in documents:
        selected.append(title)
    if "technical-calculation" in documents:
        selected += techcalc
    if "parameter-table" in documents:
        selected += tables
    if "schedule" in documents:
        selected.append(schedule)
    return selected


def _pdf_title(context: Mapping[str, Any], what: str) -> str:
    number = text((context.get("requisites") or {}).get("project_no"))
    return f"{what}" + (f" — проект МВ № {number}" if number else "")


def render_project_document(context: Mapping[str, Any], document: str, *, draft: bool = False) -> bytes:
    """Один документ проекта (`DOCUMENTS`) или весь проект (`project`, двусторонне)."""

    if document == "project":
        return frame.render(project_parts(context), title=_pdf_title(context, "Проект массового взрыва"),
                            duplex=True, draft=draft)
    if document not in DOCUMENTS:
        raise ValueError(f"Неизвестный документ проекта МВ: {document}.")
    parts = project_parts(context, (document,))
    return frame.render(parts, title=_pdf_title(context, parts[0].label), duplex=False, draft=draft)


__all__ = ["DOCUMENTS", "Margins", "project_parts", "render_project_document"]
