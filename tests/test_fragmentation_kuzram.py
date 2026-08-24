"""Kuz-Ram: Cunningham n and Rosin–Rammler percentiles."""
import unittest

from simulation.fragmentation.distributions import (
    rosin_rammler_oversize_pct,
    rosin_rammler_passing,
    rosin_rammler_size_mm,
)
from simulation.fragmentation.kuzram import cunningham_uniformity_n, predict_kuzram
from simulation.fragmentation.models import ROLE_PREDICTED, Calibration, FragmentationInputs


def _inputs(**overrides) -> FragmentationInputs:
    payload = dict(
        burden_m=4.0,
        spacing_m=5.0,
        bench_height_m=10.0,
        diameter_mm=152.0,
        charge_mass_kg=90.0,
        powder_factor_kg_m3=0.7,
        stemming_m=3.0,
        explosive_name="АНФО",
        explosive_density_t_m3=0.82,
        explosive_energy_mj_kg=3.8,
        rock_name="Гранит",
        rock_density_t_m3=2.65,
        rock_ucs_mpa=150.0,
        rock_fissuring=2.0,
        lump_size_mm=400.0,
        hole_oversize_coeff=1.05,
        influence_volume_m3=200.0,
    )
    payload.update(overrides)
    return FragmentationInputs(**payload)


class KuzRamTests(unittest.TestCase):
    def test_cunningham_n_matches_blast_py(self):
        # n = max(0.8, (2.2 - 14*B/d) * (1 + (S/B - 1)/2))
        burden = 4.0
        diameter = 0.152 * 1.05
        spacing_coeff = 5.0 / 4.0
        expected = max(0.8, (2.2 - 14 * (burden / diameter)) * (1 + (spacing_coeff - 1) / 2))
        self.assertAlmostEqual(cunningham_uniformity_n(burden, diameter, spacing_coeff), expected)

    def test_n_is_clamped(self):
        self.assertEqual(cunningham_uniformity_n(8.0, 0.1, 1.25), 0.8)

    def test_percentiles_are_monotonic(self):
        prediction = predict_kuzram(_inputs())
        self.assertLess(prediction.x20_mm, prediction.x50_mm)
        self.assertLess(prediction.x50_mm, prediction.x80_mm)
        self.assertEqual(prediction.role, ROLE_PREDICTED)
        self.assertEqual(prediction.provenance.model, "kuzram")
        self.assertTrue(prediction.provenance.model_version)
        self.assertIn("uniformity_n", prediction.provenance.parameters)
        self.assertEqual(prediction.provenance.inputs["burden_m"], 4.0)

    def test_rosin_rammler_x50_is_consistent(self):
        x50 = 200.0
        n = 1.2
        self.assertAlmostEqual(rosin_rammler_size_mm(0.5, x50, n), x50, places=6)
        self.assertAlmostEqual(rosin_rammler_passing(x50, x50, n), 0.5, places=6)

    def test_oversize_drops_when_lump_grows(self):
        x50, n = 180.0, 1.1
        self.assertGreater(
            rosin_rammler_oversize_pct(x50, n, 300.0),
            rosin_rammler_oversize_pct(x50, n, 600.0),
        )

    def test_calibration_overrides_n(self):
        default = predict_kuzram(_inputs())
        calibrated = predict_kuzram(_inputs(), Calibration(uniformity_n=2.5))
        self.assertNotAlmostEqual(default.x80_mm, calibrated.x80_mm)
        self.assertEqual(calibrated.provenance.calibration["uniformity_n"], 2.5)

    def test_cannot_mark_prediction_as_measured(self):
        prediction = predict_kuzram(_inputs())
        prediction.role = "measured"
        # dataclass __post_init__ already ran; API to_dict still forces predicted.
        self.assertEqual(prediction.to_dict()["role"], ROLE_PREDICTED)


if __name__ == "__main__":
    unittest.main()
