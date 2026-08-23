import unittest

from api.exceptions import InvalidDesignError
from api.schemas.design import (
    ChargeGenerateRequest,
    PatternGenerateRequest,
    ReceptorAttachRequest,
    VibrationPredictRequest,
)
from api.services import design_service
from design.models import ROLE_MEASURED, ROLE_PREDICTED


def _contour_payload(width: float = 24.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


class VibrationApiTests(unittest.TestCase):
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
        from api.schemas.design import TieGenerateRequest

        tie = design_service.generate_tie(
            TieGenerateRequest(holes=[h.model_dump() for h in holes], scheme="row", params={"system": "nonel"})
        )
        return {
            "design_id": "vib-api",
            "contour": _contour_payload(),
            "holes": [h.model_dump() for h in holes],
            "loads": [ld.model_dump() for ld in charged.loads],
            "network": tie.network.model_dump(),
            "pattern_params": {"spacing_a_m": 5.0, "burden_b_m": 4.0},
            "vibration_models": [
                {
                    "id": "vm-site",
                    "name": "Площадочный закон",
                    "k": 200.0,
                    "n": 1.6,
                    "scaled_distance": "q_cube_over_r",
                    "calibration_source": "ориентировочно",
                    "confidence": 0.3,
                }
            ],
            "receptors": [],
            "vibration_measurements": [],
        }

    def test_lists_explicit_conventions(self):
        response = design_service.list_vibration_conventions()
        ids = [item.id for item in response.conventions]
        self.assertEqual(ids, ["q_cube_over_r", "r_over_q_cube", "q_sqrt_over_r", "r_over_q_sqrt"])
        self.assertEqual(response.law, "PPV = K × SD^n")

    def test_attach_receptor_then_predict(self):
        design = self._charged_design()
        attached = design_service.attach_receptor(
            ReceptorAttachRequest(
                design=design,
                receptor={
                    "id": "",
                    "name": "Дробилка",
                    "kind": "crusher",
                    "location": {"x": 90.0, "y": 8.0, "z": 0.0},
                    "ppv_limit_mm_s": 10.0,
                },
            )
        )
        self.assertEqual(attached.receptor.kind, "crusher")
        self.assertTrue(attached.receptor.id)
        self.assertEqual(len(attached.receptors), 1)
        design["receptors"] = [item.model_dump() for item in attached.receptors]
        predicted = design_service.predict_vibration(
            VibrationPredictRequest(
                design=design,
                mic_window_ms=8.0,
                measured=[{"receptor_id": attached.receptor.id, "ppv_mm_s": 1.25, "source": "пост"}],
            )
        )
        self.assertEqual(predicted.convention, "q_cube_over_r")
        self.assertEqual(len(predicted.predictions), 1)
        row = predicted.predictions[0]
        self.assertEqual(row.role, ROLE_PREDICTED)
        self.assertGreater(row.ppv_mm_s, 0.0)
        self.assertGreater(row.distance_m, 0.0)
        self.assertEqual(predicted.measured[0].role, ROLE_MEASURED)
        self.assertAlmostEqual(predicted.measured[0].ppv_mm_s, 1.25)
        self.assertNotAlmostEqual(row.ppv_mm_s, 1.25)

    def test_unknown_model_is_invalid_design(self):
        design = self._charged_design()
        design["receptors"] = [
            {"id": "R-1", "name": "Дом", "kind": "building", "location": {"x": 60.0, "y": 0.0, "z": 0.0}}
        ]
        with self.assertRaises(InvalidDesignError):
            design_service.predict_vibration(VibrationPredictRequest(design=design, model_id="missing"))

    def test_upsert_same_receptor_id(self):
        design = self._charged_design()
        first = design_service.attach_receptor(
            ReceptorAttachRequest(
                design=design,
                receptor={"id": "R-7", "name": "ЛЭП", "kind": "power_line", "location": {"x": 10.0, "y": 10.0, "z": 0.0}},
            )
        )
        design["receptors"] = [item.model_dump() for item in first.receptors]
        second = design_service.attach_receptor(
            ReceptorAttachRequest(
                design=design,
                receptor={"id": "R-7", "name": "ЛЭП-2", "kind": "power_line", "location": {"x": 12.0, "y": 10.0, "z": 0.0}},
            )
        )
        self.assertEqual(len(second.receptors), 1)
        self.assertEqual(second.receptor.name, "ЛЭП-2")
        self.assertAlmostEqual(second.receptor.location.x, 12.0)


if __name__ == "__main__":
    unittest.main()
