"""Сводка проекта, максимальный заряд на ступень (MIC), изолинии времени,
проверки и оценка сейсмического воздействия по приведённому расстоянию.
"""
from __future__ import annotations

import math
from typing import Any

from collections import Counter

from design.editing import spacing_report
from design.geometry import block_volume, ensure_ccw, point_in_polygon, true_burden
from design.models import HOLE_KINDS, BlastDesign, FiringEvent, Hole, is_explosive_deck_kind
from design.timing import resolve_network

Point2 = tuple[float, float]


def summary(design: BlastDesign) -> dict[str, Any]:
    enabled = [h for h in design.holes if h.enabled]
    production = [h for h in enabled if h.kind == "production"]
    contour_holes = [h for h in enabled if h.kind == "contour"]
    counts = Counter(h.kind for h in enabled)
    footage = sum(h.length_m for h in enabled)

    enabled_ids = {h.id for h in enabled}
    active_loads = [ld for ld in design.loads if ld.hole_id in enabled_ids]
    loads_by_hole = {ld.hole_id: ld for ld in active_loads}
    total_charge_kg = sum(ld.total_charge_kg for ld in active_loads)
    charged = [ld for ld in active_loads if ld.total_charge_kg > 0]
    avg_q = sum(ld.specific_q_kg_m3 for ld in charged) / len(charged) if charged else 0.0

    explosive_breakdown: dict[str, float] = {}
    for ld in active_loads:
        for deck in ld.decks:
            if is_explosive_deck_kind(deck.kind) and deck.explosive_key:
                explosive_breakdown[deck.explosive_key] = (
                    explosive_breakdown.get(deck.explosive_key, 0.0) + deck.mass_kg
                )

    return {
        "hole_count": len(enabled),
        "production_hole_count": len(production),
        "contour_hole_count": len(contour_holes),
        "hole_counts_by_kind": {kind: counts.get(kind, 0) for kind in HOLE_KINDS},
        "drilling_footage_m": round(footage, 2),
        "block_volume_m3": round(block_volume(design.contour, design.surfaces), 2),
        "total_charge_kg": round(total_charge_kg, 2),
        "avg_specific_q_kg_m3": round(avg_q, 4),
        "explosive_breakdown_kg": {k: round(v, 2) for k, v in explosive_breakdown.items()},
        "charged_hole_count": len(charged),
        "loads_by_hole_count": len(loads_by_hole),
    }


def charge_per_delay(
    times: dict[str, float],
    loads: list,
    window_ms: float = 8.0,
    events: list[FiringEvent] | None = None,
) -> dict[str, Any]:
    """Максимальная масса ВВ, срабатывающая в любом скользящем окне `window_ms`.

    Это MIC (maximum instantaneous charge) — ключевой параметр для оценки
    сейсмического воздействия: чем больше ВВ детонирует практически
    одновременно, тем выше колебания грунта. Deck-level firing events are
    preferred when they carry mass; otherwise hole totals are used.
    """
    if events:
        deck_events = [item for item in events if item.level == "deck" and item.mass_kg > 0]
        source = deck_events or [item for item in events if item.level == "hole" and item.mass_kg > 0]
        timed = sorted((item.time_ms, item.hole_id, item.mass_kg) for item in source)
        if timed:
            return _mic_from_events(timed, window_ms)

    mass_by_hole = {ld.hole_id: ld.total_charge_kg for ld in loads if ld.total_charge_kg > 0}
    timed = sorted((times[hid], hid, mass_by_hole[hid]) for hid in mass_by_hole if hid in times)
    if not timed:
        return {"mic_kg": 0.0, "window_start_ms": 0.0, "hole_ids": []}
    return _mic_from_events(timed, window_ms)


def _mic_from_events(events: list[tuple[float, str, float]], window_ms: float) -> dict[str, Any]:
    best_mass = 0.0
    best_start = events[0][0]
    best_ids: list[str] = []
    left = 0
    running = 0.0
    for right in range(len(events)):
        running += events[right][2]
        while events[right][0] - events[left][0] > window_ms:
            running -= events[left][2]
            left += 1
        if running > best_mass:
            best_mass = running
            best_start = events[left][0]
            best_ids = [events[i][1] for i in range(left, right + 1)]
    return {"mic_kg": round(best_mass, 2), "window_start_ms": best_start, "hole_ids": best_ids}


