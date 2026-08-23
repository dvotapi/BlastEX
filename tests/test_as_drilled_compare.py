import unittest

from design.as_drilled import compare_design, record_as_drilled, record_as_drilled_many
from design.models import AsDrilledHole, BlastDesign, BlockContour, Hole, Point3


def _contour() -> BlockContour:
    return BlockContour(
        vertices=[
            Point3(x=0, y=0, z=0),
            Point3(x=20, y=0, z=0),
            Point3(x=20, y=16, z=0),
            Point3(x=0, y=16, z=0),
        ],
        free_faces=[[0, 1]],
    )


def _hole(hole_id: str, row: int, col: int, x: float, y: float, *, angle_shift: float = 0.0) -> Hole:
    return Hole(
        id=hole_id,
        row=row,
        col=col,
        collar=Point3(x=x, y=y, z=0.0),
        toe=Point3(x=x + angle_shift, y=y, z=-10.0),
        diameter_mm=152.0,
        subdrill_m=1.0,
    )


class AsDrilledCompareTests(unittest.TestCase):
    def test_zero_deviation_when_fact_matches_design(self):
        design = BlastDesign(
            design_id="cmp",
            contour=_contour(),
            holes=[_hole("1-01", 1, 1, 4.0, 4.0), _hole("1-02", 1, 2, 9.0, 4.0)],
        )
        record_as_drilled(
            design,
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=4.0, y=4.0, z=0.0),
                actual_toe=Point3(x=4.0, y=4.0, z=-10.0),
                actual_depth=10.0,
                actual_diameter=152.0,
            ),
        )
        row = compare_design(design)["deviations"][0]
        self.assertAlmostEqual(row["collar_offset_m"], 0.0)
        self.assertAlmostEqual(row["toe_offset_m"], 0.0)
        self.assertAlmostEqual(row["depth_deviation_m"], 0.0)
        self.assertAlmostEqual(row["angle_deviation_deg"], 0.0)
        self.assertAlmostEqual(row["azimuth_deviation_deg"], 0.0)

    def test_collar_toe_depth_angle_azimuth(self):
        designed = _hole("1-01", 1, 1, 0.0, 0.0)
        design = BlastDesign(design_id="cmp", contour=_contour(), holes=[designed])
        record_as_drilled(
            design,
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=3.0, y=4.0, z=0.0),
                actual_toe=Point3(x=3.0, y=4.0 + 2.0, z=-10.0),
                actual_depth=12.0,
                actual_diameter=165.0,
            ),
        )
        row = compare_design(design)["deviations"][0]
        self.assertAlmostEqual(row["collar_offset_m"], 5.0)
        self.assertGreater(row["toe_offset_m"], 5.0)
        self.assertAlmostEqual(row["depth_deviation_m"], 12.0 - designed.length_m, places=3)
        self.assertGreater(row["angle_deviation_deg"], 0.0)
        self.assertAlmostEqual(row["azimuth_deviation_deg"], 0.0, places=3)

    def test_azimuth_wraps_across_north(self):
        designed = Hole(
            id="1-01",
            row=1,
            col=1,
            collar=Point3(x=0, y=0, z=0),
            toe=Point3(x=-1.0, y=5.0, z=-10.0),
            diameter_mm=152.0,
        )
        design = BlastDesign(design_id="cmp", contour=_contour(), holes=[designed])
        record_as_drilled(
            design,
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=0, y=0, z=0),
                actual_toe=Point3(x=1.0, y=5.0, z=-10.0),
                actual_depth=designed.length_m,
                actual_diameter=152.0,
            ),
        )
        row = compare_design(design)["deviations"][0]
        self.assertGreater(row["azimuth_deviation_deg"], 0.0)
        self.assertLess(abs(row["azimuth_deviation_deg"]), 45.0)

    def test_actual_spacing_and_burden(self):
        holes = [
            _hole("1-01", 1, 1, 4.0, 4.0),
            _hole("1-02", 1, 2, 9.0, 4.0),
            _hole("2-01", 2, 1, 4.0, 8.0),
        ]
        design = BlastDesign(design_id="cmp", contour=_contour(), holes=holes)
        record_as_drilled_many(
            design,
            [
                AsDrilledHole(
                    design_hole_id="1-01",
                    actual_collar=Point3(x=4.0, y=4.2, z=0.0),
                    actual_toe=Point3(x=4.0, y=4.2, z=-10.0),
                    actual_depth=10.0,
                    actual_diameter=152.0,
                ),
                AsDrilledHole(
                    design_hole_id="1-02",
                    actual_collar=Point3(x=9.4, y=4.2, z=0.0),
                    actual_toe=Point3(x=9.4, y=4.2, z=-10.0),
                    actual_depth=10.0,
                    actual_diameter=152.0,
                ),
                AsDrilledHole(
                    design_hole_id="2-01",
                    actual_collar=Point3(x=4.0, y=8.5, z=0.0),
                    actual_toe=Point3(x=4.0, y=8.5, z=-10.0),
                    actual_depth=10.0,
                    actual_diameter=152.0,
                ),
            ],
        )
        payload = compare_design(design)
        self.assertEqual(payload["pattern_basis"], "executed")
        by_id = {row["design_hole_id"]: row for row in payload["deviations"]}
        self.assertAlmostEqual(by_id["1-01"]["actual_spacing_m"], 5.4, places=3)
        self.assertAlmostEqual(by_id["1-02"]["designed_spacing_m"], 5.0, places=3)
        self.assertAlmostEqual(by_id["2-01"]["actual_burden_m"], 4.3, places=3)
        self.assertAlmostEqual(by_id["2-01"]["designed_burden_m"], 4.0, places=3)

    def test_compare_does_not_mutate_designed_holes(self):
        design = BlastDesign(design_id="cmp", contour=_contour(), holes=[_hole("1-01", 1, 1, 2.0, 2.0)])
        record_as_drilled(
            design,
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=2.5, y=2.0, z=0.0),
                actual_toe=Point3(x=2.5, y=2.0, z=-10.0),
                actual_depth=10.0,
                actual_diameter=152.0,
            ),
        )
        before = design.holes[0].to_dict()
        compare_design(design)
        self.assertEqual(design.holes[0].to_dict(), before)


if __name__ == "__main__":
    unittest.main()
