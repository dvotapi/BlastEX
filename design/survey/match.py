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
    return ascii_name(str(text)).lower()


def _point_key(name: str, prefix: str) -> str:
    text = ascii_name(name).lower()
    if prefix and text.startswith(prefix + "-") and len(text) > len(prefix) + 1:
        text = text[len(prefix) + 1:]
    return text


class _HoleNames:
    """Скважина по имени точки: сначала точное имя (без регистра, после
    транслитерации), затем число («001» → «1») — только если оно указывает на
    одну скважину. Неоднозначное число по имени не сопоставляется — точка идёт
    в близость, а не к первой скважине списка."""

    def __init__(self, holes: list[Hole]) -> None:
        self.exact: dict[str, Hole] = {}
        self.numeric: dict[int, list[Hole]] = {}
        for hole in holes:
            key = _key(hole.id)
            self.exact.setdefault(key, hole)
            if key.isdigit():
                self.numeric.setdefault(int(key), []).append(hole)

    def find(self, key: str) -> Hole | None:
        hole = self.exact.get(key)
        if hole is not None:
            return hole
        if key.isdigit():
            candidates = self.numeric.get(int(key), [])
            if len(candidates) == 1:
                return candidates[0]
        return None


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

    def cell_of(x: float, y: float) -> tuple[int, int] | None:
        # Координаты, которые в сетку не ложатся (бесконечность после деления), —
        # не на блоке: в пары не идут, а не роняют запрос.
        try:
            return math.floor(x / cell), math.floor(y / cell)
        except (OverflowError, ValueError):
            return None

    grid: dict[tuple[int, int], list[int]] = {}
    plane: list[tuple[float, float]] = []
    for pi, point in enumerate(points):
        px, py = (point.y, point.x) if swap else (point.x, point.y)
        plane.append((px, py))
        key = cell_of(px, py)
        if key is not None:
            grid.setdefault(key, []).append(pi)
    candidates = []
    for hi, hole in enumerate(holes):
        home = cell_of(hole.collar.x, hole.collar.y)
        if home is None:
            continue
        cx, cy = home
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
    names = _HoleNames(holes)

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
        hole = names.find(_point_key(point.name, prefix))
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
