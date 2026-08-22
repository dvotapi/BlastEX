"""Шаблонные схемы коммутации и расчёт времён срабатывания скважин.

Схема строится единым алгоритмом для всех четырёх шаблонов: каждой скважине
присваивается скалярная «волновая координата» `w` (своя формула для каждой
схемы), скважины с минимальным `w` становятся стартовыми, а каждая остальная
скважина соединяется поверхностным коннектором с ближайшей скважиной из
предыдущего по `w` уровня. Время срабатывания — задача о кратчайшем пути
(Дейкстра) от стартовых скважин по графу коннекторов: реальный волновод
детонирует от первого пришедшего сигнала, а не от какого-то одного маршрута.
"""
from __future__ import annotations

import heapq
import math
from typing import Any

from design.models import Connector, Hole, InitiationNetwork

SCHEME_TYPES = ("row", "echelon", "diagonal_v", "trapezoid")
SYSTEM_TYPES = ("nonel", "electronic", "detcord")

# Номиналы поверхностных замедлителей НСИ, мс (те же, что фигурируют в схемах СИНВ/Искра).
SURFACE_NSI_MS_OPTIONS = (17, 25, 42, 67, 109)
# Номиналы пиротехнических реле для ДШ, мс — ориентировочный ряд, настраивается пользователем.
DETCORD_RELAY_MS_OPTIONS = (10, 20, 25, 35, 42)
# Внутрискважинное замедление НСИ — тот же ряд, что в cost/geometry.py.
DOWNHOLE_NSI_MS_OPTIONS = tuple(range(450, 1001, 50))

DEFAULT_INTERVAL_MS = {"nonel": 25.0, "electronic": 17.0, "detcord": 20.0}
DEFAULT_DOWNHOLE_MS = {"nonel": 500.0, "electronic": 0.0, "detcord": 0.0}


def _snap(value: float, options: tuple[float, ...]) -> float:
    return min(options, key=lambda x: abs(x - value))


def _wave_coordinate(hole: Hole, scheme: str, center_col: float, min_col: int, max_col: int) -> float:
    row = float(hole.row)
    col = float(hole.col)
    if scheme == "row":
        # Порядная схема: фронт инициирования идёт сплошным рядом.
        return row
    if scheme == "echelon":
        # Клиновая (диагональная лестница): фронт смещается по диагонали в одну сторону.
        return row + col
    if scheme == "diagonal_v":
        # Диагональная V: инициирование начинается от центра переднего ряда
        # и расходится по V к флангам и вглубь блока.
        return row + abs(col - center_col)
    if scheme == "trapezoid":
        # Трапецеидальная: каждый ряд стартует с флангов и сходится к центру —
        # изохроны образуют расширяющуюся трапецию.
        half_width = (max_col - min_col) / 2.0
        return row + max(0.0, half_width - abs(col - center_col))
    return row


def build_template_network(
    holes: list[Hole],
    scheme: str,
    params: dict[str, Any],
) -> InitiationNetwork:
    """Строит схему инициирования по шаблону.

    params:
      system              "nonel" | "electronic" | "detcord"
      interval_ms         базовый интервал между соседними уровнями волны, мс
      downhole_delay_ms   внутрискважинное замедление (одинаковое для всех скважин)
      include_contour     включать ли контурные скважины в схему (по умолчанию нет)
    """
    system = str(params.get("system", "nonel"))
    if system not in SYSTEM_TYPES:
        system = "nonel"
    if scheme not in SCHEME_TYPES:
        scheme = "row"

    include_contour = bool(params.get("include_contour", False))
    eligible = [h for h in holes if h.enabled and (include_contour or h.kind != "contour")]
    if not eligible:
        return InitiationNetwork(system=system)

    interval_ms = float(params.get("interval_ms", DEFAULT_INTERVAL_MS[system]))
    downhole_ms = float(params.get("downhole_delay_ms", DEFAULT_DOWNHOLE_MS[system]))

    if system == "nonel":
        interval_ms = _snap(interval_ms, SURFACE_NSI_MS_OPTIONS)
        downhole_ms = _snap(downhole_ms, DOWNHOLE_NSI_MS_OPTIONS) if downhole_ms > 0 else 0.0
        connector_kind = "surface_nsi"
    elif system == "detcord":
        interval_ms = _snap(interval_ms, DETCORD_RELAY_MS_OPTIONS)
        connector_kind = "ds_relay"
    else:
        connector_kind = "electronic"

    cols = [h.col for h in eligible]
    min_col, max_col = min(cols), max(cols)
    center_col = (min_col + max_col) / 2.0

    scored = [(h, _wave_coordinate(h, scheme, center_col, min_col, max_col)) for h in eligible]
    scored.sort(key=lambda item: item[1])

    min_w = scored[0][1]
    starters = [h.id for h, w in scored if w == min_w]

    connectors: list[Connector] = []
    placed: list[tuple[Hole, float]] = [item for item in scored if item[1] == min_w]
    for hole, w in scored:
        if w == min_w:
            continue
        # Ближайшая по расстоянию скважина среди уже "инициированных" уровней (w меньше текущего).
        candidates = [(other, ow) for other, ow in placed if ow < w]
        nearest = min(
            candidates,
            key=lambda item: math.hypot(hole.collar.x - item[0].collar.x, hole.collar.y - item[0].collar.y),
        )
        delay = round((w - nearest[1]) * interval_ms, 1)
        connectors.append(Connector(from_hole=nearest[0].id, to_hole=hole.id, delay_ms=delay, kind=connector_kind))
        placed.append((hole, w))

    downhole_delay_ms = {h.id: downhole_ms for h in eligible} if downhole_ms > 0 else {}

    return InitiationNetwork(
        system=system,
        starters=starters,
        connectors=connectors,
        downhole_delay_ms=downhole_delay_ms,
        electronic_times_ms={},
    )


def resolve_times(network: InitiationNetwork, holes: list[Hole]) -> tuple[dict[str, float], list[str]]:
    """Времена срабатывания скважин — кратчайший путь (Дейкстра) от стартовых скважин.

    Возвращает (времена по id скважины в мс, предупреждения). Для электронной
    системы явно заданное время в `network.electronic_times_ms` перекрывает
    расчёт по графу для этой скважины.
    """
    hole_ids = {h.id for h in holes if h.enabled}
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for c in network.connectors:
        adjacency.setdefault(c.from_hole, []).append((c.to_hole, c.delay_ms))

    surface_time: dict[str, float] = {}
    heap: list[tuple[float, str]] = [(0.0, hole_id) for hole_id in network.starters if hole_id in hole_ids]
    heapq.heapify(heap)
    while heap:
        t, hole_id = heapq.heappop(heap)
        if hole_id in surface_time and surface_time[hole_id] <= t:
            continue
        surface_time[hole_id] = t
        for neighbour_id, delay in adjacency.get(hole_id, []):
            candidate = t + max(0.0, delay)
            if neighbour_id not in surface_time or candidate < surface_time[neighbour_id]:
                heapq.heappush(heap, (candidate, neighbour_id))

    times: dict[str, float] = {}
    for hole_id in hole_ids:
        if hole_id in network.electronic_times_ms:
            times[hole_id] = network.electronic_times_ms[hole_id]
        elif hole_id in surface_time:
            times[hole_id] = surface_time[hole_id] + network.downhole_delay_ms.get(hole_id, 0.0)

    warnings = [
        f"Скважина {hole_id} не подключена к схеме инициирования — не получает сигнал."
        for hole_id in sorted(hole_ids - set(times))
    ]
    return times, warnings
