"""«Старая модель» — прежние формулы: *_legacy или версия ниже 2.0.0."""
import unittest

from design.reporting.html import _model_version_line
from design.reporting.types import PredictedOutcomes
from simulation.fragmentation.models import is_old_model


class IsOldModelTests(unittest.TestCase):
    def test_cases(self):
        cases = (
            ("kuzram", "2.0.0", False),
            ("swebrec", "2.1.0", False),
            ("kuzram", "1.0.0", True),
            ("kuzram", "1", True),
            ("kuzram", "", True),
            ("kuzram", "abc", True),
            ("kuzram_legacy", "1.0.0", True),
            ("kuzram_legacy", "2.0.0", True),
        )
        for model, version, old in cases:
            with self.subTest(model=model, version=version):
                self.assertIs(is_old_model(model, version), old)


class PassportLineTests(unittest.TestCase):
    def test_saved_prediction_before_pr2_is_marked(self):
        predicted = PredictedOutcomes()
        predicted.fragmentation_model = "kuzram"
        predicted.fragmentation_model_version = "1.0.0"

        self.assertIn("Старая модель", _model_version_line(predicted))

    def test_new_prediction_without_snapshot_is_not_marked(self):
        predicted = PredictedOutcomes()
        predicted.fragmentation_model = "kuzram"
        predicted.fragmentation_model_version = "2.0.0"

        self.assertNotIn("Старая модель", _model_version_line(predicted))


if __name__ == "__main__":
    unittest.main()
