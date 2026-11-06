"""«Глубина» из параметров сетки — глубина вертикальной скважины (решение
владельца 06.11.2026): у наклонной длина по оси = глубина / cos α, забой на той
же отметке. Сохранённые черновики автопересчёт не трогает."""
import math

import pytest

from design.geometry import hole_depth_m, hole_from_collar
from design.hole_recompute import recompute_hole
from design.models import Hole, Point3
from design.pattern import generate_pattern
from tests.front_rows_fixtures import PATTERN, rect_contour

CONTOUR = rect_contour()


def test_explicit_depth_is_vertical_for_inclined_hole():
    length = hole_depth_m(Point3(0, 0, 0), 30.0, 180.0, 1.0, CONTOUR, None, 10.0)
    assert length == pytest.approx(10.0 / math.cos(math.radians(30.0)))


def test_explicit_depth_unchanged_for_vertical_hole():
    assert hole_depth_m(Point3(0, 0, 0), 0.0, 0.0, 1.0, CONTOUR, None, 10.0) == pytest.approx(10.0)


def test_explicit_depth_at_ninety_degrees_does_not_divide_by_zero():
    assert hole_depth_m(Point3(0, 0, 0), 90.0, 0.0, 1.0, CONTOUR, None, 10.0) == pytest.approx(10.0)


def test_generated_inclined_grid_toe_at_same_elevation_as_vertical():
    holes = generate_pattern(CONTOUR, {**PATTERN, "angle_deg": 20.0, "depth_m": 11.0})
    assert holes
    assert all(h.collar.z - h.toe.z == pytest.approx(11.0) for h in holes)


def test_recompute_keeps_length_of_saved_draft_with_explicit_depth():
    collar = Point3(10.0, 10.0, 0.0)
    hole = Hole(id="1-01", row=0, col=0, collar=collar, toe=hole_from_collar(collar, 11.0, 20.0, 180.0),
                diameter_mm=152.0, subdrill_m=1.0)
    out = recompute_hole(hole, CONTOUR, None, {"depth_m": 11.0}).hole
    assert out.length_m == pytest.approx(11.0)
