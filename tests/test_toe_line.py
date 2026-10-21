"""Линия подошвы откоса: по съёмке нижней бровки или от верхней бровки по углу."""
from __future__ import annotations

import math

import pytest

from design.models import BenchSurface, BlastDesign, BlockContour, Hole, Point3
from design.toe_line import allowed_floor_burden_m, floor_burdens, slope_offset_m, toe_line

PATTERN = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.7}


def rect_contour(cad=None, free_faces=None) -> BlockContour:
    return BlockContour(
        vertices=[Point3(0, 0, 0), Point3(40, 0, 0), Point3(40, 22, 0), Point3(0, 22, 0)],
        free_faces=[[0, 1]] if free_faces is None else free_faces,
        bench=BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75),
        cad=cad,
    )


def test_offset_for_15_degrees_from_vertical():
    bench = BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75)
    assert slope_offset_m(bench) == pytest.approx(2.6795, abs=1e-4)


def test_vertical_face_has_zero_offset():
    bench = BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=90)
    assert slope_offset_m(bench) == pytest.approx(0.0)


def test_built_toe_line_lies_outside_block_at_offset():
    line = toe_line(rect_contour())
    assert line.source == "built"
    ys = [y for poly in line.polylines for _, y in poly]
    assert all(y == pytest.approx(-2.6795, abs=1e-3) for y in ys)


def test_survey_toe_line_uses_bottom_ring_edge_near_free_face():
    # cad.bottom — кольцо по нижней бровке: фронт на y = -3, тыл и фланги совпадают с контуром.
    contour = rect_contour(cad={"bottom": [[0, -3], [40, -3], [40, 22], [0, 22]]})
    line = toe_line(contour)
    assert line.source == "survey"
    ys = {round(y, 6) for poly in line.polylines for _, y in poly}
    assert ys == {-3.0}  # только фронтальное ребро, без тыла y = 22


def test_edited_contour_ignores_survey():
    contour = rect_contour(cad={"bottom": [[0, -3], [40, -3], [40, 22], [0, 22]], "edited": True})
    assert toe_line(contour).source == "built"


def test_survey_without_edge_near_face_falls_back_to_built():
    contour = rect_contour(cad={"bottom": [[0, -30], [40, -30], [40, 22], [0, 22]]})
    assert toe_line(contour).source == "built"


def test_no_free_faces_gives_none():
    assert toe_line(rect_contour(free_faces=[])) is None


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


def test_vertical_hole_floor_burden_adds_slope_offset():
    hole = vertical_hole("1-01", x=10, y=3.7, row=0, subdrill=1.0)
    fb = floor_burdens(design_with([hole]))["1-01"]
    assert fb.value_m == pytest.approx(3.7 + 2.6795, abs=1e-3)
    assert fb.allowed_m == pytest.approx(3.811)
    assert fb.excess is True


def test_hole_inclined_15_degrees_to_face_cancels_offset():
    # Наклон 15° к откосу (азимут 180° — к линии y = 0): на глубине H = 10 м ось
    # уходит к откосу на 2,6795 м — ровно на смещение подошвы. ЛСП = расстоянию
    # от устья до верхней бровки.
    hole = inclined_hole("1-01", x=10, y=3.7, row=0, angle_deg=15, azimuth_deg=180, bench_h=10, subdrill=1.0)
    assert floor_burdens(design_with([hole]))["1-01"].value_m == pytest.approx(3.7, abs=1e-3)


def test_within_three_percent_is_not_excess():
    hole = vertical_hole("1-01", x=10, y=3.8 - 2.6795, row=0)
    assert floor_burdens(design_with([hole]))["1-01"].excess is False


def test_second_row_hole_has_no_floor_burden():
    first = vertical_hole("1-01", x=10, y=1.0, row=0)
    second = vertical_hole("2-01", x=10, y=4.7, row=1)
    result = floor_burdens(design_with([first, second]))
    assert "1-01" in result and "2-01" not in result


def test_walls_and_disabled_holes_are_skipped():
    wall = vertical_hole("K1-01", x=10, y=1.0, row=-1, kind="contour")
    off = vertical_hole("1-02", x=20, y=1.0, row=0, enabled=False)
    assert floor_burdens(design_with([wall, off])) == {}


def test_only_production_holes_get_floor_burden():
    satellite = vertical_hole("S1", x=10, y=1.0, row=0, kind="satellite")
    assert floor_burdens(design_with([satellite])) == {}


def test_square_pattern_uses_spacing_as_w():
    assert allowed_floor_burden_m({"pattern": "square", "spacing_a_m": 4.0}) == pytest.approx(4.12)


def test_no_w_means_no_check():
    hole = vertical_hole("1-01", x=10, y=20.0, row=0)
    fb = floor_burdens(design_with([hole], pattern_params={}))["1-01"]
    assert fb.allowed_m is None and fb.excess is False


def face_design() -> BlastDesign:
    """Прямоугольник 40×22 м, откос 75°: 1-01 у свободной грани (ЛСП 6,38 м), 2-01 — второй ряд."""
    return design_with([vertical_hole("1-01", 10, 3.7, 0), vertical_hole("2-01", 10, 7.4, 1)])
