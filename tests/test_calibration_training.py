import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.calibration.persistence import save_model
from intelligence.calibration.prediction import apply_residual
from intelligence.calibration.training import train_from_snapshot
from intelligence.calibration.types import STATUS_CANDIDATE
from tests.calibration_fixtures import synthetic_snapshot

TEAM_ID = "cal-train-team"


class CalibrationTrainingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_trained_model_has_required_metadata_and_candidate_status(self):
        snapshot = synthetic_snapshot(dataset_version=3)
        model = train_from_snapshot(snapshot, model_type="kuzram_residual", model_version=2)
        self.assertEqual(model.site_id, "quarry-1")
        self.assertEqual(model.model_type, "kuzram_residual")
        self.assertEqual(model.model_version, 2)
        self.assertEqual(model.training_dataset_version, 3)
        self.assertEqual(model.training_dataset_id, "snap-ml")
        self.assertTrue(model.feature_schema_version)
        self.assertTrue(model.training_date)
        self.assertIn("mae", model.metrics)
        self.assertEqual(model.status, STATUS_CANDIDATE)
        self.assertEqual(model.algorithm, "random_forest")
        self.assertGreaterEqual(model.sample_count, 4)
        self.assertIsNotNone(model.estimator)

    def test_in_sample_calibrated_mae_beats_baseline(self):
        model = train_from_snapshot(synthetic_snapshot(n=8), model_type="kuzram_residual")
        self.assertLess(model.metrics["calibrated_mae"], model.metrics["baseline_mae"])

    def test_too_few_samples_are_rejected(self):
        with self.assertRaises(ValueError):
            train_from_snapshot(synthetic_snapshot(n=2), model_type="ppv_residual")

    def test_oversize_and_ppv_types_train(self):
        oversize = train_from_snapshot(synthetic_snapshot(), model_type="oversize")
        ppv = train_from_snapshot(synthetic_snapshot(), model_type="ppv")
        self.assertEqual(oversize.model_type, "oversize_residual")
        self.assertEqual(ppv.model_type, "ppv_residual")
        self.assertEqual(oversize.status, STATUS_CANDIDATE)

    def test_site_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", site_id="other")

    def test_save_forces_candidate_even_if_status_was_changed(self):
        model = train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual")
        model.status = "production"
        saved = save_model(TEAM_ID, model)
        self.assertEqual(saved.status, STATUS_CANDIDATE)


def _mark_predictions(snapshot, marks: dict[int, tuple[str, str]]):
    """Проставить модель сохранённого прогноза строкам снимка (индекс → (модель, версия))."""
    for index, (model, version) in marks.items():
        group = snapshot.samples[index].targets["FRAGMENTATION"]
        group["predicted_model"] = model
        group["predicted_model_version"] = version
    return snapshot


