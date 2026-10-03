"""Калибровки кусковатости учатся на baseline текущей базы и запоминают её."""
import unittest

from intelligence.calibration.base import CURRENT_BASE
from intelligence.calibration.features import BASELINE_FEATURE, residual_table
from intelligence.calibration.training import OLD_SNAPSHOT_MESSAGE, train_from_snapshot
from intelligence.spatial.training import train_from_snapshot as train_spatial
from tests.calibration_fixtures import synthetic_snapshot
from tests.spatial_fixtures import synthetic_spatial_snapshot


class CalibrationTrainingBaseTests(unittest.TestCase):
    def test_artifact_records_snapshot_base(self):
        for model_type, field in (("kuzram_residual", "baseline_x50_mm"), ("oversize_residual", "baseline_oversize_pct")):
            with self.subTest(model_type=model_type):
                model = train_from_snapshot(synthetic_snapshot(), model_type=model_type)

                self.assertEqual(
                    (model.baseline_model, model.baseline_model_version),
                    (CURRENT_BASE.model, CURRENT_BASE.model_version),
                )
                self.assertEqual(model.baseline_field, field)

    def test_trains_on_current_baseline_not_stored_prediction(self):
        snapshot = synthetic_snapshot()
        for sample in snapshot.samples:
            sample.targets["FRAGMENTATION"]["predicted_x50_mm"] = 999.0

        table = residual_table(snapshot, "kuzram_residual", baseline_field="baseline_x50_mm")

        self.assertEqual(set(table.baselines), {150.0})

    def test_oversize_trains_on_current_baseline_not_stored_prediction(self):
        snapshot = synthetic_snapshot()
        for sample in snapshot.samples:
            sample.targets["FRAGMENTATION"]["predicted_oversize_pct"] = 99.0

        table = residual_table(snapshot, "oversize_residual", baseline_field="baseline_oversize_pct")
        model = train_from_snapshot(snapshot, model_type="oversize_residual")

        self.assertEqual(set(table.baselines), {4.0})
        column = model.feature_names.index(BASELINE_FEATURE)
        self.assertEqual({row[column] for row in model.training_matrix}, {4.0})

    def test_old_snapshot_message(self):
        """Снимки после PR 2 несут прогнозы новой формулы: «только старой формулы» — неправда."""
        self.assertEqual(
            OLD_SNAPSHOT_MESSAGE,
            "Снимок собран до перехода калибровок на базу модели кусковатости: в нём нет baseline "
            "текущей модели — соберите новый снимок.",
        )

    def test_row_without_baseline_is_skipped(self):
        snapshot = synthetic_snapshot()
        snapshot.samples[0].targets["FRAGMENTATION"]["baseline_x50_mm"] = None

        model = train_from_snapshot(snapshot, model_type="kuzram_residual")

        self.assertEqual(model.sample_count, snapshot.sample_count - 1)

    def test_old_snapshot_is_refused_for_fragmentation(self):
        for model_type in ("kuzram_residual", "oversize_residual"):
            with self.subTest(model_type=model_type), self.assertRaisesRegex(ValueError, "соберите новый снимок"):
                train_from_snapshot(synthetic_snapshot(legacy=True), model_type=model_type)

    def test_old_snapshot_still_trains_ppv(self):
        model = train_from_snapshot(synthetic_snapshot(legacy=True), model_type="ppv_residual")

        self.assertEqual(model.baseline_model, "")
        self.assertEqual(model.baseline_field, "predicted_max_ppv_mm_s")


class SpatialTrainingBaseTests(unittest.TestCase):
    def test_base_from_snapshot(self):
        snapshot = synthetic_spatial_snapshot()
        snapshot.fragmentation_base = CURRENT_BASE.to_dict()

        model = train_spatial(snapshot, team_id="sp-base")

        self.assertEqual(
            (model.baseline_model, model.baseline_model_version), (CURRENT_BASE.model, CURRENT_BASE.model_version)
        )

    def test_old_snapshot_gives_old_base(self):
        model = train_spatial(synthetic_spatial_snapshot(), team_id="sp-base")

        self.assertEqual(model.baseline_model, "")


if __name__ == "__main__":
    unittest.main()
