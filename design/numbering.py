"""Нумерация скважин по позиции: после того как расположение зафиксировано.

Основная сетка — по эшелонам (решение владельца 09.11.2026): эшелон — линия
скважин от бровки вглубь блока (`deep_dir`), эшелоны считаются с левого фланга,
если смотреть с откоса вглубь, внутри эшелона — от бровки к тылу. Сетка:
«1-01» — у бровки на левом фланге, «1-02» — следующая к тылу, «2-01» —
соседний эшелон у бровки.

Стенки и вспомогательные виды — со своим префиксом и прежней нумерацией по
рядам: ряд — линия вдоль оси блока (`row_azimuth_deg`), ряды — по направлению
продвижения, внутри ряда — с севера на юг. P (пресплит), K (контур), B (буфер),
T (подрезка), SAT (сателлиты), S (стабилизация), I (инфилл). Префикс делает id
уникальным между группами.
Наклонная у откоса (пара) своего номера не получает: номер её вертикальной с
суффиксом «T» (`5-08T`). Ручные скважины (`source == "manual"`) id не меняют.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from design.geometry import local_basis
from design.models import FACE_PAIR_ID_SUFFIX, FACE_TOE_KIND, Hole, face_pair_partner_id

PREFIX = {
    "presplit": "P",
    "contour": "K",
    "buffer": "B",
    "trim": "T",
    "satellite": "SAT",
    "stab": "S",
    "infill": "I",
}


def _family(kind: str) -> str:
    return kind if kind in PREFIX else "grid"


def _id(family: str, row: int, col: int) -> str:
    prefix = "" if family == "grid" else PREFIX[family]
    return f"{prefix}{row + 1}-{col + 1:02d}"


def _bands(
    items: list[tuple[int, Hole]],
    advance: tuple[float, float],
    tolerance_m: float,
    xy: Callable[[tuple[int, Hole]], tuple[float, float]],
) -> list[list[tuple[int, Hole]]]:
    """Ряды: скважины с одинаковым положением поперёк оси (по направлению продвижения)."""
    def across(item: tuple[int, Hole]) -> float:
        x, y = xy(item)
        return x * advance[0] + y * advance[1]

    ordered = sorted(items, key=across)
    bands: list[list[tuple[int, Hole]]] = []
    for item in ordered:
        if bands and abs(across(bands[-1][-1]) - across(item)) <= tolerance_m:
            bands[-1].append(item)
        else:
            bands.append([item])
    return bands


def number_by_position(
    holes: list[Hole],
    tolerance_m: float = 0.05,
    row_azimuth_deg: float = 0.0,
    positions: list[tuple[float, float] | None] | None = None,
    partners: list[int | None] | None = None,
    deep_dir: tuple[float, float] | None = None,
) -> list[Hole]:
    """Возвращает скважины с новыми id по расположению относительно оси блока.

    `deep_dir` — направление от бровки вглубь блока (у генератора — продвижение
    рядов после `pattern_origin`); None — продвижение по оси ряда
    (`local_basis`). Эшелоны основной сетки — полосы вдоль него, слева направо,
    если смотреть вдоль него.

    Допуск — 5 см: скважины одного ряда совпадают по положению поперёк оси до
    погрешности вычислений, а соседние ряды отстоят на burden (от 1 м и выше).

    `row` и `col` не меняются: это техническая сетка от откоса, по ней считаются
    первый слой, стабилизация и тайминг. Нумерация своя у каждой группы (сетка,
    пресплит, контур, буфер). Порядок исходного списка сохраняется. Ручные
    скважины пропускаются.

    `positions` — положение для нумерации вместо устья (по индексу скважины,
    None — устье): у плавного перехода устья рядов за наклонными сдвинуты к
    откосу, и ряды нумеруются по месту в сетке до сдвига.

    `partners` — у пары у откоса индекс её вертикальной (None — не пара).
    Без него вертикальная ищется по прежнему номеру пары без «T». Пара
    получает новый номер вертикальной с «T»; пара без вертикальной номер
    не меняет.
    """

    def xy(item: tuple[int, Hole]) -> tuple[float, float]:
        index, hole = item
        own = positions[index] if positions is not None else None
        return own if own is not None else (hole.collar.x, hole.collar.y)

    row_dir, advance = local_basis(row_azimuth_deg)
    # Внутри ряда — к югу; у горизонтальной оси — к востоку (слева направо).
    dx, dy = row_dir
    if abs(dy) > 1e-9:
        along_dir = (dx, dy) if dy < 0 else (-dx, -dy)
    else:
        along_dir = (dx, dy) if dx > 0 else (-dx, -dy)
    south = along_dir

    if partners is None:
        by_id = {hole.id: index for index, hole in enumerate(holes) if hole.kind != FACE_TOE_KIND}
        partners = [
            by_id.get(partner) if (partner := face_pair_partner_id(hole)) is not None else None for hole in holes
        ]

    result = list(holes)
    families: dict[str, list[tuple[int, Hole]]] = {}
    pairs: list[tuple[int, int]] = []
    for index, hole in enumerate(holes):
        if hole.source == "manual":
            continue
        if hole.kind == FACE_TOE_KIND:
            if partners[index] is not None:
                pairs.append((index, partners[index]))
            continue
        families.setdefault(_family(hole.kind), []).append((index, hole))

    deep = deep_dir if deep_dir is not None else advance
    # Вправо, если смотреть вглубь: deep, повёрнутый на −90°.
    right = (deep[1], -deep[0])
    for family, items in families.items():
        if family == "grid":
            # Эшелоны — полосы вдоль deep, слева направо; внутри — от бровки.
            for echelon_index, band in enumerate(_bands(items, right, tolerance_m, xy)):
                depth = lambda item: xy(item)[0] * deep[0] + xy(item)[1] * deep[1]  # noqa: E731
                for place, (index, hole) in enumerate(sorted(band, key=depth)):
                    result[index] = replace(hole, id=_id(family, echelon_index, place))
            continue
        for row_index, band in enumerate(_bands(items, advance, tolerance_m, xy)):
            along = lambda item: xy(item)[0] * south[0] + xy(item)[1] * south[1]  # noqa: E731
            for col_index, (index, hole) in enumerate(sorted(band, key=along)):
                result[index] = replace(hole, id=_id(family, row_index, col_index))
    for index, partner in pairs:
        result[index] = replace(holes[index], id=result[partner].id + FACE_PAIR_ID_SUFFIX)
    return result
