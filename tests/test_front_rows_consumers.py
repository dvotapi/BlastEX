"""Потребители Hole.row видят ряды впереди первого как отдельную группу.

Ряды впереди (номера ниже FRONT_ROW_BASE) не должны выпадать из правил, которые
работают с соседними рядами: стабилизация, шаг между рядами, границы групп.
"""
import unittest

from design.editing import spacing_report
from design.models import FRONT_ROW_BASE, logical_row
from design.pattern import generate_pattern
from tests.test_design_pattern_full_contour import BOOT, PARAMS, _contour


def _production(holes):
    return [h for h in holes if h.enabled and h.kind == "production"]


class FrontRowConsumersTest(unittest.TestCase):
    def test_stab_goes_to_row_nearest_free_face_when_front_rows_exist(self):
        holes = generate_pattern(_contour(BOOT), {**PARAMS, "stab_row": True, "stab_depth_m": 3.0})
        production = _production(holes)
        self.assertTrue(any(h.row <= FRONT_ROW_BASE for h in production))
        face_logical = min(logical_row(h.row) for h in production)
        expected_rows = {h.row for h in production if logical_row(h.row) == face_logical}
        stab_rows = {h.row for h in holes if h.kind == "stab"}
        self.assertTrue(stab_rows)
        self.assertEqual(stab_rows, expected_rows)

    def test_stab_stays_on_row_zero_without_front_rows(self):
        flat = _contour([(0.0, 0.0), (0.0, 60.0), (60.0, 60.0), (60.0, 0.0)], free_faces=[[0, 1]])
        holes = generate_pattern(flat, {**PARAMS, "stab_row": True, "stab_depth_m": 3.0})
        self.assertFalse(any(h.row <= FRONT_ROW_BASE for h in holes))
        stab_rows = {h.row for h in holes if h.kind == "stab"}
        self.assertEqual(stab_rows, {0})

    def test_spacing_b_ignores_contour_and_buffer_rows(self):
        holes = generate_pattern(
            _contour(BOOT),
            {**PARAMS, "contour_row": True, "buffer_row": True, "contour_spacing_m": 3.0},
        )
        self.assertTrue(any(h.kind == "buffer" for h in holes))
        self.assertTrue(any(h.kind == "contour" for h in holes))
        with_walls = spacing_report(holes, 5.0, 5.0)["spacing_b"]
        production_only = spacing_report(_production(holes), 5.0, 5.0)["spacing_b"]
        self.assertEqual(with_walls, production_only)


if __name__ == "__main__":
    unittest.main()
