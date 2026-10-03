"""Присланный клиентом baseline кусковатости принимается, только если посчитан базой калибровки.

Калибровка — поправка к конкретной формуле: артефакт помнит модель и версию
baseline, на котором обучен, а клиент называет модель и версию присланного
baseline. Решает общее правило совместимости: x50 — любая модель той же
базы, негабарит — та же модель и версия.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidCalibrationError
from api.schemas.calibration import CalibrationPredictRequest, CalibrationTrainRequest
from api.services import calibration_service
from intelligence.calibration.persistence import new_model_id, save_model
from intelligence.calibration.training import train_from_snapshot
from intelligence.calibration.types import MODEL_SPECS
from intelligence.datasets.builder import build_snapshot
from intelligence.datasets.persistence import save_snapshot
from simulation.fragmentation.models import ModelProvenance
from tests.calibration_fixtures import CURRENT_VERSION, PR2_VERSION, synthetic_snapshot, varied_closed_designs

TEAM_ID = "api-cal-provided"
X50 = "kuzram_residual"
OVERSIZE = "oversize_residual"


class _ProvidedBaselineCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.snapshot = save_snapshot(TEAM_ID, synthetic_snapshot())
        self._trained: dict[str, str] = {}

    def _train(self, model_type: str) -> str:
        trained = calibration_service.train_calibration(
            TEAM_ID, CalibrationTrainRequest(dataset_id=self.snapshot.dataset_id, model_type=model_type)
        )
        return trained.model_id

    def _model_id(self, model_type: str) -> str:
        # Калибровка каждого типа обучается один раз за тест, а не на каждый запрос.
        if model_type not in self._trained:
            self._trained[model_type] = self._train(model_type)
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

    def _assert_applied(self, model_type: str, model: str, version: str):
        with self.subTest(model_type=model_type, model=model, version=version, applied=True):
            result = self._predict(model_type, baseline_model=model, baseline_model_version=version)

            self.assertTrue(result.calibration_applied)

    def _assert_refused(self, result, reason: str):
        self.assertFalse(result.calibration_applied)
        self.assertEqual(result.calibrated, 150.0)
        self.assertTrue(result.warnings)
        self.assertIn(reason, result.warnings[0])


class NewArtifactProvidedBaselineTests(_ProvidedBaselineCase):
    """Калибровка обучена на текущей базе Kuz-Ram (версия — из реестра моделей движка)."""

    def test_current_base_baseline_is_calibrated(self):
        for model_type in (X50, OVERSIZE):
            self._assert_applied(model_type, "kuzram", CURRENT_VERSION)

    def test_x50_accepts_any_model_of_current_base(self):
        # x50 трёх моделей одной базы одинаков, поэтому поправка x50 ложится на любую из них.
        for model in ("swebrec", "kuznetsov"):
            self._assert_applied(X50, model, CURRENT_VERSION)

    def test_oversize_needs_same_model(self):
        """Та же база, другая кривая: переобучение не поможет — негабарит учится на kuzram."""
        result = self._predict(OVERSIZE, baseline_model="swebrec", baseline_model_version=CURRENT_VERSION)

        self._assert_refused(result, "Калибровка негабарита обучена на кривой")
        self.assertNotIn("переобучить", result.warnings[0])

    def test_old_model_baseline_is_refused(self):
        for model, version in (("kuzram_legacy", "1.0.0"), ("kuzram", "1.0.0")):
            with self.subTest(model=model, version=version):
                result = self._predict(X50, baseline_model=model, baseline_model_version=version)

                self._assert_refused(result, "переобучить")

    def test_other_versions_are_refused(self):
        # Версия PR 2 (2.0.0) — не старая модель, но x50 у неё другой, чем у текущей базы.
        versions = ("2", "3.0.0", PR2_VERSION)
        self.assertNotIn(CURRENT_VERSION, versions)
        for version in versions:
            with self.subTest(version=version):
                result = self._predict(X50, baseline_model="kuzram", baseline_model_version=version)

                self._assert_refused(result, "переобучить")

    def test_unrecognized_version_is_refused(self):
        huge = "9" * 5000 + ".0"  # длиннее лимита int() — не должно быть 500
        cases = (("kuzram", "v2.0.0"), ("kuzram", "abc"), ("kuzram", "²"), ("kuzram_legacy", "abc"), ("kuzram", huge))
        for model, version in cases:
            with self.subTest(model=model, version=version[:12]):
                result = self._predict(X50, baseline_model=model, baseline_model_version=version)

                self._assert_refused(result, "не распознана")

    def test_unknown_model_baseline_is_refused(self):
        result = self._predict(X50, baseline_model="abc", baseline_model_version=CURRENT_VERSION)

        self._assert_refused(result, "Неизвестная модель")

    def test_baseline_without_version_is_refused(self):
        for model in ("kuzram", "kuzram_legacy"):
            for model_type in (X50, OVERSIZE):
                for version in ("", "   "):
                    with self.subTest(model=model, model_type=model_type, version=version):
                        result = self._predict(model_type, baseline_model=model, baseline_model_version=version)

                        self._assert_refused(result, "Не указано")

    def test_baseline_without_model_is_refused(self):
        for model_type in (X50, OVERSIZE):
            for fields in ({}, {"baseline_model": "  ", "baseline_model_version": CURRENT_VERSION}):
                with self.subTest(model_type=model_type, fields=fields):
                    result = self._predict(model_type, **fields)

                    self._assert_refused(result, "Не указано")

    def test_ppv_needs_no_model(self):
        result = self._predict("ppv_residual")

        self.assertTrue(result.calibration_applied)


class OldArtifactProvidedBaselineTests(_ProvidedBaselineCase):
    """Артефакт, обученный до PR 3: базы в нём нет, он считается старой базой Kuz-Ram 1.0.0."""

    def _train(self, model_type: str) -> str:
        model = train_from_snapshot(self.snapshot, model_type=model_type, model_id=new_model_id())
        model.baseline_model = ""
        model.baseline_model_version = ""
        model.baseline_field = MODEL_SPECS[model_type]["baseline_field"]
        return save_model(TEAM_ID, model).model_id

    def test_old_model_baseline_is_calibrated(self):
        for model, version in (("kuzram_legacy", "1.0.0"), ("kuzram", "1.0.0"), ("kuzram", "1")):
            self._assert_applied(X50, model, version)

    def test_x50_accepts_any_old_model(self):
        for model in ("swebrec_legacy", "kuznetsov_legacy"):
            self._assert_applied(X50, model, "1.0.0")

    def test_oversize_accepts_only_kuzram_curve(self):
        for model in ("kuzram_legacy", "kuzram"):
            self._assert_applied(OVERSIZE, model, "1.0.0")
        for model in ("swebrec_legacy", "kuznetsov_legacy"):
            with self.subTest(model=model, applied=False):
                result = self._predict(OVERSIZE, baseline_model=model, baseline_model_version="1.0.0")

                self._assert_refused(result, "Калибровка негабарита обучена на кривой")

    def test_new_model_baseline_is_refused(self):
        result = self._predict(X50, baseline_model="kuzram", baseline_model_version=CURRENT_VERSION)

        self._assert_refused(result, "переобучить")
        self.assertIn("Kuz-Ram (старая) 1.0.0", result.warnings[0])
        self.assertIn(f"Kuz-Ram {CURRENT_VERSION}", result.warnings[0])


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
                model="kuzram", model_version=CURRENT_VERSION
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
