"""Поддержка ручной правки уже построенной сетки скважин."""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

from design.geometry import local_basis, pattern_origin
from design.models import BlockContour, Hole


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
    """
    enabled = [h for h in holes if h.enabled]
    by_row: dict[int, list[Hole]] = {}
    for h in enabled:
        by_row.setdefault(h.row, []).append(h)

    a_values: list[float] = []
    flagged: list[dict[str, Any]] = []
    for group in by_row.values():
        ordered = sorted(group, key=lambda h: h.col)
        for h1, h2 in zip(ordered, ordered[1:]):
            d = _distance2d(h1, h2)
            a_values.append(d)
            if expected_a_m is not None and abs(d - expected_a_m) > tolerance_m:
                flagged.append(
                    {"hole_id": h1.id, "neighbour_id": h2.id, "kind": "a", "distance_m": d}
                )

    b_values: list[float] = []
    rows_sorted = sorted(by_row.keys())
    for r1, r2 in zip(rows_sorted, rows_sorted[1:]):
        for h1 in by_row[r1]:
            nearest = min(by_row[r2], key=lambda h2: _distance2d(h1, h2), default=None)
            if nearest is None:
                continue
            d = _distance2d(h1, nearest)
            b_values.append(d)
            if expected_b_m is not None and abs(d - expected_b_m) > tolerance_m:
                flagged.append(
                    {"hole_id": h1.id, "neighbour_id": nearest.id, "kind": "b", "distance_m": d}
                )

    return {
        "spacing_a": _stats(a_values),
        "spacing_b": _stats(b_values),
        "flagged": flagged,
    }


def renumber(
    holes: list[Hole],
    contour: BlockContour,
    row_azimuth_deg: float = 0.0,
    row_tolerance_m: float = 1.0,
) -> list[Hole]:
    """Пересчитывает row/col/id по проекции устьев на базис раскладки контура.

    `row_tolerance_m` — половина ожидаемого шага между рядами (`burden_b_m`);
    скважины, чья проекция на направление продвижения рядов отличается от
    предыдущей меньше, чем на это значение, считаются одним рядом. Контурные
    скважины (`kind == "contour"`) не переиндексируются — их нумерация ведётся
    отдельным проходом при генерации контурного ряда.
    """
    row_dir, advance_dir = local_basis(row_azimuth_deg)
    origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)

    production = [h for h in holes if h.kind != "contour"]
    contour_holes = [h for h in holes if h.kind == "contour"]

    def _v(h: Hole) -> float:
        return (h.collar.x - origin[0]) * advance_dir[0] + (h.collar.y - origin[1]) * advance_dir[1]

    def _u(h: Hole) -> float:
        return (h.collar.x - origin[0]) * row_dir[0] + (h.collar.y - origin[1]) * row_dir[1]

    # Группируем по близости вдоль направления продвижения рядов (v), не по
    # старому полю row, — правка могла сдвинуть скважину в другой ряд.
    ordered = sorted(production, key=_v)
    rows: list[list[Hole]] = []
    for h in ordered:
        v = _v(h)
        if rows and abs(v - _v(rows[-1][-1])) < row_tolerance_m:
            rows[-1].append(h)
        else:
            rows.append([h])

    renumbered: list[Hole] = []
    for row_index, group in enumerate(rows):
        for col_index, h in enumerate(sorted(group, key=_u)):
            renumbered.append(
                replace(h, row=row_index, col=col_index, id=f"{row_index + 1}-{col_index + 1:02d}")
            )

    return renumbered + contour_holes
