"""Manual edits of an already generated hole pattern."""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from design.geometry import (
    angle_azimuth,
    distance_to_free_faces,
    drape_collar,
    hole_from_collar,
)
from design.models import (
    FACE_TOE_KIND,
    BlockContour,
    Hole,
    Point3,
    logical_row,
    row_family,
)
from design.toe_line import floor_point

# Запас к допуску шага, м: шаг ровно на допуске не мигает из-за округления.
SPACING_EPS_M = 1e-6


def _distance2d(a: Hole, b: Hole) -> float:
    return math.hypot(a.collar.x - b.collar.x, a.collar.y - b.collar.y)


def neighbours(
    holes: list[Hole], hole_id: str, k: int = 6, radius_m: float | None = None
) -> list[Hole]:
    """k ближайших к заданной скважине (по устью), опционально в пределах radius_m."""
    target = next((h for h in holes if h.id == hole_id), None)
    if target is None:
        return []
    candidates = [h for h in holes if h.id != hole_id and h.enabled]
    scored = sorted(candidates, key=lambda h: _distance2d(target, h))
    if radius_m is not None:
        scored = [h for h in scored if _distance2d(target, h) <= radius_m]
    return scored[:k]


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "avg": 0.0, "max": 0.0}
    return {"min": min(values), "avg": sum(values) / len(values), "max": max(values)}


def spacing_report(
    holes: list[Hole],
    expected_a_m: float | None = None,
    expected_b_m: float | None = None,
    tolerance_m: float = 0.5,
) -> dict[str, Any]:
    """Фактические шаги сетки по факту и отклонения от проектных значений.

    В пределах ряда (`Hole.row`) шаг вдоль ряда считается между соседями по
    `col`; между соседними рядами — по ближайшей скважине следующего ряда.
    Шаги меряются между точками оси на уровне подошвы (`floor_point`), а не
    между устьями: плавный переход у откоса держит решётку именно у подошвы
    (устья соседних рангов сближены намеренно). У вертикальных скважин это те
    же расстояния, что между устьями. Но результат `hole_spacing` меняется у
    существующих проектов с углом паспорта на неровной кровле (длины, а с ними
    точки на подошве, у скважин разные) и у скважин, наклонённых вручную, —
    их шаг считается там, где ось встречает подошву. Пара у откоса
    (`face_toe`) стоит в ряду и столбце своей вертикальной в 1 м от неё — не
    шаг сетки, в отчёт не входит. Сравнение с допуском — с запасом
    `SPACING_EPS_M` на ошибку округления.
    """
    enabled = [h for h in holes if h.enabled and h.kind != FACE_TOE_KIND]
    at_floor = {h.id: floor_point(h) for h in enabled}

    def _distance2d(a: Hole, b: Hole) -> float:
        (ax, ay), (bx, by) = at_floor[a.id], at_floor[b.id]
        return math.hypot(ax - bx, ay - by)

    # Ключ — группа рядов и логический номер: ряды впереди первого идут подряд у
    # первого ряда, контурные (-1…-n) и буферные (-10) не сливаются с сеткой.
    by_row: dict[tuple[str, int], list[Hole]] = {}
    for h in enabled:
        by_row.setdefault((row_family(h.kind), logical_row(h.row)), []).append(h)

    a_values: list[float] = []
    flagged: list[dict[str, Any]] = []
    for group in by_row.values():
        ordered = sorted(group, key=lambda h: h.col)
        for h1, h2 in zip(ordered, ordered[1:]):
            d = _distance2d(h1, h2)
            a_values.append(d)
            if expected_a_m is not None and abs(d - expected_a_m) > tolerance_m + SPACING_EPS_M:
                flagged.append(
                    {"hole_id": h1.id, "neighbour_id": h2.id, "kind": "a", "distance_m": d}
                )

    b_values: list[float] = []
    rows_sorted = sorted(by_row.keys())
    for r1, r2 in zip(rows_sorted, rows_sorted[1:]):
        if r1[0] != r2[0]:
            continue
        for h1 in by_row[r1]:
            nearest = min(by_row[r2], key=lambda h2: _distance2d(h1, h2), default=None)
            if nearest is None:
                continue
            d = _distance2d(h1, nearest)
            b_values.append(d)
            if expected_b_m is not None and abs(d - expected_b_m) > tolerance_m + SPACING_EPS_M:
                flagged.append(
                    {"hole_id": h1.id, "neighbour_id": nearest.id, "kind": "b", "distance_m": d}
                )

    return {
        "spacing_a": _stats(a_values),
        "spacing_b": _stats(b_values),
        "flagged": flagged,
    }


