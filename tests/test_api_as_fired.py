import unittest

from api.exceptions import InvalidDesignError
from api.schemas.design import (
    AsFiredCompareRequest,
    AsFiredRecordRequest,
    ExecutionCompareRequest,
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


class AsFiredApiTests(unittest.TestCase):
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
        first = holes[0]
        return {
            "design_id": "af-api",
            "contour": _contour_payload(),
            "holes": [h.model_dump() for h in holes],
            "network": {
                "system": "electronic",
                "detonators": [
                    {
                        "id": "det-1",
                        "hole_id": first.id,
                        "delay_ms": 0.0,
                        "product": "i-kon",
                        "kind": "electronic",
                        "deck_index": None,
                        "primer_index": None,
                        "channel_id": "ch-1",
                    }
                ],
                "electronic_times_ms": {first.id: 33.0},
                "electronic_channels": [
                    {"id": "ch-1", "hole_id": first.id, "time_ms": 33.0, "deck_index": None, "primer_index": None, "label": ""}
                ],
            },
            "as_fired_holes": [],
        }

    def test_record_returns_deviations_and_keeps_designed_network(self):
        design = self._design()
        first = design["holes"][0]
        designed_product = design["network"]["detonators"][0]["product"]
        designed_time = design["network"]["electronic_times_ms"][first["id"]]
        response = design_service.record_as_fired(
            AsFiredRecordRequest(
                design=design,
                holes=[
                    {
                        "design_hole_id": first["id"],
                        "detonator": {
                            "id": "det-a",
                            "hole_id": first["id"],
                            "product": "DaveyTronic",
                            "kind": "electronic",
                            "delay_ms": 0.0,
                        },
                        "programmed_time_ms": 40.0,
                        "verified_time_ms": 41.0,
                    }
                ],
            )
        )
        self.assertEqual(response.as_fired_count, 1)
        self.assertAlmostEqual(response.deviations[0].programmed_time_delta_ms or 0.0, 7.0, places=3)
        self.assertTrue(response.deviations[0].detonator_product_mismatch)
        self.assertEqual(response.network.detonators[0].product, designed_product)
        self.assertAlmostEqual(response.network.electronic_times_ms[first["id"]], designed_time)
        echoed_hole = next(hole for hole in response.holes if hole.id == first["id"])
        self.assertEqual(echoed_hole.collar.model_dump(), first["collar"])

    def test_compare_reads_stored_as_fired(self):
        design = self._design()
        first = design["holes"][0]
        recorded = design_service.record_as_fired(
            AsFiredRecordRequest(
                design=design,
                holes=[
                    {
                        "design_hole_id": first["id"],
                        "detonator": design["network"]["detonators"][0],
                        "programmed_time_ms": 33.0,
                        "verified_time_ms": 33.0,
                    }
                ],
            )
        )
        design["as_fired_holes"] = [item.model_dump() for item in recorded.as_fired_holes]
        compared = design_service.compare_as_fired(AsFiredCompareRequest(design=design))
        self.assertEqual(compared.compared_count, 1)
        self.assertAlmostEqual(compared.deviations[0].programmed_time_delta_ms or 0.0, 0.0)

    def test_unknown_design_hole_is_invalid(self):
        design = self._design()
        with self.assertRaises(InvalidDesignError):
            design_service.record_as_fired(
                AsFiredRecordRequest(
                    design=design,
                    holes=[{"design_hole_id": "no-such-hole", "programmed_time_ms": 1.0}],
                )
            )

    def test_execution_compare_includes_three_reports(self):
        design = self._design()
        first = design["holes"][0]
        design["as_drilled_holes"] = [
            {
                "design_hole_id": first["id"],
                "actual_collar": first["collar"],
                "actual_toe": first["toe"],
                "actual_depth": 10.0,
                "actual_diameter": 152.0,
            }
        ]
        fired = design_service.record_as_fired(
            AsFiredRecordRequest(
                design=design,
                holes=[
                    {
                        "design_hole_id": first["id"],
                        "detonator": design["network"]["detonators"][0],
                        "programmed_time_ms": 33.0,
                    }
                ],
            )
        )
        design["as_fired_holes"] = [item.model_dump() for item in fired.as_fired_holes]
        summary = design_service.compare_execution(ExecutionCompareRequest(design=design))
        self.assertEqual(summary.design_vs_drilled.compared_count, 1)
        self.assertEqual(summary.design_vs_fired.compared_count, 1)
        self.assertEqual(summary.as_drilled_count, 1)
        self.assertEqual(summary.as_fired_count, 1)


if __name__ == "__main__":
    unittest.main()
