"""Оценка пробуренных скважин по съёмке маркшейдера (TASK-014, PR 5а).

Чистый модуль. Допуски — из паспорта на бурение блока (`tol_*`, решение М1):
глубина ±0,3 м, устье ±0,3 м, угол ±1°, ЛСПП ±5 %, расстояние между
скважинами ±5 % по умолчанию. Правила оценки — решение М7 спецификации:

- смещение устья — в плане (XY): разница отметок на неровной площадке не смещение;
- глубина сравнивается с **нужной** длиной при снятой отметке устья:
  L_нужн = (Z_уст.ф − Z_подошвы)/cos α + Δ, подошва проектная
  (Z_уст.проект − `Hole.bench_height_m`), Δ — проектный перебур
  (`Hole.design_subdrill_m`, если съёмку уже применяли, иначе `subdrill_m`), α —
  угол по съёмке (нет — проектный); та же формула, что `geometry.hole_depth_m`;
- угол — отклонение оси по съёмке от проектной (угол между осями: у
  вертикальной скважины азимут ничего не значит);
- ЛСПП (первый ряд) — `toe_line.floor_burdens` на проекте и на проекте по
  съёмке, отклонение в % от проектной; расстояние до соседей —
  `editing.local_spacing` по смешанной сетке: съёмка, где она есть, иначе
  проект (как графы Ф проекта МВ, `mass_blast_fact._fact_geometry`).

Оцениваются только скважины, сопоставленные с точкой без проблемы.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Mapping

from design.editing import local_spacing
from design.geometry import hole_from_collar
from design.models import BlastDesign, Hole, Point3
from design.survey.match import SurveyMatch
from design.survey.read import SurveyedPoint
from design.toe_line import FloorBurden, floor_burdens

__all__ = [
    "TOLERANCE_SOURCES",
    "UNCHANGED_ANGLE_DEG",
    "UNCHANGED_DEPTH_M",
    "UNCHANGED_XYZ_M",
    "VERDICT_CODES",
    "HoleVerdict",
    "SurveyTolerances",
    "applied_points",
    "design_subdrill",
    "evaluate_survey",
    "required_length_m",
    "surveyed_geometry",
    "surveyed_hole",
    "tolerances_from_payload",
]

VERDICT_CODES = ("ok", "underdrill", "overdrill", "offset", "angle", "burden", "spacing", "no_depth")
TOLERANCE_SOURCES = ("passport", "parent_passport", "default")

# «Без изменения» — округление файла маркшейдера: 1 мм в плане и по отметке,
# 1 см по глубине (спецификация, §7). Угол файл пишет до 0,1°: половина шага
# округления (15,05° → 15,1°) — ещё «без изменения», граница включается.
UNCHANGED_XYZ_M = 0.001
UNCHANGED_DEPTH_M = 0.01
UNCHANGED_ANGLE_DEG = 0.05
# Сравнение с допуском без шума плавающей точки.
_EPS = 1e-9


@dataclass(frozen=True)
class SurveyTolerances:
    """Допуски оценки: глубина и устье — ± м, угол — ±°, ЛСПП и шаг — ± % от проекта."""

    depth_m: float = 0.3
    collar_m: float = 0.3
    angle_deg: float = 1.0
    burden_pct: float = 5.0
    spacing_pct: float = 5.0
    source: str = "default"  # passport | parent_passport | default


# Поле паспорта на бурение → поле допусков.
_PAYLOAD_KEYS = {
    "tol_depth_m": "depth_m",
    "tol_collar_m": "collar_m",
    "tol_angle_deg": "angle_deg",
    "tol_burden_pct": "burden_pct",
    "tol_spacing_pct": "spacing_pct",
}


def _positive(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def tolerances_from_payload(payload: Mapping | None, *, source: str) -> SurveyTolerances:
    """Допуски из payload паспорта на бурение; недостающие и негодные поля — умолчания.

    Паспорта нет (`payload` None) — умолчания с источником «default».
    """

    if payload is None:
        return SurveyTolerances()
    values = {
        field: number
        for key, field in _PAYLOAD_KEYS.items()
        if (number := _positive(payload.get(key))) is not None
    }
    return SurveyTolerances(**values, source=source)


@dataclass
class HoleVerdict:
    hole_id: str
    codes: list[str]
    offset_m: float | None  # смещение устья в плане
    depth_delta_m: float | None  # замер − нужная длина; None — глубина не замерена
    required_length_m: float | None  # нужная длина при снятой отметке устья
    angle_delta_deg: float | None  # отклонение оси; None — угол и азимут не сняты
    burden_delta_pct: float | None  # ЛСПП: (съёмка − проект)/проект, %; None — не первый ряд
    spacing_delta_pct: float | None  # расстояние до соседа в ряду, %; None — соседей нет
    unchanged: bool  # разница с проектом в пределах округления файла


@dataclass(frozen=True)
class _Surveyed:
    """Скважина по съёмке: устье, угол, азимут и длина (не замерено — по проекту)."""

    collar: Point3
    angle_deg: float
    azimuth_deg: float
    length_m: float


def applied_points(design: BlastDesign, matches: list[SurveyMatch]) -> dict[str, SurveyedPoint]:
    """Точки, сопоставленные со скважиной проекта без проблемы: hole_id → точка."""

    ids = {hole.id for hole in design.holes}
    return {
        match.hole_id: match.point
        for match in matches
        if match.point is not None and not match.issue and match.hole_id is not None and match.hole_id in ids
    }


def _surveyed(hole: Hole, point: SurveyedPoint) -> _Surveyed:
    z = hole.collar.z if point.z is None else point.z
    return _Surveyed(
        collar=Point3(x=point.x, y=point.y, z=z),
        angle_deg=hole.angle_deg if point.angle_deg is None else point.angle_deg,
        azimuth_deg=hole.azimuth_deg if point.azimuth_deg is None else point.azimuth_deg,
        length_m=hole.length_m if point.depth_m is None else point.depth_m,
    )


def _length_to_floor(hole: Hole, collar_z: float, angle_deg: float) -> float | None:
    """Длина по оси от устья на отметке `collar_z` до проектной подошвы скважины."""

    cos_a = math.cos(math.radians(angle_deg))
    if cos_a < 1e-6:
        return None
    floor_z = hole.collar.z - hole.bench_height_m
    return (collar_z - floor_z) / cos_a


def design_subdrill(hole: Hole) -> float:
    """Проектный перебур Δ: после «Применить» `subdrill_m` — фактический, проектный — в `design_subdrill_m`."""

    return hole.subdrill_m if hole.design_subdrill_m is None else hole.design_subdrill_m


def required_length_m(hole: Hole, collar_z: float, angle_deg: float) -> float | None:
    """L_нужн = (Z_уст.ф − Z_подошвы)/cos α + Δ: подошва и перебур — проектные."""

    to_floor = _length_to_floor(hole, collar_z, angle_deg)
    return None if to_floor is None else to_floor + design_subdrill(hole)


def surveyed_hole(hole: Hole, point: SurveyedPoint) -> Hole:
    """Скважина по съёмке: устье, угол, азимут и длина из точки, не снятое — из проекта.

    Перебур — длина за проектной подошвой по оси: точка оси на уровне подошвы
    (ЛСПП) остаётся на проектной отметке подошвы, как у графы Ф проекта МВ
    (`mass_blast_fact._fact_geometry`). Перебур сменился — прежний проектный
    запоминается в `design_subdrill_m` (если его ещё нет): по нему пересъёмка
    после добуривания считает нужную длину. Остальные поля — те же объекты, что
    у `hole` (копия неглубокая); `hole` не меняется.
    """

    surveyed = _surveyed(hole, point)
    to_floor = _length_to_floor(hole, surveyed.collar.z, surveyed.angle_deg)
    subdrill = hole.subdrill_m if to_floor is None else surveyed.length_m - to_floor
    changed = abs(subdrill - hole.subdrill_m) > _EPS
    return replace(
        hole,
        collar=surveyed.collar,
        toe=hole_from_collar(surveyed.collar, surveyed.length_m, surveyed.angle_deg, surveyed.azimuth_deg),
        subdrill_m=subdrill,
        design_subdrill_m=design_subdrill(hole) if changed else hole.design_subdrill_m,
    )


def surveyed_geometry(design: BlastDesign, matches: list[SurveyMatch]) -> BlastDesign:
    """Копия проекта: у скважин с точкой — геометрия по съёмке (`surveyed_hole`).

    Скважины без точки — по проекту (смешанная сетка). Проект на входе не меняется.
    """

    points = applied_points(design, matches)
    copy = deepcopy(design)
    copy.holes = [
        surveyed_hole(hole, points[hole.id]) if hole.id in points else hole for hole in copy.holes
    ]
    return copy


def _axis(angle_deg: float, azimuth_deg: float) -> tuple[float, float, float]:
    a, az = math.radians(angle_deg), math.radians(azimuth_deg)
    return (math.sin(a) * math.sin(az), math.sin(a) * math.cos(az), -math.cos(a))


def _axis_deviation_deg(hole: Hole, surveyed: _Surveyed) -> float:
    one = _axis(hole.angle_deg, hole.azimuth_deg)
    two = _axis(surveyed.angle_deg, surveyed.azimuth_deg)
    dot = sum(p * q for p, q in zip(one, two))
    cross = (
        one[1] * two[2] - one[2] * two[1],
        one[2] * two[0] - one[0] * two[2],
        one[0] * two[1] - one[1] * two[0],
    )
    # atan2, а не acos: у малых углов (порог «без изменения») acos теряет точность.
    return math.degrees(math.atan2(math.hypot(*cross), dot))


def _percent(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or abs(base) < 1e-9:
        return None
    return (value - base) / base * 100.0


def _signed(burden: FloorBurden | None) -> float | None:
    """ЛСПП со знаком: точка на подошве за линией подошвы — отрицательная."""

    if burden is None:
        return None
    return -burden.value_m if burden.beyond_toe else burden.value_m


def _over(value: float | None, tolerance: float) -> bool:
    return value is not None and abs(value) > tolerance + _EPS


def evaluate_survey(design: BlastDesign, matches: list[SurveyMatch], tol: SurveyTolerances) -> list[HoleVerdict]:
    """Оценка скважин с точкой съёмки, в порядке скважин проекта.

    Несколько нарушений — все коды (в порядке `VERDICT_CODES`); «ok» — только
    без других кодов. Глубина не замерена — код «no_depth», проверки глубины
    пропускаются (длина по проекту для ЛСПП и шага).
    """

    points = applied_points(design, matches)
    if not points:
        return []
    surveyed_design = surveyed_geometry(design, matches)
    burdens = floor_burdens(design)
    surveyed_burdens = floor_burdens(surveyed_design)
    surveyed_holes = {hole.id: hole for hole in surveyed_design.holes}
    verdicts = []
    for hole in design.holes:
        point = points.get(hole.id)
        if point is None:
            continue
        surveyed = _surveyed(hole, point)
        offset = math.hypot(surveyed.collar.x - hole.collar.x, surveyed.collar.y - hole.collar.y)
        required = required_length_m(hole, surveyed.collar.z, surveyed.angle_deg)
        depth_delta = None if point.depth_m is None or required is None else point.depth_m - required
        angle_delta = (
            None if point.angle_deg is None and point.azimuth_deg is None else _axis_deviation_deg(hole, surveyed)
        )
        burden_delta = _percent(_signed(surveyed_burdens.get(hole.id)), _signed(burdens.get(hole.id)))
        spacing_delta = _percent(
            local_spacing(surveyed_design.holes, surveyed_holes[hole.id]), local_spacing(design.holes, hole)
        )
        found = {
            "underdrill": depth_delta is not None and depth_delta < -tol.depth_m - _EPS,
            "overdrill": depth_delta is not None and depth_delta > tol.depth_m + _EPS,
            "offset": offset > tol.collar_m + _EPS,
            "angle": _over(angle_delta, tol.angle_deg),
            "burden": _over(burden_delta, tol.burden_pct),
            "spacing": _over(spacing_delta, tol.spacing_pct),
            "no_depth": point.depth_m is None,
        }
        codes = [code for code in VERDICT_CODES if found.get(code)] or ["ok"]
        unchanged = (
            offset < UNCHANGED_XYZ_M
            and abs(surveyed.collar.z - hole.collar.z) < UNCHANGED_XYZ_M
            and abs(surveyed.length_m - hole.length_m) < UNCHANGED_DEPTH_M
            and (angle_delta is None or angle_delta <= UNCHANGED_ANGLE_DEG + _EPS)
        )
        verdicts.append(
            HoleVerdict(
                hole_id=hole.id, codes=codes, offset_m=offset, depth_delta_m=depth_delta,
                required_length_m=required, angle_delta_deg=angle_delta, burden_delta_pct=burden_delta,
                spacing_delta_pct=spacing_delta, unchanged=unchanged,
            )
        )
    return verdicts
