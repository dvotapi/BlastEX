import unittest

from design.models import (
    DESIGN_VERSION,
    ROLE_EXECUTED,
    AsDrilledHole,
    BlastDesign,
    Hole,
    MwdSample,
    Point3,
    SurveyPoint,
)
from design.as_drilled import record_as_drilled


def _hole(hole_id: str = "1-01", x: float = 0.0, y: float = 0.0) -> Hole:
    return Hole(
        id=hole_id,
        row=1,
        col=1,
        collar=Point3(x=x, y=y, z=0.0),
        toe=Point3(x=x, y=y, z=-10.0),
        diameter_mm=152.0,
        subdrill_m=1.0,
    )


class AsDrilledModelTests(unittest.TestCase):
    def test_round_trip_forces_executed_role(self):
        item = AsDrilledHole(
            design_hole_id="1-01",
            actual_collar=Point3(x=1.0, y=2.0, z=0.0),
            actual_toe=Point3(x=1.2, y=2.1, z=-10.5),
            actual_depth=10.6,
            actual_diameter=165.0,
            survey_points=[SurveyPoint(depth_m=10.6, x=1.2, y=2.1, z=-10.5)],
            mwd_samples=[MwdSample(depth_m=5.0, penetration_rate=1.4, torque=1800.0)],
        )
        restored = AsDrilledHole.from_dict(item.to_dict())
        self.assertEqual(restored.role, ROLE_EXECUTED)
        self.assertEqual(restored.provenance.role, ROLE_EXECUTED)
        self.assertAlmostEqual(restored.actual_collar.x, 1.0)
        self.assertAlmostEqual(restored.survey_points[0].depth_m, 10.6)
        self.assertAlmostEqual(restored.mwd_samples[0].torque or 0.0, 1800.0)

    def test_design_version_includes_as_drilled(self):
        design = BlastDesign(design_id="ad")
        payload = design.to_dict()
        self.assertEqual(payload["version"], DESIGN_VERSION)
        self.assertEqual(payload["as_drilled_holes"], [])
        self.assertEqual(DESIGN_VERSION, 9)

    def test_record_does_not_overwrite_designed_hole(self):
        design = BlastDesign(design_id="ad", holes=[_hole()])
        designed_before = design.holes[0].to_dict()
        recorded = record_as_drilled(
            design,
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=0.4, y=-0.2, z=0.1),
                actual_toe=Point3(x=0.5, y=-0.1, z=-10.4),
                actual_depth=10.5,
                actual_diameter=160.0,
            ),
        )
        self.assertEqual(recorded.role, ROLE_EXECUTED)
        self.assertEqual(design.holes[0].to_dict(), designed_before)
        self.assertAlmostEqual(design.holes[0].collar.x, 0.0)
        self.assertAlmostEqual(design.as_drilled_holes[0].actual_collar.x, 0.4)

    def test_record_unknown_hole_is_rejected(self):
        design = BlastDesign(design_id="ad", holes=[_hole()])
        with self.assertRaises(ValueError):
            record_as_drilled(
                design,
                AsDrilledHole(
                    design_hole_id="missing",
                    actual_collar=Point3(x=0, y=0, z=0),
                    actual_toe=Point3(x=0, y=0, z=-1),
                ),
            )
        self.assertEqual(design.as_drilled_holes, [])
        self.assertEqual(design.holes[0].id, "1-01")

    def test_survey_points_fill_toe_and_depth(self):
        item = AsDrilledHole.from_dict(
            {
                "design_hole_id": "1-01",
                "actual_collar": {"x": 0, "y": 0, "z": 0},
                "actual_toe": {"x": 0, "y": 0, "z": 0},
                "survey_points": [{"depth_m": 12.0, "x": 1.0, "y": 0.5, "z": -11.5}],
            }
        )
        from design.as_drilled import normalize_as_drilled

        normalized = normalize_as_drilled(item)
        self.assertAlmostEqual(normalized.actual_toe.x, 1.0)
        self.assertAlmostEqual(normalized.actual_depth, 12.0)


if __name__ == "__main__":
    unittest.main()
