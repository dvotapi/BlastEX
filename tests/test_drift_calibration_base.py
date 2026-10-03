"""Дрейф калибровки считается только на строках той же базы, что и артефакт."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from intelligence.calibration.base import CURRENT_BASE
from intelligence.drift.scoring import _score_calibration
from tests.calibration_fixtures import PR2_VERSION

KEY = "prediction.calibrated_x50_mm"
OLD_ROW = {"x50_mm": 160.0, "predicted_x50_mm": 150.0}
CURRENT = (CURRENT_BASE.model, CURRENT_BASE.model_version)
NEW_STORED_ROW = {
    "x50_mm": 160.0,
    "predicted_x50_mm": 150.0,
    "predicted_model": CURRENT_BASE.model,
    "predicted_model_version": CURRENT_BASE.model_version,
}
NEW_ROW = {
    **NEW_STORED_ROW,
    "baseline_x50_mm": 140.0,
    "baseline_model": CURRENT_BASE.model,
    "baseline_model_version": CURRENT_BASE.model_version,
}
# Прогноз, сохранённый в PR 2: не старая модель, но и не текущая база (сила ВВ считалась иначе).
PR2_STORED_ROW = {**NEW_STORED_ROW, "predicted_model_version": PR2_VERSION}


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
        self.assertEqual(_score(CURRENT, OLD_ROW, NEW_ROW), [140.0])

    def test_new_artifact_skips_stored_pr2_prediction(self):
        self.assertEqual(_score(CURRENT, OLD_ROW, PR2_STORED_ROW), [])

    def test_old_artifact_skips_stored_pr2_prediction(self):
        self.assertEqual(_score(("", ""), PR2_STORED_ROW), [])

    def test_unknown_artifact_model_scores_nothing(self):
        """Неизвестная модель в файле артефакта не роняет дрейф: сравнивать нечего."""
        self.assertEqual(_score(("no_such_model", CURRENT_BASE.model_version), OLD_ROW, NEW_ROW), [])


if __name__ == "__main__":
    unittest.main()
