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
  (`evaluate.surveyed_hole`); без отметки — устье на кровле, без глубины —
  длина до подошвы; скважина ставится пересчётом по кровле
  (`hole_recompute.recompute_hole`) до факта и зарядов;
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
from design.as_drilled import SURVEY_NO_DEPTH_METHOD, normalize_as_drilled, record_as_drilled
from design.charging import apply_charge_rules
from design.geology import designed_water_intervals
from design.geometry import Point2, hole_from_collar, layout_axes
from design.models import (
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    AsDrilledHole,
    BlastDesign,
    DataProvenance,
    Hole,
    HoleInterval,
    HoleLoad,
    ManualOffset,
    Point3,
    SurveyApplication,
    WaterInterval,
)
from design.pattern import MOVED_FLAG, is_moved_hole
from design.survey.evaluate import VERDICT_CODES, HoleVerdict, applied_points, final_hole
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


def _fact(
    hole: Hole, point: SurveyedPoint, drilled: Hole, provenance: DataProvenance, previous: AsDrilledHole | None
) -> AsDrilledHole:
    """Запись факта по скважине `drilled` (геометрия, которая ляжет в проект).

    Диаметра съёмка не несёт: у прежней записи скважины — её замер, у новой — проектный.
    Глубины в точке нет, а у прежней записи она замерена (MWD, ручной ввод, съёмка с
    глубиной — не `METHOD_NO_DEPTH`) — замер и его пометка остаются, забой — по нему
    вдоль оси съёмки; из съёмки берутся устье (и угол с азимутом, если сняты).
    """

    toe = drilled.toe
    depth = drilled.length_m
    method = METHOD if point.depth_m is not None else METHOD_NO_DEPTH
    if point.depth_m is None and previous is not None and previous.provenance.method != METHOD_NO_DEPTH:
        depth = normalize_as_drilled(deepcopy(previous)).actual_depth
        toe = hole_from_collar(drilled.collar, depth, drilled.angle_deg, drilled.azimuth_deg)
        method = previous.provenance.method
    return AsDrilledHole(
        design_hole_id=hole.id,
        actual_collar=Point3(drilled.collar.x, drilled.collar.y, drilled.collar.z),
        actual_toe=Point3(toe.x, toe.y, toe.z),
        # Глубина не замерена — длина по плану (до подошвы): `AsDrilledHole.actual_depth` пустой не бывает
        # (0 нормализуется в расстояние устье — забой); что она не замер — `METHOD_NO_DEPTH`.
        actual_depth=depth,
        actual_diameter=(previous.actual_diameter if previous is not None else 0.0) or hole.diameter_mm,
        role=ROLE_EXECUTED,
        provenance=replace(deepcopy(provenance), method=method),
    )


def _shaped(
    design: BlastDesign, hole: Hole, point: SurveyedPoint, axes: tuple[Point2, Point2]
) -> Hole:
    """Скважина по съёмке для проекта: итоговая геометрия — та же, что видела оценка
    (`evaluate.final_hole`: устье на кровле без отметки, ручные `"collar_z"`/`"length"`,
    пересчёт по кровле и подошве), плюс пометка сдвига TASK-017 (`"xy"`, `manual_offset`).
    """

    updated = final_hole(design, hole, point)
    manual = list(updated.manual)
    offset = hole.manual_offset
    if hole.source != "manual":
        offset = moved_offset(hole, point.x, point.y, *axes)
        if offset is None:
            manual = [flag for flag in manual if flag != MOVED_FLAG]
        elif MOVED_FLAG not in manual:
            manual.append(MOVED_FLAG)
    return replace(updated, manual=manual, manual_offset=offset)


def _finish(hole: Hole, shaped: Hole, *, geometry: bool, water: list[WaterInterval] | None) -> Hole:
    """Скважина по съёмке: геометрия `shaped` (если `geometry`) и вода.

    Сменилась геометрия — проектная геология и проектная вода прежнего места
    сбрасываются, как при сдвиге на плане (`designReducer`, MOVE_HOLES): заряды
    пересчитываются уже без них. Непроектные интервалы и `measured_*` — как были.
    """

    updated = shaped if geometry else replace(hole)
    water_intervals = [deepcopy(iv) for iv in hole.water_intervals]
    intervals = hole.intervals
    if geometry:
        intervals = [iv for iv in intervals if iv.role != ROLE_DESIGNED]
    if water is not None or geometry:
        water_intervals = [iv for iv in water_intervals if iv.role != ROLE_DESIGNED] + (water or [])
    return replace(updated, intervals=intervals, water_intervals=water_intervals)


def _geology_reset(before: Hole, after: Hole) -> bool:
    """У скважины пропала проектная геология или проектная вода прежнего места."""

    def designed(items: list[HoleInterval] | list[WaterInterval]) -> bool:
        return any(iv.role == ROLE_DESIGNED for iv in items)

    rock = designed(before.intervals) and not designed(after.intervals)
    water = designed(before.water_intervals) and not designed(after.water_intervals)
    return rock or water


TRAJECTORY_RESET_TEXT = "Траектория скважин {count} сброшена съёмкой."
GEOLOGY_RESET_TEXT = "Геология {count} скважин сброшена после сдвига — пересеките геологию заново."


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
    reset = 0
    trajectories = 0
    for hole in work.holes:
        point = points.get(hole.id)
        if point is None:
            holes.append(hole)
            continue
        geometry = hole.id not in unchanged
        shaped = (
            _shaped(work, hole, point, axes)
            if geometry
            else final_hole(work, hole, point)
        )
        # Факт — до правки скважины: запись сверяет, что проектная скважина не меняется.
        previous = next((item for item in work.as_drilled_holes if item.design_hole_id == hole.id), None)
        recorded = record_as_drilled(work, _fact(hole, point, shaped, fact, previous))
        if geometry and any(sample.has_xyz for sample in recorded.survey_points):
            # Новое устье и ось: траектория прежней записи заменила бы забой (`normalize_as_drilled`).
            recorded.survey_points = [sample for sample in recorded.survey_points if not sample.has_xyz]
            trajectories += 1
        water = _survey_water(hole.id, point, shaped.length_m if geometry else hole.length_m, survey, warnings)
        if not geometry and not _water_differs(hole, water):
            holes.append(hole)
            continue
        updated = _finish(hole, shaped, geometry=geometry, water=water)
        if geometry and _geology_reset(hole, updated):
            reset += 1
        holes.append(updated)
        changed_ids.append(hole.id)
    if reset:
        warnings.append(GEOLOGY_RESET_TEXT.format(count=reset))
    if trajectories:
        warnings.append(TRAJECTORY_RESET_TEXT.format(count=trajectories))

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
