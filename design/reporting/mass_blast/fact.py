"""Документ 11 — слой «Факт» (TASK-018, PR 5): исполнительная таблица параметров и Г.1 по съёмке.

Источник — только ревизия слоя: `seed.blocks_fact` (строки Р ревизии проекта
с графами Ф, геометрия плана Г.1 ревизии проекта и точки скважин по съёмке) и
`view` (отказы и примечания по факту, дата и время взрыва по факту). Таблица —
тот же рендер, что у проекта (`param_table.table_story(..., fact=...)`), Г.1 —
тот же лист, что в «Графике» (`plans.g1_drawings`): скважины по съёмке, без
съёмки — серыми по проекту. Две части — один документ со своей нумерацией.
"""
from __future__ import annotations

from typing import Any, Mapping

from reportlab.platypus import PageBreak

from design.reporting.mass_blast import frame
from design.reporting.mass_blast.common import spacer, text
from design.reporting.mass_blast.frame import Part
from design.reporting.mass_blast.graphics import plans
from design.reporting.mass_blast.graphics.sheet import MARGINS as SHEET_MARGINS
from design.reporting.mass_blast.graphics.sheet import signature
from design.reporting.mass_blast.param_table import MARGINS as TABLE_MARGINS
from design.reporting.mass_blast.param_table import table_story

FACT_LABEL = "Таблица параметров (исполнительная)"
FACT_TABLE_TITLE = "Таблица параметров взрывных работ — исполнительная (приложение № 11 к ФНП 494, п. 412)"
FACT_G1_TITLE = "Приложение Г.1. Схема расположения скважин по исполнительной съёмке"
NUMBERING = "group:EXECUTION"


def _blocks(revision: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    view = revision.get("view") or {}
    return list(view.get("blocks") or (revision.get("seed") or {}).get("blocks_fact") or [])


def fact_context(revision: Mapping[str, Any]) -> dict[str, Any]:
    """Ревизия слоя в виде, который читают таблица и лист Г.1 проекта."""

    seed = revision.get("seed") or {}
    blocks = []
    for block in _blocks(revision):
        summary = block.get("summary") or {}
        consumption = [{"kind": "explosive", "name": name} for name in summary.get("explosives") or []]
        consumption += [{"kind": "primer", "name": name} for name in summary.get("primers") or []]
        blocks.append(
            {
                "code": block.get("code", ""),
                "horizon": block.get("horizon", ""),
                "parameter_table": block.get("parameter_table") or {},
                "consumption": consumption,
                "technical_calculation": [{"number": "4", "p_kg_m": summary.get("p_kg_m")}],
                "safety": {"params": {"hardness_f": summary.get("hardness_f")}},
                "graphics": block.get("graphics"),
            }
        )
    return {
        "project": dict(seed.get("project") or {}),
        "requisites": dict(seed.get("requisites") or {}),
        "blocks": [{"code": b["code"], "horizon": b["horizon"]} for b in blocks],
        "blocks_v2": blocks,
    }


def _suffix(context: Mapping[str, Any], index: int) -> str:
    blocks = context.get("blocks_v2") or []
    return f" · блок {text(blocks[index].get('code'))}" if len(blocks) > 1 else ""


def fact_parts(revision: Mapping[str, Any], header: str) -> list[Part]:
    """Исполнительные таблицы по блокам (книжные) и Г.1 по съёмке (альбомные)."""

    context = fact_context(revision)
    view = revision.get("view") or {}
    fact = {"blast_date": view.get("blast_date", ""), "blast_time": view.get("blast_time", "")}
    width = frame.frame_width(False, TABLE_MARGINS)
    parts = [
        Part(key=f"layer:EXECUTION:table:{i}", label=FACT_LABEL + _suffix(context, i), title=FACT_TABLE_TITLE,
             header=header, story=lambda i=i: table_story(context, i, width, fact=fact), numbering=NUMBERING,
             margins=TABLE_MARGINS)
        for i in range(len(context["blocks_v2"]))
    ]
    sheets = []
    for index, block in enumerate(context["blocks_v2"]):
        graphics = block.get("graphics")
        if not graphics or not graphics.get("holes"):
            continue
        view_ = plans.block_view(graphics)
        title = f"{FACT_G1_TITLE}, М 1:{view_.scale:,}".replace(",", " ") + _suffix(context, index)

        def story(graphics=graphics, view_=view_) -> list:
            field, legend = plans.g1_drawings(graphics, view_)
            return [field, spacer(0.5), legend, signature(context, surveyor=True)]

        sheets.append((title, story))
    if sheets:
        def g1_story() -> list:
            result: list = []
            for number, (_title, build) in enumerate(sheets):
                if number:
                    result.append(PageBreak())
                result += build()
            return result

        parts.append(Part(
            key="layer:EXECUTION:g1", label=FACT_LABEL, title=sheets[0][0], header=header, story=g1_story,
            numbering=NUMBERING, landscape=True, header_pages="all", margins=SHEET_MARGINS,
            page_titles=tuple(title for title, _build in sheets), actual_size=True, one_page_per_title=True,
        ))
    return parts


__all__ = ["FACT_LABEL", "fact_context", "fact_parts"]
