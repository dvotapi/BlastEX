"""Монтаж «магистраль + цепочки» для неэлектрической системы (СИНВ).

Вруб — крайняя голова столбца у выбранного фланга первого ряда. От него по
головам столбцов идёт магистраль (25 мс между соседними головами), от каждой
головы назад по рядам — цепочка (42 мс к скважине следующего ряда).

Член столбца — скважина семейства сетки, кроме стабилизации, сателлитов и
наклонной у откоса. Голова — член, у которого в предыдущем логическом ряду нет
скважины ближе 0,75·a по оси ряда; на ступенчатой бровке головы лежат в разных
рядах решётки, и магистраль идёт по ним, а не по ряду 1. Пара у откоса
(`face_toe`) получает копию входящей связи своей вертикальной. Прочие скважины
(стенки, стабилизация, сателлиты, ручные вне столбцов) привязываются связью
цепочки к ближайшей уже привязанной.

Модуль не строит `InitiationNetwork`: он отдаёт граф связей и времена
поверхностной сети от вруба (`TrunkPlan`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from design.models import FACE_TOE_KIND, Hole, face_pair_partner_id, logical_row, row_family
from design.timing import SURFACE_NSI_MS_OPTIONS, _snap

TRUNK_SCHEME = "trunk_chains"
DOWNHOLE_CHOICES_MS = (500.0, 700.0, 1000.0)

# Не члены столбцов: короткие вставки и пара у откоса (как в темпе отбойки).
_NON_COLUMN_KINDS = frozenset({"stab", "satellite", FACE_TOE_KIND})
# Предшественник в цепочке — не дальше этой доли шага a по оси ряда: на
# шахматной сетке (смещение a/2) это ближайший по диагонали.
_CHAIN_OFFSET_FACTOR = 0.75

Vec = tuple[float, float]


@dataclass(frozen=True)
class TrunkPlan:
    """Граф монтажа: стартовые скважины, связи (откуда, куда, мс), времена от вруба."""

    starters: list[str]
    ties: list[tuple[str, str, float]]
    surface_ms: dict[str, float]
    warnings: list[str] = field(default_factory=list)


def _is_column_member(hole: Hole) -> bool:
    return row_family(hole.kind) == "grid" and hole.kind not in _NON_COLUMN_KINDS


def _xy(holes: list[Hole]) -> np.ndarray:
    return np.array([[h.collar.x, h.collar.y] for h in holes], dtype=float).reshape(-1, 2)


def _principal_axis(points: np.ndarray) -> np.ndarray | None:
    """Главная ось устьев (SVD центрированных координат); None — разброса нет."""
    if len(points) < 2:
        return None
    centered = points - points.mean(axis=0)
    _, s, vt = np.linalg.svd(centered, full_matrices=False)
    if s[0] <= 1e-9:
        return None
    return vt[0]


def row_axis(holes: list[Hole]) -> tuple[Vec, Vec]:
    """(ось ряда, направление «от откоса вглубь») — единичные векторы.

    Вглубь — ось, повёрнутая на +90°: наименьшая проекция на ось — левый фланг,
    если смотреть с откоса вглубь блока.
    """
    members = [h for h in holes if _is_column_member(h)] or list(holes)
    groups: dict[int, list[Hole]] = {}
    for h in members:
        groups.setdefault(logical_row(h.row), []).append(h)
    total = np.zeros(2)
    reference: np.ndarray | None = None
    for row in sorted(groups):
        group = groups[row]
        axis = _principal_axis(_xy(group))
        if axis is None:
            continue
        if reference is None:
            reference = axis
        elif float(axis @ reference) < 0:
            axis = -axis
        total += axis * len(group)
    if float(np.hypot(*total)) <= 1e-9:
        total = _principal_axis(_xy(members))
        if total is None:
            total = np.array([1.0, 0.0])
    axis = total / float(np.hypot(*total))
    deep = np.array([-axis[1], axis[0]])
    # Знак «вглубь» — по росту логического ряда; при одной строке — любой.
    if members:
        rows = np.array([logical_row(h.row) for h in members], dtype=float)
        proj = _xy(members) @ deep
        if float(((proj - proj.mean()) * (rows - rows.mean())).sum()) < 0:
            axis, deep = -axis, -deep
    return (float(axis[0]), float(axis[1])), (float(deep[0]), float(deep[1]))


def _row_step(rows: dict[int, list[tuple[float, Hole]]]) -> float:
    """Шаг ряда a — медиана расстояний между соседними по оси скважинами ряда."""
    gaps: list[float] = []
    for items in rows.values():
        for (_, a), (_, b) in zip(items, items[1:]):
            gaps.append(math.hypot(a.collar.x - b.collar.x, a.collar.y - b.collar.y))
    return float(np.median(gaps)) if gaps else math.inf


def _nsi_step(value: float, label: str, warnings: list[str]) -> float:
    snapped = float(_snap(float(value), SURFACE_NSI_MS_OPTIONS))
    if abs(snapped - float(value)) > 1e-9:
        warnings.append(f"Замедление {label} {value:g} мс заменено ближайшим из НСИ: {snapped:g} мс.")
    return snapped


def plan_trunk_chains(
    holes: list[Hole],
    *,
    trunk_ms: float = 25.0,
    chain_ms: float = 42.0,
    cut_flank: str = "left",
) -> TrunkPlan:
    """Граф «магистраль + цепочки» по уже отфильтрованным скважинам."""
    warnings: list[str] = []
    trunk = _nsi_step(trunk_ms, "магистрали", warnings)
    chain = _nsi_step(chain_ms, "цепочки", warnings)
    if not holes:
        return TrunkPlan(starters=[], ties=[], surface_ms={}, warnings=warnings)

    by_id = {h.id: h for h in holes}
    (ax, ay), _ = row_axis(holes)

    def along(h: Hole) -> float:
        return h.collar.x * ax + h.collar.y * ay

    members = [h for h in holes if _is_column_member(h)]
    pairs = [h for h in holes if h.kind == FACE_TOE_KIND and face_pair_partner_id(h) in by_id
             and _is_column_member(by_id[face_pair_partner_id(h)])]
    pair_ids = {h.id for h in pairs}
    member_ids = {h.id for h in members}
    others = [h for h in holes if h.id not in member_ids and h.id not in pair_ids]

    rows: dict[int, list[tuple[float, Hole]]] = {}
    for h in members:
        rows.setdefault(logical_row(h.row), []).append((along(h), h))
    for items in rows.values():
        items.sort(key=lambda item: (item[0], item[1].id))
    limit = _CHAIN_OFFSET_FACTOR * _row_step(rows)

    incoming: dict[str, tuple[str, float]] = {}
    heads: list[tuple[float, Hole]] = []
    ordered_rows = sorted(rows)
    for index, row in enumerate(ordered_rows):
        previous = rows[ordered_rows[index - 1]] if index > 0 else []
        for pos, hole in rows[row]:
            best = min(previous, key=lambda item: (abs(item[0] - pos), item[0], item[1].id), default=None)
            if best is not None and abs(best[0] - pos) <= limit:
                incoming[hole.id] = (best[1].id, chain)
            else:
                heads.append((pos, hole))

    starters: list[str] = []
    if heads:
        heads.sort(key=lambda item: (item[0], item[1].id))
        if cut_flank == "right":
            heads.reverse()
        starters.append(heads[0][1].id)
        for (_, prev), (_, head) in zip(heads, heads[1:]):
            incoming[head.id] = (prev.id, trunk)
    elif others:
        # Сетки нет — вруб у фланга среди прочих скважин.
        flank = max if cut_flank == "right" else min
        first = flank(others, key=lambda h: (along(h), h.id))
        starters.append(first.id)
        others = [h for h in others if h.id != first.id]

    # Пара у откоса — та же входящая связь, что у её вертикальной.
    for toe in pairs:
        partner = face_pair_partner_id(toe)
        if partner in starters:
            starters.append(toe.id)
        else:
            incoming[toe.id] = incoming[partner]

    # Прочие — по возрастанию расстояния до ближайшей привязанной (жадно, как Прим).
    tied = [by_id[i] for i in starters] + [by_id[i] for i in incoming]
    best_dist: dict[str, tuple[float, str]] = {}
    for h in others:
        near = min(tied, key=lambda t: (math.hypot(t.collar.x - h.collar.x, t.collar.y - h.collar.y), t.id))
        best_dist[h.id] = (math.hypot(near.collar.x - h.collar.x, near.collar.y - h.collar.y), near.id)
    pending = {h.id: h for h in others}
    while pending:
        hid = min(pending, key=lambda i: (best_dist[i][0], i))
        hole = pending.pop(hid)
        incoming[hid] = (best_dist[hid][1], chain)
        for other in pending.values():
            d = math.hypot(other.collar.x - hole.collar.x, other.collar.y - hole.collar.y)
            if d < best_dist[other.id][0]:
                best_dist[other.id] = (d, hid)

    ties = [(frm, to, ms) for to, (frm, ms) in incoming.items()]
    surface_ms = _times_from_starters(starters, ties)
    return TrunkPlan(starters=starters, ties=ties, surface_ms=surface_ms, warnings=warnings)


def _times_from_starters(starters: list[str], ties: list[tuple[str, str, float]]) -> dict[str, float]:
    """Время каждой скважины от вруба по дереву связей."""
    children: dict[str, list[tuple[str, float]]] = {}
    for frm, to, ms in ties:
        children.setdefault(frm, []).append((to, ms))
    times = {s: 0.0 for s in starters}
    stack = list(starters)
    while stack:
        current = stack.pop()
        for to, ms in children.get(current, []):
            if to not in times:
                times[to] = times[current] + ms
                stack.append(to)
    return times
