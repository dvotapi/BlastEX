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
Предшественник ищется во всех рядах впереди, поэтому голова — скважина, у
которой ни в одном ряду впереди нет скважины в 0,75·a по оси: между головами
переднего края глубокая голова оказывается только в разрыве фронта шире
1,5·a, и отдельный участок магистрали там законен.

Ступени СИНВ привязываются к НСИ, ДШ — к реле ДШ; у электронной системы
ступень — любое число не меньше 1 мс.

Член столбца — скважина ряда решётки при любом виде (`models.is_lattice_hole`:
не ручная, не наклонная у откоса, номер ряда основной сетки). Стабилизация и
сателлиты — члены, только когда это вид основной сетки (`main_kind`, вид
основной сетки паспорта): иначе это отдельно сгенерированные вставки (они
носят номер ряда своей скважины). Отдельные стеночные ряды (номера −1…−n,
буферный −10) — прочие. Пара у откоса (`face_toe`) получает копию входящей
связи своей вертикальной. Прочие скважины (стенки, вставки, ручные)
привязываются связью цепочки к ближайшей уже привязанной.

На шахматке у скважины два предшественника на равном смещении: сторона
чередуется по чётности логического ряда (нечётный — левый, чётный — правый),
а предшественник, уже занятый соседкой по ряду, уступает свободному — иначе
две соседние скважины ряда срабатывали бы разом. Если свободного нет — тот же
предшественник со следующей ступенью системы, а когда следующей нет (ДШ при
42 мс) — связь от соседки, уже взявшей его, наименьшей ступенью системы.

Времена считаются рядами спереди назад. Скважина, которая по выбранной связи
сработала бы не позже какой-либо скважины впереди в 0,75·a по оси (шахматка с
пропусками: предшественница из одного столбца раньше соседки из другого),
перепривязывается к самой поздней из них — по тем же правилам занятого.

