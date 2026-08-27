import unittest

from Blast import ExplosiveProperties
from design.charging import apply_charge_rules
from design.models import (
    ROLE_MEASURED,
    ROLE_PREDICTED,
    BenchSurface,
    BlastDesign,
    BlockContour,
    Point3,
    Receptor,
    VibrationMeasurement,
    VibrationModel,
)
from design.pattern import generate_pattern
from design.timing import build_template_network
from design.vibration import (
    CONVENTION_Q_CUBE_OVER_R,
    CONVENTION_R_OVER_Q_SQRT,
    event_mic,
    predict_design,
    predict_ppv,
    receptor_distance_m,
)

EXPLOSIVE = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)


def _charged_design() -> BlastDesign:
    contour = BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (20, 0), (20, 16), (0, 16)]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
        free_faces=[[0, 1]],
    )
    params = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 4.0, "offset_from_face_m": 0.0, "edge_margin_m": 0.0}
    holes = generate_pattern(contour, params)
    loads = apply_charge_rules(
        holes, {"stemming_m": 3.0, "decking": "continuous", "grid_a_m": 4.0, "grid_b_m": 4.0}, EXPLOSIVE
    )
    network = build_template_network(holes, "echelon", {"system": "nonel"})
    return BlastDesign(
        design_id="vib",
        contour=contour,
        holes=holes,
        loads=loads,
        network=network,
        pattern_params=params,
        vibration_models=[
            VibrationModel(id="vm-site", k=200.0, n=1.6, scaled_distance=CONVENTION_Q_CUBE_OVER_R, confidence=0.4)
        ],
        receptors=[
            Receptor(
                id="R-1",
                name="Здание",
                kind="building",
                location=Point3(x=80.0, y=8.0, z=0.0),
                ppv_limit_mm_s=5.0,
            ),
            Receptor(
                id="R-2",
                name="Сейсмопост",
                kind="monitoring_station",
                location=Point3(x=30.0, y=8.0, z=0.0),
            ),
        ],
    )


class EventMicReuseTests(unittest.TestCase):
    def test_reuses_charge_per_delay_window(self):
        from design.analysis import charge_per_delay
        from design.timing import resolve_network

        design = _charged_design()
        resolved = resolve_network(design.network, [h for h in design.holes if h.enabled], design.loads)
        expected = charge_per_delay(resolved.times_ms, design.loads, window_ms=8.0, events=resolved.events)
        got = event_mic(design, window_ms=8.0)
        self.assertEqual(got["mic_kg"], expected["mic_kg"])
        self.assertEqual(got["hole_ids"], expected["hole_ids"])

    def test_wider_window_does_not_decrease_mic(self):
        design = _charged_design()
        narrow = event_mic(design, window_ms=1.0)
        wide = event_mic(design, window_ms=500.0)
        self.assertLessEqual(narrow["mic_kg"], wide["mic_kg"])

    def test_rejects_non_positive_window(self):
        with self.assertRaises(ValueError):
            event_mic(_charged_design(), window_ms=0.0)


class PredictDesignTests(unittest.TestCase):
    def test_predictions_are_separate_from_measurements(self):
        design = _charged_design()
        design.vibration_measurements = [
            VibrationMeasurement(
                id="VM-1",
                receptor_id="R-1",
                ppv_mm_s=0.11,
                source="сейсмопост",
                scaled_distance=CONVENTION_Q_CUBE_OVER_R,
            )
        ]
        result = predict_design(design, mic_window_ms=8.0)
        self.assertEqual(result["convention"], CONVENTION_Q_CUBE_OVER_R)
        self.assertEqual(len(result["predictions"]), 2)
        building = next(item for item in result["predictions"] if item["receptor_id"] == "R-1")
        self.assertEqual(building["role"], ROLE_PREDICTED)
        self.assertNotAlmostEqual(building["ppv_mm_s"], 0.11)
        self.assertEqual(building["measured"][0]["role"], ROLE_MEASURED)
        self.assertEqual(building["measured"][0]["ppv_mm_s"], 0.11)
        self.assertEqual(result["measured"][0]["role"], ROLE_MEASURED)

    def test_near_receptor_has_higher_ppv(self):
        result = predict_design(_charged_design(), mic_window_ms=8.0)
        by_id = {item["receptor_id"]: item for item in result["predictions"]}
        self.assertGreater(by_id["R-2"]["ppv_mm_s"], by_id["R-1"]["ppv_mm_s"])
        self.assertLess(by_id["R-2"]["distance_m"], by_id["R-1"]["distance_m"])

    def test_limit_flag(self):
        design = _charged_design()
        design.receptors[0].ppv_limit_mm_s = 0.0001
        result = predict_design(design)
        building = next(item for item in result["predictions"] if item["receptor_id"] == "R-1")
        self.assertTrue(building["exceeds_limit"])

    def test_unknown_model_is_rejected(self):
        with self.assertRaises(ValueError):
            predict_design(_charged_design(), model_id="no-such")

    def test_measurement_convention_mismatch_is_warned_not_converted(self):
        design = _charged_design()
        result = predict_design(
            design,
            measurements=[
                VibrationMeasurement(
                    id="VM-x",
                    receptor_id="R-1",
                    ppv_mm_s=2.0,
                    scaled_distance=CONVENTION_R_OVER_Q_SQRT,
                )
            ],
        )
        self.assertTrue(any("Нельзя смешивать" in message for message in result["warnings"]))
        building = next(item for item in result["predictions"] if item["receptor_id"] == "R-1")
        self.assertFalse(building["measured"][0]["scaled_distance_compatible"])
        self.assertEqual(building["scaled_distance"], CONVENTION_Q_CUBE_OVER_R)

    def test_distance_uses_nearest_mic_hole(self):
        design = _charged_design()
        mic = event_mic(design, window_ms=8.0)
        distance, hole_id = receptor_distance_m(design.receptors[0], design.holes, mic["hole_ids"])
        self.assertGreater(distance, 0.0)
        self.assertIn(hole_id, mic["hole_ids"] or [h.id for h in design.holes])

    def test_matches_site_law_at_reported_distance(self):
        design = _charged_design()
        result = predict_design(design)
        row = result["predictions"][0]
        model = design.vibration_models[0]
        expected = predict_ppv(row["mic_kg"], row["distance_m"], model)
        self.assertAlmostEqual(row["ppv_mm_s"], round(expected, 4), places=4)


if __name__ == "__main__":
    unittest.main()
