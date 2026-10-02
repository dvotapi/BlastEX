"""Пересчёт отметок устьев и длин скважин по кровле и подошве (TASK-013, PR 3).

Одна формула для генерации сетки, правок и автоматического пересчёта
(`geometry.drape_collar`): устье — на кровле (вне её — ближайшая вершина TIN
и флаг «вне поверхности»), длина L = (S − Z)/cos α + Δ, перебур вдоль оси.

Пересчёт не трогает то, что инженер задал руками (`Hole.manual`): отметку
устья (`collar_z`) и длину (`length`). Скважины, у вида которых в параметрах
сетки своя глубина (контурные, предщелевые, заоткосные, stab, сателлиты),
сохраняют длину — двигается только устье. Отключённые скважины
пересчитываются так же: включение не должно давать старую длину.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from design.geometry import angle_azimuth, collar_on_roof, hole_depth_m, hole_from_collar
from design.models import BlockContour, Hole, Point3

MANUAL_COLLAR_Z = "collar_z"
MANUAL_LENGTH = "length"
FLAG_OUTSIDE_SURFACE = "outside_surface"
FLAG_SHORT_BENCH = "short_bench"
# Высота уступа у скважины меньше этого — флаг (§2 «Длины скважин»).
SHORT_BENCH_M = 1.0
# Глубина stab по умолчанию — как в `pattern._generate_stab_holes`.
STAB_DEPTH_M = 3.0
_KIND_DEPTH_KEYS = {
    "contour": "contour_depth_m",
    "presplit": "presplit_depth_m",
    "trim": "trim_depth_m",
    "satellite": "satellite_depth_m",
}
_SAME_M = 1e-9


@dataclass
class RecomputedHole:
    hole: Hole
    flags: list[str] = field(default_factory=list)


def explicit_depth_m(kind: str, params: dict[str, Any]) -> float | None:
    """Своя глубина вида скважины в параметрах сетки (как при генерации)."""

    if kind == "stab":
        return float(params.get("stab_depth_m", STAB_DEPTH_M))
    key = _KIND_DEPTH_KEYS.get(kind)
    raw = params.get(key) if key else None
    if raw in (None, ""):
        raw = params.get("depth_m")
    return None if raw in (None, "") else float(raw)


def recompute_hole(hole: Hole, contour: BlockContour, surfaces: object | None, params: dict[str, Any]) -> RecomputedHole:
    manual = set(hole.manual)
    angle, azimuth = angle_azimuth(hole.collar, hole.toe)
    z, outside = collar_on_roof(hole.collar.x, hole.collar.y, contour, surfaces)
    if MANUAL_COLLAR_Z in manual:
        z = hole.collar.z
    collar = Point3(x=hole.collar.x, y=hole.collar.y, z=z)
    if MANUAL_LENGTH in manual or explicit_depth_m(hole.kind, params) is not None:
        length = hole.length_m
    else:
        length = hole_depth_m(collar, angle, azimuth, hole.subdrill_m, contour, surfaces)
    if abs(z - hole.collar.z) <= _SAME_M and abs(length - hole.length_m) <= _SAME_M:
        # Ничего не сменилось — забой как был, без накопления ошибок округления.
        updated = hole
    else:
        updated = replace(hole, collar=collar, toe=hole_from_collar(collar, length, angle, azimuth))
    flags = []
    if outside:
        flags.append(FLAG_OUTSIDE_SURFACE)
    if collar.z - contour.bench.toe_z_m < SHORT_BENCH_M:
        flags.append(FLAG_SHORT_BENCH)
    return RecomputedHole(updated, flags)


def recompute_holes(
    holes: list[Hole], contour: BlockContour, surfaces: object | None, params: dict[str, Any]
) -> list[RecomputedHole]:
    return [recompute_hole(hole, contour, surfaces, params) for hole in holes]
