"""Новые модели движка: общая база Каннингема, различие — только кривая."""
import unittest

from simulation.fragmentation.base import region_point
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.distributions import DEFAULT_KUZNETSOV_N, rosin_rammler_oversize_pct
from simulation.fragmentation.kuznetsov import predict_kuznetsov
from simulation.fragmentation.kuzram import predict_kuzram
from simulation.fragmentation.models import Calibration
from simulation.fragmentation.swebrec import predict_swebrec
from tests.test_fragmentation_kuzram import _inputs

PREDICTORS = (predict_kuznetsov, predict_kuzram, predict_swebrec)


class NewModelsTests(unittest.TestCase):
    def test_kuzram_is_region_point(self):
        inputs = _inputs(charge_length_m=7.0)
        settings = KuzRamSettings(rock_factor_correction=1.2)
        point = region_point(inputs, settings)

        prediction = predict_kuzram(inputs, None, settings)

        self.assertEqual(prediction.x50_mm, round(point.x50_mm, 1))
        self.assertEqual(prediction.oversize_pct, round(point.oversize_pct, 2))
        self.assertEqual(prediction.provenance.parameters["uniformity_n"], point.uniformity.value)
        self.assertEqual(prediction.provenance.parameters["x50_mm"], point.x50_mm)
        self.assertEqual((prediction.provenance.model, prediction.provenance.model_version), ("kuzram", "2.0.0"))
        self.assertEqual(prediction.warnings, [])

    def test_three_models_share_base(self):
        inputs = _inputs(charge_length_m=7.0)

        predictions = [predict(inputs) for predict in PREDICTORS]

        self.assertEqual({item.x50_mm for item in predictions}, {predictions[0].x50_mm})
        self.assertEqual(
            {item.provenance.parameters["rock_factor_A"] for item in predictions},
            {predictions[0].provenance.parameters["rock_factor_A"]},
        )
        self.assertEqual([item.provenance.model for item in predictions], ["kuznetsov", "kuzram", "swebrec"])
        self.assertEqual({item.provenance.model_version for item in predictions}, {"2.0.0"})

    def test_kuznetsov_uses_fixed_n(self):
        prediction = predict_kuznetsov(_inputs(charge_length_m=7.0))

        self.assertEqual(prediction.provenance.parameters["uniformity_n"], DEFAULT_KUZNETSOV_N)
        self.assertEqual(prediction.provenance.parameters["distribution"], "rosin_rammler")

    def test_swebrec_curve_on_new_x50(self):
        prediction = predict_swebrec(_inputs(charge_length_m=7.0))

        self.assertEqual(prediction.provenance.parameters["distribution"], "swebrec")
        self.assertGreater(prediction.provenance.parameters["xmax_mm"], prediction.provenance.parameters["x50_mm"])

    def test_uniformity_override_is_applied(self):
        inputs = _inputs(charge_length_m=7.0)
        point = region_point(inputs)

        prediction = predict_kuzram(inputs, Calibration(uniformity_n=2.5))

        self.assertEqual(prediction.provenance.parameters["uniformity_n"], 2.5)
        self.assertEqual(prediction.oversize_pct, round(rosin_rammler_oversize_pct(point.x50_mm, 2.5, 400.0), 2))

    def test_rock_factor_override_is_ignored_with_warning(self):
        inputs = _inputs(charge_length_m=7.0)

        plain = predict_kuzram(inputs)
        overridden = predict_kuzram(inputs, Calibration(rock_factor_A=12.0))

        self.assertEqual(overridden.x50_mm, plain.x50_mm)
        self.assertTrue(any("фактор породы A" in item for item in overridden.warnings))

    def test_missing_charge_length_warns(self):
        prediction = predict_kuzram(_inputs())

        self.assertTrue(any("L/H" in item for item in prediction.warnings))

    def test_zero_charge_mass_is_russian_error(self):
        for predict in PREDICTORS:
            with self.subTest(model=predict.__name__):
                with self.assertRaises(ValueError) as ctx:
                    predict(_inputs(charge_mass_kg=0.0, charge_length_m=7.0))
                self.assertIn("Масса заряда", str(ctx.exception))

    def test_settings_change_numbers(self):
        inputs = _inputs(charge_length_m=7.0)

        plain = predict_kuzram(inputs)
        tuned = predict_kuzram(inputs, None, KuzRamSettings(rock_factor_correction=1.5))

        self.assertGreater(tuned.x50_mm, plain.x50_mm)


if __name__ == "__main__":
    unittest.main()
