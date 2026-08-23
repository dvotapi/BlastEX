import unittest

from api.schemas.design import AnalyzeRequest, TieGenerateRequest
from api.services import design_service
from design.models import InitiationNetwork


def _contour_payload(width: float = 20.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


class TimingApiTests(unittest.TestCase):
    def _holes(self):
        from api.schemas.design import PatternGenerateRequest

        response = design_service.generate_pattern(
            PatternGenerateRequest(
                contour=_contour_payload(),
                params={
                    "pattern": "rectangular",
                    "spacing_a_m": 4.0,
                    "burden_b_m": 4.0,
                    "offset_from_face_m": 0.0,
                    "edge_margin_m": 0.0,
                },
            )
        )
        return response.holes

    def test_tie_generate_includes_v2_objects(self):
        holes = self._holes()
        response = design_service.generate_tie(
            TieGenerateRequest(holes=[h.model_dump() for h in holes], scheme="row", params={"system": "nonel"})
        )
        self.assertGreater(response.starters_count, 0)
        self.assertGreater(response.connectors_count, 0)
        self.assertTrue(response.network.starter_items)
        self.assertTrue(response.network.surface_connectors)
        self.assertTrue(response.network.detonators)

    def test_electronic_expression_and_analyze_events(self):
        holes = self._holes()
        tie = design_service.generate_tie(
            TieGenerateRequest(
                holes=[h.model_dump() for h in holes],
                scheme="row",
                params={
                    "system": "electronic",
                    "timing_mode": "expression",
                    "timing_expression": "interval * row",
                    "interval_ms": 17.0,
                },
            )
        )
        self.assertEqual(tie.network.timing_mode, "expression")
        self.assertTrue(tie.network.electronic_channels)
        analyzed = design_service.analyze_design(
            AnalyzeRequest(
                design={
                    "design_id": "t",
                    "holes": [h.model_dump() for h in holes],
                    "contour": _contour_payload(),
                    "network": tie.network.model_dump(),
                    "loads": [],
                },
                isoline_step_ms=25.0,
            )
        )
        self.assertEqual(len(analyzed.times_ms), len(holes))
        self.assertTrue(analyzed.firing_events)
        self.assertTrue(all(event.level == "hole" for event in analyzed.firing_events))

    def test_bad_expression_is_invalid_design(self):
        from api.exceptions import InvalidDesignError

        holes = self._holes()
        with self.assertRaises(InvalidDesignError):
            design_service.generate_tie(
                TieGenerateRequest(
                    holes=[h.model_dump() for h in holes],
                    scheme="row",
                    params={
                        "system": "electronic",
                        "timing_mode": "expression",
                        "timing_expression": "__import__('os')",
                    },
                )
            )

    def test_legacy_network_analyzes(self):
        holes = self._holes()
        from design.models import Connector

        network = InitiationNetwork(
            system="nonel",
            starters=[holes[0].id],
            connectors=[Connector(from_hole=holes[0].id, to_hole=holes[1].id, delay_ms=25.0)],
        )
        analyzed = design_service.analyze_design(
            AnalyzeRequest(
                design={
                    "design_id": "legacy",
                    "holes": [h.model_dump() for h in holes[:2]],
                    "contour": _contour_payload(),
                    "network": network.to_dict(),
                }
            )
        )
        self.assertIn(holes[1].id, analyzed.times_ms)


if __name__ == "__main__":
    unittest.main()
