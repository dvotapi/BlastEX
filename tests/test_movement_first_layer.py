"""Первый слой сетки в движке разлёта: по откосу, а не по номеру ряда.

Ряды впереди первого у изогнутой бровки получают отрицательные номера, поэтому
первым слоем считаются скважины, ближайшие к свободной поверхности.
"""
import unittest

from design.pattern import generate_pattern
from design.models import BenchSurface, BlockContour, Point3
from simulation.movement.engine import _is_first_layer
from tests.test_design_pattern_full_contour import BOOT, PARAMS, _contour


class _Design:
    def __init__(self, contour):
        self.contour = contour


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
        design = _Design(contour)
        for h in holes:
            self.assertEqual(_is_first_layer(h, holes, design, 5.0), h.row == min_row, h.id)

    def test_strip_and_pocket_rows_are_first_layer_on_bent_crest(self):
        contour = _contour(BOOT)
        holes = [h for h in generate_pattern(contour, PARAMS) if h.enabled]
        design = _Design(contour)
        nearest = min(holes, key=lambda h: _dist(h, contour))
        self.assertTrue(_is_first_layer(nearest, holes, design, 5.0))
        # Ряд впереди первого у бровки (отрицательный номер) тоже первый слой.
        pocket = [h for h in holes if h.row < 0]
        self.assertTrue(pocket)
        self.assertTrue(any(_is_first_layer(h, holes, design, 5.0) for h in pocket))


def _dist(hole, contour):
    from design.geometry import distance_to_free_faces

    return distance_to_free_faces((hole.collar.x, hole.collar.y), contour)


if __name__ == "__main__":
    unittest.main()