Модуль не строит `InitiationNetwork`: он отдаёт граф связей и времена
поверхностной сети от вруба (`TrunkPlan`).
"""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from design.models import (
    Connector,
    Hole,
    InitiationNetwork,
    face_pair_partner_id,
    is_lattice_hole,
    logical_row,
)
from design.timing import (
    DEFAULT_DOWNHOLE_MS,
    DETCORD_RELAY_MS_OPTIONS,
    ELECTRONIC_MODES,
    SURFACE_NSI_MS_OPTIONS,
    SYSTEM_TYPES,
    _connector_kind,
    _populate_v2_from_graph,
    _snap,
)

TRUNK_SCHEME = "trunk_chains"
DOWNHOLE_CHOICES_MS = (500.0, 700.0, 1000.0)

# Короткие вставки: члены столбцов, только когда это вид основной сетки.
_INSERT_KINDS = frozenset({"stab", "satellite"})
# Предшественник в цепочке — не дальше этой доли шага a по оси ряда: на
# шахматной сетке (смещение a/2) это ближайший по диагонали.
_CHAIN_OFFSET_FACTOR = 0.75
# Вруб выбирается среди голов, лежащих не глубже самой передней + 1,5·b:
# ступень бровки — в пределах, задний ряд расширяющегося контура — нет.
_CUT_DEPTH_FACTOR = 1.5
# Стенки: в этой схеме они «прочие» и срабатывают после соседней сетки.
_WALL_KINDS = frozenset({"contour", "presplit", "trim"})
# Равенство смещений до предшественника, м (погрешность координат).
_OFFSET_TIE_M = 1e-6
# Наименьшая ступень электронной системы, мс.
_ELECTRONIC_MIN_STEP_MS = 1.0

DOWNHOLE_LATE_WARNING = (
    "Фронт инициирования отстаёт: поверхностная сеть не короче 1000 мс — возможен подбой."
)
WALLS_AFTER_GRID_WARNING = (
    "Стенки (контур, пресплит) в этой схеме срабатывают после сетки — "
    "опережающий пресплит постройте отдельно."
)
ELECTRONIC_MODE_IGNORED_WARNING = (
    "Электронный режим тайминга не применяется к схеме „Магистраль + цепочки“: "
    "времена — по связям."
)

Vec = tuple[float, float]


@dataclass(frozen=True)
class TrunkPlan:
    """Граф монтажа: стартовые скважины, связи (откуда, куда, мс), времена от вруба."""

    starters: list[str]
    ties: list[tuple[str, str, float]]
    surface_ms: dict[str, float]
    warnings: list[str] = field(default_factory=list)
    # Ступени после привязки к номиналам системы.
    trunk_ms: float = 25.0
    chain_ms: float = 42.0


def _is_column_member(hole: Hole, main_kind: str = "") -> bool:
    # Ручная скважина (row −1000) не член столбца: иначе она стала бы
    # «самым передним рядом» и перевернула ось и фланг. Ряд решётки
    # стеночного вида (основная сетка или строка `row_params`) — член,
    # отдельный стеночный ряд — нет.
    if not is_lattice_hole(hole):
        return False
    # Вставки стабилизации и сателлиты носят номер ряда своей скважины: их
    # отличает вид, а не ряд.
    return hole.kind not in _INSERT_KINDS or hole.kind == main_kind


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


def row_axis(holes: list[Hole], main_kind: str = "") -> tuple[Vec, Vec]:
    """(ось ряда, направление «от откоса вглубь») — единичные векторы.

    Вглубь — ось, повёрнутая на +90°: наименьшая проекция на ось — левый фланг,
    если смотреть с откоса вглубь блока.
    """
    members = [h for h in holes if _is_column_member(h, main_kind)] or list(holes)
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
    """Шаг ряда a — медиана расстояний между соседними по оси скважинами ряда;
    math.inf — в каждом ряду по одной скважине."""
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


def _chain_limit(rows: dict[int, list[tuple[float, Hole]]], deep: Vec) -> float:
    """Порог смещения до предшественника: 0,75·a; a не определяется — 0,75·b;
    не определяется и b — без ограничения."""
    step = _row_step(rows)
    if math.isinf(step):
        step = _row_burden(rows, deep, math.inf)
    return _CHAIN_OFFSET_FACTOR * step


def _step_options(system: str) -> tuple[tuple[float, ...], str]:
    """Номиналы ступеней системы и их название в предупреждении."""
    if system == "detcord":
        return DETCORD_RELAY_MS_OPTIONS, "номиналов реле ДШ"
    return SURFACE_NSI_MS_OPTIONS, "НСИ"


def _snap_step(value: float, label: str, system: str, warnings: list[str]) -> float:
    if system == "electronic":
        # Электронный детонатор программируется с точностью 1 мс: номиналов нет.
        if float(value) >= _ELECTRONIC_MIN_STEP_MS:
            return float(value)
        warnings.append(f"Замедление {label} {value:g} мс заменено на {_ELECTRONIC_MIN_STEP_MS:g} мс.")
        return _ELECTRONIC_MIN_STEP_MS
    options, name = _step_options(system)
    snapped = float(_snap(float(value), options))
    if abs(snapped - float(value)) > 1e-9:
        warnings.append(f"Замедление {label} {value:g} мс заменено ближайшим из {name}: {snapped:g} мс.")
    return snapped


def normalize_flank(value: Any) -> str:
    """Фланг вруба: "right" или "left" (всё прочее — левый)."""
    return "right" if str(value) == "right" else "left"


def plan_trunk_chains(
    holes: list[Hole],
    *,
    trunk_ms: float = 25.0,
    chain_ms: float = 42.0,
    cut_flank: str = "left",
    system: str = "nonel",
    main_kind: str = "",
) -> TrunkPlan:
    """Граф «магистраль + цепочки» по уже отфильтрованным скважинам.

    Ступени привязываются к номиналам системы: ДШ — к реле ДШ, СИНВ — к НСИ;
    у электронной — любое число не меньше 1 мс. `main_kind` — вид основной
    сетки: её скважины стеночного вида тоже члены столбцов.
    """
    warnings: list[str] = []
    trunk = _snap_step(trunk_ms, "магистрали", system, warnings)
    chain = _snap_step(chain_ms, "цепочки", system, warnings)
    cut_flank = normalize_flank(cut_flank)
    if not holes:
        return TrunkPlan(starters=[], ties=[], surface_ms={}, warnings=warnings, trunk_ms=trunk, chain_ms=chain)

    by_id = {h.id: h for h in holes}
    (ax, ay), (dx, dy) = row_axis(holes, main_kind)

    def along(h: Hole) -> float:
        return h.collar.x * ax + h.collar.y * ay

    members = [h for h in holes if _is_column_member(h, main_kind)]
    # Пара у откоса и номер её вертикальной (вертикальная — член столбца).
    pairs: list[tuple[Hole, str]] = []
    for h in holes:
        partner = face_pair_partner_id(h)
        if partner is not None and partner in by_id and _is_column_member(by_id[partner], main_kind):
            pairs.append((h, partner))
    pair_ids = {h.id for h, _ in pairs}
    member_ids = {h.id for h in members}
    others = [h for h in holes if h.id not in member_ids and h.id not in pair_ids]

    rows: dict[int, list[tuple[float, Hole]]] = {}
    for h in members:
        rows.setdefault(logical_row(h.row), []).append((along(h), h))
    for items in rows.values():
        items.sort(key=lambda item: (item[0], item[1].id))
    deep = (dx, dy)
    limit = _chain_limit(rows, deep)
    ordered_rows = sorted(rows)
    positions = {row: [p for p, _ in rows[row]] for row in ordered_rows}

    def ahead_of(index: int, pos: float) -> list[tuple[float, Hole]]:
        """Скважины всех рядов впереди в limit по оси от pos."""
        found: list[tuple[float, Hole]] = []
        for back in ordered_rows[:index]:
            lo = bisect_left(positions[back], pos - limit - 1e-6)
            hi = bisect_right(positions[back], pos + limit + 1e-6)
            found.extend(item for item in rows[back][lo:hi] if abs(item[0] - pos) <= limit)
        return found

    # Голова — член, у которого ни в одном ряду впереди нет скважины в limit по оси.
    heads: list[tuple[float, Hole]] = [
        (pos, hole) for index, row in enumerate(ordered_rows) for pos, hole in rows[row] if not ahead_of(index, pos)
    ]
    head_ids = {hole.id for _, hole in heads}

    incoming: dict[str, tuple[str, float]] = {}

    starters: list[str] = []
    if heads:
        heads.sort(key=lambda item: (item[0], item[1].id))
        if cut_flank == "right":
            heads.reverse()
        # Вруб — крайняя у фланга голова среди голов у переднего края
        # (глубина не дальше 1,5·b от самой передней): на контуре,
        # расширяющемся вглубь, вруб не уходит в задний ряд.
        depths = [h.collar.x * dx + h.collar.y * dy for _, h in heads]
        front_limit = min(depths) + _CUT_DEPTH_FACTOR * _row_burden(rows, deep, limit / _CHAIN_OFFSET_FACTOR)
        cut = next(i for i, depth in enumerate(depths) if depth <= front_limit + 1e-9)
        starters.append(heads[cut][1].id)
        # Магистраль от вруба к дальнему флангу, головы со стороны фланга —
        # от вруба в обратном порядке; 25 мс между соседними головами.
        for (_, prev), (_, head) in zip(heads[cut:], heads[cut + 1:]):
            incoming[head.id] = (prev.id, trunk)
        flank_side = heads[: cut + 1][::-1]
        for (_, prev), (_, head) in zip(flank_side, flank_side[1:]):
            incoming[head.id] = (prev.id, trunk)
        _tie_chains(
            rows, ordered_rows, limit, ahead_of, head_ids, starters, incoming, chain=chain, system=system
        )
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
    return TrunkPlan(
        starters=starters, ties=ties, surface_ms=surface_ms, warnings=warnings, trunk_ms=trunk, chain_ms=chain
    )


def _tie_chains(
    rows: dict[int, list[tuple[float, Hole]]],
    ordered_rows: list[int],
    limit: float,
    ahead_of: Callable[[int, float], list[tuple[float, Hole]]],
    head_ids: set[str],
    starters: list[str],
    incoming: dict[str, tuple[str, float]],
    *,
    chain: float,
    system: str,
) -> None:
    """Цепочки рядами спереди назад; дописывает связи в `incoming`.

    Скважина берёт предшественника по столбцу (`_chain_predecessor`). Если по
    этой связи она сработала бы не позже какой-либо скважины впереди в 0,75·a
    по оси, она перепривязывается к самой поздней из них. Занятый соседкой по
    ряду предшественник — со следующей ступенью системы; следующей нет — связь
    от соседки, уже взявшей его, наименьшей ступенью системы.
    """
    step_up = _next_step(chain, system)
    least = _least_step(system)

    def link(predecessor: Hole, taken: dict[str, str]) -> tuple[str, float]:
        """Связь от предшественника; занятый соседкой — следующая ступень,
        а без неё — от соседки, уже взявшей его, наименьшей ступенью."""
        if predecessor.id not in taken:
            return predecessor.id, chain
        if step_up is not None:
            return predecessor.id, step_up
        return taken[predecessor.id], least

    # Времена голов — по магистрали от вруба.
    times = _times_from_starters(starters, [(frm, to, ms) for to, (frm, ms) in incoming.items()])
    for index, row in enumerate(ordered_rows):
        # Шахматка: при равном смещении нечётный ряд берёт левого, чётный —
        # правого (зигзаг держит столбцы).
        side = -1.0 if row % 2 else 1.0
        # Предшественник → последняя скважина ряда, взявшая его.
        taken: dict[str, str] = {}
        for pos, hole in rows[row]:
            if hole.id in head_ids:
                continue
            found = _chain_predecessor(rows, ordered_rows[:index], pos, limit, side, taken)
            if found is None:  # не бывает: у не-головы впереди есть скважина в пределе
                continue
            predecessor = found[0]
            tie = link(predecessor, taken)
            # Самая поздняя скважина впереди в пределе; при равенстве — ближайшая по оси.
            latest = max(
                ahead_of(index, pos), key=lambda item: (times[item[1].id], -abs(item[0] - pos), item[1].id)
            )[1]
            if times[tie[0]] + tie[1] <= times[latest.id] + 1e-9:
                predecessor = latest
                tie = link(latest, taken)
            incoming[hole.id] = tie
            times[hole.id] = times[tie[0]] + tie[1]
            taken[predecessor.id] = hole.id


def _next_step(chain_ms: float, system: str) -> float | None:
    """Следующий номинал системы выше ступени цепочки; выше нет — None.

    У электронной системы номиналов нет: следующий номинал НСИ выше ступени,
    а если ступень не меньше наибольшего — ступень + наименьший номинал НСИ.
    """
    options, _ = _step_options(system)
    above = next((float(o) for o in sorted(options) if o > chain_ms + 1e-9), None)
    if above is not None:
        return above
    if system == "electronic":
        return chain_ms + float(min(SURFACE_NSI_MS_OPTIONS))
    return None


def _least_step(system: str) -> float:
    """Наименьшая ступень системы: ДШ — 10 мс, НСИ — 17 мс, электронная — 1 мс."""
    if system == "electronic":
        return _ELECTRONIC_MIN_STEP_MS
    options, _ = _step_options(system)
    return float(min(options))


def _chain_predecessor(
    rows: dict[int, list[tuple[float, Hole]]],
    rows_ahead: list[int],
    pos: float,
    limit: float,
    side: float,
    taken: Collection[str],
) -> tuple[Hole, bool] | None:
    """Предшественник по столбцу — в ближайшем ряду впереди со скважиной в limit по оси.

    Возвращает скважину и признак «уже взята соседкой по ряду». Выключенная
    скважина столбца пропускается: скважина за ней не становится головой. Из
    кандидатов ряда — с наименьшим смещением, при равенстве — со стороны `side`;
    занятый соседкой по ряду уступает свободному. Если в ряду все кандидаты
    заняты, берётся ближайший из них (дальше вперёд поиск не идёт: край ряда
    шахматки не обгоняет скважину перед собой) — вызывающий даёт такой связи
    следующую ступень, а без неё — связь от соседки наименьшей ступенью.
    """
    for back in reversed(rows_ahead):
        near = [(abs(p - pos), p, h) for p, h in rows[back] if abs(p - pos) <= limit]
        if not near:
            continue
        least = min(d for d, _, _ in near)

        def order(item: tuple[float, float, Hole], least: float = least) -> tuple[bool, float, bool, str]:
            offset, p, h = item
            tied = offset <= least + _OFFSET_TIE_M
            return (not tied, 0.0 if tied else offset, side * (pos - p) > 0, h.id)

        near.sort(key=order)
        free = next((h for _, _, h in near if h.id not in taken), None)
        if free is not None:
            return free, False
        return near[0][2], True
    return None


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
    return DOWNHOLE_CHOICES_MS[-1], [DOWNHOLE_LATE_WARNING]


def build_trunk_chains_network(
    holes: list[Hole], params: dict[str, Any]
) -> tuple[InitiationNetwork, list[str]]:
    """Сеть «Магистраль + цепочки» и предупреждения построения."""
    system = str(params.get("system", "nonel"))
    if system not in SYSTEM_TYPES:
        system = "nonel"
    main_kind = str(params.get("main_kind") or "").strip().lower()
    include_contour = bool(params.get("include_contour", False))
    # Основная сетка контурного вида входит в сеть и без include_contour:
    # флаг касается только отдельных контурных рядов.
    eligible = [
        h
        for h in holes
        if h.enabled and (include_contour or h.kind != "contour" or _is_column_member(h, main_kind))
    ]
    if not eligible:
        return InitiationNetwork(system=system), []

    trunk_ms = float(params.get("trunk_ms", 25.0))
    chain_ms = float(params.get("chain_ms", 42.0))
    cut_flank = normalize_flank(params.get("cut_flank", "left"))
    plan = plan_trunk_chains(
        eligible, trunk_ms=trunk_ms, chain_ms=chain_ms, cut_flank=cut_flank, system=system, main_kind=main_kind
    )
    warnings = list(plan.warnings)
    # Режимы электронного тайминга этой схеме не применяются: времена — по связям.
    if system == "electronic" and str(params.get("timing_mode", "") or "") in ELECTRONIC_MODES:
        warnings.append(ELECTRONIC_MODE_IGNORED_WARNING)
    if any(h.kind in _WALL_KINDS and not _is_column_member(h, main_kind) for h in eligible):
        warnings.append(WALLS_AFTER_GRID_WARNING)

    if system == "nonel":
        downhole_ms, extra = pick_downhole_ms(max(plan.surface_ms.values(), default=0.0))
        warnings.extend(extra)
    else:
        # ДШ и электронная — из поля, как у остальных схем; не задано — умолчание системы.
        downhole_ms = float(params.get("downhole_delay_ms", DEFAULT_DOWNHOLE_MS[system]))

    kind = _connector_kind(system)
    network = InitiationNetwork(
        system=system,
        starters=list(plan.starters),
        connectors=[Connector(from_hole=a, to_hole=b, delay_ms=ms, kind=kind) for a, b, ms in plan.ties],
        timing_params={
            "scheme": TRUNK_SCHEME,
            "trunk_ms": plan.trunk_ms,
            "chain_ms": plan.chain_ms,
            "cut_flank": cut_flank,
            "downhole_delay_ms": downhole_ms,
        },
    )
    network = _populate_v2_from_graph(network, downhole_ms=downhole_ms, eligible=eligible)
    # У ДШ общий шнур через все скважины подряд дал бы связи «расстояние / скорость»
    # между несвязанными скважинами, и кратчайший путь обошёл бы реле 25/42 мс.
    # Здесь времена задают сами связи-реле: каждое ребро графа — отрезок шнура с реле.
    network.detonating_cords = []
    return network, warnings
