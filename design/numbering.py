"""Нумерация скважин по позиции: после того как расположение зафиксировано.

Ряды группируются по оси блока (`row_azimuth_deg`): скважины одного ряда лежат на
одной линии вдоль оси. Порядок рядов — по направлению продвижения блока (для блока
без поворота — с запада на восток). Внутри ряда — с севера на юг, то есть по оси
ряда в сторону юга. Сетка: «1-01», «1-02», «2-01» …; стенки — P/K/B: «P1-01», «K1-01», «B1-01».
Ручные скважины (`source == "manual"`) id не меняют.
"""

from __future__ import annotations

from dataclasses import replace

from design.geometry import local_basis
from design.models import Hole

WALL_PREFIX = {"presplit": "P", "contour": "K", "buffer": "B"}


def _family(kind: str) -> str:
    return kind if kind in WALL_PREFIX else "grid"


def _id(family: str, row: int, col: int) -> str:
    prefix = "" if family == "grid" else WALL_PREFIX[family]
    return f"{prefix}{row + 1}-{col + 1:02d}"


def _bands(items: list[tuple[int, Hole]], advance: tuple[float, float], tolerance_m: float) -> list[list[tuple[int, Hole]]]:
    """Ряды: скважины с одинаковым положением поперёк оси (по направлению продвижения)."""
    def across(item: tuple[int, Hole]) -> float:
        hole = item[1]
        return hole.collar.x * advance[0] + hole.collar.y * advance[1]

    ordered = sorted(items, key=across)
    bands: list[list[tuple[int, Hole]]] = []
    for item in ordered:
        if bands and abs(across(bands[-1][-1]) - across(item)) <= tolerance_m:
            bands[-1].append(item)
        else:
            bands.append([item])
    return bands


def number_by_position(
    holes: list[Hole], tolerance_m: float = 1.0, row_azimuth_deg: float = 0.0
) -> list[Hole]:
    """Возвращает скважины с новыми id по расположению относительно оси блока.

    `row` и `col` не меняются: это техническая сетка от откоса, по ней считаются
    первый слой, стабилизация и тайминг. Нумерация своя у каждой группы (сетка,
    пресплит, контур, буфер). Порядок исходного списка сохраняется. Ручные
    скважины пропускаются.
    """
    row_dir, advance = local_basis(row_azimuth_deg)
    # Внутри ряда — к югу; у горизонтальной оси — к востоку (слева направо).
    dx, dy = row_dir
    if abs(dy) > 1e-9:
        along_dir = (dx, dy) if dy < 0 else (-dx, -dy)
    else:
        along_dir = (dx, dy) if dx > 0 else (-dx, -dy)
    south = along_dir

    result = list(holes)
    families: dict[str, list[tuple[int, Hole]]] = {}
    for index, hole in enumerate(holes):
        if hole.source != "manual":
            families.setdefault(_family(hole.kind), []).append((index, hole))

    for family, items in families.items():
        for row_index, band in enumerate(_bands(items, advance, tolerance_m)):
            along = lambda item: item[1].collar.x * south[0] + item[1].collar.y * south[1]  # noqa: E731
            for col_index, (index, hole) in enumerate(sorted(band, key=along)):
                result[index] = replace(hole, id=_id(family, row_index, col_index))
    return result
