"""Сдвиг сетки вдоль ряда и азимут бровки."""
import unittest

from design.geometry import crest_azimuth_deg, local_basis
from design.models import BenchSurface, BlockContour, Point3
from design.pattern import generate_pattern


def _contour(free_faces):
    verts = [(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
        free_faces=free_faces,
    )


PARAMS = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 4.0, "row_azimuth_deg": 90.0}


def _sig(holes):
    return [(h.id, round(h.collar.x, 6), round(h.collar.y, 6)) for h in holes]


class CrestAzimuthTests(unittest.TestCase):
    def test_crest_azimuth_straight_face(self):
        self.assertAlmostEqual(crest_azimuth_deg(_contour([[0, 1]])), 90.0, places=6)
        self.assertAlmostEqual(crest_azimuth_deg(_contour([[0, 3]])), 0.0, places=6)

    def test_crest_azimuth_none_without_faces(self):
        self.assertIsNone(crest_azimuth_deg(_contour([])))


class GridShiftTests(unittest.TestCase):
    def setUp(self):
        self.contour = _contour([[0, 3]])
        self.base = generate_pattern(self.contour, PARAMS)

    def test_shift_zero_is_identical(self):
        zero = generate_pattern(self.contour, {**PARAMS, "grid_shift_along_m": 0})
        self.assertEqual(_sig(zero), _sig(self.base))

    def test_shift_moves_columns(self):
        moved = generate_pattern(self.contour, {**PARAMS, "grid_shift_along_m": 1.0})
        row_dir, _ = local_basis(90.0)
        proj = lambda h: h.collar.x * row_dir[0] + h.collar.y * row_dir[1]  # noqa: E731
        self.assertTrue(moved)
        base_res = {round(proj(h) % 4.0, 6) for h in self.base}
        for h in moved:
            self.assertIn(round((proj(h) - 1.0) % 4.0, 6), base_res)
        self.assertNotEqual(_sig(moved), _sig(self.base))

    def test_shift_wraps_by_spacing(self):
        one = generate_pattern(self.contour, {**PARAMS, "grid_shift_along_m": 1.0})
        five = generate_pattern(self.contour, {**PARAMS, "grid_shift_along_m": 5.0})
        self.assertEqual(_sig(one), _sig(five))
