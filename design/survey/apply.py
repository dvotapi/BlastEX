"""«Применить съёмку к проекту» (TASK-014, PR 5а, спецификация §7, решения М8, М9).

Чистый модуль: проект и сопоставленные точки съёмки → новые скважины, заряды,
записи факта и запись применения. Проект на входе не меняется; что из этого
сохранить (одним шагом отмены), решает вызывающий.

Переносятся все скважины с точкой без проблемы сопоставления — в допуске и вне
его (решение владельца В1). «Без изменения» (оценка `HoleVerdict.unchanged`,
округление файла) и вода съёмки та же — скважина не трогается, пишется только
запись факта. У перенесённой:

- устье → снятая точка: скважина сетки — сдвиг с пометкой TASK-017 (`"xy"` и
  `manual_offset` от узла в осях раскладки, как `holeMove.markMoved`), ручная —
  новое устье без пометки;
- снятая отметка устья → `manual` `"collar_z"`, замеренная глубина → длина и
  `"length"`; угол и азимут — из съёмки, иначе проектные; подошва проектная
  (`evaluate.surveyed_hole`);
- вода (М8): отметка «обводнена» и уровень заменяют проектные интервалы воды
  (роль `designed`, источник — съёмка); «сухая» — убирает их; о воде ни слова —
  прежние;
- заряды (М9): правилами — только у изменённых скважин, остальные как были.

Коммутацию модуль не трогает: её помечает устаревшей и пересчитывает фронт,
как после сдвига мышкой (TASK-017, PR 3).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace

from Blast import ExplosiveProperties
from design.as_drilled import SURVEY_NO_DEPTH_METHOD, record_as_drilled
from design.charging import apply_charge_rules
from design.geology import designed_water_intervals
from design.geometry import Point2, layout_axes
from design.hole_recompute import MANUAL_COLLAR_Z, MANUAL_LENGTH
from design.models import (
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    AsDrilledHole,
    BlastDesign,
    DataProvenance,
    Hole,
    HoleLoad,
    ManualOffset,
    Point3,
    SurveyApplication,
    WaterInterval,
)
from design.pattern import MOVED_FLAG, is_moved_hole
from design.survey.evaluate import VERDICT_CODES, HoleVerdict, applied_points, surveyed_hole
from design.survey.match import SurveyMatch
from design.survey.read import SurveyedPoint

__all__ = [
    "METHOD",
    "METHOD_NO_DEPTH",
    "ChargeInputs",
    "SurveyApplication",
    "SurveyResult",
    "apply_survey",
    "moved_offset",
]

# `provenance.method` записей факта и интервалов воды из съёмки.
METHOD = "survey_import"
# Запись факта точки без замера глубины: длина в ней проектная, в графы Ф
# глубины и перебура проекта МВ она не идёт (`mass_blast_fact.block_fact`).
METHOD_NO_DEPTH = SURVEY_NO_DEPTH_METHOD
# Вернулась в узел ближе этого по каждой оси — без пометки сдвига (`holeMove.markMoved`).
_AT_NODE_M = 0.0005
_LENGTH_EPS = 1e-6


@dataclass
class ChargeInputs:
    """Параметры заряжания проекта для пересчёта зарядов изменённых скважин."""

    rules: dict
    explosive: ExplosiveProperties
    explosives: list[ExplosiveProperties] = field(default_factory=list)


@dataclass
class SurveyResult:
    holes: list[Hole]
    loads: list[HoleLoad] | None  # None — заряды не трогались (их нет или нечем пересчитать)
    as_drilled_holes: list[AsDrilledHole]
    application: SurveyApplication
    changed_ids: list[str]
    warnings: list[str] = field(default_factory=list)


def _round6(value: float) -> float:
    return round(value, 6) + 0.0  # + 0.0: без «-0.0»


def moved_offset(before: Hole, new_x: float, new_y: float, along: Point2, across: Point2) -> ManualOffset | None:
    """Пометка сдвига скважины сетки в новое устье (порт `holeMove.markMoved`).

    Узел — из прежней пометки, иначе прежнее устье. Смещение — от узла до
    нового устья в осях раскладки, до 1e-6 м; ближе 0,5 мм по обеим осям —
    `None` (скважина в узле, пометка снимается).
    """

    if is_moved_hole(before) and before.manual_offset is not None:
        node_x, node_y = before.manual_offset.node_x, before.manual_offset.node_y
    else:
        node_x, node_y = before.collar.x, before.collar.y
    dx, dy = new_x - node_x, new_y - node_y
    offset_along = dx * along[0] + dy * along[1]
    offset_across = dx * across[0] + dy * across[1]
    if abs(offset_along) < _AT_NODE_M and abs(offset_across) < _AT_NODE_M:
        return None
    return ManualOffset(node_x, node_y, _round6(offset_along), _round6(offset_across))


def _survey_water(
    hole_id: str, point: SurveyedPoint, length_m: float, provenance: DataProvenance, warnings: list[str]
) -> list[WaterInterval] | None:
    """Проектные интервалы воды по съёмке; `None` — съёмка о воде ничего не говорит.

    Уровень воды — глубина от устья; уровня нет — обводнена вся скважина.
    Уровень ниже забоя — проектной воды нет, с предупреждением.
    """

    if point.wet is False:
        return []
    if point.wet is None and point.water_depth_m is None:
        return None
    top = max(0.0, float(point.water_depth_m or 0.0))
    if top >= length_m - _LENGTH_EPS:
        warnings.append(f"Скважина {hole_id}: уровень воды ниже забоя — проектной воды нет.")
        return []
    return [
        WaterInterval(from_m=top, to_m=length_m, condition="wet", provenance=deepcopy(provenance), role=ROLE_DESIGNED)
    ]


def _fact(hole: Hole, point: SurveyedPoint, provenance: DataProvenance) -> AsDrilledHole:
    drilled = surveyed_hole(hole, point)
    return AsDrilledHole(
        design_hole_id=hole.id,
        actual_collar=Point3(drilled.collar.x, drilled.collar.y, drilled.collar.z),
        actual_toe=Point3(drilled.toe.x, drilled.toe.y, drilled.toe.z),
        # Глубина не замерена — длина проектная: `AsDrilledHole.actual_depth` пустой не бывает
        # (0 нормализуется в расстояние устье — забой); что она не замер — `METHOD_NO_DEPTH`.
        actual_depth=drilled.length_m,
        actual_diameter=hole.diameter_mm,
        role=ROLE_EXECUTED,
        provenance=replace(deepcopy(provenance), method=METHOD if point.depth_m is not None else METHOD_NO_DEPTH),
    )


def _apply_hole(
    hole: Hole,
    point: SurveyedPoint,
    *,
    geometry: bool,
    water: list[WaterInterval] | None,
    axes: tuple[Point2, Point2],
) -> Hole:
    """Скважина по съёмке: геометрия (если `geometry`) с пометками ручной правки и вода."""

    updated = surveyed_hole(hole, point) if geometry else replace(hole)
    manual = list(hole.manual)
    offset = hole.manual_offset
    if geometry:
        if point.z is not None and MANUAL_COLLAR_Z not in manual:
            manual.append(MANUAL_COLLAR_Z)
        if point.depth_m is not None and MANUAL_LENGTH not in manual:
            manual.append(MANUAL_LENGTH)
        if hole.source != "manual":
            offset = moved_offset(hole, point.x, point.y, *axes)
            if offset is None:
                manual = [flag for flag in manual if flag != MOVED_FLAG]
            elif MOVED_FLAG not in manual:
                manual.append(MOVED_FLAG)
    water_intervals = [deepcopy(iv) for iv in hole.water_intervals]
    if water is not None:
        water_intervals = [iv for iv in water_intervals if iv.role != ROLE_DESIGNED] + water
    return replace(updated, manual=manual, manual_offset=offset, water_intervals=water_intervals)


def _water_differs(hole: Hole, water: list[WaterInterval] | None) -> bool:
    if water is None:
        return False
    return [iv.to_dict() for iv in designed_water_intervals(hole)] != [iv.to_dict() for iv in water]


def _loads(
    design: BlastDesign, holes: list[Hole], changed_ids: list[str], charge: ChargeInputs | None, warnings: list[str]
) -> list[HoleLoad] | None:
    """Заряды по правилам — только изменённым скважинам (М9); прочие — как были."""

    if not design.loads:
        return None
    if not changed_ids:
        return design.loads
    if charge is None:
        warnings.append("Заряды изменённых скважин не пересчитаны: нет параметров заряжания — рассчитайте заряды.")
        return None
    # Правила — на всех скважинах: шаблоны заряжания смотрят на соседей.
    fresh = {
        load.hole_id: load
        for load in apply_charge_rules(
            holes, charge.rules, charge.explosive, contour=design.contour, explosives=charge.explosives
        )
    }
    missing = [hole_id for hole_id in changed_ids if hole_id not in fresh]
    if missing:
        warnings.append(
            f"Правила заряжания не дали заряда скважинам {', '.join(missing)} — прежний заряд оставлен, проверьте его."
        )
    changed = set(changed_ids)
    loads = [fresh.get(load.hole_id, load) if load.hole_id in changed else load for load in design.loads]
    present = {load.hole_id for load in design.loads}
    loads += [fresh[hole_id] for hole_id in changed_ids if hole_id not in present and hole_id in fresh]
    return loads


def _counts(
    matches: list[SurveyMatch], verdicts: list[HoleVerdict], applied: set[str], changed_ids: list[str]
) -> dict[str, int]:
    counts = {code: 0 for code in VERDICT_CODES}
    for verdict in verdicts:
        if verdict.hole_id not in applied:
            continue
        for code in verdict.codes:
            if code in counts:
                counts[code] += 1
    counts["changed"] = len(changed_ids)
    for issue in ("unmatched_point", "missing_point"):
        counts[issue] = sum(1 for match in matches if match.issue == issue)
    return counts


def apply_survey(
    design: BlastDesign,
    matches: list[SurveyMatch],
    verdicts: list[HoleVerdict],
    *,
    file_name: str,
    file_sha256: str,
    survey_date: str,
    actor: str,
    charge: ChargeInputs | None,
    now: str,
) -> SurveyResult:
    """Съёмка → скважины, заряды и факт проекта блока; `design` не меняется.

    Применяются скважины с точкой без проблемы сопоставления; `verdicts` —
    оценка тех же сопоставлений (`evaluate_survey`): скважина «без изменения»
    геометрию не меняет. Запись факта — по каждой применённой скважине
    (прежняя запись той же скважины заменяется, замеры MWD и инклинометрии
    остаются — `as_drilled.record_as_drilled`).
    """

    work = deepcopy(design)
    points = applied_points(work, matches)
    unchanged = {verdict.hole_id for verdict in verdicts if verdict.unchanged}
    axes = layout_axes(work.contour, float(work.pattern_params.get("row_azimuth_deg", 0.0) or 0.0))
    survey = DataProvenance(source=file_name, method=METHOD, timestamp=survey_date, role=ROLE_DESIGNED)
    fact = DataProvenance(source=file_name, method=METHOD, timestamp=survey_date, role=ROLE_EXECUTED)
    warnings: list[str] = []
    holes: list[Hole] = []
    changed_ids: list[str] = []
    for hole in work.holes:
        point = points.get(hole.id)
        if point is None:
            holes.append(hole)
            continue
        # Факт — до правки скважины: запись сверяет, что проектная скважина не меняется.
        record_as_drilled(work, _fact(hole, point, fact))
        geometry = hole.id not in unchanged
        length = surveyed_hole(hole, point).length_m if geometry else hole.length_m
        water = _survey_water(hole.id, point, length, survey, warnings)
        if not geometry and not _water_differs(hole, water):
            holes.append(hole)
            continue
        holes.append(_apply_hole(hole, point, geometry=geometry, water=water, axes=axes))
        changed_ids.append(hole.id)

    application = SurveyApplication(
        applied_at=now,
        survey_date=survey_date,
        file_name=file_name,
        file_sha256=file_sha256,
        actor=actor,
        counts=_counts(matches, verdicts, set(points), changed_ids),
    )
    return SurveyResult(
        holes=holes,
        loads=_loads(work, holes, changed_ids, charge, warnings),
        as_drilled_holes=work.as_drilled_holes,
        application=application,
        changed_ids=changed_ids,
        warnings=warnings,
    )