def _idw_value(x: float, y: float, points: list[tuple[float, float, float]], power: int = 2, k: int = 4) -> float:
    scored = []
    for px, py, val in points:
        d2 = (x - px) ** 2 + (y - py) ** 2
        if d2 < 1e-9:
            return val
        scored.append((d2, val))
    scored.sort(key=lambda item: item[0])
    nearest = scored[:k]
    weights = [1.0 / (d2**power) for d2, _ in nearest]
    total_w = sum(weights)
    if total_w <= 0:
        return sum(val for _, val in nearest) / len(nearest)
    return sum(w * val for w, (_, val) in zip(weights, nearest)) / total_w


_EDGE_PAIRS: dict[int, list[tuple[str, str]]] = {
    0: [],
    1: [("left", "bottom")],
    2: [("bottom", "right")],
    3: [("left", "right")],
    4: [("right", "top")],
    5: [("left", "bottom"), ("right", "top")],
    6: [("bottom", "top")],
    7: [("left", "top")],
    8: [("top", "left")],
    9: [("bottom", "top")],
    10: [("bottom", "right"), ("top", "left")],
    11: [("right", "top")],
    12: [("left", "right")],
    13: [("bottom", "right")],
    14: [("left", "bottom")],
    15: [],
}


def _edge_point(edge: str, p00, p10, p11, p01, v00, v10, v11, v01, level: float) -> Point2:
    if edge == "bottom":
        a, b, va, vb = p00, p10, v00, v10
    elif edge == "right":
        a, b, va, vb = p10, p11, v10, v11
    elif edge == "top":
        a, b, va, vb = p11, p01, v11, v01
    else:  # left
        a, b, va, vb = p01, p00, v01, v00
    t = 0.5 if vb == va else (level - va) / (vb - va)
    t = max(0.0, min(1.0, t))
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def timing_isolines(
    times: dict[str, float], holes: list[Hole], step_ms: float, resolution_m: float | None = None
) -> list[dict[str, Any]]:
    """Изолинии времени срабатывания — интерполяция на регулярную сетку
    (обратные квадраты расстояний по ближайшим 4 скважинам) + marching squares.

    Возвращает список сегментов ломаных по уровням; сегменты внутри одного
    уровня не сшиты в непрерывные полилинии — для визуализации на плане это
    не требуется, а сшивка добавила бы существенную сложность без пользы.
    """
    points = [
        (h.collar.x, h.collar.y, times[h.id]) for h in holes if h.enabled and h.id in times
    ]
    if len(points) < 4 or step_ms <= 0:
        return []

    xs_raw = [p[0] for p in points]
    ys_raw = [p[1] for p in points]
    x_min, x_max = min(xs_raw) - 2.0, max(xs_raw) + 2.0
    y_min, y_max = min(ys_raw) - 2.0, max(ys_raw) + 2.0
    width, height = x_max - x_min, y_max - y_min
    if width <= 0 or height <= 0:
        return []

    if resolution_m is None:
        resolution_m = max(1.0, min(15.0, math.hypot(width, height) / 30.0))

    nx = max(4, min(60, int(width / resolution_m) + 2))
    ny = max(4, min(60, int(height / resolution_m) + 2))
    xs = [x_min + i * (width / (nx - 1)) for i in range(nx)]
    ys = [y_min + j * (height / (ny - 1)) for j in range(ny)]

    grid = [[_idw_value(x, y, points) for x in xs] for y in ys]

    t_min = min(p[2] for p in points)
    t_max = max(p[2] for p in points)
    if t_max <= t_min:
        return []

    isolines: list[dict[str, Any]] = []
    level = math.ceil(t_min / step_ms) * step_ms
    while level < t_max:
        segments: list[list[Point2]] = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                v00, v10, v11, v01 = grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]
                case = (
                    (1 if v00 >= level else 0)
                    | (2 if v10 >= level else 0)
                    | (4 if v11 >= level else 0)
                    | (8 if v01 >= level else 0)
                )
                pairs = _EDGE_PAIRS[case]
                if not pairs:
                    continue
                p00, p10 = (xs[i], ys[j]), (xs[i + 1], ys[j])
                p11, p01 = (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])
                for edge_a, edge_b in pairs:
                    pa = _edge_point(edge_a, p00, p10, p11, p01, v00, v10, v11, v01, level)
                    pb = _edge_point(edge_b, p00, p10, p11, p01, v00, v10, v11, v01, level)
                    segments.append([list(pa), list(pb)])
        if segments:
            isolines.append({"time_ms": round(level, 1), "segments": segments})
        level += step_ms

    return isolines


