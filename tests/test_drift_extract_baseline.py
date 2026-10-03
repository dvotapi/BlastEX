"""Дрейф: baseline текущей базы в строке снимка — контекст модели, а не измеренная цель."""
import unittest

from intelligence.datasets.builder import build_snapshot
from intelligence.drift.extract import stored_prediction_series, target_series
from tests.dataset_fixtures import closed_design


class BaselineIsNotTargetTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = build_snapshot(
            [closed_design("d-1"), closed_design("d-2")], site_id="quarry-1", dataset_id="s", dataset_version=1
        )

    def test_row_carries_baseline_numbers_and_nested_settings(self):
        frag = self.snapshot.samples[0].targets["FRAGMENTATION"]

        self.assertIsNotNone(frag["baseline_x50_mm"])
        self.assertIn("rock_factor_correction", frag["baseline_settings"]["values"])

    def test_baseline_fields_do_not_become_target_series(self):
        series = target_series([self.snapshot])

        self.assertEqual([key for key in series if key.startswith("FRAGMENTATION.baseline_")], [])
        self.assertIn("FRAGMENTATION.x50_mm", series)

    def test_model_strings_and_baseline_make_no_series_at_all(self):
        everything = {**target_series([self.snapshot]), **stored_prediction_series([self.snapshot])}

        self.assertEqual([key for key in everything if "baseline_" in key], [])
        self.assertEqual([key for key in everything if "_model" in key], [])
        self.assertIn("FRAGMENTATION.predicted_x50_mm", everything)


if __name__ == "__main__":
    unittest.main()
