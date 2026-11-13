"""Initiation network 2.0: template ties, electronic programs, firing events.

Template graphs still use a wave coordinate plus Dijkstra (earliest arrival).
Electronic programs assign absolute times by row, selection, direction,
gradient, V/diagonal pattern, or a safe custom expression (never eval).
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, replace
from typing import Any

from design.models import (
    ELECTRONIC_TIMING_MODES,
    logical_row,
    Connector,
    DetonatingCord,
    Detonator,
    DownholeConnector,
    ElectronicChannel,
    FiringEvent,
    Hole,
    HoleLoad,
    InitiationNetwork,
    Starter,
    SurfaceConnector,
    is_explosive_deck_kind,
)
from design.timing_expr import TimingExprError, evaluate_timing_expression

__all__ = [
    "SCHEME_TYPES",
    "SYSTEM_TYPES",
    "ELECTRONIC_MODES",
    "TimingExprError",
    "TimingResult",
    "build_template_network",
    "apply_electronic_timing",
    "add_surface_tie",
    "remove_surface_tie",
    "update_surface_tie",
    "toggle_starter",
    "resolve_network",
    "resolve_times",
    "build_firing_events",
    "ORIGIN_TEMPLATE",
    "ORIGIN_EDITED",
    "GEOMETRY_STALE_KEY",
    "template_timing_params",
    "retie_params",
    "tie_catalog",
]

SCHEME_TYPES = ("row", "echelon", "diagonal_v", "trapezoid", "trunk_chains")
SYSTEM_TYPES = ("nonel", "electronic", "detcord")
ELECTRONIC_MODES = ELECTRONIC_TIMING_MODES

SURFACE_NSI_MS_OPTIONS = (17, 25, 42, 67, 109)
DETCORD_RELAY_MS_OPTIONS = (10, 20, 25, 35, 42)
DOWNHOLE_NSI_MS_OPTIONS = tuple(range(450, 1001, 50))

DEFAULT_INTERVAL_MS = {"nonel": 25.0, "electronic": 17.0, "detcord": 20.0}
# Стенки старых шаблонов: пресплит стартует до блока, контур и буфер — после сетки.
_WALL_KINDS = ("presplit", "contour", "buffer")
DEFAULT_DOWNHOLE_MS = {"nonel": 500.0, "electronic": 0.0, "detcord": 0.0}

DETCORD_VELOCITY_M_S = 7000.0

# Происхождение сети (TASK-017, PR 3): построена шаблоном и не правлена руками —
# «template», после ручной правки — «edited». Сеть без ключа (построена до
# PR 3) считается правленой: её параметров не хватает для пересчёта.
ORIGIN_TEMPLATE = "template"
ORIGIN_EDITED = "edited"
# Пометка «устарела по геометрии»: скважины сдвинуты, добавлены, удалены,
# исключены или сменили вид после построения сети (ставит фронт).
GEOMETRY_STALE_KEY = "geometry_stale"

# Параметры запроса, которые сеть хранит для повторного построения без формы
# (ключи — только заданные в запросе). Азимут бровки не хранится: его заново
# считает `generate_tie` по контуру; система — `network.system`.
_WAVE_PARAM_KEYS = ("interval_ms", "downhole_delay_ms", "include_contour", "presplit_lead_ms", "wall_after_ms")
_ELECTRONIC_PARAM_KEYS = (
    "timing_mode",
    "timing_expression",
    "base_ms",
    "direction_azimuth_deg",
    "gradient_from_ms",
    "gradient_to_ms",
)
# `timing_mode` у «Магистраль + цепочки» не применяется, но даёт предупреждение
# построения — хранится, чтобы пересчёт его повторил.
_TRUNK_PARAM_KEYS = (
    "trunk_ms",
    "chain_ms",
    "cut_flank",
    "downhole_delay_ms",
    "include_contour",
    "main_kind",
    "burning_front_m",
    "timing_mode",
)
# Порядок «по выбору» — поле сети `selected_hole_ids` (его переименовывает
# перенумерация), а не копия в `timing_params`.
_SERVICE_KEYS = ("scheme", "origin", GEOMETRY_STALE_KEY, "selected_hole_ids")


def template_timing_params(scheme: str, system: str, params: dict[str, Any], built: dict[str, Any]) -> dict[str, Any]:
    """`timing_params` сети, построенной шаблоном: схема, `origin`, заданные ключи
    семейства схемы и поверх — значения, к которым их привёл построитель
    (`built`: ступень по номиналу, фланг, подобранное замедление).

    Пустые значения (None, пустая строка, пустой список) не пишутся.
    """
    if scheme == "trunk_chains":
        keys: tuple[str, ...] = _TRUNK_PARAM_KEYS
    else:
        keys = _WAVE_PARAM_KEYS
        if system == "electronic" and str(params.get("timing_mode", "") or "") in ELECTRONIC_MODES:
            keys = keys + _ELECTRONIC_PARAM_KEYS
    stored: dict[str, Any] = {"scheme": scheme, "origin": ORIGIN_TEMPLATE}
    for key in keys:
        value = built[key] if key in built else params.get(key)
        if value is None or value == "" or value == []:
            continue
        stored[key] = list(value) if isinstance(value, (list, tuple)) else value
    return stored


def retie_params(network: InitiationNetwork) -> tuple[str, dict[str, Any]] | None:
    """Схема и параметры повторного построения сети по её `timing_params`.

    Сеть без `origin` (построена до PR 3) или с неизвестной схемой — None:
    параметров для пересчёта не хватает.
    """
    timing = network.timing_params or {}
    scheme = timing.get("scheme")
    if "origin" not in timing or scheme not in SCHEME_TYPES:
        return None
    params = {key: value for key, value in timing.items() if key not in _SERVICE_KEYS}
    params["system"] = network.system
    if network.selected_hole_ids:
        params["selected_hole_ids"] = list(network.selected_hole_ids)
    return str(scheme), params


def tie_catalog() -> dict[str, Any]:
    """Номиналы ступеней по системам — для палитры правки коммутации на плане
    (TASK-017, PR 4): фронт берёт их отсюда, а не держит свою копию.

    `surface_ms` — поверхностные ступени (у электронной — те же, что у СИНВ, и
    любое своё значение: `custom_surface`), `downhole_ms` — номиналы
    внутрискважинных детонаторов (у ДШ и электронной номиналов нет — своё).
    """
    def system(surface: tuple[int, ...], downhole: tuple[int, ...], name: str, custom: bool) -> dict[str, Any]:
        return {
            "surface_ms": list(surface),
            "downhole_ms": list(downhole),
            "downhole_default_ms": DEFAULT_DOWNHOLE_MS[name],
            "custom_surface": custom,
        }

    return {
        "systems": {
            "nonel": system(SURFACE_NSI_MS_OPTIONS, DOWNHOLE_NSI_MS_OPTIONS, "nonel", False),
            "detcord": system(DETCORD_RELAY_MS_OPTIONS, (), "detcord", False),
            "electronic": system(SURFACE_NSI_MS_OPTIONS, (), "electronic", True),
        },
        "detcord_velocity_m_s": DETCORD_VELOCITY_M_S,
    }


def _snap(value: float, options: tuple[float, ...]) -> float:
    return min(options, key=lambda x: abs(x - value))


def _wave_coordinate(hole: Hole, scheme: str, center_col: float, min_col: int, max_col: int) -> float:
    row = float(logical_row(hole.row))
    col = float(hole.col)
    if scheme == "row":
        return row
    if scheme == "echelon":
        return row + col
    if scheme == "diagonal_v":
        return row + abs(col - center_col)
    if scheme == "trapezoid":
        half_width = (max_col - min_col) / 2.0
        return row + max(0.0, half_width - abs(col - center_col))
    return row


def _anchor_manual(
    holes: list[Hole], coords: dict[str, float], keep: set[str] | frozenset[str] = frozenset()
) -> dict[str, float]:
    """Ручные скважины не задают начало отсчёта: их координата — у самой ранней основной.

    Основная — не стенка и не ручная. Иначе ручная скважина (row -1000 и т.п.)
    сдвигала бы весь блок на тысячи интервалов в режимах, где координата берётся
    из геометрии. `keep` — ручные с уже заданной координатой (стенки порядной
    схемы: пресплит — до блока, контур и буфер — после), их не трогаем.
    """
    wall_kinds = _WALL_KINDS
    grid_values = [
        coords[h.id]
        for h in holes
        if h.source != "manual" and h.kind not in wall_kinds and h.id in coords
    ]
    anchor = min(grid_values) if grid_values else 0.0
    for hole in holes:
        if hole.source == "manual" and hole.id not in keep:
            coords[hole.id] = anchor
    return coords


def _block_row_coordinates(holes: list[Hole], interval_ms: float, params: dict[str, Any]) -> dict[str, float]:
    """Координаты в ряд: пресплит — до блока, буфер и контур — после сетки, ручные — с первым рядом.

    Единица — интервал. Основные ряды (сетка и прочее) идут по логическим номерам и
    сюда не попадают. Пресплит стартует presplit_lead_ms до первого основного ряда,
    буфер и контур — wall_after_ms после последнего (по умолчанию один интервал).
    Без основных рядов или без стенок словарь пуст — порядок прежний.
    """
    wall_kinds = _WALL_KINDS
    # Ручные скважины (row -1000 и т.п.) не задают начало отсчёта: они стартуют
    # с первым основным рядом и не сдвигают весь блок.
    grid = [h for h in holes if h.kind not in wall_kinds and h.source != "manual"]
    if not grid or interval_ms <= 0:
        return {}
    first = min(logical_row(h.row) for h in grid)
    last = max(logical_row(h.row) for h in grid)
    lead_units = float(params.get("presplit_lead_ms", 150.0)) / interval_ms
    after_units = float(params.get("wall_after_ms", interval_ms)) / interval_ms
    coords: dict[str, float] = {}
    for hole in holes:
        if hole.kind == "presplit":
            coords[hole.id] = first - lead_units
        elif hole.kind in ("contour", "buffer"):
            coords[hole.id] = last + after_units
        elif hole.source == "manual":
            coords[hole.id] = float(first)
    return coords


def _eligible_holes(holes: list[Hole], include_contour: bool) -> list[Hole]:
    return [h for h in holes if h.enabled and (include_contour or h.kind != "contour")]


def _connector_kind(system: str) -> str:
    if system == "nonel":
        return "surface_nsi"
    if system == "detcord":
        return "ds_relay"
    return "electronic"


def _grid_extents(holes: list[Hole]) -> tuple[int, int, float]:
    cols = [h.col for h in holes]
    min_col, max_col = min(cols), max(cols)
    return min_col, max_col, (min_col + max_col) / 2.0


def _populate_v2_from_graph(
    network: InitiationNetwork,
    *,
    downhole_ms: float,
    eligible: list[Hole],
    off_cord: set[str] | None = None,
) -> InitiationNetwork:
    """Связи v2 по графу; `off_cord` — скважины вне общего шнура ДШ (ручные «прочие»)."""
    kind = _connector_kind(network.system)
    network.starter_items = [
        Starter(id=f"st-{hole_id}", hole_id=hole_id) for hole_id in network.starters
    ]
    network.surface_connectors = [
        SurfaceConnector(
            id=f"sc-{item.from_hole}-{item.to_hole}",
            from_hole=item.from_hole,
            to_hole=item.to_hole,
            delay_ms=item.delay_ms,
            kind=item.kind or kind,
        )
        for item in network.connectors
    ]
    if downhole_ms > 0:
        network.downhole_delay_ms = {hole.id: downhole_ms for hole in eligible}
        network.downhole_connectors = [
            DownholeConnector(
                id=f"dh-{hole.id}",
                hole_id=hole.id,
                delay_ms=downhole_ms,
                kind="electronic" if network.system == "electronic" else "downhole_nsi",
            )
            for hole in eligible
        ]
        detonator_kind = "electronic" if network.system == "electronic" else "nonel"
        network.detonators = [
            Detonator(
                id=f"det-{hole.id}",
                hole_id=hole.id,
                delay_ms=downhole_ms,
                kind=detonator_kind,
            )
            for hole in eligible
        ]
    else:
        network.downhole_delay_ms = {}
        network.downhole_connectors = []
        if network.system == "electronic":
            network.detonators = [
                Detonator(id=f"det-{hole.id}", hole_id=hole.id, delay_ms=0.0, kind="electronic")
                for hole in eligible
            ]
        else:
            network.detonators = []
    if network.system == "detcord" and network.starters:
        ordered = list(network.starters)
        seen = set(ordered) | (off_cord or set())
        for item in network.connectors:
            if item.to_hole not in seen:
                ordered.append(item.to_hole)
                seen.add(item.to_hole)
        network.detonating_cords = [
            DetonatingCord(
                id="dc-main",
                hole_ids=ordered,
                velocity_m_s=DETCORD_VELOCITY_M_S,
                relay_delay_ms=0.0,
            )
        ]
    network.sync_legacy_from_v2()
    return network


def build_template_network(
    holes: list[Hole],
    scheme: str,
    params: dict[str, Any],
) -> InitiationNetwork:
    """Build an initiation scheme from a template and optional electronic mode."""
    return build_template_network_with_warnings(holes, scheme, params)[0]


# Номеров ручных скважин в предупреждении не больше этого, остальные — числом.
MANUAL_WARNING_IDS = 10


# Режимы электронного тайминга, где ручная скважина получает время первого ряда
# (`_anchor_manual`, у порядного — `_block_row_coordinates`).
_FIRST_ROW_MODES = ("row", "v_pattern", "diagonal")


def _shown_ids(hole_ids: list[str]) -> str:
    shown = ", ".join(hole_ids[:MANUAL_WARNING_IDS])
    if len(hole_ids) > MANUAL_WARNING_IDS:
        shown += f" и ещё {len(hole_ids) - MANUAL_WARNING_IDS}"
    return shown


def manual_holes_warning(hole_ids: list[str], step_ms: float) -> str:
    """Предупреждение о ручных скважинах, подключённых к сетке шаблона «прочими»."""
    if step_ms > 0:
        when = f"через {f'{step_ms:g}'.replace('.', ',')} мс"
    else:
        when = "одновременно с ними"
    return f"Ручные скважины ({_shown_ids(hole_ids)}) подключены от ближайших скважин {when} — проверьте их время."


def manual_first_row_warning(hole_ids: list[str]) -> str:
    """Предупреждение о ручных скважинах в режиме электронного тайминга."""
    return (
        f"Ручные скважины ({_shown_ids(hole_ids)}) запрограммированы со временем первого ряда, "
        "где бы они ни стояли, — проверьте их время."
    )


def _first_row_manual(eligible: list[Hole], mode: str) -> list[str]:
    """Ручные скважины, которым режим электронного тайминга ставит время первого ряда.

    У порядного режима ручные стенки получают время стенок, у «V» и «диагонали» —
    все ручные; у остальных режимов время ручной — по её месту или выбору.
    Без основной сетки якоря нет — предупреждения тоже.
    """
    if mode not in _FIRST_ROW_MODES or not any(h.source != "manual" and h.kind not in _WALL_KINDS for h in eligible):
        return []
    return [
        h.id
        for h in eligible
        if h.source == "manual" and (mode != "row" or h.kind not in _WALL_KINDS)
    ]


def build_template_network_with_warnings(
    holes: list[Hole],
    scheme: str,
    params: dict[str, Any],
) -> tuple[InitiationNetwork, list[str]]:
    """Сеть шаблона и предупреждения построения (их показывает генерация связей)."""
    system = str(params.get("system", "nonel"))
    if system not in SYSTEM_TYPES:
        system = "nonel"
    if scheme not in SCHEME_TYPES:
        scheme = "row"
    if scheme == "trunk_chains":
        # Импорт здесь: trunk_network сам импортирует timing.
        from design.trunk_network import build_trunk_chains_network

        return build_trunk_chains_network(holes, params)

    include_contour = bool(params.get("include_contour", False))
    eligible = _eligible_holes(holes, include_contour)
    if not eligible:
        return InitiationNetwork(system=system), []

    timing_mode = str(params.get("timing_mode", "") or "")
    if timing_mode and timing_mode not in ELECTRONIC_MODES:
        timing_mode = ""

    warnings: list[str] = []
    if system == "electronic" and timing_mode:
        # Режим электронного тайминга программирует времена сам (ручные — с
        # первым рядом, `_anchor_manual`); связи схемы здесь — лишь рисунок.
        network = apply_electronic_timing(eligible, timing_mode, params)
        network.system = system
        if not network.surface_connectors:
            graph, _manual = _build_wave_graph(eligible, scheme, system, params, tie_manual=False)
            network.connectors = graph.connectors
            network.surface_connectors = graph.surface_connectors
            network.sync_legacy_from_v2()
        first_row = _first_row_manual(eligible, timing_mode)
        if first_row:
            warnings.append(manual_first_row_warning(first_row))
    else:
        network, manual = _build_wave_graph(eligible, scheme, system, params)
        if manual:
            warnings.append(manual_holes_warning(manual, float(network.timing_params["interval_ms"])))
    network.timing_params = template_timing_params(scheme, system, params, network.timing_params)
    return network, warnings


def tie_to_nearest(others: list[Hole], tied: list[Hole]) -> list[tuple[str, str]]:
    """«Прочие» скважины — связями (откуда, куда) от ближайшей уже подключённой.

    Жадно, по возрастанию расстояния, как Прим: подключённая прочая сама
    становится источником для следующих; равные расстояния — по номеру. Общее
    правило «Магистраль + цепочки» (`trunk_network`) и ручных скважин старых
    шаблонов.
    """

    def distance(a: Hole, b: Hole) -> float:
        return math.hypot(a.collar.x - b.collar.x, a.collar.y - b.collar.y)

    best: dict[str, tuple[float, str]] = {}
    for hole in others:
        near = min(tied, key=lambda item: (distance(item, hole), item.id))
        best[hole.id] = (distance(near, hole), near.id)
    pending = {hole.id: hole for hole in others}
    ties: list[tuple[str, str]] = []
    while pending:
        hole_id = min(pending, key=lambda item: (best[item][0], item))
        hole = pending.pop(hole_id)
        ties.append((best[hole_id][1], hole_id))
        for other in pending.values():
            d = distance(other, hole)
            if d < best[other.id][0]:
                best[other.id] = (d, hole_id)
    return ties


def _build_wave_graph(
    eligible: list[Hole],
    scheme: str,
    system: str,
    params: dict[str, Any],
    *,
    tie_manual: bool = True,
) -> tuple[InitiationNetwork, list[str]]:
    """Сеть волнами по координате схемы и номера ручных скважин, подключённых «прочими».

    Ручные скважины, кроме стенок, в волны не входят: стартовой посреди блока
    они бы стали сами, а сетку вели бы через себя (у ДШ — и через общий шнур).
    Ручные стенки — в волнах, как стенки схемы (решение владельца 14.11.2026):
    у порядной пресплит — за `presplit_lead_ms` до первого ряда, контур и буфер
    — после последнего; у остальных схем — с первой волной. Без сетки
    подключать ручные не к чему — тогда они идут волнами, как раньше. Источник
    связи ручной — скважина основной сетки, а не стенка (пресплит стартует до
    блока, контур и буфер — после); стенки — только когда сетки, кроме них,
    нет. `tie_manual = False` (режим электронного тайминга: время ручной
    программируется с первым рядом) — ручные без связей.
    """
    manual = [hole for hole in eligible if hole.source == "manual" and hole.kind not in _WALL_KINDS]
    if any(hole.source != "manual" for hole in eligible):
        waves = [hole for hole in eligible if not (hole.source == "manual" and hole.kind not in _WALL_KINDS)]
    else:
        manual, waves = [], eligible
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

    min_col, max_col, center_col = _grid_extents(waves)
    if system in ("nonel", "detcord"):
        # Пресплит идёт одним поверхностным соединителем: его задержка — ступень системы.
        ladder = SURFACE_NSI_MS_OPTIONS if system == "nonel" else DETCORD_RELAY_MS_OPTIONS
        lead = float(params.get("presplit_lead_ms", 150.0))
        below = [option for option in ladder if option <= lead]
        params = {**params, "presplit_lead_ms": float(max(below) if below else min(ladder))}
    wall_coords = _block_row_coordinates(waves, interval_ms, params) if scheme == "row" else {}
    coords = {h.id: _wave_coordinate(h, scheme, center_col, min_col, max_col) for h in waves}
    coords.update(wall_coords)
    coords = _anchor_manual(waves, coords, keep=set(wall_coords))
    scored = [(h, coords[h.id]) for h in waves]
    scored.sort(key=lambda item: item[1])

    min_w = scored[0][1]
    starters = [h.id for h, w in scored if w == min_w]

    connectors: list[Connector] = []
    placed: list[tuple[Hole, float]] = [item for item in scored if item[1] == min_w]
    for hole, w in scored:
        if w == min_w:
            continue
        candidates = [(other, ow) for other, ow in placed if ow < w]
        nearest = min(
            candidates,
            key=lambda item: math.hypot(hole.collar.x - item[0].collar.x, hole.collar.y - item[0].collar.y),
        )
        delay = round((w - nearest[1]) * interval_ms, 1)
        connectors.append(Connector(from_hole=nearest[0].id, to_hole=hole.id, delay_ms=delay, kind=connector_kind))
        placed.append((hole, w))

    if manual and tie_manual:
        sources = [hole for hole in waves if hole.kind not in _WALL_KINDS] or waves
        step = round(interval_ms, 1)
        connectors.extend(
            Connector(from_hole=frm, to_hole=to, delay_ms=step, kind=connector_kind)
            for frm, to in tie_to_nearest(manual, sources)
        )
    downhole_delay_ms = {h.id: downhole_ms for h in eligible} if downhole_ms > 0 else {}
    network = InitiationNetwork(
        system=system,
        starters=starters,
        connectors=connectors,
        downhole_delay_ms=downhole_delay_ms,
        electronic_times_ms={},
        timing_mode="",
        timing_params={"scheme": scheme, "interval_ms": interval_ms, "downhole_delay_ms": downhole_ms},
    )
    network = _populate_v2_from_graph(
        network, downhole_ms=downhole_ms, eligible=eligible, off_cord={hole.id for hole in manual}
    )
    return network, [hole.id for hole in manual]


def _sorted_selected(holes: list[Hole], selected_ids: list[str]) -> list[Hole]:
    by_id = {hole.id: hole for hole in holes}
    ordered = [by_id[hole_id] for hole_id in selected_ids if hole_id in by_id]
    if ordered:
        return ordered
    return sorted(holes, key=lambda hole: (logical_row(hole.row), hole.col, hole.id))


def apply_electronic_timing(
    holes: list[Hole],
    mode: str,
    params: dict[str, Any],
) -> InitiationNetwork:
    """Assign absolute electronic times. Does not use Python eval."""
    if mode not in ELECTRONIC_MODES:
        mode = "row"
    eligible = [hole for hole in holes if hole.enabled]
    if not eligible:
        return InitiationNetwork(system="electronic", timing_mode=mode)

    interval_ms = float(params.get("interval_ms", DEFAULT_INTERVAL_MS["electronic"]))
    base_ms = float(params.get("base_ms", params.get("downhole_delay_ms", 0.0)) or 0.0)
    downhole_ms = float(params.get("downhole_delay_ms", 0.0) or 0.0)
    selected_ids = [str(item) for item in params.get("selected_hole_ids", [])]
    expression = str(params.get("timing_expression", "") or "")
    azimuth_deg = float(params.get("direction_azimuth_deg", 0.0) or 0.0)
    gradient_from = float(params.get("gradient_from_ms", 0.0) or 0.0)
    gradient_to = float(params.get("gradient_to_ms", interval_ms * 10.0) or 0.0)

    wall_coords = _block_row_coordinates(eligible, interval_ms, params) if mode == "row" else {}
    times = _electronic_times(
        eligible,
        mode,
        interval_ms=interval_ms,
        base_ms=base_ms,
        selected_ids=selected_ids,
        expression=expression,
        azimuth_deg=azimuth_deg,
        gradient_from_ms=gradient_from,
        gradient_to_ms=gradient_to,
        wall_coords=wall_coords,
    )

    min_time = min(times.values()) if times else 0.0
    starters = [hole.id for hole in eligible if abs(times.get(hole.id, min_time) - min_time) < 1e-6]
    channels = [
        ElectronicChannel(id=f"ch-{hole.id}", hole_id=hole.id, time_ms=round(times[hole.id], 3), label=mode)
        for hole in eligible
        if hole.id in times
    ]
    detonators = [
        Detonator(
            id=f"det-{channel.hole_id}",
            hole_id=channel.hole_id,
            delay_ms=0.0,
            kind="electronic",
            channel_id=channel.id,
        )
        for channel in channels
    ]
    downhole_connectors = []
    downhole_delay_ms: dict[str, float] = {}
    if downhole_ms > 0:
        downhole_delay_ms = {hole.id: downhole_ms for hole in eligible}
        downhole_connectors = [
            DownholeConnector(id=f"dh-{hole.id}", hole_id=hole.id, delay_ms=downhole_ms, kind="electronic")
            for hole in eligible
        ]

    network = InitiationNetwork(
        system="electronic",
        starters=starters,
        connectors=[],
        downhole_delay_ms=downhole_delay_ms,
        electronic_times_ms={channel.hole_id: channel.time_ms for channel in channels},
        detonators=detonators,
        surface_connectors=[],
        downhole_connectors=downhole_connectors,
        detonating_cords=[],
        starter_items=[Starter(id=f"st-{hole_id}", hole_id=hole_id) for hole_id in starters],
        electronic_channels=channels,
        timing_mode=mode,
        timing_expression=expression,
        timing_params={
            "interval_ms": interval_ms,
            "base_ms": base_ms,
            "downhole_delay_ms": downhole_ms,
            "direction_azimuth_deg": azimuth_deg,
            "gradient_from_ms": gradient_from,
            "gradient_to_ms": gradient_to,
        },
        selected_hole_ids=selected_ids,
    )
    network.sync_legacy_from_v2()
    return network


def _electronic_times(
    holes: list[Hole],
    mode: str,
    *,
    interval_ms: float,
    base_ms: float,
    selected_ids: list[str],
    expression: str,
    azimuth_deg: float,
    gradient_from_ms: float,
    gradient_to_ms: float,
    wall_coords: dict[str, float] | None = None,
) -> dict[str, float]:
    min_col, max_col, center_col = _grid_extents(holes)
    times: dict[str, float] = {}

    if mode == "selection":
        ordered = _sorted_selected(holes, selected_ids)
        for index, hole in enumerate(ordered):
            times[hole.id] = base_ms + index * interval_ms
        for hole in holes:
            times.setdefault(hole.id, base_ms)
        return times

    if mode == "direction":
        angle = math.radians(azimuth_deg)
        ux, uy = math.sin(angle), math.cos(angle)
        projections = [
            (hole, hole.collar.x * ux + hole.collar.y * uy) for hole in holes
        ]
        values = [item[1] for item in projections]
        lo, hi = min(values), max(values)
        span = hi - lo if hi > lo else 1.0
        for hole, projection in projections:
            times[hole.id] = base_ms + ((projection - lo) / span) * interval_ms * max(1, len(holes) - 1)
        return times

    if mode == "gradient":
        xs = [hole.collar.x for hole in holes]
        ys = [hole.collar.y for hole in holes]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1.0
        for hole in holes:
            t = ((hole.collar.x - x0) * dx + (hole.collar.y - y0) * dy) / (length * length)
            t = max(0.0, min(1.0, t))
            times[hole.id] = gradient_from_ms + t * (gradient_to_ms - gradient_from_ms)
        return times

    if mode == "expression":
        if not expression.strip():
            raise TimingExprError("Задайте выражение тайминга.")
        for index, hole in enumerate(sorted(holes, key=lambda item: (logical_row(item.row), item.col, item.id))):
            variables = {
                "row": float(logical_row(hole.row)),
                "col": float(hole.col),
                "x": float(hole.collar.x),
                "y": float(hole.collar.y),
                "z": float(hole.collar.z),
                "index": float(index),
                "hole_index": float(index),
                "i": float(index),
                "n": float(len(holes)),
                "interval": float(interval_ms),
                "base": float(base_ms),
            }
            times[hole.id] = evaluate_timing_expression(expression, variables)
        return times

    scheme = {
        "row": "row",
        "v_pattern": "diagonal_v",
        "diagonal": "echelon",
    }.get(mode, "row")
    if scheme == "row":
        coords = {hole.id: float(logical_row(hole.row)) for hole in holes}
        coords.update(wall_coords or {})
        origin = min(coords.values())
        for hole in holes:
            times[hole.id] = base_ms + (coords[hole.id] - origin) * interval_ms
        return times
    # Отсчёт — ноль, но не выше самой ранней волны: ряды впереди дают отрицательные
    # координаты, и без этого первая скважина стартовала бы до базового времени.
    waves = _anchor_manual(
        holes, {hole.id: _wave_coordinate(hole, scheme, center_col, min_col, max_col) for hole in holes}
    )
    origin = min(0.0, min(waves.values()))
    for hole in holes:
        times[hole.id] = base_ms + (waves[hole.id] - origin) * interval_ms
    return times


def add_surface_tie(
    network: InitiationNetwork,
    from_hole: str,
    to_hole: str,
    delay_ms: float,
    kind: str = "",
) -> InitiationNetwork:
    """Add or replace a manual surface tie."""
    if not from_hole or not to_hole or from_hole == to_hole:
        return network
    connector_kind = kind or _connector_kind(network.system)
    connector_id = f"sc-{from_hole}-{to_hole}"
    remaining = [
        item
        for item in network.surface_connectors
        if not (item.from_hole == from_hole and item.to_hole == to_hole)
    ]
    remaining.append(
        SurfaceConnector(
            id=connector_id,
            from_hole=from_hole,
            to_hole=to_hole,
            delay_ms=float(delay_ms),
            kind=connector_kind,
        )
    )
    network.surface_connectors = remaining
    if from_hole not in network.starters and not any(
        item.to_hole == from_hole for item in network.surface_connectors
    ):
        if from_hole not in {item.hole_id for item in network.starter_items}:
            network.starter_items.append(Starter(id=f"st-{from_hole}", hole_id=from_hole))
    network.sync_legacy_from_v2()
    return network


def remove_surface_tie(network: InitiationNetwork, connector_id: str) -> InitiationNetwork:
    network.surface_connectors = [item for item in network.surface_connectors if item.id != connector_id]
    if not any(item.id == connector_id for item in network.surface_connectors):
        # Also drop a matching legacy pair if the id encodes from-to.
        if connector_id.startswith("sc-"):
            parts = connector_id[3:].split("-", 1)
            if len(parts) == 2:
                from_hole, to_hole = parts
                network.surface_connectors = [
                    item
                    for item in network.surface_connectors
                    if not (item.from_hole == from_hole and item.to_hole == to_hole)
                ]
    network.sync_legacy_from_v2()
    return network


def update_surface_tie(network: InitiationNetwork, connector_id: str, delay_ms: float) -> InitiationNetwork:
    updated: list[SurfaceConnector] = []
    for item in network.surface_connectors:
        if item.id == connector_id:
            updated.append(replace(item, delay_ms=float(delay_ms)))
        else:
            updated.append(item)
    network.surface_connectors = updated
    network.sync_legacy_from_v2()
    return network


def toggle_starter(network: InitiationNetwork, hole_id: str) -> InitiationNetwork:
    existing = {item.hole_id: item for item in network.starter_items}
    if hole_id in existing:
        network.starter_items = [item for item in network.starter_items if item.hole_id != hole_id]
    else:
        network.starter_items.append(Starter(id=f"st-{hole_id}", hole_id=hole_id))
    network.sync_legacy_from_v2()
    return network


def _surface_edges(network: InitiationNetwork, holes: list[Hole]) -> dict[str, list[tuple[str, float]]]:
    adjacency: dict[str, list[tuple[str, float]]] = {}
    connectors = network.surface_connectors or [
        SurfaceConnector(
            id=f"sc-{item.from_hole}-{item.to_hole}",
            from_hole=item.from_hole,
            to_hole=item.to_hole,
            delay_ms=item.delay_ms,
            kind=item.kind,
        )
        for item in network.connectors
    ]
    for item in connectors:
        adjacency.setdefault(item.from_hole, []).append((item.to_hole, max(0.0, item.delay_ms)))

    holes_by_id = {hole.id: hole for hole in holes}
    for cord in network.detonating_cords:
        velocity = cord.velocity_m_s if cord.velocity_m_s > 0 else DETCORD_VELOCITY_M_S
        for left_id, right_id in zip(cord.hole_ids, cord.hole_ids[1:]):
            left = holes_by_id.get(left_id)
            right = holes_by_id.get(right_id)
            if left is None or right is None:
                continue
            distance_m = math.hypot(right.collar.x - left.collar.x, right.collar.y - left.collar.y)
            delay = (distance_m / velocity) * 1000.0 + max(0.0, cord.relay_delay_ms)
            adjacency.setdefault(left_id, []).append((right_id, delay))
            adjacency.setdefault(right_id, []).append((left_id, delay))
    return adjacency


def _starter_seeds(network: InitiationNetwork, hole_ids: set[str]) -> list[tuple[float, str]]:
    seeds: list[tuple[float, str]] = []
    if network.starter_items:
        for item in network.starter_items:
            if item.hole_id in hole_ids:
                seeds.append((max(0.0, item.delay_ms), item.hole_id))
    else:
        for hole_id in network.starters:
            if hole_id in hole_ids:
                seeds.append((0.0, hole_id))
    return seeds


def _downhole_for(network: InitiationNetwork, hole_id: str) -> float:
    for item in network.downhole_connectors:
        if item.hole_id == hole_id and item.deck_index is None and item.primer_index is None:
            return item.delay_ms
    return network.downhole_delay_ms.get(hole_id, 0.0)


def _offset_for(network: InitiationNetwork, hole_id: str, *, deck_index: int | None, primer_index: int | None) -> float:
    for channel in network.electronic_channels:
        if (
            channel.hole_id == hole_id
            and channel.deck_index == deck_index
            and channel.primer_index == primer_index
        ):
            hole_time = network.electronic_times_ms.get(hole_id)
            if hole_time is None:
                hole_channel = next(
                    (
                        item
                        for item in network.electronic_channels
                        if item.hole_id == hole_id and item.deck_index is None and item.primer_index is None
                    ),
                    None,
                )
                hole_time = hole_channel.time_ms if hole_channel else 0.0
            return channel.time_ms - hole_time
    for item in network.downhole_connectors:
        if item.hole_id == hole_id and item.deck_index == deck_index and item.primer_index == primer_index:
            return item.delay_ms
    for item in network.detonators:
        if item.hole_id == hole_id and item.deck_index == deck_index and item.primer_index == primer_index:
            return item.delay_ms
    return 0.0


@dataclass
class TimingResult:
    times_ms: dict[str, float]
    warnings: list[str]
    events: list[FiringEvent]


def resolve_network(
    network: InitiationNetwork,
    holes: list[Hole],
    loads: list[HoleLoad] | None = None,
) -> TimingResult:
    """Resolve hole times and hole/deck/primer firing events."""
    hole_ids = {h.id for h in holes if h.enabled}
    adjacency = _surface_edges(network, holes)

    surface_time: dict[str, float] = {}
    heap: list[tuple[float, str]] = _starter_seeds(network, hole_ids)
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
    hole_channels = {
        item.hole_id: item.time_ms
        for item in network.electronic_channels
        if item.hole_id in hole_ids and item.deck_index is None and item.primer_index is None
    }
    for hole_id in hole_ids:
        if hole_id in hole_channels:
            times[hole_id] = hole_channels[hole_id]
        elif hole_id in network.electronic_times_ms:
            times[hole_id] = network.electronic_times_ms[hole_id]
        elif hole_id in surface_time:
            times[hole_id] = surface_time[hole_id] + _downhole_for(network, hole_id)

    warnings = [
        f"Скважина {hole_id} не подключена к схеме инициирования — не получает сигнал."
        for hole_id in sorted(hole_ids - set(times))
    ]
    events = build_firing_events(network, holes, loads or [], times)
    network.firing_events = events
    return TimingResult(times_ms=times, warnings=warnings, events=events)


def resolve_times(network: InitiationNetwork, holes: list[Hole]) -> tuple[dict[str, float], list[str]]:
    """Hole firing times — shortest path from starters, plus electronic overrides."""
    result = resolve_network(network, holes)
    return result.times_ms, result.warnings


def build_firing_events(
    network: InitiationNetwork,
    holes: list[Hole],
    loads: list[HoleLoad],
    times: dict[str, float],
) -> list[FiringEvent]:
    """Hole-, deck- and primer-level events for the resolved hole times."""
    loads_by_hole = {load.hole_id: load for load in loads}
    events: list[FiringEvent] = []
    for hole in holes:
        if not hole.enabled or hole.id not in times:
            continue
        hole_time = times[hole.id]
        load = loads_by_hole.get(hole.id)
        hole_mass = load.total_charge_kg if load else 0.0
        events.append(
            FiringEvent(
                id=f"fire-{hole.id}",
                hole_id=hole.id,
                time_ms=round(hole_time, 3),
                level="hole",
                mass_kg=hole_mass,
            )
        )
        if load is None:
            continue
        for index, deck in enumerate(load.decks):
            if not is_explosive_deck_kind(deck.kind):
                continue
            deck_time = hole_time + _offset_for(network, hole.id, deck_index=index, primer_index=None)
            events.append(
                FiringEvent(
                    id=f"fire-{hole.id}-d{index}",
                    hole_id=hole.id,
                    time_ms=round(deck_time, 3),
                    level="deck",
                    deck_index=index,
                    mass_kg=deck.mass_kg,
                )
            )
        primers = list(load.primer_items)
        if not primers and load.primers:
            from design.models import Primer

            primers = [Primer(position_m=depth) for depth in load.primers]
        for index, primer in enumerate(primers):
            primer_time = hole_time + _offset_for(network, hole.id, deck_index=None, primer_index=index)
            events.append(
                FiringEvent(
                    id=f"fire-{hole.id}-p{index}",
                    hole_id=hole.id,
                    time_ms=round(primer_time, 3),
                    level="primer",
                    primer_index=index,
                    mass_kg=primer.mass_kg,
                )
            )
    events.sort(key=lambda item: (item.time_ms, item.level, item.hole_id))
    return events
