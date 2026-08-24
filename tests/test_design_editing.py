import unittest

from design.editing import (
    apply_azimuth,
    apply_depth,
    apply_hole_geometry,
    apply_inclination,
    apply_toe,
    insert_manual_hole,
    neighbours,
    renumber,
    spacing_report,
)
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

    def test_renumber_keeps_contour_and_satellite_ids(self):
        contour = BlockContour(
            vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (20, 0), (20, 20), (0, 20)]],
            bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
        )
        holes = [
            _hole("1-01", 0, 0, 0.0, 0.0),
            _hole("1-03", 0, 2, 10.0, 0.0),
            Hole(
                id="K1-01",
                row=-1,
                col=0,
                collar=Point3(x=1, y=0, z=0),
                toe=Point3(x=1, y=0, z=-10),
                diameter_mm=152.0,
                kind="contour",
            ),
            Hole(
                id="SAT-1-01-1",
                row=0,
                col=0,
                collar=Point3(x=1, y=1, z=0),
                toe=Point3(x=1, y=1, z=-10),
                diameter_mm=89.0,
                kind="satellite",
            ),
        ]
        result = renumber(holes, contour, row_azimuth_deg=0.0)
        ids = {h.id for h in result}
        self.assertIn("K1-01", ids)
        self.assertIn("SAT-1-01-1", ids)


class GeometryEditTests(unittest.TestCase):
    def test_depth_inclination_azimuth_and_toe(self):
        hole = _hole("1-01", 0, 0, 2.0, 3.0)
        deeper = apply_depth(hole, 15.0)
        self.assertAlmostEqual(deeper.length_m, 15.0)
        inclined = apply_inclination(deeper, 15.0)
        self.assertAlmostEqual(inclined.angle_deg, 15.0, places=5)
        turned = apply_azimuth(inclined, 90.0)
        self.assertAlmostEqual(turned.azimuth_deg, 90.0, places=5)
        moved_toe = apply_toe(turned, Point3(x=4.0, y=3.0, z=-8.0))
        self.assertAlmostEqual(moved_toe.toe.x, 4.0)
        self.assertAlmostEqual(moved_toe.collar.x, 2.0)

    def test_apply_hole_geometry_patch_and_manual_insert(self):
        contour = BlockContour(
            vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (20, 0), (20, 20), (0, 20)]],
            bench=BenchSurface(crest_z_m=5.0, toe_z_m=-5.0),
        )
        hole = _hole("1-01", 0, 0, 2.0, 3.0)
        updated = apply_hole_geometry(hole, {"depth_m": 12.0, "angle_deg": 10.0, "kind": "buffer"})
        self.assertEqual(updated.kind, "buffer")
        self.assertAlmostEqual(updated.length_m, 12.0)
        inserted = insert_manual_hole([], 4.0, 5.0, contour, {"kind": "stab", "angle_deg": 0.0, "subdrill_m": 1.0})
        self.assertEqual(inserted.source, "manual")
        self.assertEqual(inserted.kind, "stab")
        self.assertTrue(inserted.id.startswith("M-"))
        self.assertAlmostEqual(inserted.collar.z, 5.0)


if __name__ == "__main__":
    unittest.main()

