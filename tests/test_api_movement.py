"""BDX-023 movement API: predicted overlay, estimate label, no design rewrite."""
import copy
import unittest

from api.schemas.design import ChargeGenerateRequest, PatternGenerateRequest
from api.schemas.movement import MovementPredictRequest
from api.services import design_service
from design.models import ROLE_MEASURED, ROLE_PREDICTED
from simulation.movement.models import KIND_ESTIMATE


def _contour_payload(width: float = 24.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


class MovementApiTests(unittest.TestCase):
    def _charged_design(self) -> dict:
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
        charged = design_service.generate_charge(
            ChargeGenerateRequest(
                holes=[h.model_dump() for h in holes],
                rules={"stemming_m": 3.0, "decking": "continuous", "grid_a_m": 5.0, "grid_b_m": 4.0},
                explosive={"name": "АНФО", "density_t_m3": 0.82, "power_mj_kg": 3.8},
                contour=_contour_payload(),
            )
        )
        return {
            "design_id": "heave-api",
            "contour": _contour_payload(),
            "holes": [h.model_dump() for h in holes],
            "loads": [ld.model_dump() for ld in charged.loads],
            "pattern_params": {"spacing_a_m": 5.0, "burden_b_m": 4.0},
            "charge_rules": {"stemming_m": 3.0, "grid_a_m": 5.0, "grid_b_m": 4.0},
            "explosive_key": "АНФО",
        }

    def test_lists_estimate_model(self):
        response = design_service.list_movement_models()
        self.assertEqual(response.models[0].id, "kinematic_heave")
        self.assertEqual(response.kind, KIND_ESTIMATE)
        self.assertEqual(response.label_ru, "оценка")
        self.assertEqual(response.label_en, "estimate")
        self.assertFalse(response.is_physics_simulation)
        self.assertIn("оценка", response.disclaimer.lower())
        self.assertNotIn("simulation of physics", response.disclaimer.lower())

    def test_predict_is_predicted_estimate(self):
        design = self._charged_design()
        original = copy.deepcopy(design)
        response = design_service.predict_movement(MovementPredictRequest(design=design))
        self.assertEqual(response.role, ROLE_PREDICTED)
        self.assertEqual(response.kind, KIND_ESTIMATE)
        self.assertFalse(response.is_physics_simulation)
        self.assertFalse(response.design_rewritten)
        self.assertTrue(response.prediction_applied)
        self.assertEqual(response.muckpile.role, ROLE_PREDICTED)
        self.assertGreater(response.muckpile.throw_m, 0.0)
        self.assertGreater(response.muckpile.heave_m, 0.0)
        self.assertGreater(len(response.holes), 0)
        self.assertTrue(all(item.role == ROLE_PREDICTED for item in response.holes))
        self.assertEqual(response.maps.role, ROLE_PREDICTED)
        self.assertEqual(response.maps.metrics, ["throw", "heave", "swell"])
        self.assertEqual(original["holes"], design["holes"])
        self.assertEqual(original["loads"], design["loads"])
        self.assertEqual(original["pattern_params"], design["pattern_params"])

    def test_measured_is_not_mixed_into_prediction(self):
        response = design_service.predict_movement(
            MovementPredictRequest(
                design=self._charged_design(),
                measured=[{"role": "measured", "throw_m": 99.0, "length_m": 120.0, "notes": "survey"}],
            )
        )
        self.assertEqual(response.measured[0].role, ROLE_MEASURED)
        self.assertEqual(response.measured[0].throw_m, 99.0)
        self.assertNotAlmostEqual(response.muckpile.throw_m, 99.0)
        self.assertEqual(response.muckpile.role, ROLE_PREDICTED)


if __name__ == "__main__":
    unittest.main()
