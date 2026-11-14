"""Сопоставление точек съёмки со скважинами проекта.

Чистый модуль. Порядок: ручная привязка (`manual`) → имя точки → близость в
плане (не дальше 2·`tol_collar_m`, жадно по возрастанию расстояния, одна точка —
одна скважина). Решения инженера (`manual`, `skip`) — по строке файла
(`SurveyedPoint.line`), а не по имени: у двух точек с одним именем они разные.
Отключённые скважины участвуют: пробуренная отключённая — тоже факт. Забойные точки файла выноса («…_T») и лишние точки (репер, станция) в
скважины не попадают и по близости не подбираются.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from design.export_survey import TOE_SUFFIX, ascii_name
from design.models import Hole
from design.survey.read import SurveyedPoint


@dataclass
class SurveyMatch:
    hole_id: str | None
    point: SurveyedPoint | None
    by: str
    issue: str = ""


def _key(text: str) -> str:
    text = ascii_name(str(text)).lower()
    return str(int(text)) if text.isdigit() else text


def _point_key(name: str, prefix: str) -> str:
    text = ascii_name(name).lower()
    if prefix and text.startswith(prefix + "-") and len(text) > len(prefix) + 1:
        text = text[len(prefix) + 1:]
    return str(int(text)) if text.isdigit() else text


def _is_toe(name: str) -> bool:
    return ascii_name(name).lower().endswith(TOE_SUFFIX.lower())


def _pairs(
    holes: list[Hole], points: list[SurveyedPoint], limit: float, swap: bool = False
) -> list[tuple[Hole, SurveyedPoint]]:
    """Жадное сопоставление по близости в плане: ближайшие пары первыми.

    Точки — в сетку с ячейкой `limit` (как подписи DXF в `read`): скважина
    сравнивается только с точками соседних ячеек, а не со всеми.
    """

    cell = limit if limit > 0 else 1.0
    grid: dict[tuple[int, int], list[int]] = {}
    plane: list[tuple[float, float]] = []
    for pi, point in enumerate(points):
        px, py = (point.y, point.x) if swap else (point.x, point.y)
        plane.append((px, py))
        grid.setdefault((math.floor(px / cell), math.floor(py / cell)), []).append(pi)
    candidates = []
    for hi, hole in enumerate(holes):
        cx, cy = math.floor(hole.collar.x / cell), math.floor(hole.collar.y / cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for pi in grid.get((cx + dx, cy + dy), ()):
                    px, py = plane[pi]
                    dist = math.hypot(hole.collar.x - px, hole.collar.y - py)
                    if dist <= limit:
                        candidates.append((dist, hi, pi))
    candidates.sort()
    used_h: set[int] = set()
    used_p: set[int] = set()
    out = []
    for _, hi, pi in candidates:
        if hi in used_h or pi in used_p:
            continue
        used_h.add(hi)
        used_p.add(pi)
        out.append((holes[hi], points[pi]))
    return out


def swap_detect(holes: list[Hole], points: list[SurveyedPoint], tol_collar_m: float) -> bool:
    """True, если при перестановке x/y по близости сопоставляется больше точек."""

    limit = 2 * tol_collar_m
    plain = len(_pairs(holes, points, limit))
    swapped = len(_pairs(holes, points, limit, swap=True))
    return swapped > plain


def match_survey(
    holes: list[Hole],
    points: list[SurveyedPoint],
    *,
    block: str,
    tol_collar_m: float,
    manual: dict[int, str] | None = None,
    skip: set[int] | None = None,
) -> list[SurveyMatch]:
    """По записи на каждую скважину (в том числе `missing_point`) и на каждую
    точку без скважины (`unmatched_point`) или спорную (`duplicate_point`).

    Точки, чья строка файла в `skip`, в результат не попадают вовсе. `manual` —
    {строка файла: id скважины}, главнее имени и близости; пустой id — «без
    скважины»: точка не сопоставляется ни по имени, ни по близости
    (`unmatched_point` со способом «manual»). Неизвестный id не действует.
    """

    manual = manual or {}
    skip = skip or set()
    prefix = ascii_name(block).lower()
    by_id = {h.id: h for h in holes}
    hole_by_key: dict[str, Hole] = {}
    for hole in holes:
        hole_by_key.setdefault(_key(hole.id), hole)

    assigned: dict[str, list[tuple[SurveyedPoint, str]]] = {}
    duplicates: set[str] = set()  # id скважин со спором
    loose: list[SurveyedPoint] = []
    orphans: list[SurveyedPoint] = []  # имя указывает на скважину, занятую вручную
    toes: list[SurveyedPoint] = []
    detached: list[SurveyedPoint] = []  # «без скважины» по решению инженера
    pending: list[SurveyedPoint] = []

    for point in points:
        if point.line in skip:
            continue
        decision = manual.get(point.line)
        if decision in by_id:
            assigned.setdefault(decision, []).append((point, "manual"))
        elif decision == "":
            detached.append(point)
        elif _is_toe(point.name):
            toes.append(point)
        else:
            pending.append(point)

    taken = set(assigned)
    named: dict[str, list[SurveyedPoint]] = {}
    for point in pending:
        hole = hole_by_key.get(_point_key(point.name, prefix))
        if hole is not None and hole.id in taken:
            orphans.append(point)
        elif hole is not None:
            named.setdefault(hole.id, []).append(point)
        else:
            loose.append(point)
    for hole_id, group in named.items():
        for point in group:
            assigned.setdefault(hole_id, []).append((point, "name"))

    for hole_id, group in assigned.items():
        if len(group) > 1:
            duplicates.add(hole_id)

    free_holes = [h for h in holes if h.id not in assigned]
    pairs = _pairs(free_holes, loose, 2 * tol_collar_m)
    for hole, point in pairs:
        assigned.setdefault(hole.id, []).append((point, "nearest"))
    matched_ids = {id(p) for _, p in pairs}

    result: list[SurveyMatch] = []
    for hole in holes:
        group = assigned.get(hole.id)
        if not group:
            result.append(SurveyMatch(hole.id, None, "", "missing_point"))
        elif hole.id in duplicates:
            result.append(SurveyMatch(hole.id, None, "", "missing_point"))
            result.extend(SurveyMatch(hole.id, p, by, "duplicate_point") for p, by in group)
        else:
            point, by = group[0]
            result.append(SurveyMatch(hole.id, point, by))
    for point in loose:
        if id(point) not in matched_ids:
            result.append(SurveyMatch(None, point, "", "unmatched_point"))
    result.extend(SurveyMatch(None, point, "", "unmatched_point") for point in orphans)
    result.extend(SurveyMatch(None, point, "", "unmatched_point") for point in toes)
    result.extend(SurveyMatch(None, point, "manual", "unmatched_point") for point in detached)
    return result
