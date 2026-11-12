"""Данные графической части Г.1–Г.5 проекта МВ (TASK-018, PR 4).

Всё, что определяет содержание листов, считается здесь, при сборке контекста
v2, и лежит в ревизии: рендер (`design/reporting/mass_blast/graphics/`)
только раскладывает это на бумаге — масштаб, поворот, подписи.

- `block_graphics` — по блоку: план (та же `plan_geometry`, что у плана
  паспорта на бурение), скважины со временем сети, разрезы А–А и Б–Б (Г.2),
  сеть (Г.4), колонки и заходки СЗМ (Г.3);
- `project_graphics` — ситуационный план Г.5: кольца опасных зон от блоков,
  ситуация в пределах зоны для людей, ближайшие точки охраняемых объектов,
  точки постов, взрывной станции, укрытия и места сбора (`layout_points`).

Чистые функции: проект блока только читается, сеть разрешается на копии.
Координаты — в СК объекта, до миллиметра.
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.ops import nearest_points, unary_union

from design.drilling_passport import plan_geometry
from design.geometry import local_basis
from design.mass_blast_objects import OBJECT_SOURCE_SITUATION, layer_geometry, project_geometry
from design.models import BlastDesign, Hole, is_explosive_deck_kind
from design.mass_blast_table import _natural
from design.timing import _downhole_for, resolve_network
from design.toe_line import crest_geometry, effective_face_angle_deg, grid_steps_m

__all__ = [
    "GRAPHICS_VERSION",
    "LAYOUT_POINT_KINDS",
    "SZM_START_FLANKS",
    "block_graphics",
    "project_graphics",
]

GRAPHICS_VERSION = "graphics-v1"
# Контур по скважинам (TASK §4): объединение кругов радиусом шаг сетки с отступом 1,9 м.
HOLE_CONTOUR_OFFSET_M = 1.9
SECTION_SHARES = (1 / 3, 2 / 3)
SECTION_NAMES = ("А", "Б")
# Линия разреза выходит за крайние скважины на 7 м (форма v0.7).
SECTION_OVERHANG_M = 7.0
# Форма: полоса ± 2 м и ряды не ближе 1,6 м — при шаге 3,7 м.
SECTION_BAND_M = 2.0
SECTION_ROW_GAP_M = 1.6
SECTION_ROW_GAP_SHARE = 0.45
# Колонка: шаг от бровки вглубь не меньше 0,4·b (иначе это сосед по ряду).
COLUMN_ADVANCE_SHARE = 0.4
COLUMN_NEIGHBOUR_SHARE = 1.5
COLUMN_ANGLE_DEG = 35.0
# Заходка начинается за тыльным рядом на 1,8 м (форма v0.8).
PASS_LEAD_M = 1.8
WINDOW_MS = 8.0                # «в окне 8 мс»: разница ≤ 8 мс, как у МИС
FORBIDDEN_ZONE_M = 20.0        # запретная зона при заряжании, п. 159 ФНП 494
SZM_START_FLANKS = ("left", "right")
ZONE_KINDS = ("people", "mechanisms", "buildings")
ZONE_SIMPLIFY_M = 1.0
SITUATION_SIMPLIFY_M = 0.5
SITUATION_MAX_POINTS = 20_000
SITUATION_MARGIN_SHARE = 0.1
SITUATION_MARGIN_M = 50.0
LAYOUT_POINT_KINDS = {
    "guard_post": "пост охраны",
    "blast_station": "взрывная станция",
    "shelter": "укрытие",
    "gather": "место сбора",
}
LABEL_OFFSET_REAR_M = 7.0
LABEL_OFFSET_FRONT_M = 3.5

XY = tuple[float, float]


def _r(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def _xy(point: Iterable[float]) -> list[float]:
    x, y = list(point)[:2]
    return [_r(x), _r(y)]


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else np.array([1.0, 0.0])


# --------------------------------------------------------------- сетка, оси

def _grid_steps(design: BlastDesign, collars: np.ndarray) -> tuple[float | None, float | None, float]:
    """Шаги a, b (только введённые) и характерный шаг — для контура и колонок."""

    params = design.pattern_params or {}
    if params.get("spacing_a_m"):
        a, b = grid_steps_m(params)
        return a, b, max(a, b)
    if len(collars) >= 2:
        from scipy.spatial import cKDTree

        distances, _ = cKDTree(collars).query(collars, k=2)
        step = float(np.median(distances[:, 1]))
        return None, None, step if step > 0 else 3.0
    return None, None, 3.0


def _front_dir(design: BlastDesign, collars: np.ndarray) -> np.ndarray:
    """Направление рядов: ось рядов сетки, нет её — самая длинная сторона оболочки (форма)."""

    azimuth = (design.pattern_params or {}).get("row_azimuth_deg")
    if isinstance(azimuth, (int, float)) and not isinstance(azimuth, bool):
        row_dir, _advance = local_basis(float(azimuth))
        return _unit(np.array(row_dir, dtype=float))
    if len(collars) >= 3:
        hull = MultiPoint([tuple(p) for p in collars]).convex_hull
        if isinstance(hull, Polygon):
            ring = np.array(hull.exterior.coords)
            edges = np.diff(ring, axis=0)
            return _unit(max(edges, key=lambda edge: float(np.linalg.norm(edge))))
        if isinstance(hull, LineString):
            coords = np.array(hull.coords)
            return _unit(coords[-1] - coords[0])
    return np.array([1.0, 0.0])


def _inward(front: np.ndarray, collars: np.ndarray, first: np.ndarray, crest) -> np.ndarray:
    """Нормаль к рядам от откоса вглубь блока: первый ряд (или бровка) — ближе к откосу."""

    normal = np.array([-front[1], front[0]])
    centre = collars.mean(axis=0)
    if len(first):
        ahead = first.mean(axis=0)
    elif crest is not None:
        ahead = np.array(crest.centroid.coords[0])
    else:
        return normal
    return normal if float((centre - ahead) @ normal) >= 0 else -normal


# --------------------------------------------------------------- контур

def _hole_contour(collars: np.ndarray, step: float) -> list[list[float]]:
    """Контур по скважинам: круги радиусом шаг, затем назад до отступа 1,9 м."""

    if len(collars) == 0:
        return []
    shape = unary_union([Point(float(x), float(y)).buffer(step, quad_segs=8) for x, y in collars])
    shape = shape.buffer(-step + HOLE_CONTOUR_OFFSET_M, quad_segs=8).simplify(0.3)
    if shape.is_empty:
        return []
    if shape.geom_type == "MultiPolygon":
        shape = max(shape.geoms, key=lambda item: item.area)
    return [_xy(p) for p in list(shape.exterior.coords)[:-1]]


# --------------------------------------------------------------- сеть

def _surface_links(network, ids: set[str]) -> list[dict[str, Any]]:
    links = network.surface_connectors or []
    if not links:
        return [
            {"from": item.from_hole, "to": item.to_hole, "delay_ms": _r(item.delay_ms, 1), "product": "", "kind": item.kind}
            for item in network.connectors
            if item.from_hole in ids and item.to_hole in ids
        ]
    return [
        {"from": item.from_hole, "to": item.to_hole, "delay_ms": _r(item.delay_ms, 1), "product": item.product, "kind": item.kind}
        for item in links
        if item.from_hole in ids and item.to_hole in ids
    ]


def _group_label(product: str, kind: str, delay: float, system: str) -> str:
    delay_text = f"{delay:g}".replace(".", ",")
    if product:
        return f"{product} — {delay_text} мс"
    name = {"ds_relay": "реле ДШ", "electronic": "электронный"}.get(kind, "НСИ" if system != "detcord" else "реле ДШ")
    return f"{name} {delay_text} мс"


def _window_max(times: Sequence[float]) -> int:
    ordered = sorted(times)
    best, start = 0, 0
    for end, value in enumerate(ordered):
        while value - ordered[start] > WINDOW_MS + 1e-9:
            start += 1
        best = max(best, end - start + 1)
    return best


def _network(design: BlastDesign, holes: Sequence[Hole]) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, str]]]:
    """Сеть для Г.4 и времена по скважинам; сеть разрешается на копии."""

    network = copy.deepcopy(design.network)
    ids = {hole.id for hole in holes}
    result = resolve_network(network, list(holes), copy.deepcopy(design.loads))
    system = str(network.system or "nonel")
    electronic = system == "electronic"
    times: dict[str, dict[str, Any]] = {}
    downholes: set[float] = set()
    for hole in holes:
        total = result.times_ms.get(hole.id)
        if total is None:
            times[hole.id] = {"time_ms": None, "surface_ms": None}
            continue
        down = 0.0 if electronic else float(_downhole_for(network, hole.id))
        downholes.add(round(down, 1))
        times[hole.id] = {"time_ms": _r(total, 1), "surface_ms": _r(total - down, 1)}
    # У скважины подписывается поверхностное время, если замедление в скважине
    # у всех одно (оно — в легенде); иначе — полное время.
    surface_labels = not electronic and len(downholes) == 1
    for value in times.values():
        value["label_ms"] = value["surface_ms"] if surface_labels else value["time_ms"]
    links = _surface_links(network, ids)
    groups: dict[tuple[str, str, float], dict[str, Any]] = {}
    for link in links:
        key = (link["product"], link["kind"], link["delay_ms"])
        group = groups.setdefault(key, {"label": _group_label(*key, system), "delay_ms": link["delay_ms"], "count": 0})
        group["count"] += 1
    ordered_groups = sorted(groups.items(), key=lambda item: (item[1]["delay_ms"], item[1]["label"]))
    index = {key: number for number, (key, _group) in enumerate(ordered_groups)}
    for link in links:
        link["group"] = index[(link["product"], link["kind"], link["delay_ms"])]
    cords = [
        {
            "hole_ids": [hole_id for hole_id in cord.hole_ids if hole_id in ids],
            "product": cord.product,
            "relay_delay_ms": _r(cord.relay_delay_ms, 1),
        }
        for cord in network.detonating_cords
    ]
    starters = [item.hole_id for item in network.starter_items if item.hole_id in ids] or [
        hole_id for hole_id in network.starters if hole_id in ids
    ]
    known = [value["time_ms"] for value in times.values() if value["time_ms"] is not None]
    rounded = Counter(round(value, 1) for value in known)
    unconnected = sorted((hole_id for hole_id, value in times.items() if value["time_ms"] is None), key=_natural)
    issues: list[dict[str, str]] = []
    if not links and not cords and not electronic:
        issues.append(
            {
                "level": "warning",
                "code": "graphics_network_missing",
                "message": "У проекта блока нет сети инициирования: схема взрывной сети (Г.4) — только скважины.",
                "path": "graphics.network",
            }
        )
    elif unconnected and known:
        issues.append(
            {
                "level": "warning",
                "code": "graphics_unconnected_holes",
                "message": f"Скважины не подключены к сети: {', '.join(unconnected[:10])}"
                + (f" и ещё {len(unconnected) - 10}" if len(unconnected) > 10 else "")
                + " — на Г.4 отмечены крестом.",
                "path": "graphics.network",
            }
        )
    data = {
        "system": system,
        "links": links,
        "groups": [{**group} for _key, group in ordered_groups],
        "cords": [cord for cord in cords if len(cord["hole_ids"]) >= 2],
        "starters": starters,
        "downhole_ms": sorted(downholes)[0] if surface_labels else None,
        "label_mode": "surface" if surface_labels else "total",
        "unconnected": unconnected,
        "block_ms": max(known) if known else None,
        "same_time_max": max(rounded.values()) if rounded else 0,
        "window_8ms_max": _window_max(known),
    }
    return data, times, issues


# --------------------------------------------------------------- разрезы Г.2

def _deck_rows(design: BlastDesign, hole_id: str) -> tuple[list[dict[str, Any]], list[float]]:
    load = next((item for item in design.loads if item.hole_id == hole_id), None)
    if load is None:
        return [], []
    decks = [
        {"from_m": _r(min(d.from_m, d.to_m), 2), "to_m": _r(max(d.from_m, d.to_m), 2),
         "kind": "explosive" if is_explosive_deck_kind(d.kind) else str(d.kind), "product": d.product or d.explosive_key}
        for d in load.decks
    ]
    primers = [item.position_m for item in load.primer_items] or list(load.primers)
    return sorted(decks, key=lambda d: d["from_m"]), [_r(p, 2) for p in primers]


def _line_hit(line: LineString, target, near: np.ndarray) -> np.ndarray | None:
    """Точка пересечения линии разреза с бровкой — ближайшая к `near`."""

    if target is None or target.is_empty:
        return None
    hit = line.intersection(target)
    if hit.is_empty:
        return None
    points = [np.array(p.coords[0]) for p in getattr(hit, "geoms", [hit]) if p.geom_type == "Point"]
    if not points:
        return None
    return min(points, key=lambda p: float(np.linalg.norm(p - near)))


def _sections(
    design: BlastDesign,
    holes: Sequence[Hole],
    rows: Mapping[str, Mapping[str, Any]],
    *,
    front: np.ndarray,
    inward: np.ndarray,
    steps: tuple[float | None, float | None],
    toe_lines: Sequence[Sequence[Sequence[float]]],
) -> list[dict[str, Any]]:
    if len(holes) < 2:
        return []
    collars = np.array([(h.collar.x, h.collar.y) for h in holes])
    centre = collars.mean(axis=0)
    s = (collars - centre) @ front
    t = (collars - centre) @ inward
    a, b = steps
    band = a / 2 if a else SECTION_BAND_M
    gap = SECTION_ROW_GAP_SHARE * b if b else SECTION_ROW_GAP_M
    crest = crest_geometry(design.contour) if len(design.contour.vertices) >= 3 else None
    toe = shapely.union_all([LineString(line) for line in toe_lines if len(line) >= 2]) if toe_lines else None
    angle = effective_face_angle_deg(design.contour.bench)
    result: list[dict[str, Any]] = []
    span = float(s.max() - s.min())
    for name, share in zip(SECTION_NAMES, SECTION_SHARES):
        s0 = float(s.min()) + span * share
        order = sorted(range(len(holes)), key=lambda i: abs(s[i] - s0))
        chosen: list[int] = []
        for i in order:
            if abs(s[i] - s0) > band:
                break
            if all(abs(t[i] - t[j]) > gap for j in chosen):
                chosen.append(i)
        chosen.sort(key=lambda i: t[i])
        if not chosen:
            continue
        start = centre + front * s0 + inward * (float(t.min()) - SECTION_OVERHANG_M)
        end = centre + front * s0 + inward * (float(t.max()) + SECTION_OVERHANG_M)
        line = LineString([tuple(start), tuple(end)])

        def station(point: np.ndarray) -> float:
            return float((point - start) @ inward)

        section_holes = []
        for i in chosen:
            hole = holes[i]
            row = rows.get(hole.id, {})
            decks, primers = _deck_rows(design, hole.id)
            section_holes.append(
                {
                    "hole_id": hole.id,
                    "first_row": bool(row.get("first_row")),
                    "station_m": _r(station(np.array((hole.collar.x, hole.collar.y))), 2),
                    "toe_station_m": _r(station(np.array((hole.toe.x, hole.toe.y))), 2),
                    "collar_z": _r(hole.collar.z, 2),
                    "toe_z": _r(hole.toe.z, 2),
                    "floor_z": _r(hole.collar.z - hole.bench_height_m, 2),
                    "length_m": _r(hole.length_m, 2),
                    "charge_kg": row.get("charge_kg"),
                    "stemming_m": row.get("stemming_m"),
                    "lspp_m": row.get("lspp_m"),
                    "decks": decks,
                    "primers_m": primers,
                }
            )
        first = section_holes[0]
        first_xy = np.array((holes[chosen[0]].collar.x, holes[chosen[0]].collar.y))
        crest_hit = _line_hit(line, crest, first_xy)
        toe_hit = _line_hit(line, toe, first_xy)
        floor_z = first["floor_z"]
        height = first["collar_z"] - floor_z
        run = height / math.tan(math.radians(angle)) if angle > 0 else 0.0
        if crest_hit is not None and station(crest_hit) <= first["station_m"] + 0.01:
            crest_station = station(crest_hit)
            if toe_hit is not None and station(toe_hit) < crest_station:
                toe_station = station(toe_hit)
            else:
                toe_station = crest_station - run
            source = "contour"
        else:
            lspp = first.get("lspp_m") or 3.0
            toe_station = first["station_m"] - float(lspp)
            crest_station = toe_station + run
            source = "lspp"
        result.append(
            {
                "name": name,
                "line": [_xy(start), _xy(end)],
                "holes": section_holes,
                "crest_station_m": _r(crest_station, 2),
                "toe_station_m": _r(toe_station, 2),
                "floor_z": floor_z,
                "face_angle_deg": _r(angle, 1),
                "slope_source": source,
            }
        )
    return result


# --------------------------------------------------------------- колонки и заходки Г.3

def _columns(
    holes: Sequence[Hole],
    depth: Mapping[str, float],
    links: Sequence[Mapping[str, Any]],
    *,
    step: float,
    b: float | None,
) -> list[list[str]]:
    """Колонки от бровки вглубь (форма v0.8): у каждой скважины — сосед ближе к
    бровке не дальше 1,5·шаг, в пределах ±35° от направления к бровке, и шаг
    к бровке не меньше 0,4·b. Из таких соседей берётся связанный с ней
    соединителем сети, а нет такого — ближайший: колонки повторяют цепочки
    сети там, где они идут от бровки вглубь, и не рвутся там, где сеть идёт
    вдоль рядов."""

    advance = COLUMN_ADVANCE_SHARE * (b or step)
    reach = COLUMN_NEIGHBOUR_SHARE * step
    cos_limit = math.cos(math.radians(COLUMN_ANGLE_DEG))
    ids = [hole.id for hole in holes]
    xy = {hole.id: np.array((hole.collar.x, hole.collar.y)) for hole in holes}
    linked: set[tuple[str, str]] = set()
    for link in links:
        linked.add((str(link["from"]), str(link["to"])))
        linked.add((str(link["to"]), str(link["from"])))
    parent: dict[str, str] = {}
    if len(ids) >= 2:
        from scipy.spatial import cKDTree

        tree = cKDTree(np.array([xy[hole_id] for hole_id in ids]))
        for far in ids:
            options = []
            for index in tree.query_ball_point(xy[far], reach):
                near = ids[index]
                rise = depth[far] - depth[near]
                distance = float(np.linalg.norm(xy[far] - xy[near]))
                # Направление к бровке — убывание расстояния до неё; перепад к длине шага — косинус угла.
                if near != far and rise >= advance and distance > 0 and rise / distance >= cos_limit:
                    options.append((0 if (near, far) in linked else 1, distance, near))
            if options:
                parent[far] = min(options)[2]
    children: dict[str, list[str]] = {}
    for far, near in parent.items():
        children.setdefault(near, []).append(far)
    columns: list[list[str]] = []
    used: set[str] = set()
    heads = sorted((hole_id for hole_id in ids if hole_id not in parent), key=lambda h: (depth[h], _natural(h)))
    queue = list(heads)
    while queue:
        head = queue.pop(0)
        if head in used:
            continue
        column = [head]
        used.add(head)
        current = head
        while True:
            options = [child for child in children.get(current, []) if child not in used]
            if not options:
                break
            nxt = min(options, key=lambda child: float(np.linalg.norm(xy[child] - xy[current])))
            queue += [child for child in options if child != nxt]
            column.append(nxt)
            used.add(nxt)
            current = nxt
        columns.append(column)
    return columns


def _szm(
    holes: Sequence[Hole],
    depth: Mapping[str, float],
    columns: list[list[str]],
    *,
    left: np.ndarray,
    inward: np.ndarray,
    start_flank: str,
    step: float,
    a: float | None,
) -> dict[str, Any]:
    xy = {hole.id: np.array((hole.collar.x, hole.collar.y)) for hole in holes}
    if not columns:
        return {"start_flank": start_flank, "columns": [], "passes": [], "rear_label": None, "front_label": None}
    # Порядок колонок вдоль фронта — по положению головы, с выбранного фланга.
    sign = -1.0 if start_flank == "left" else 1.0
    columns = sorted(columns, key=lambda column: (sign * float(xy[column[0]] @ left), _natural(column[0])))
    reach = COLUMN_NEIGHBOUR_SHARE * step
    passes: list[dict[str, Any]] = []
    flank = left if start_flank == "right" else -left       # в сторону конца нумерации
    for number, start in enumerate(range(0, len(columns), 2), start=1):
        pair = columns[start:start + 2]
        main = max(pair, key=len)
        other = [hole_id for column in pair if column is not main for hole_id in column]
        points: list[np.ndarray] = []
        for hole_id in main:
            if other:
                near = min(other, key=lambda o: float(np.linalg.norm(xy[o] - xy[hole_id])))
                if float(np.linalg.norm(xy[near] - xy[hole_id])) <= reach:
                    points.append((xy[hole_id] + xy[near]) / 2)
                    continue
            # Одна колонка (последняя при нечётном числе) — заходка рядом, на полшага к флангу.
            points.append(xy[hole_id] + flank * ((a or step) / 2 if not other else 0.0))
        unique: list[np.ndarray] = []
        for point in points:
            if all(float(np.linalg.norm(point - seen)) > 0.05 for seen in unique):
                unique.append(point)
        unique.sort(key=lambda p: -float(p @ inward))           # от тыла к бровке
        if len(unique) >= 2:
            lead = unique[0] + _unit(unique[0] - unique[1]) * PASS_LEAD_M
        elif unique:
            lead = unique[0] + inward * PASS_LEAD_M
            unique.append(unique[0] - inward * PASS_LEAD_M)
        else:
            continue
        passes.append({"number": number, "points": [_xy(p) for p in [lead, *unique]]})
    rears = [xy[column[-1]] for column in columns]
    fronts = [xy[column[0]] for column in columns]
    middle = len(columns) // 2
    return {
        "start_flank": start_flank,
        "columns": columns,
        "passes": passes,
        "rear_label": _xy(rears[middle] + inward * LABEL_OFFSET_REAR_M),
        "front_label": _xy(fronts[middle] - inward * LABEL_OFFSET_FRONT_M),
        "forbidden_zone_m": FORBIDDEN_ZONE_M,
    }


# --------------------------------------------------------------- блок

def block_graphics(
    design: BlastDesign,
    table_rows: Sequence[Mapping[str, Any]],
    *,
    situation_layers: Sequence[Mapping[str, Any]] = (),
    szm_start_flank: str = "left",
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Данные Г.1–Г.4 одного блока и предупреждения."""

    holes = sorted((hole for hole in design.holes if hole.enabled), key=lambda hole: _natural(hole.id))
    rows = {str(row["hole_id"]): row for row in table_rows}
    issues: list[dict[str, str]] = []
    plan = plan_geometry(design, situation_layers)
    collars = np.array([(h.collar.x, h.collar.y) for h in holes]) if holes else np.zeros((0, 2))
    a, b, step = _grid_steps(design, collars)
    contour_source = "design" if plan["contour"] else "holes"
    contour = plan["contour"] or _hole_contour(collars, step)
    network, times, network_issues = _network(design, holes)
    issues += network_issues
    hole_rows = []
    for hole in holes:
        row = rows.get(hole.id, {})
        time = times.get(hole.id, {})
        inclined = math.hypot(hole.toe.x - hole.collar.x, hole.toe.y - hole.collar.y) > 0.05
        hole_rows.append(
            {
                "hole_id": hole.id,
                "x": _r(hole.collar.x), "y": _r(hole.collar.y), "z": _r(hole.collar.z),
                "toe": _xy((hole.toe.x, hole.toe.y)) if inclined else None,
                "depth_m": _r(hole.length_m, 2),
                "charge_kg": row.get("charge_kg"),
                "first_row": bool(row.get("first_row")),
                "diameter_mm": round(hole.diameter_mm),
                "time_ms": time.get("time_ms"),
                "label_ms": time.get("label_ms"),
            }
        )
    first = np.array([(h.collar.x, h.collar.y) for h in holes if rows.get(h.id, {}).get("first_row")]).reshape(-1, 2)
    crest = crest_geometry(design.contour) if len(design.contour.vertices) >= 3 else None
    front = _front_dir(design, collars) if len(collars) else np.array([1.0, 0.0])
    inward = _inward(front, collars, first, crest) if len(collars) else np.array([0.0, 1.0])
    left = np.array([-inward[1], inward[0]])                   # левый фланг, если смотреть с откоса вглубь
    # Разрез А–А — ближе к левому флангу, Б–Б — к правому (как в эталоне).
    if float(front @ left) > 0:
        front = -front
    # «Вглубь» — одно направление на блок (нормаль к рядам от первого ряда),
    # как в генераторе формы: на изломе бровки местное направление дало бы
    # пересекающиеся колонки двух крыльев.
    depth = {h.id: float(np.array((h.collar.x, h.collar.y)) @ inward) for h in holes}
    sections = _sections(design, holes, rows, front=front, inward=inward, steps=(a, b), toe_lines=plan["crest_toe"])
    columns = _columns(holes, depth, network["links"], step=step, b=b)
    flank = szm_start_flank if szm_start_flank in SZM_START_FLANKS else "left"
    szm = _szm(holes, depth, columns, left=left, inward=inward, start_flank=flank, step=step, a=a)
    crs = design.coordinate_system
    return (
        {
            "version": GRAPHICS_VERSION,
            "plan": {**plan, "contour": contour},
            "contour_source": contour_source,
            "holes": hole_rows,
            "sections": sections,
            "network": network,
            "szm": szm,
            "crs": {
                "name": str(getattr(crs, "name", "") or ""),
                "epsg": getattr(crs, "epsg", None),
                "height_system": str(getattr(crs, "height_system", "") or ""),
            },
        },
        issues,
    )


