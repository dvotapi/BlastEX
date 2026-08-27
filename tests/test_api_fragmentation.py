import unittest

from api.schemas.design import ChargeGenerateRequest, FragmentationPredictRequest, PatternGenerateRequest
from api.services import design_service
from simulation.fragmentation.models import ROLE_MEASURED, ROLE_PREDICTED


def _contour_payload(width: float = 24.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


class FragmentationApiTests(unittest.TestCase):
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
            "design_id": "frag-api",
            "contour": _contour_payload(),
            "holes": [h.model_dump() for h in holes],
            "loads": [ld.model_dump() for ld in charged.loads],
            "pattern_params": {"spacing_a_m": 5.0, "burden_b_m": 4.0},
            "charge_rules": {"stemming_m": 3.0, "hole_oversize_coeff": 1.05, "grid_a_m": 5.0, "grid_b_m": 4.0},
            "explosive_key": "АНФО",
        }

    def test_lists_three_models(self):
        response = design_service.list_fragmentation_models()
        ids = [item.id for item in response.models]
        self.assertEqual(ids, ["kuznetsov", "kuzram", "swebrec"])

    def test_predict_kuzram_on_design(self):
        response = design_service.predict_fragmentation(
            FragmentationPredictRequest(
                design=self._charged_design(),
                model="kuzram",
                lump_size_mm=400.0,
                rock={"name": "Гранит", "density_t_m3": 2.65, "ucs_mpa": 150.0, "fissuring_ff": 2.0},
                explosive={"name": "АНФО", "density_t_m3": 0.82, "power_mj_kg": 3.8},
            )
        )
        self.assertEqual(response.model, "kuzram")
        self.assertEqual(response.site.prediction.role, ROLE_PREDICTED)
        self.assertEqual(response.target.role, "designed")
        self.assertEqual(response.measured, [])
        self.assertGreater(len(response.holes), 0)
        self.assertEqual(response.maps.metrics, ["x50", "x80", "oversize", "powder_factor"])
        self.assertLess(response.site.prediction.x20_mm, response.site.prediction.x50_mm)
        self.assertTrue(response.site.prediction.curve)
        self.assertTrue(response.site.prediction.provenance.inputs)
        self.assertTrue(response.site.prediction.provenance.parameters)

    def test_measured_payload_is_not_mixed_into_prediction(self):
        response = design_service.predict_fragmentation(
            FragmentationPredictRequest(
                design=self._charged_design(),
                model="swebrec",
                lump_size_mm=400.0,
                rock={"name": "Гранит", "density_t_m3": 2.65, "ucs_mpa": 150.0, "fissuring_ff": 2.0},
                explosive={"name": "АНФО", "density_t_m3": 0.82, "power_mj_kg": 3.8},
                measured=[{"role": "measured", "x50_mm": 55.0, "source": "sieve", "method": "lab"}],
            )
        )
        self.assertEqual(response.measured[0].role, ROLE_MEASURED)
        self.assertEqual(response.measured[0].x50_mm, 55.0)
        self.assertNotEqual(response.site.prediction.x50_mm, 55.0)
        self.assertEqual(response.site.prediction.role, ROLE_PREDICTED)

    def test_unknown_model_is_invalid_design(self):
        from api.exceptions import InvalidDesignError

        with self.assertRaises(InvalidDesignError):
            design_service.predict_fragmentation(
                FragmentationPredictRequest(design=self._charged_design(), model="vibration")
            )


if __name__ == "__main__":
    unittest.main()