def validate(
    design: BlastDesign,
    *,
    min_burden_m: float = 1.0,
    min_stemming_m: float = 0.5,
    spacing_tolerance_m: float = 0.5,
) -> list[dict[str, Any]]:
    """Предупреждения проекта: не утверждение соответствия ФНП, а ориентировочные
    пороги для помощи проектировщику."""
    warnings: list[dict[str, Any]] = []
    enabled = [h for h in design.holes if h.enabled]
    holes_by_id = {h.id: h for h in enabled}

    boundary = ensure_ccw(design.contour.points_xy)
    if len(boundary) >= 3:
        for h in enabled:
            if not point_in_polygon((h.collar.x, h.collar.y), boundary):
                warnings.append(
                    {
                        "code": "hole_outside_contour",
                        "hole_id": h.id,
                        "message": f"Скважина {h.id} находится вне контура блока.",
                    }
                )

    pattern_params = design.pattern_params or {}
    expected_a = pattern_params.get("spacing_a_m")
    expected_b = pattern_params.get("burden_b_m")
    report = spacing_report(
        enabled,
        expected_a_m=float(expected_a) if expected_a is not None else None,
        expected_b_m=float(expected_b) if expected_b is not None else None,
        tolerance_m=spacing_tolerance_m,
    )
    for item in report["flagged"]:
        warnings.append(
            {
                "code": "hole_spacing",
                "hole_id": item["hole_id"],
                "message": (
                    f"Расстояние {item['hole_id']} → {item['neighbour_id']} = "
                    f"{item['distance_m']:.2f} м, отклоняется от проектного шага."
                ),
            }
        )

    for h in enabled:
        if h.kind not in ("production", "buffer"):
            continue
        burden = true_burden(h, design.contour)
        if burden is not None and burden < min_burden_m:
            warnings.append(
                {
                    "code": "burden_too_small",
                    "hole_id": h.id,
                    "message": f"ЛНС скважины {h.id} ≈ {burden:.2f} м — меньше допустимого {min_burden_m:.2f} м.",
                }
            )

    for load in design.loads:
        hole = holes_by_id.get(load.hole_id)
        if hole is None:
            continue
        length = hole.length_m
        for deck in load.decks:
            if deck.to_m > length + 1e-6:
                warnings.append(
                    {
                        "code": "charge_exceeds_hole",
                        "hole_id": hole.id,
                        "message": f"Заряд скважины {hole.id} выходит за глубину скважины.",
                    }
                )
                break
        stemming = next((d for d in load.decks if d.kind == "stemming"), None)
        if stemming is not None and (stemming.to_m - stemming.from_m) < min_stemming_m:
            warnings.append(
                {
                    "code": "stemming_too_short",
                    "hole_id": hole.id,
                    "message": f"Забойка скважины {hole.id} короче минимальной {min_stemming_m:.2f} м.",
                }
            )

    if (
        design.network.connectors
        or design.network.starters
        or design.network.surface_connectors
        or design.network.starter_items
        or design.network.electronic_channels
        or design.network.electronic_times_ms
    ):
        result = resolve_network(design.network, enabled, design.loads)
        for message in result.warnings:
            hole_id = None
            for hid in sorted((h.id for h in enabled), key=len, reverse=True):
                if hid in message:
                    hole_id = hid
                    break
            warnings.append({"code": "unconnected_holes", "hole_id": hole_id, "message": message})
        warnings.extend(timing_diagnostics(design, result.times_ms, result.events))

    return warnings


