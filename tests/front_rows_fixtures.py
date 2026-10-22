"""Общие заготовки тестов первого ряда у откоса: контуры, сетки, скважины.

Ими пользуются `test_toe_line`, `test_design_pattern_front_tilt` и
`test_design_analysis`.
"""
from __future__ import annotations

import math

from design.models import BenchSurface, BlastDesign, BlockContour, Hole, Point3


# --- Линия подошвы и ЛСП: прямоугольник 40×22 м, откос 75° ---------------------

PATTERN = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.7}


def rect_contour(cad=None, free_faces=None) -> BlockContour:
    return BlockContour(
        vertices=[Point3(0, 0, 0), Point3(40, 0, 0), Point3(40, 22, 0), Point3(0, 22, 0)],
        free_faces=[[0, 1]] if free_faces is None else free_faces,
        bench=BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75),
        cad=cad,
    )


def vertical_hole(hole_id, x, y, row, subdrill=1.0, kind="production", enabled=True, bench_h=10.0) -> Hole:
    return Hole(
        id=hole_id, row=row, col=0, collar=Point3(x, y, 0.0),
        toe=Point3(x, y, -(bench_h + subdrill)), diameter_mm=215.0,
        subdrill_m=subdrill, kind=kind, enabled=enabled,
    )


def inclined_hole(hole_id, x, y, row, angle_deg, azimuth_deg, bench_h=10.0, subdrill=1.0) -> Hole:
    # Перебор откладывается вдоль оси: до подошвы (глубина H) ось идёт H / cos α,
    # забой — ещё на subdrill дальше по оси.
    a = math.radians(angle_deg)
    az = math.radians(azimuth_deg)
    length = bench_h / math.cos(a) + subdrill
    horizontal = length * math.sin(a)
    return Hole(
        id=hole_id, row=row, col=0, collar=Point3(x, y, 0.0),
        toe=Point3(x + horizontal * math.sin(az), y + horizontal * math.cos(az), -length * math.cos(a)),
        diameter_mm=215.0, subdrill_m=subdrill,
    )


def design_with(holes, pattern_params=None) -> BlastDesign:
    return BlastDesign(
        design_id="t", contour=rect_contour(), holes=holes,
        pattern_params=PATTERN if pattern_params is None else pattern_params,
    )


# --- Разрыв между рядами у подошвы -------------------------------------------

GAP_PATTERN = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.5, "row_azimuth_deg": 90.0}


def grid_rows(row_one_tilt_deg: float = 0.0, rows: int = 4, tilted_row: int = 0) -> list[Hole]:
    """Сетка 4×3,5 м у грани y = 0: устья по сетке, ряд `tilted_row` (0 — ряд 1, y = 2) наклонён к откосу."""
    holes = []
    for r in range(rows):
        for c, x in enumerate((8.0, 12.0, 16.0, 20.0, 24.0)):
            y = 2.0 + 3.5 * r
            hid = f"{r + 1}-{c + 1:02d}"
            if r == tilted_row and row_one_tilt_deg:
                hole = inclined_hole(hid, x, y, r, row_one_tilt_deg, 180)
            else:
                hole = vertical_hole(hid, x, y, r)
            holes.append(Hole(**{**hole.__dict__, "col": c}))
    return holes


ACROSS_PATTERN = {"pattern": "rectangular", "spacing_a_m": 5.0, "burden_b_m": 3.5, "row_azimuth_deg": 0.0}


def rows_across_face(tilted: tuple[str, ...] = ()) -> list[Hole]:
    """Ряды поперёк бровки y = 0: в ряду шаг a = 5 (к откосу), между рядами b = 3,5.

    `tilted` — номера скважин, наклонённых к откосу на 15° без сдвига устья.
    """
    holes = []
    for r, x in enumerate((8.0, 11.5, 15.0, 18.5, 22.0)):
        for c, y in enumerate((2.0, 7.0, 12.0, 17.0)):
            hid = f"{r + 1}-{c + 1:02d}"
            hole = inclined_hole(hid, x, y, r, 15, 180) if hid in tilted else vertical_hole(hid, x, y, r)
            holes.append(Hole(**{**hole.__dict__, "col": c}))
    return holes


# --- Генератор сетки: плавный переход и пара у откоса ------------------------

# Откос 55° от горизонтали: подошва в 10·tan 35° = 7,0 м от бровки — запас,
# при котором наклон до 30° не упирается в ограничение по ЛСП (0,8·W = 2,8 м;
# оно проверяется отдельно).
FACE_ANGLE_DEG = 55.0


def _rect_contour(width: float, height: float, free_faces=((0, 1),), face_angle_deg=FACE_ANGLE_DEG) -> BlockContour:
    """Прямоугольник как в tests/test_design_pattern.py; откос — нижнее ребро y = 0."""
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return _contour_of(verts, free_faces, face_angle_deg)


def _contour_of(verts, free_faces, face_angle_deg=FACE_ANGLE_DEG) -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        free_faces=[list(edge) for edge in free_faces],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=face_angle_deg),
    )


CONTOUR = _rect_contour(40.0, 30.0)
# Ряды вдоль бровки (по +X), a = 4, b = 3,5, первый ряд в 2 м от откоса.
BASE = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": 3.5,
    "row_azimuth_deg": 90.0,
    "offset_from_face_m": 2.0,
    "edge_margin_m": 0.0,
    "subdrill_m": 1.0,
}


# Бровка под углом к рядам: откос — ребро (0, 0) → (40, 4), 75° (подошва в
# 2,68 м от бровки), ряды вдоль X. ЛСП вертикальных первого ряда — от 6,8 до
# 4,7 м: ограничение угла (α = 30°, цель 2,8 м) у каждой скважины своё.
SLANT = [(0.0, 0.0), (40.0, 4.0), (40.0, 30.0), (0.0, 30.0)]


def _poly_contour(face_angle_deg):
    return _contour_of([(0, 0), (30, -5), (60, 3), (70, 40), (10, 50)], ((0, 1, 2),), face_angle_deg)


def _arc_contour(face_angle_deg):
    arc = [(-20.0, 25.0)] + [
        (20.0 * math.cos(math.pi * (1 + i / 12)), -20.0 + 20.0 * math.sin(math.pi * (1 + i / 12))) for i in range(13)
    ] + [(20.0, 25.0)]
    return _contour_of(arc, (tuple(range(1, 14)),), face_angle_deg)


# Ступенчатая бровка: слева откос на y = 0, справа отступает к y = 8.
STEP = [(0.0, 0.0), (20.0, 0.0), (20.0, 8.0), (40.0, 8.0), (40.0, 30.0), (0.0, 30.0)]
STEP_FACE = ((0, 1, 2, 3),)
