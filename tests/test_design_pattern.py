import unittest

from design.models import BenchSurface, BlockContour, Hole, Point3
from design.pattern import generate_pattern


def _rect_contour(width: float, height: float) -> BlockContour:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )


class RectangularPatternCountTests(unittest.TestCase):
    def test_100x50_rectangle_matches_manual_count(self):
        # row_azimuth=0 => ряды вдоль Y (высота 50, шаг a=5 => 11 узлов на ряд:
        # 0,5,...,50), продвижение рядов вдоль X (глубина 100, шаг b=4 => 26
        # рядов: 0,4,...,100). Итого 11 * 26 = 286.
        contour = _rect_contour(100.0, 50.0)
        holes = generate_pattern(
            contour,
            {
                "pattern": "rectangular",
                "spacing_a_m": 5.0,
                "burden_b_m": 4.0,
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
            },
        )
        self.assertEqual(len(holes), 286)


class PatternTypeTests(unittest.TestCase):
    def test_square_forces_b_equal_to_a(self):
        contour = _rect_contour(20.0, 20.0)
        holes = generate_pattern(
            contour,
            {
                "pattern": "square",
                "spacing_a_m": 5.0,
                "burden_b_m": 999.0,  # должно игнорироваться
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
            },
        )
        rows = sorted({h.row for h in holes})
        # При реальном шаге b=5 (не 999) на глубину 20 м укладывается 5 рядов.
        self.assertEqual(rows, [0, 1, 2, 3, 4])

    def test_rectangular_rows_are_not_shifted(self):
        contour = _rect_contour(20.0, 20.0)
        holes = generate_pattern(
            contour,
            {
                "pattern": "rectangular",
                "spacing_a_m": 10.0,
                "burden_b_m": 10.0,
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
            },
        )
        row0_col0 = min((h for h in holes if h.row == 0), key=lambda h: h.col)
        row1_col0 = min((h for h in holes if h.row == 1), key=lambda h: h.col)
        self.assertAlmostEqual(row0_col0.collar.y, row1_col0.collar.y)

    def test_staggered_shifts_odd_rows_by_ratio(self):
        contour = _rect_contour(20.0, 20.0)
        holes = generate_pattern(
            contour,
            {
                "pattern": "staggered",
                "spacing_a_m": 10.0,
                "burden_b_m": 10.0,
                "row_shift_ratio": 0.5,
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
            },
        )
        row0_col0 = min((h for h in holes if h.row == 0), key=lambda h: h.col)
        row1_col0 = min((h for h in holes if h.row == 1), key=lambda h: h.col)
        self.assertAlmostEqual(row1_col0.collar.y - row0_col0.collar.y, 5.0)


class AzimuthRotationTests(unittest.TestCase):
    def test_90_degree_rotation_mirrors_layout_on_symmetric_contour(self):
        contour = _rect_contour(20.0, 20.0)
        base_params = {
            "pattern": "rectangular",
            "spacing_a_m": 5.0,
            "burden_b_m": 5.0,
            "offset_from_face_m": 0.0,
            "edge_margin_m": 0.0,
        }
        holes_0 = generate_pattern(contour, {**base_params, "row_azimuth_deg": 0.0})
        holes_90 = generate_pattern(contour, {**base_params, "row_azimuth_deg": 90.0})

        points_0 = sorted((round(h.collar.x, 3), round(h.collar.y, 3)) for h in holes_0)
        points_90 = sorted((round(h.collar.x, 3), round(h.collar.y, 3)) for h in holes_90)
        mirrored_0 = sorted((y, x) for x, y in points_0)
        self.assertEqual(mirrored_0, points_90)


class EdgeMarginTests(unittest.TestCase):
    def test_margin_reduces_hole_count(self):
        contour = _rect_contour(20.0, 20.0)
        base_params = {
            "pattern": "rectangular",
            "spacing_a_m": 5.0,
            "burden_b_m": 5.0,
            "offset_from_face_m": 0.0,
        }
        holes_no_margin = generate_pattern(contour, {**base_params, "edge_margin_m": 0.0})
        holes_with_margin = generate_pattern(contour, {**base_params, "edge_margin_m": 3.0})
        self.assertLess(len(holes_with_margin), len(holes_no_margin))


class ManualHolePreservationTests(unittest.TestCase):
    def test_manual_holes_survive_regeneration(self):
        contour = _rect_contour(20.0, 20.0)
        manual_hole = Hole(
            id="manual-1",
            row=99,
            col=99,
            collar=Point3(x=5.0, y=5.0, z=0.0),
            toe=Point3(x=5.0, y=5.0, z=-10.0),
            diameter_mm=152.0,
            source="manual",
        )
        params = {
            "pattern": "rectangular",
            "spacing_a_m": 5.0,
            "burden_b_m": 5.0,
            "offset_from_face_m": 0.0,
            "edge_margin_m": 0.0,
        }
        first = generate_pattern(contour, params)
        first[0] = manual_hole
        regenerated = generate_pattern(contour, params, existing_holes=first)
        self.assertTrue(any(h.id == "manual-1" for h in regenerated))
        generated_only = [h for h in regenerated if h.source == "generated"]
        self.assertEqual(len(generated_only), len(generate_pattern(contour, params)))


if __name__ == "__main__":
    unittest.main()