def apply_collar_xy(
    hole: Hole,
    x: float,
    y: float,
    contour: BlockContour,
    surfaces: object | None = None,
) -> Hole:
    """Move the collar in plan and drape onto the top surface, keeping axis geometry."""
    angle_deg, azimuth_deg = angle_azimuth(hole.collar, hole.toe)
    depth_m = hole.length_m
    collar, toe = drape_collar(
        x, y, angle_deg, azimuth_deg, hole.subdrill_m, contour, surfaces, depth_m
    )
    return replace(hole, collar=collar, toe=toe, source=hole.source)


def apply_toe(hole: Hole, toe: Point3) -> Hole:
    """Replace the toe point. Collar stays put."""
    return replace(hole, toe=toe)


def apply_depth(hole: Hole, depth_m: float) -> Hole:
    """Keep collar, inclination and azimuth; change drilled length."""
    toe = hole_from_collar(hole.collar, max(0.0, float(depth_m)), hole.angle_deg, hole.azimuth_deg)
    return replace(hole, toe=toe)


def apply_inclination(hole: Hole, angle_deg: float) -> Hole:
    """Keep collar, depth and azimuth; change inclination from vertical."""
    toe = hole_from_collar(hole.collar, hole.length_m, float(angle_deg), hole.azimuth_deg)
    return replace(hole, toe=toe)


def apply_azimuth(hole: Hole, azimuth_deg: float) -> Hole:
    """Keep collar, depth and inclination; change dip azimuth."""
    toe = hole_from_collar(hole.collar, hole.length_m, hole.angle_deg, float(azimuth_deg))
    return replace(hole, toe=toe)


def apply_hole_geometry(
    hole: Hole,
    patch: dict[str, Any],
    contour: BlockContour | None = None,
    surfaces: object | None = None,
) -> Hole:
    """Apply collar / toe / depth / inclination / azimuth edits.

    Collar XY moves drape onto terrain when a contour is provided.
    """
    updated = hole
    if "collar" in patch and isinstance(patch["collar"], dict):
        raw = patch["collar"]
        x = float(raw.get("x", updated.collar.x))
        y = float(raw.get("y", updated.collar.y))
        if contour is not None:
            updated = apply_collar_xy(updated, x, y, contour, surfaces)
            if "z" in raw:
                updated = replace(
                    updated,
                    collar=replace(updated.collar, z=float(raw["z"])),
                )
        else:
            updated = replace(
                updated,
                collar=Point3(x=x, y=y, z=float(raw.get("z", updated.collar.z))),
            )
    if "x" in patch or "y" in patch:
        x = float(patch.get("x", updated.collar.x))
        y = float(patch.get("y", updated.collar.y))
        if contour is not None:
            updated = apply_collar_xy(updated, x, y, contour, surfaces)
        else:
            dx, dy = x - updated.collar.x, y - updated.collar.y
            updated = replace(
                updated,
                collar=replace(updated.collar, x=x, y=y),
                toe=replace(updated.toe, x=updated.toe.x + dx, y=updated.toe.y + dy),
            )
    if "toe" in patch and isinstance(patch["toe"], dict):
        updated = apply_toe(updated, Point3.from_dict(patch["toe"]))
    if "depth_m" in patch and patch["depth_m"] is not None:
        updated = apply_depth(updated, float(patch["depth_m"]))
    if "angle_deg" in patch and patch["angle_deg"] is not None:
        updated = apply_inclination(updated, float(patch["angle_deg"]))
    if "azimuth_deg" in patch and patch["azimuth_deg"] is not None:
        updated = apply_azimuth(updated, float(patch["azimuth_deg"]))
    if "kind" in patch and patch["kind"]:
        updated = replace(updated, kind=str(patch["kind"]))
    if "subdrill_m" in patch and patch["subdrill_m"] is not None:
        updated = replace(updated, subdrill_m=float(patch["subdrill_m"]))
    if "diameter_mm" in patch and patch["diameter_mm"] is not None:
        updated = replace(updated, diameter_mm=float(patch["diameter_mm"]))
    if "enabled" in patch:
        updated = replace(updated, enabled=bool(patch["enabled"]))
    return updated


