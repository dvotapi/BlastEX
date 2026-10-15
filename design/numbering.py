"""Нумерация скважин по позиции: после того как расположение зафиксировано.

Основная сетка — ряды сверху вниз по карте (с севера на юг), внутри ряда слева
направо (с запада на восток): «1-01», «1-02», «2-01» …
Пресплит, контур и буфер нумеруются отдельно буквами P, K, B: «P1-01», «K1-01», «B1-01».
Ручные скважины (`source == "manual"`) номера не меняют — у них свой идентификатор.
"""

from __future__ import annotations

from dataclasses import replace

from design.models import Hole

WALL_PREFIX = {"presplit": "P", "contour": "K", "buffer": "B"}


def _family(kind: str) -> str:
    return kind if kind in WALL_PREFIX else "grid"


def _id(family: str, row: int, col: int) -> str:
    prefix = "" if family == "grid" else WALL_PREFIX[family]
    return f"{prefix}{row + 1}-{col + 1:02d}"


def _bands(items: list[tuple[int, Hole]], tolerance_m: float) -> list[list[tuple[int, Hole]]]:
    """Ряды: скважины, отстоящие по Y не дальше tolerance_m от соседней, — одна полоса.

    Полосы идут с севера (большой Y) на юг.
    """
    ordered = sorted(items, key=lambda item: -item[1].collar.y)
    bands: list[list[tuple[int, Hole]]] = []
    for item in ordered:
        if bands and abs(bands[-1][-1][1].collar.y - item[1].collar.y) <= tolerance_m:
            bands[-1].append(item)
        else:
            bands.append([item])
    return bands


def number_by_position(holes: list[Hole], tolerance_m: float = 1.0) -> list[Hole]:
    """Возвращает скважины с новыми id по расположению.

    `row` и `col` не меняются: это техническая сетка от откоса, по ней считаются
    первый слой, стабилизация и тайминг. Нумерация своя у каждой группы (сетка,
    пресплит, контур, буфер). Порядок исходного списка сохраняется. Ручные
    скважины пропускаются.
    """
    result = list(holes)
    families: dict[str, list[tuple[int, Hole]]] = {}
    for index, hole in enumerate(holes):
        if hole.source != "manual":
            families.setdefault(_family(hole.kind), []).append((index, hole))

    for family, items in families.items():
        for row_index, band in enumerate(_bands(items, tolerance_m)):
            for col_index, (index, hole) in enumerate(sorted(band, key=lambda item: item[1].collar.x)):
                result[index] = replace(hole, id=_id(family, row_index, col_index))
    return result
