"""Дрейф калибровки считается только на строках той же базы, что и артефакт."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from intelligence.drift.scoring import _score_calibration

KEY = "prediction.calibrated_x50_mm"
OLD_ROW = {"x50_mm": 160.0, "predicted_x50_mm": 150.0}
NEW_STORED_ROW = {"x50_mm": 160.0, "predicted_x50_mm": 150.0, "predicted_model": "kuzram", "predicted_model_version": "2.0.0"}
NEW_ROW = {**NEW_STORED_ROW, "baseline_x50_mm": 140.0, "baseline_model": "kuzram", "baseline_model_version": "2.0.0"}


def _samples(*rows):
    return [SimpleNamespace(targets={"FRAGMENTATION": row}, features={}) for row in rows]


def _score(base: tuple[str, str], *rows):
    model = SimpleNamespace(
        model_type="kuzram_residual", baseline_model=base[0], baseline_model_version=base[1]
    )
    with patch("intelligence.calibration.persistence.load_model", return_value=model), patch(
        "intelligence.calibration.prediction.apply_residual",
        side_effect=lambda model, *, features, baseline, baseline_source: SimpleNamespace(calibrated=baseline),
    ):
        return _score_calibration("team", "cal", _samples(*rows)).get(KEY, [])


class DriftBaseTests(unittest.TestCase):
    def test_old_artifact_scores_only_old_rows(self):
        self.assertEqual(_score(("", ""), OLD_ROW, NEW_STORED_ROW), [150.0])

    def test_new_artifact_scores_current_baseline(self):
        self.assertEqual(_score(("kuzram", "2.0.0"), OLD_ROW, NEW_ROW), [140.0])

    def test_unknown_artifact_model_scores_nothing(self):
        """Неизвестная модель в файле артефакта не роняет дрейф: сравнивать нечего."""
        self.assertEqual(_score(("no_such_model", "2.0.0"), OLD_ROW, NEW_ROW), [])


if __name__ == "__main__":
    unittest.main()