class CalibrationTrainingBaseTests(unittest.TestCase):
    """Калибровки кусковатости учатся только на прогнозах старой базы Kuz-Ram 1.0.0."""

    def _snapshot(self):
        return _mark_predictions(
            synthetic_snapshot(n=12),
            {
                0: ("kuzram", "2.0.0"),
                1: ("kuzram", "2.0.0"),
                2: ("kuzram", "3.0.0"),
                3: ("kuzram", "abc"),
                4: ("kuzram", ""),
                5: ("kuzram_legacy", "1.0.0"),
                6: ("kuzram", "1.0.0"),
                7: ("", ""),
                # строки 8-11 без полей модели: снимки, собранные до появления полей
            },
        )

    def test_rows_with_new_model_predictions_are_excluded(self):
        for model_type in ("kuzram_residual", "oversize_residual"):
            with self.subTest(model_type=model_type):
                model = train_from_snapshot(self._snapshot(), model_type=model_type)

                self.assertEqual(model.sample_count, 7)
                self.assertEqual(
                    sorted(model.source_blast_ids),
                    sorted(f"blast-{index}" for index in (5, 6, 7, 8, 9, 10, 11)),
                )

    def test_ppv_training_keeps_all_rows(self):
        model = train_from_snapshot(self._snapshot(), model_type="ppv_residual")

        self.assertEqual(model.sample_count, 12)

    def test_snapshot_without_model_fields_trains_on_all_rows(self):
        model = train_from_snapshot(synthetic_snapshot(n=8), model_type="kuzram_residual")

        self.assertEqual(model.sample_count, 8)

    def test_error_names_excluded_rows_of_new_model(self):
        snapshot = _mark_predictions(
            synthetic_snapshot(n=6),
            {0: ("kuzram", "2.0.0"), 1: ("kuzram", "2.0.0"), 2: ("kuzram", "2.0.0")},
        )

        with self.assertRaises(ValueError) as caught:
            train_from_snapshot(snapshot, model_type="kuzram_residual")

        self.assertIn("новой модели: 3", str(caught.exception))

    def _legacy_curves_snapshot(self):
        return _mark_predictions(
            synthetic_snapshot(n=12),
            {
                0: ("swebrec_legacy", "1.0.0"),
                1: ("swebrec_legacy", "1.0.0"),
                2: ("kuznetsov_legacy", "1.0.0"),
                3: ("kuznetsov_legacy", "1.0.0"),
                4: ("kuzram_legacy", "1.0.0"),
                5: ("kuzram", "1.0.0"),
                6: ("", ""),
                # строки 7-11 без полей модели
            },
        )

    def test_oversize_training_keeps_only_kuzram_curve(self):
        model = train_from_snapshot(self._legacy_curves_snapshot(), model_type="oversize_residual")

        self.assertEqual(model.sample_count, 8)
        self.assertEqual(
            sorted(model.source_blast_ids),
            sorted(f"blast-{index}" for index in range(4, 12)),
        )

    def test_x50_training_keeps_rows_of_every_old_model(self):
        # x50 всех старых моделей одинаков, поэтому строки swebrec_legacy и kuznetsov_legacy годятся.
        model = train_from_snapshot(self._legacy_curves_snapshot(), model_type="kuzram_residual")

        self.assertEqual(model.sample_count, 12)

    def test_ppv_training_ignores_prediction_curve(self):
        model = train_from_snapshot(self._legacy_curves_snapshot(), model_type="ppv_residual")

        self.assertEqual(model.sample_count, 12)

    def test_oversize_error_names_rows_of_other_curve(self):
        snapshot = _mark_predictions(
            synthetic_snapshot(n=6),
            {0: ("swebrec_legacy", "1.0.0"), 1: ("swebrec_legacy", "1.0.0"), 2: ("kuznetsov_legacy", "1.0.0")},
        )

        with self.assertRaises(ValueError) as caught:
            train_from_snapshot(snapshot, model_type="oversize_residual")

        self.assertIn("не по кривой Kuz-Ram: 3", str(caught.exception))
        self.assertNotIn("новой модели", str(caught.exception))
        self.assertEqual(train_from_snapshot(snapshot, model_type="kuzram_residual").sample_count, 6)

    def test_error_without_excluded_rows_is_unchanged(self):
        with self.assertRaises(ValueError) as caught:
            train_from_snapshot(synthetic_snapshot(n=2), model_type="kuzram_residual")

        self.assertNotIn("новой модели", str(caught.exception))
        self.assertNotIn("Kuz-Ram:", str(caught.exception))


class CalibrationPredictionTests(unittest.TestCase):
    def test_hybrid_prediction_exposes_version_and_does_not_mutate_features(self):
        snapshot = synthetic_snapshot(n=8)
        model = train_from_snapshot(snapshot, model_type="kuzram_residual", model_version=1)
        features = copy.deepcopy(snapshot.samples[-1].features)
        original = copy.deepcopy(features)
        prediction = apply_residual(model, features=features, baseline=150.0, baseline_source="kuzram")
        self.assertEqual(features, original)
        self.assertFalse(prediction.modifies_design)
        self.assertEqual(prediction.applied_as, "recommendation_overlay")
        self.assertEqual(prediction.model_version, 1)
        self.assertEqual(prediction.status, STATUS_CANDIDATE)
        self.assertTrue(prediction.calibration_applied)
        self.assertIn("provenance", prediction.to_dict())
        self.assertAlmostEqual(prediction.calibrated, prediction.baseline + prediction.residual)
        self.assertGreater(prediction.calibrated, prediction.baseline)
        payload = prediction.to_dict()
        for key in ("prediction", "uncertainty", "confidence", "similarity_score", "applicability_warning"):
            self.assertIn(key, payload)
        self.assertEqual(payload["prediction"], prediction.calibrated)
        self.assertLessEqual(payload["uncertainty"]["lower"], payload["prediction"])
        self.assertGreaterEqual(payload["uncertainty"]["upper"], payload["prediction"])

    def test_candidate_warning_is_present(self):
        model = train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual")
        prediction = apply_residual(model, features=synthetic_snapshot().samples[0].features, baseline=150.0)
        self.assertTrue(any("candidate" in item for item in prediction.warnings))
        self.assertTrue(any("не изменяет" in item.lower() or "не утверждает" in item for item in prediction.warnings))


if __name__ == "__main__":
    unittest.main()