def _neighbour_pairs(holes: list[Hole], max_distance_m: float) -> list[tuple[Hole, Hole, float]]:
    pairs: list[tuple[Hole, Hole, float]] = []
    for i, left in enumerate(holes):
        for right in holes[i + 1 :]:
            distance = math.hypot(left.collar.x - right.collar.x, left.collar.y - right.collar.y)
            if 0 < distance <= max_distance_m:
                pairs.append((left, right, distance))
    return pairs


def _face_distance(hole: Hole, design: BlastDesign) -> float | None:
    """Distance from a hole to the nearest free-face edge (plan)."""
    points = design.contour.points_xy
    n = len(points)
    if n < 2:
        return None
    edges = list(design.contour.free_faces)
    if not edges:
        # South edge of the bounding box — typical bench face when unmarked.
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        y_min = min(ys)
        return abs(hole.collar.y - y_min)
    best = None
    for edge in edges:
        if len(edge) < 2:
            continue
        a = points[edge[0] % n]
        b = points[edge[1] % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length_sq = dx * dx + dy * dy
        if length_sq < 1e-9:
            distance = math.hypot(hole.collar.x - a[0], hole.collar.y - a[1])
        else:
            t = max(0.0, min(1.0, ((hole.collar.x - a[0]) * dx + (hole.collar.y - a[1]) * dy) / length_sq))
            px, py = a[0] + t * dx, a[1] + t * dy
            distance = math.hypot(hole.collar.x - px, hole.collar.y - py)
        if best is None or distance < best:
            best = distance
    return best


def timing_diagnostics(
    design: BlastDesign,
    times: dict[str, float],
    events: list[FiringEvent] | None = None,
    *,
    min_delay_ms: float = 8.0,
    mic_window_ms: float = 8.0,
    high_mic_fraction: float = 0.35,
    high_mic_kg: float = 2000.0,
) -> list[dict[str, Any]]:
    """Initiation-network diagnostics used by analyze/validate."""
    warnings: list[dict[str, Any]] = []
    enabled = [h for h in design.holes if h.enabled]
    if not times:
        return warnings

    if design.network.system == "electronic":
        rounded: dict[float, list[str]] = {}
        for hole_id, time_ms in times.items():
            rounded.setdefault(round(time_ms, 1), []).append(hole_id)
        for time_ms, hole_ids in sorted(rounded.items()):
            if len(hole_ids) > 1:
                warnings.append(
                    {
                        "code": "duplicate_times",
                        "hole_id": hole_ids[0],
                        "message": (
                            f"Одинаковое время {time_ms:.1f} мс у скважин {', '.join(hole_ids[:8])}"
                            + ("…" if len(hole_ids) > 8 else "")
                            + "."
                        ),
                    }
                )

    pattern_params = design.pattern_params or {}
    expected_a = float(pattern_params.get("spacing_a_m") or 5.0)
    expected_b = float(pattern_params.get("burden_b_m") or 4.0)
    neighbour_limit = 1.6 * max(expected_a, expected_b)
    for left, right, _distance in _neighbour_pairs(enabled, neighbour_limit):
        if left.id not in times or right.id not in times:
            continue
        delta = abs(times[left.id] - times[right.id])
        if 0 < delta < min_delay_ms:
            warnings.append(
                {
                    "code": "insufficient_delays",
                    "hole_id": left.id,
                    "message": (
                        f"Между {left.id} и {right.id} всего {delta:.1f} мс "
                        f"(меньше {min_delay_ms:.0f} мс)."
                    ),
                }
            )

    face_by_id = {h.id: _face_distance(h, design) for h in enabled}
    inversions = 0
    for left, right, _distance in _neighbour_pairs(enabled, neighbour_limit):
        if left.id not in times or right.id not in times:
            continue
        d_left, d_right = face_by_id.get(left.id), face_by_id.get(right.id)
        if d_left is None or d_right is None:
            continue
        if d_left + 0.5 < d_right and times[left.id] > times[right.id] + min_delay_ms:
            inversions += 1
            if inversions <= 4:
                warnings.append(
                    {
                        "code": "unexpected_firing_order",
                        "hole_id": left.id,
                        "message": (
                            f"Скважина {right.id} дальше от откоса, но срабатывает раньше {left.id}."
                        ),
                    }
                )

    distances = [face_by_id[h.id] for h in enabled if h.id in times and face_by_id.get(h.id) is not None]
    if len(distances) >= 4:
        cutoff = min(distances) + 0.35 * (max(distances) - min(distances) or 1.0)
        front_times = [
            times[h.id]
            for h in enabled
            if h.id in times and face_by_id.get(h.id) is not None and face_by_id[h.id] <= cutoff
        ]
        back_times = [
            times[h.id]
            for h in enabled
            if h.id in times and face_by_id.get(h.id) is not None and face_by_id[h.id] > cutoff
        ]
        if front_times and back_times and (sum(back_times) / len(back_times)) + min_delay_ms < (
            sum(front_times) / len(front_times)
        ):
            warnings.append(
                {
                    "code": "relief_direction",
                    "hole_id": None,
                    "message": "Фронт инициирования идёт к открытому откосу, а не от него — нет линии наименьшего сопротивления.",
                }
            )

    mic = charge_per_delay(times, design.loads, window_ms=mic_window_ms, events=events)
    total_charge = sum(ld.total_charge_kg for ld in design.loads)
    mic_limit = max(high_mic_kg, high_mic_fraction * total_charge) if total_charge > 0 else high_mic_kg
    if mic["mic_kg"] > mic_limit and len(mic["hole_ids"]) > 2:
        warnings.append(
            {
                "code": "high_mic",
                "hole_id": mic["hole_ids"][0] if mic["hole_ids"] else None,
                "message": (
                    f"Высокий MIC: {mic['mic_kg']:.0f} кг в окне {mic_window_ms:.0f} мс "
                    f"(скважины {', '.join(mic['hole_ids'][:6])})."
                ),
            }
        )

    hole_ids = {h.id for h in enabled}
    adjacency: dict[str, set[str]] = {hid: set() for hid in hole_ids}
    for item in design.network.surface_connectors or design.network.connectors:
        from_hole = getattr(item, "from_hole", None)
        to_hole = getattr(item, "to_hole", None)
        if from_hole in adjacency and to_hole in adjacency:
            adjacency[from_hole].add(to_hole)
            adjacency[to_hole].add(from_hole)
    for cord in design.network.detonating_cords:
        for left_id, right_id in zip(cord.hole_ids, cord.hole_ids[1:]):
            if left_id in adjacency and right_id in adjacency:
                adjacency[left_id].add(right_id)
                adjacency[right_id].add(left_id)

    starters = {item.hole_id for item in design.network.starter_items} or set(design.network.starters)
    visited: set[str] = set()

    def _walk(start: str) -> set[str]:
        stack = [start]
        component: set[str] = set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(adjacency.get(node, ()))
        return component

    isolated: list[str] = []
    for hole_id in sorted(hole_ids):
        if hole_id in visited:
            continue
        component = _walk(hole_id)
        visited |= component
        if component.isdisjoint(starters) and any(
            hole_id in times or neighbour in times for neighbour in component
        ):
            isolated.extend(sorted(component))
        elif component.isdisjoint(starters) and any(adjacency[node] for node in component):
            isolated.extend(sorted(component))
    if isolated:
        sample = isolated[:8]
        warnings.append(
            {
                "code": "isolated_network_branches",
                "hole_id": sample[0],
                "message": (
                    "Изолированные ветви сети: "
                    + ", ".join(sample)
                    + ("…" if len(isolated) > 8 else "")
                    + "."
                ),
            }
        )

    return warnings


def estimate_ppv(mic_kg: float, distance_m: float, k: float, n: float) -> float:
    """Legacy single-point PPV in the ``q_cube_over_r`` convention: V = K·(Q^(1/3)/R)^n.

    Site-calibrated laws live on ``VibrationModel`` and must carry their own
    scaled-distance convention. Do not reuse this helper with a square-root
    or R/Q law — call ``design.vibration.predict_ppv`` instead.
    """
    from design.models import VibrationModel
    from design.vibration import CONVENTION_Q_CUBE_OVER_R, predict_ppv

    model = VibrationModel(id="legacy-analyze", k=k, n=n, scaled_distance=CONVENTION_Q_CUBE_OVER_R)
    return predict_ppv(mic_kg, distance_m, model)