# --------------------------------------------------------------- проект: Г.5

def _rings(geometry) -> list[list[list[float]]]:
    if geometry is None or geometry.is_empty:
        return []
    polygons = list(getattr(geometry, "geoms", [geometry]))
    return [[_xy(p) for p in list(poly.exterior.coords)[:-1]] for poly in polygons if poly.geom_type == "Polygon"]


def _clipped_situation(layers: Sequence[Mapping[str, Any]], box) -> tuple[list[dict[str, Any]], float]:
    shapes: list[tuple[str, str, list[Any]]] = []
    for layer in layers:
        parts = []
        for line in layer.get("lines") or ():
            points = [(float(p[0]), float(p[1])) for p in line.get("points") or ()]
            if len(points) < 2:
                continue
            geometry = LineString(points + ([points[0]] if line.get("closed") and len(points) >= 3 else []))
            clipped = shapely.clip_by_rect(geometry, *box)
            parts += [part for part in getattr(clipped, "geoms", [clipped]) if not part.is_empty and part.geom_type == "LineString"]
        if parts:
            shapes.append((str(layer.get("name") or ""), str(layer.get("kind") or ""), parts))
    tolerance = SITUATION_SIMPLIFY_M
    while True:
        result = []
        total = 0
        for name, kind, parts in shapes:
            lines = []
            for part in parts:
                simple = part.simplify(tolerance)
                coords = [_xy(p) for p in simple.coords]
                if len(coords) >= 2:
                    lines.append(coords)
                    total += len(coords)
            if lines:
                result.append({"name": name, "kind": kind, "lines": lines})
        if total <= SITUATION_MAX_POINTS or tolerance > 1000:
            return result, tolerance
        tolerance *= 2


