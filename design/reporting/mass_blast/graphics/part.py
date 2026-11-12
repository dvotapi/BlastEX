"""Документ «Графика»: листы Г.1–Г.5 одной частью комплекта (TASK-018 §2, §4).

Порядок листов — по коду: Г.1 по блокам, Г.2 по блокам, …, Г.5 — один на
проект. A4 альбомный, шапка на каждом листе, название листа с масштабом —
по страницам. Масштабы и поворот считаются здесь же, до сборки (название
листа их печатает). В PDF с графикой — «печатать в фактическом размере»
(`actual_size`). Ревизия v2 без данных графики (выпущена до PR 4) графику
не печатает.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from reportlab.lib.units import mm
from reportlab.platypus import KeepInFrame, PageBreak, Table, TableStyle

from design.reporting.mass_blast.common import header_line, spacer, text
from design.reporting.mass_blast.frame import Part
from design.reporting.mass_blast.graphics import plans, profiles, situation
from design.reporting.mass_blast.graphics.sheet import FIELD_W_MM, MARGINS, signature

GRAPHICS_LABEL = "Графика"
SHEET_TITLES = {
    "G1": "Приложение Г.1. Схема расположения скважин (по маркшейдерской съёмке)",
    "G2": "Приложение Г.2. Поперечные профили через заряды",
    "G3": "Приложение Г.3. Схема заряжания, забойки и отвода оборудования",
    "G4": "Приложение Г.4. Схема взрывной сети с интервалами замедления",
    "G5": "Приложение Г.5. Ситуационный план: опасная зона, охраняемые объекты, посты охраны, взрывная станция",
}


def has_graphics(context: Mapping[str, Any]) -> bool:
    """Есть ли в ревизии данные графики (ревизии v2 до PR 4 их не имеют)."""

    blocks = context.get("blocks_v2") or []
    return bool(blocks) and isinstance(context.get("graphics"), Mapping) and all(
        isinstance(block.get("graphics"), Mapping) for block in blocks
    )


def graphics_sheet_counts(context: Mapping[str, Any]) -> dict[str, int]:
    """«Листов» у Г.1–Г.5 в «Составе проекта»: Г.1–Г.4 — по листу на блок, Г.5 — один."""

    if not has_graphics(context):
        return {}
    blocks = len(context.get("blocks_v2") or [])
    return {"G1": blocks, "G2": blocks, "G3": blocks, "G4": blocks, "G5": 1}


def _scale_text(scale: int) -> str:
    return f"М 1:{scale:,}".replace(",", " ")


def _block_suffix(context: Mapping[str, Any], index: int) -> str:
    blocks = context.get("blocks_v2") or []
    return f" · блок {text(blocks[index].get('code'))}" if len(blocks) > 1 else ""


def graphics_part(context: Mapping[str, Any]) -> Part | None:
    """Часть «Графика» или None, если данных графики в ревизии нет."""

    if not has_graphics(context):
        return None
    blocks = list(context.get("blocks_v2") or [])
    zones = context.get("zones") or {}
    sheets: list[tuple[str, Callable[[], list]]] = []

    def plan_sheet(code: str, index: int, build: Callable[..., tuple]) -> None:
        graphics = blocks[index]["graphics"]
        view = plans.block_view(graphics)
        title = f"{SHEET_TITLES[code]}, {_scale_text(view.scale)}{_block_suffix(context, index)}"

        def story() -> list:
            args = (graphics, view, zones) if code == "G3" else (graphics, view)
            field, legend = build(*args)
            return [field, spacer(0.5), legend, signature(context, surveyor=code == "G1")]

        sheets.append((title, story))

    for index in range(len(blocks)):
        plan_sheet("G1", index, plans.g1_drawings)
    for index in range(len(blocks)):
        sections = list(blocks[index]["graphics"].get("sections") or ())
        scale = profiles.profile_scale(sections)
        title = f"{SHEET_TITLES['G2']}, {_scale_text(scale)}{_block_suffix(context, index)}"

        def g2_story(sections=sections) -> list:
            drawings, legend, _scale = profiles.g2_drawings(sections)
            return [*drawings, *([spacer(profiles.PROFILE_H_MM)] * (2 - len(drawings))), spacer(0.5), legend,
                    signature(context, surveyor=False)]

        sheets.append((title, g2_story))
    for index in range(len(blocks)):
        plan_sheet("G3", index, plans.g3_drawings)
    for index in range(len(blocks)):
        plan_sheet("G4", index, plans.g4_drawings)
    view = situation.situation_view(context.get("graphics") or {})

    def g5_story() -> list:
        panel = KeepInFrame(situation.PANEL_W_MM * mm, situation.MAP_H_MM * mm, situation.panel(context), mode="shrink")
        table = Table([[situation.map_drawing(context, view), panel]],
                      colWidths=[situation.MAP_W_MM * mm, (FIELD_W_MM - situation.MAP_W_MM) * mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (1, 0), (1, 0), 4 * mm),
        ]))
        return [table, spacer(0.5), signature(context, surveyor=False)]

    sheets.append((f"{SHEET_TITLES['G5']}, {_scale_text(view.scale)}", g5_story))

    def story() -> list:
        result: list = []
        for index, (_title, build) in enumerate(sheets):
            if index:
                result.append(PageBreak())
            result += build()
        return result

    return Part(
        key="graphics",
        label=GRAPHICS_LABEL,
        title=sheets[0][0],
        header=header_line(context),
        story=story,
        landscape=True,
        header_pages="all",
        margins=MARGINS,
        page_titles=tuple(title for title, _build in sheets),
        actual_size=True,
        one_page_per_title=True,
    )


__all__ = ["GRAPHICS_LABEL", "SHEET_TITLES", "graphics_part", "graphics_sheet_counts", "has_graphics"]
