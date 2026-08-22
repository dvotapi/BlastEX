import unittest

from design.editing import neighbours, renumber, spacing_report
from design.models import BenchSurface, BlockContour, Hole, Point3
from design.pattern import generate_pattern


def _hole(id_: str, row: int, col: int, x: float, y: float) -> Hole:
    return Hole(
        id=id_,
        row=row,
        col=col,
        collar=Point3(x=x, y=y, z=0.0),
        toe=Point3(x=x, y=y, z=-10.0),
        diameter_mm=152.0,
    )


class NeighboursTests(unittest.TestCase):
    def test_returns_closest_by_row_and_column(self):
        holes = [
            _hole("1-01", 0, 0, 0.0, 0.0),
            _hole("1-02", 0, 1, 5.0, 0.0),
            _hole("1-03", 0, 2, 10.0, 0.0),
            _hole("2-01", 1, 0, 0.0, 5.0),
            _hole("2-02", 1, 1, 5.0, 5.0),
        ]
        nearest = neighbours(holes, "1-01", k=2)
        self.assertEqual({h.id for h in nearest}, {"1-02", "2-01"})

    def test_missing_hole_returns_empty(self):
        holes = [_hole("1-01", 0, 0, 0.0, 0.0)]
        self.assertEqual(neighbours(holes, "does-not-exist"), [])


class SpacingReportTests(unittest.TestCase):
    def test_flags_hole_with_broken_row_spacing(self):
        holes = [
            _hole("1-01", 0, 0, 0.0, 0.0),
            _hole("1-02", 0, 1, 5.0, 0.0),
            _hole("1-03", 0, 2, 11.0, 0.0),  # шаг 6 м вместо 5 — сбитая сетка
            _hole("2-01", 1, 0, 0.0, 4.0),
            _hole("2-02", 1, 1, 5.0, 4.0),
        ]
        report = spacing_report(holes, expected_a_m=5.0, expected_b_m=4.0, tolerance_m=0.5)
        self.assertAlmostEqual(report["spacing_a"]["min"], 5.0)
        self.assertAlmostEqual(report["spacing_a"]["max"], 6.0)
        flagged_a = [f for f in report["flagged"] if f["kind"] == "a"]
        self.assertTrue(
            any(f["hole_id"] == "1-02" and f["neighbour_id"] == "1-03" for f in flagged_a)
        )


class RenumberTests(unittest.TestCase):
    def test_renumber_after_deletions_is_contiguous(self):
        contour = BlockContour(
            vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (20, 0), (20, 20), (0, 20)]],
            bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
        )
        holes = generate_pattern(
            contour,
            {
                "pattern": "rectangular",
                "spacing_a_m": 5.0,
                "burden_b_m": 5.0,
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
            },
        )
        # Удаляем две скважины, образуя разрывы в нумерации.
        remaining = [h for h in holes if h.id not in {"2-02", "3-03"}]

        renumbered = renumber(remaining, contour, row_azimuth_deg=0.0)

        rows = sorted({h.row for h in renumbered})
        self.assertEqual(rows, list(range(len(rows))))
        ids = [h.id for h in renumbered]
        self.assertEqual(len(ids), len(set(ids)))
        for h in renumbered:
            self.assertEqual(h.id, f"{h.row + 1}-{h.col + 1:02d}")


if __name__ == "__main__":
    unittest.main()
