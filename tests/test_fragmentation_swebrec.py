"""Swebrec function: bounds, inversion, and oversize."""
import unittest

from simulation.fragmentation.distributions import swebrec_passing, swebrec_size_mm
from simulation.fragmentation.models import ROLE_PREDICTED, Calibration
from simulation.fragmentation.swebrec import default_xmax_mm, predict_swebrec
from tests.test_fragmentation_kuzram import _inputs


class SwebrecTests(unittest.TestCase):
    def test_passing_at_x50_is_half(self):
        self.assertAlmostEqual(swebrec_passing(200.0, 200.0, 4000.0, 2.27), 0.5)

    def test_passing_at_xmax_is_one(self):
        self.assertEqual(swebrec_passing(4000.0, 200.0, 4000.0, 2.27), 1.0)
        self.assertEqual(swebrec_passing(0.0, 200.0, 4000.0, 2.27), 0.0)

    def test_inversion_round_trip(self):
        x50, xmax, b = 180.0, 5000.0, 2.27
        for passing in (0.2, 0.5, 0.8):
            size = swebrec_size_mm(passing, x50, xmax, b)
            self.assertAlmostEqual(swebrec_passing(size, x50, xmax, b), passing, places=6)

    def test_predict_exposes_curve_and_provenance(self):
        prediction = predict_swebrec(_inputs())
        self.assertEqual(prediction.role, ROLE_PREDICTED)
        self.assertEqual(prediction.provenance.model, "swebrec")
        self.assertLess(prediction.x20_mm, prediction.x50_mm)
        self.assertLess(prediction.x50_mm, prediction.x80_mm)
        self.assertTrue(prediction.curve)
        self.assertGreater(prediction.provenance.parameters["xmax_mm"], prediction.x50_mm)

    def test_xmax_floor_keeps_x50_below_xmax(self):
        xmax = default_xmax_mm(0.0, 0.0, 250.0)
        self.assertGreater(xmax, 250.0)

    def test_calibration_b_changes_spread(self):
        tight = predict_swebrec(_inputs(), Calibration(swebrec_b=4.0))
        wide = predict_swebrec(_inputs(), Calibration(swebrec_b=1.2))
        self.assertLess(tight.x80_mm - tight.x20_mm, wide.x80_mm - wide.x20_mm)


if __name__ == "__main__":
    unittest.main()
