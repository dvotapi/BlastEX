"""Присланный клиентом baseline кусковатости принимается только вместе с моделью.

Калибровки обучены на Kuz-Ram 1.0.0; x50 модели 2.0.0, наложенный без
проверки, нарушает решение владельца № 3.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.schemas.calibration import CalibrationPredictRequest, CalibrationTrainRequest
from api.services import calibration_service
from intelligence.datasets.persistence import save_snapshot
from tests.calibration_fixtures import synthetic_snapshot

TEAM_ID = "api-cal-provided"


class ProvidedBaselineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.snapshot = save_snapshot(TEAM_ID, synthetic_snapshot())

    def _predict(self, model_type: str, **fields):
        trained = calibration_service.train_calibration(
            TEAM_ID, CalibrationTrainRequest(dataset_id=self.snapshot.dataset_id, model_type=model_type)
        )
        return calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(
                model_type=model_type,
                model_id=trained.model_id,
                site_id="quarry-1",
                baseline=150.0,
                features=self.snapshot.samples[-1].features,
                **fields,
            ),
        )

    def test_new_model_baseline_is_refused(self):
        result = self._predict("kuzram_residual", baseline_model="kuzram", baseline_model_version="2.0.0")

        self.assertFalse(result.calibration_applied)
        self.assertEqual(result.calibrated, 150.0)
        self.assertIn("переобучить", result.warnings[0])

    def test_old_model_baseline_is_calibrated(self):
        for model, version in (("kuzram_legacy", "1.0.0"), ("kuzram", "1.0.0")):
            with self.subTest(model=model):
                result = self._predict("kuzram_residual", baseline_model=model, baseline_model_version=version)

                self.assertTrue(result.calibration_applied)

    def test_unknown_model_baseline_is_refused(self):
        result = self._predict("kuzram_residual", baseline_model="abc", baseline_model_version="1.0.0")

        self.assertFalse(result.calibration_applied)
        self.assertEqual(result.calibrated, 150.0)
        self.assertTrue(result.warnings)
        self.assertIn("abc", result.warnings[0])

    def test_baseline_without_model_is_refused(self):
        result = self._predict("oversize_residual")

        self.assertFalse(result.calibration_applied)
        self.assertIn("Не указано", result.warnings[0])

    def test_ppv_needs_no_model(self):
        result = self._predict("ppv_residual")

        self.assertTrue(result.calibration_applied)


if __name__ == "__main__":
    unittest.main()
