"""Первый слой сетки в движке разлёта и номера рядов впереди первого.

Ряды впереди первого у изогнутой бровки получают номера из отдельного
диапазона (FRONT_ROW_BASE), чтобы не пересекаться с контурными и буферными
рядами. Первым слоем основной сетки считаются скважины, ближайшие к откосу.
"""
import unittest

from design.geometry import distance_to_free_faces
from design.models import BenchSurface, BlockContour, Point3
from design.pattern import FRONT_ROW_BASE, generate_pattern
from simulation.movement.engine import _first_layer_ids
from tests.test_design_pattern_full_contour import BOOT, PARAMS, _contour


class _Design:
    def __init__(self, contour, pattern_params=None):
        self.contour = contour
        self.pattern_params = pattern_params or {}


def _rect(face):
    v = [(0.0, 0.0), (40.0, 0.0), (40.0, 22.0), (0.0, 22.0)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in v],
        free_faces=face,
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )


class FirstLayerTests(unittest.TestCase):
    def test_rectangle_first_layer_is_the_min_row(self):
        contour = _rect([[0, 1]])
        params = {"pattern": "square", "spacing_a_m": 5.0, "burden_b_m": 5.0,
                  "offset_from_face_m": 2.5, "row_azimuth_deg": 90.0, "depth_m": 10.0}
        holes = [h for h in generate_pattern(contour, params) if h.enabled]
        min_row = min(h.row for h in holes)
        first = _first_layer_ids(_Design(contour, {"burden_b_m": 5.0}), holes)
        self.assertEqual({h.id for h in holes if id(h) in first}, {h.id for h in holes if h.row == min_row})

    def test_bent_crest_front_rows_are_first_layer_by_proximity(self):
        contour = _contour(BOOT)
        holes = [h for h in generate_pattern(contour, PARAMS) if h.enabled]
        first = _first_layer_ids(_Design(contour, {"burden_b_m": 5.0}), holes)
        nearest = min(holes, key=lambda h: distance_to_free_faces((h.collar.x, h.collar.y), contour))
        self.assertIn(id(nearest), first)
        self.assertTrue(any(h.row <= FRONT_ROW_BASE for h in holes))
        self.assertTrue(any(id(h) in first for h in holes if h.row <= FRONT_ROW_BASE))

    def test_contour_rows_keep_their_own_first_row_with_front_rows(self):
        # Контурный ряд — первый в своей группе, даже если впереди есть ряды сетки.
        contour = _contour(BOOT)
        params = {**PARAMS, "contour_row": True, "contour_offset_m": 1.0, "contour_spacing_m": 3.0}
        holes = [h for h in generate_pattern(contour, params) if h.enabled]
        contour_holes = [h for h in holes if h.kind == "contour"]
        self.assertTrue(contour_holes)
        first = _first_layer_ids(_Design(contour, {"burden_b_m": 5.0}), holes)
        self.assertTrue(all(id(h) in first for h in contour_holes if h.row == min(c.row for c in contour_holes)))

    def test_front_rows_do_not_collide_with_wall_rows(self):
        contour = _contour(BOOT)
        params = {**PARAMS, "contour_row": True, "contour_offset_m": 1.0, "contour_spacing_m": 3.0}
        holes = generate_pattern(contour, params)
        production_rows = {h.row for h in holes if h.kind == "production"}
        wall_rows = {h.row for h in holes if h.kind == "contour"}
        self.assertFalse(production_rows & wall_rows)
        self.assertEqual(len({h.id for h in holes}), len(holes))

    def test_narrow_row_burden_does_not_pull_later_rows_into_first_layer(self):
        # Первый ряд у бровки с burden 1 м, общий 10 м: ряд на 3,5 м не первый слой.
        contour = _rect([[0, 1]])
        params = {"pattern": "variable", "spacing_a_m": 5.0, "burden_b_m": 10.0,
                  "offset_from_face_m": 2.5, "row_azimuth_deg": 90.0, "depth_m": 10.0,
                  "row_params": [{"burden_b_m": 1.0}]}
        holes = [h for h in generate_pattern(contour, params) if h.enabled]
        first = _first_layer_ids(_Design(contour, {"burden_b_m": 10.0}), holes)
        ys_first = {round(h.collar.y, 6) for h in holes if id(h) in first}
        self.assertNotIn(round(3.5, 6), ys_first)
        self.assertNotIn(round(6.5, 6), ys_first)


if __name__ == "__main__":
    unittest.main()
