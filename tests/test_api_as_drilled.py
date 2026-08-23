import unittest

from api.exceptions import InvalidDesignError
from api.schemas.design import (
    AsDrilledCompareRequest,
    AsDrilledRecordRequest,
    MwdImportRequest,
    PatternGenerateRequest,
)
from api.services import design_service


def _contour_payload(width: float = 24.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


class AsDrilledApiTests(unittest.TestCase):
    def _design(self) -> dict:
        holes = design_service.generate_pattern(
            PatternGenerateRequest(
                contour=_contour_payload(),
                params={
                    "pattern": "rectangular",
                    "spacing_a_m": 5.0,
                    "burden_b_m": 4.0,
                    "offset_from_face_m": 0.0,
                    "edge_margin_m": 0.0,
                    "diameter_mm": 152.0,
                    "subdrill_m": 1.0,
                },
            )
        ).holes
        return {
            "design_id": "ad-api",
            "contour": _contour_payload(),
            "holes": [h.model_dump() for h in holes],
            "pattern_params": {"spacing_a_m": 5.0, "burden_b_m": 4.0},
            "as_drilled_holes": [],
        }

    def test_mwd_schema_lists_six_physical_fields(self):
        schema = design_service.list_mwd_schema()
        self.assertIsNone(schema.manufacturer)
        self.assertEqual(
            [field.id for field in schema.fields],
            [
                "depth_m",
                "penetration_rate",
                "rotation_pressure",
                "feed_pressure",
                "torque",
                "air_pressure",
            ],
        )

    def test_record_returns_deviations_and_keeps_designed_holes(self):
        design = self._design()
        first = design["holes"][0]
        designed_collar = dict(first["collar"])
        response = design_service.record_as_drilled(
            AsDrilledRecordRequest(
                design=design,
                holes=[
                    {
                        "design_hole_id": first["id"],
                        "actual_collar": {
                            "x": first["collar"]["x"] + 0.6,
                            "y": first["collar"]["y"] + 0.8,
                            "z": first["collar"]["z"],
                        },
                        "actual_toe": {
                            "x": first["toe"]["x"] + 0.6,
                            "y": first["toe"]["y"] + 0.8,
                            "z": first["toe"]["z"] - 0.4,
                        },
                        "actual_depth": 11.2,
                        "actual_diameter": 165.0,
                    }
                ],
            )
        )
        self.assertEqual(response.as_drilled_count, 1)
        self.assertEqual(response.deviations[0].design_hole_id, first["id"])
        self.assertAlmostEqual(response.deviations[0].collar_offset_m, 1.0, places=3)
        self.assertGreater(abs(response.deviations[0].depth_deviation_m), 0.0)
        echoed = next(hole for hole in response.holes if hole.id == first["id"])
        self.assertEqual(echoed.collar.model_dump(), designed_collar)
        self.assertAlmostEqual(echoed.diameter_mm, first["diameter_mm"])

    def test_compare_reads_stored_as_drilled(self):
        design = self._design()
        first = design["holes"][0]
        recorded = design_service.record_as_drilled(
            AsDrilledRecordRequest(
                design=design,
                holes=[
                    {
                        "design_hole_id": first["id"],
                        "actual_collar": first["collar"],
                        "actual_toe": first["toe"],
                        "actual_depth": 10.0,
                        "actual_diameter": 152.0,
                    }
                ],
            )
        )
        design["as_drilled_holes"] = [item.model_dump() for item in recorded.as_drilled_holes]
        compared = design_service.compare_as_drilled(AsDrilledCompareRequest(design=design))
        self.assertEqual(compared.compared_count, 1)
        self.assertAlmostEqual(compared.deviations[0].collar_offset_m, 0.0)

    def test_mwd_import_uses_aliases_and_leaves_design_intact(self):
        design = self._design()
        first = design["holes"][0]
        designed_toe = dict(first["toe"])
        response = design_service.import_mwd(
            MwdImportRequest(
                design=design,
                design_hole_id=first["id"],
                samples=[
                    {"depth": 0.0, "rop": 0.9, "pulldown": 70},
                    {"depth_m": 6.0, "penetration_rate": 1.4, "torque": 2100, "air_pressure": 17},
                ],
                source="json",
            )
        )
        self.assertEqual(len(response.as_drilled_holes[0].mwd_samples), 2)
        self.assertAlmostEqual(response.as_drilled_holes[0].mwd_samples[1].torque or 0.0, 2100)
        echoed = next(hole for hole in response.holes if hole.id == first["id"])
        self.assertEqual(echoed.toe.model_dump(), designed_toe)

    def test_unknown_design_hole_is_invalid(self):
        design = self._design()
        with self.assertRaises(InvalidDesignError):
            design_service.record_as_drilled(
                AsDrilledRecordRequest(
                    design=design,
                    holes=[
                        {
                            "design_hole_id": "no-such-hole",
                            "actual_collar": {"x": 0, "y": 0, "z": 0},
                            "actual_toe": {"x": 0, "y": 0, "z": -10},
                        }
                    ],
                )
            )


if __name__ == "__main__":
    unittest.main()
