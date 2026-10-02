"""Присланный клиентом baseline кусковатости принимается только вместе с моделью.

Калибровки обучены на Kuz-Ram 1.0.0; x50 модели 2.0.0, наложенный без
проверки, нарушает решение владельца № 3.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidCalibrationError
from api.schemas.calibration import CalibrationPredictRequest, CalibrationTrainRequest
from api.services import calibration_service
from intelligence.datasets.builder import build_snapshot
from intelligence.datasets.persistence import save_snapshot
from simulation.fragmentation.models import ModelProvenance
from tests.calibration_fixtures import synthetic_snapshot, varied_closed_designs

TEAM_ID = "api-cal-provided"


class ProvidedBaselineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.snapshot = save_snapshot(TEAM_ID, synthetic_snapshot())
        self._trained: dict[str, str] = {}

    def _model_id(self, model_type: str) -> str:
        # Калибровка каждого типа обучается один раз за тест, а не на каждый запрос.
        if model_type not in self._trained:
            trained = calibration_service.train_calibration(
                TEAM_ID, CalibrationTrainRequest(dataset_id=self.snapshot.dataset_id, model_type=model_type)
            )
            self._trained[model_type] = trained.model_id
        return self._trained[model_type]

    def _predict(self, model_type: str, **fields):
        return calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(
                model_type=model_type,
                model_id=self._model_id(model_type),
                site_id="quarry-1",
                baseline=150.0,
                features=self.snapshot.samples[-1].features,
                **fields,
            ),
        )

    def _assert_refused(self, result, reason: str):
        self.assertFalse(result.calibration_applied)
        self.assertEqual(result.calibrated, 150.0)
        self.assertTrue(result.warnings)
        self.assertIn(reason, result.warnings[0])

    def test_new_model_baseline_is_refused(self):
        result = self._predict("kuzram_residual", baseline_model="kuzram", baseline_model_version="2.0.0")

        self._assert_refused(result, "переобучить")

    def test_new_major_versions_are_refused(self):
        for version in ("2", "3.0.0"):
            with self.subTest(version=version):
                result = self._predict("kuzram_residual", baseline_model="kuzram", baseline_model_version=version)

                self._assert_refused(result, "переобучить")

    def test_unrecognized_version_is_refused(self):
        huge = "9" * 5000 + ".0"  # длиннее лимита int() — не должно быть 500
        for model, version in (("kuzram", "v2.0.0"), ("kuzram", "abc"), ("kuzram_legacy", "abc"), ("kuzram", huge)):
            with self.subTest(model=model, version=version[:12]):
                result = self._predict("kuzram_residual", baseline_model=model, baseline_model_version=version)

                self._assert_refused(result, "не распознана")

    def test_old_model_baseline_is_calibrated(self):
        for model, version in (("kuzram_legacy", "1.0.0"), ("kuzram", "1.0.0")):
            with self.subTest(model=model):
                result = self._predict("kuzram_residual", baseline_model=model, baseline_model_version=version)

                self.assertTrue(result.calibration_applied)

    def test_x50_accepts_any_old_model(self):
        # x50 всех старых моделей одинаков, поэтому поправка кусковатости ложится на любую из них.
        result = self._predict("kuzram_residual", baseline_model="swebrec_legacy", baseline_model_version="1.0.0")

        self.assertTrue(result.calibration_applied)

    def test_oversize_accepts_only_kuzram_curve(self):
        for model in ("kuzram_legacy", "kuzram"):
            with self.subTest(model=model, applied=True):
                result = self._predict("oversize_residual", baseline_model=model, baseline_model_version="1.0.0")

                self.assertTrue(result.calibration_applied)
        for model in ("swebrec_legacy", "kuznetsov_legacy"):
            with self.subTest(model=model, applied=False):
                result = self._predict("oversize_residual", baseline_model=model, baseline_model_version="1.0.0")

                self._assert_refused(result, "кривой Kuz-Ram")

    def test_unknown_model_baseline_is_refused(self):
        result = self._predict("kuzram_residual", baseline_model="abc", baseline_model_version="1.0.0")

        self._assert_refused(result, "Неизвестная модель")

    def test_baseline_without_version_is_refused(self):
        for model in ("kuzram", "kuzram_legacy"):
            for model_type in ("kuzram_residual", "oversize_residual"):
                with self.subTest(model=model, model_type=model_type):
                    result = self._predict(model_type, baseline_model=model, baseline_model_version="")

                    self._assert_refused(result, "Не указано")

    def test_blank_version_is_refused(self):
        result = self._predict("kuzram_residual", baseline_model="kuzram", baseline_model_version="   ")

        self._assert_refused(result, "Не указано")

    def test_baseline_without_model_is_refused(self):
        result = self._predict("oversize_residual")

        self._assert_refused(result, "Не указано")

    def test_ppv_needs_no_model(self):
        result = self._predict("ppv_residual")

        self.assertTrue(result.calibration_applied)


class TrainOnCurrentBaseTests(unittest.TestCase):
    """Снимок из закрытых взрывов: калибровки кусковатости учатся на baseline текущей базы."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _snapshot_with_new_predictions(self, total: int, new_count: int, *, old_snapshot: bool = False):
        designs = varied_closed_designs(total)
        for design in designs[:new_count]:
            design.blast_result.basis.predicted_fragmentation.provenance = ModelProvenance(
                model="kuzram", model_version="2.0.0"
            )
        snapshot = build_snapshot(designs, site_id="quarry-1", dataset_id="from-closed-new", dataset_version=1)
        if old_snapshot:
            snapshot.fragmentation_base = {}  # как снимок, собранный до PR 3
        return save_snapshot(TEAM_ID, snapshot)

    def _train(self, snapshot, model_type: str):
        return calibration_service.train_calibration(
            TEAM_ID, CalibrationTrainRequest(dataset_id=snapshot.dataset_id, model_type=model_type)
        )

    def test_rows_with_new_model_predictions_stay_in_training(self):
        snapshot = self._snapshot_with_new_predictions(total=8, new_count=3)

        for model_type in ("kuzram_residual", "oversize_residual", "ppv_residual"):
            with self.subTest(model_type=model_type):
                self.assertEqual(self._train(snapshot, model_type).sample_count, 8)

    def test_old_snapshot_is_refused_for_fragmentation(self):
        snapshot = self._snapshot_with_new_predictions(total=8, new_count=0, old_snapshot=True)

        for model_type in ("kuzram_residual", "oversize_residual"):
            with self.subTest(model_type=model_type), self.assertRaises(InvalidCalibrationError) as caught:
                self._train(snapshot, model_type)

            self.assertIn("соберите новый снимок", str(caught.exception))

    def test_old_snapshot_still_trains_ppv(self):
        snapshot = self._snapshot_with_new_predictions(total=8, new_count=0, old_snapshot=True)

        self.assertEqual(self._train(snapshot, "ppv_residual").sample_count, 8)


if __name__ == "__main__":
    unittest.main()
