"""Монтаж «магистраль + цепочки» для неэлектрической системы (СИНВ).

Голова столбца — член, у которого впереди по столбцу никого нет: в рядах
впереди (ближайший ряд, где есть скважина в 0,75·a по оси) не нашлось
предшественника; выключенная скважина столбца пропускается. На ступенчатой
бровке головы лежат в разных рядах решётки, и магистраль идёт по ним, а не по
ряду 1. Вруб — крайняя у выбранного фланга голова среди голов у переднего края
(не глубже самой передней + 1,5·b): на контуре, расширяющемся вглубь, он
остаётся в первом ряду. Магистраль (25 мс между соседними по оси головами)
идёт от вруба к дальнему флангу, а головы со стороны фланга — от вруба в
обратном порядке. От каждой головы назад по рядам — цепочка (42 мс).

Член столбца — скважина семейства сетки, кроме стабилизации, сателлитов и
наклонной у откоса. Пара у откоса (`face_toe`) получает копию входящей связи
своей вертикальной. Прочие скважины (стенки, стабилизация, сателлиты, ручные
вне столбцов) привязываются связью цепочки к ближайшей уже привязанной.

Модуль не строит `InitiationNetwork`: он отдаёт граф связей и времена
поверхностной сети от вруба (`TrunkPlan`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from design.models import (
    FACE_TOE_KIND,
    Connector,
    Hole,
    InitiationNetwork,
    face_pair_partner_id,
    logical_row,
    row_family,
)
from design.timing import (
    DEFAULT_DOWNHOLE_MS,
    SURFACE_NSI_MS_OPTIONS,
    SYSTEM_TYPES,
    _connector_kind,
    _eligible_holes,
    _populate_v2_from_graph,
    _snap,
)

TRUNK_SCHEME = "trunk_chains"
DOWNHOLE_CHOICES_MS = (500.0, 700.0, 1000.0)

# Не члены столбцов: короткие вставки и пара у откоса (как в темпе отбойки).
_NON_COLUMN_KINDS = frozenset({"stab", "satellite", FACE_TOE_KIND})
# Предшественник в цепочке — не дальше этой доли шага a по оси ряда: на
# шахматной сетке (смещение a/2) это ближайший по диагонали.
_CHAIN_OFFSET_FACTOR = 0.75
# Вруб выбирается среди голов, лежащих не глубже самой передней + 1,5·b:
# ступень бровки — в пределах, задний ряд расширяющегося контура — нет.
_CUT_DEPTH_FACTOR = 1.5

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


def _row_burden(rows: dict[int, list[tuple[float, Hole]]], deep: Vec, fallback: float) -> float:
    """Шаг между рядами b — медиана разностей средней глубины соседних логических рядов."""
    means = [
        float(np.mean([h.collar.x * deep[0] + h.collar.y * deep[1] for _, h in rows[row]]))
        for row in sorted(rows)
    ]
    steps = [b - a for a, b in zip(means, means[1:]) if b - a > 1e-9]
    return float(np.median(steps)) if steps else fallback


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
    (ax, ay), (dx, dy) = row_axis(holes)

    def along(h: Hole) -> float:
        return h.collar.x * ax + h.collar.y * ay

    members = [h for h in holes if _is_column_member(h)]
    # Пара у откоса и номер её вертикальной (вертикальная — член столбца).
    pairs: list[tuple[Hole, str]] = []
    for h in holes:
        partner = face_pair_partner_id(h)
        if partner is not None and partner in by_id and _is_column_member(by_id[partner]):
            pairs.append((h, partner))
    pair_ids = {h.id for h, _ in pairs}
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
        for pos, hole in rows[row]:
            # Предшественник — в ближайшем ряду впереди, где есть скважина в
            # 0,75·a по оси: выключенная скважина столбца пропускается, и
            # скважина за ней не становится головой.
            predecessor = None
            for back in reversed(ordered_rows[:index]):
                best = min(rows[back], key=lambda item: (abs(item[0] - pos), item[0], item[1].id))
                if abs(best[0] - pos) <= limit:
                    predecessor = best[1]
                    break
            if predecessor is not None:
                incoming[hole.id] = (predecessor.id, chain)
            else:
                heads.append((pos, hole))

    starters: list[str] = []
    if heads:
        heads.sort(key=lambda item: (item[0], item[1].id))
        if cut_flank == "right":
            heads.reverse()
        # Вруб — крайняя у фланга голова среди голов у переднего края
        # (глубина не дальше 1,5·b от самой передней): на контуре,
        # расширяющемся вглубь, вруб не уходит в задний ряд.
        depths = [h.collar.x * dx + h.collar.y * dy for _, h in heads]
        front_limit = min(depths) + _CUT_DEPTH_FACTOR * _row_burden(rows, (dx, dy), limit / _CHAIN_OFFSET_FACTOR)
        cut = next(i for i, depth in enumerate(depths) if depth <= front_limit + 1e-9)
        starters.append(heads[cut][1].id)
        # Магистраль от вруба к дальнему флангу, головы со стороны фланга —
        # от вруба в обратном порядке; 25 мс между соседними головами.
        for (_, prev), (_, head) in zip(heads[cut:], heads[cut + 1:]):
            incoming[head.id] = (prev.id, trunk)
        flank_side = heads[: cut + 1][::-1]
        for (_, prev), (_, head) in zip(flank_side, flank_side[1:]):
            incoming[head.id] = (prev.id, trunk)
    elif others:
        # Сетки нет — вруб у фланга среди прочих скважин.
        flank = max if cut_flank == "right" else min
        first = flank(others, key=lambda h: (along(h), h.id))
        starters.append(first.id)
        others = [h for h in others if h.id != first.id]

    # Пара у откоса — та же входящая связь, что у её вертикальной.
    for toe, partner in pairs:
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


def pick_downhole_ms(max_surface_ms: float) -> tuple[float, list[str]]:
    """Внутрискважинное замедление блока: наименьшее из НСИ, строго большее
    наибольшего поверхностного времени сети; иначе 1000 мс и предупреждение."""
    for choice in DOWNHOLE_CHOICES_MS:
        if choice > max_surface_ms:
            return choice, []
    return DOWNHOLE_CHOICES_MS[-1], [
        "Фронт инициирования отстаёт: поверхностная сеть длиннее 1000 мс — возможен подбой."
    ]


def build_trunk_chains_network(
    holes: list[Hole], params: dict[str, Any]
) -> tuple[InitiationNetwork, list[str]]:
    """Сеть «Магистраль + цепочки» и предупреждения построения."""
    system = str(params.get("system", "nonel"))
    if system not in SYSTEM_TYPES:
        system = "nonel"
    eligible = _eligible_holes(holes, bool(params.get("include_contour", False)))
    if not eligible:
        return InitiationNetwork(system=system), []

    trunk_ms = float(params.get("trunk_ms", 25.0))
    chain_ms = float(params.get("chain_ms", 42.0))
    cut_flank = str(params.get("cut_flank", "left"))
    plan = plan_trunk_chains(eligible, trunk_ms=trunk_ms, chain_ms=chain_ms, cut_flank=cut_flank)
    warnings = list(plan.warnings)

    if system == "nonel":
        downhole_ms, extra = pick_downhole_ms(max(plan.surface_ms.values(), default=0.0))
        warnings.extend(extra)
    else:
        downhole_ms = DEFAULT_DOWNHOLE_MS[system]

    kind = _connector_kind(system)
    network = InitiationNetwork(
        system=system,
        starters=list(plan.starters),
        connectors=[Connector(from_hole=a, to_hole=b, delay_ms=ms, kind=kind) for a, b, ms in plan.ties],
        timing_params={
            "scheme": TRUNK_SCHEME,
            "trunk_ms": trunk_ms,
            "chain_ms": chain_ms,
            "cut_flank": cut_flank,
            "downhole_delay_ms": downhole_ms,
        },
    )
    network = _populate_v2_from_graph(network, downhole_ms=downhole_ms, eligible=eligible)
    return network, warnings