def project_graphics(
    blocks: Sequence[tuple[Sequence[Sequence[float]], Sequence[tuple[float, float]]]],
    *,
    zones: Mapping[str, Mapping[str, Any]],
    objects: Sequence[Mapping[str, Any]],
    situation_layers: Sequence[Mapping[str, Any]],
    has_situation: bool,
    layout_points: Sequence[Mapping[str, Any]],
    guard_posts: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Данные Г.5. `blocks` — по блоку (кольцо контура, устья), как у охраняемых объектов."""

    issues: list[dict[str, str]] = []
    geometry = project_geometry(blocks)
    outlines = []
    for ring, collars in blocks:
        if len(ring) >= 3:
            outlines.append([_xy(p) for p in ring])
        elif collars:
            hull = MultiPoint(list(collars)).convex_hull.buffer(HOLE_CONTOUR_OFFSET_M)
            outlines += _rings(hull)
    zone_rows = []
    for kind in ZONE_KINDS:
        value = (zones.get(kind) or {}).get("value")
        if not value or geometry is None or geometry.is_empty:
            continue
        ring = geometry.buffer(float(value), quad_segs=16).simplify(ZONE_SIMPLIFY_M)
        zone_rows.append({"kind": kind, "value_m": float(value), "rings": _rings(ring)})
    people = float((zones.get("people") or {}).get("value") or 0.0)
    situation: list[dict[str, Any]] = []
    tolerance = SITUATION_SIMPLIFY_M
    if geometry is not None and not geometry.is_empty and situation_layers:
        x0, y0, x1, y1 = geometry.bounds
        reach = people * (1 + SITUATION_MARGIN_SHARE) + SITUATION_MARGIN_M
        situation, tolerance = _clipped_situation(situation_layers, (x0 - reach, y0 - reach, x1 + reach, y1 + reach))
    object_rows = []
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for layer in situation_layers:
        by_name.setdefault(str(layer.get("name") or "").strip(), []).append(layer)
    for number, item in enumerate(objects, start=1):
        key = str(item.get("key") or "")
        link = None
        if key.startswith(f"{OBJECT_SOURCE_SITUATION}:") and geometry is not None and not geometry.is_empty:
            name = key.split(":", 1)[1]
            shapes = [layer_geometry(layer.get("lines") or ()) for layer in by_name.get(name, [])]
            shapes = [shape for shape in shapes if shape is not None and not shape.is_empty]
            if shapes:
                near_block, near_object = nearest_points(geometry, shapely.union_all(shapes))
                link = [_xy(near_block.coords[0]), _xy(near_object.coords[0])]
        object_rows.append({"number": number, "key": key, "link": link})
    # Пост — по коду; при повторе кода номер — у первого поста с этим кодом.
    posts: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for index, post in enumerate(guard_posts, start=1):
        posts.setdefault(str(post.get("code") or ""), (index, post))
    point_rows: list[dict[str, Any]] = []
    placed_posts: set[str] = set()
    placed_kinds: set[str] = set()
    for index, item in enumerate(layout_points):
        kind = str(item.get("kind") or "")
        try:
            x, y = float(item.get("x")), float(item.get("y"))
        except (TypeError, ValueError):
            continue
        if kind not in LAYOUT_POINT_KINDS or not (math.isfinite(x) and math.isfinite(y)):
            continue
        ref = str(item.get("ref") or "")
        label = str(item.get("label") or "").strip()
        number = None
        if kind == "guard_post":
            if ref not in posts:
                issues.append(
                    {
                        "level": "error",
                        "code": "layout_point_unknown_post",
                        "message": f"Точка на плане ссылается на пост «{ref}», которого нет в списке постов охраны.",
                        "path": f"layout_points[{index}]",
                    }
                )
                continue
            number, post = posts[ref]
            placed_posts.add(ref)
            label = label or str(post.get("location") or "")
        placed_kinds.add(kind)
        distance = float(geometry.distance(Point(x, y))) if geometry is not None and not geometry.is_empty else None
        inside = distance is not None and people > 0 and distance < people
        if inside and kind == "guard_post":
            issues.append(
                {
                    "level": "warning",
                    "code": "guard_post_inside_zone",
                    "message": f"Пост № {number} — {round(distance)} м от блока, ближе зоны для людей {round(people)} м "
                    "(п. 35 распорядка: посты — на границе опасной зоны).",
                    "path": f"layout_points[{index}]",
                }
            )
        if inside and kind in ("blast_station", "shelter"):
            issues.append(
                {
                    "level": "warning",
                    "code": "station_inside_zone",
                    "message": f"{LAYOUT_POINT_KINDS[kind].capitalize()} — {round(distance)} м от блока, внутри зоны для людей "
                    f"{round(people)} м: проверьте, что укрытие защищённое.",
                    "path": f"layout_points[{index}]",
                }
            )
        point_rows.append(
            {
                "kind": kind,
                "number": number,
                "ref": ref,
                "label": label,
                "x": _r(x),
                "y": _r(y),
                "distance_m": None if distance is None else round(distance),
            }
        )
    missing = [
        f"пост № {index}" for index, post in enumerate(guard_posts, start=1)
        if str(post.get("code") or "") not in placed_posts
    ]
    missing += [LAYOUT_POINT_KINDS[kind] for kind in ("blast_station", "shelter") if kind not in placed_kinds]
    if missing:
        issues.append(
            {
                "level": "warning",
                "code": "layout_point_missing",
                "message": "Нет точки на плане: " + ", ".join(missing) + " — на Г.5 они только в списке.",
                "path": "layout_points",
            }
        )
    point_rows.sort(key=lambda row: (list(LAYOUT_POINT_KINDS).index(row["kind"]), row["number"] or 0))
    return (
        {
            "version": GRAPHICS_VERSION,
            "outlines": outlines,
            "zones": zone_rows,
            "situation": situation,
            "situation_tolerance_m": tolerance,
            "has_situation": bool(has_situation and situation_layers),
            "objects": object_rows,
            "points": point_rows,
        },
        issues,
    )