def insert_manual_hole(
    holes: list[Hole],
    x: float,
    y: float,
    contour: BlockContour,
    params: dict[str, Any] | None = None,
    surfaces: object | None = None,
) -> Hole:
    """Insert a manual hole draped onto terrain. Caller appends it to the list."""
    params = params or {}
    angle_deg = float(params.get("angle_deg", 0.0))
    azimuth_deg = float(params.get("azimuth_deg", 0.0))
    subdrill_m = float(params.get("subdrill_m", 1.0))
    depth_override = params.get("depth_m")
    depth_m = float(depth_override) if depth_override is not None else None
    collar, toe = drape_collar(x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m)
    existing_manual = [h for h in holes if str(h.id).startswith("M-")]
    next_index = len(existing_manual) + 1
    kind = str(params.get("kind", "production"))
    return Hole(
        id=f"M-{next_index}",
        row=-1000,
        col=next_index,
        collar=collar,
        toe=toe,
        diameter_mm=float(params.get("diameter_mm", 152.0)),
        subdrill_m=subdrill_m,
        kind=kind,
        source="manual",
    )


def local_spacing(holes: list[Hole], hole: Hole) -> float | None:
    """Distance to the nearest enabled neighbour in the same row."""
    same_row = [h for h in holes if h.enabled and h.id != hole.id and h.row == hole.row]
    if not same_row:
        return None
    return min(_distance2d(hole, other) for other in same_row)


def row_index(holes: list[Hole]) -> dict[tuple[str, int], list[Hole]]:
    """Включённые скважины по (группа рядов, логический номер). Строится один раз на набор."""
    index: dict[tuple[str, int], list[Hole]] = {}
    for h in holes:
        if h.enabled:
            index.setdefault((row_family(h.kind), logical_row(h.row)), []).append(h)
    return index


def previous_row_holes(index: dict[tuple[str, int], list[Hole]], hole: Hole) -> list[Hole]:
    """Скважины соседнего ряда позади — только в своей группе рядов."""
    return [
        other
        for other in index.get((row_family(hole.kind), logical_row(hole.row) - 1), [])
        if other is not hole
    ]


def previous_row_distance(index: dict[tuple[str, int], list[Hole]], hole: Hole) -> float | None:
    """Расстояние до ближайшей скважины соседнего ряда позади; None, если его нет."""
    others = previous_row_holes(index, hole)
    if not others:
        return None
    return min(_distance2d(hole, other) for other in others)


def previous_row_step(
    index: dict[tuple[str, int], list[Hole]], hole: Hole, advance: tuple[float, float]
) -> float | None:
    """Шаг между рядами поперёк рядов: проекция на направление продвижения.

    На шахматной сетке диагональ до соседа включает половину шага сдвига вдоль
    ряда; шаг между рядами — только поперёк.
    """
    others = previous_row_holes(index, hole)
    if not others:
        return None
    return min(
        abs((hole.collar.x - o.collar.x) * advance[0] + (hole.collar.y - o.collar.y) * advance[1])
        for o in others
    )


def local_burden(holes: list[Hole], hole: Hole, contour: BlockContour) -> float | None:
    """Distance to the previous row, or collar-to-face if this is the first row.

    Соседа ищем по логическому номеру в своей группе рядов (см. previous_row_distance).
    """
    distance = previous_row_distance(row_index(holes), hole)
    if distance is not None:
        return distance
    return distance_to_free_faces((hole.collar.x, hole.collar.y), contour)