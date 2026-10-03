"""Дрейф калибровки считается только на строках той же базы, что и артефакт."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from intelligence.calibration.base import CURRENT_BASE, LEGACY_BASE, sample_baseline
from intelligence.calibration.persistence import save_model
from intelligence.calibration.training import train_from_snapshot
from intelligence.datasets.persistence import save_snapshot
from intelligence.drift.monitor import check_production_model, compare_windows
from intelligence.drift.scoring import _score_calibration
from intelligence.drift.types import KIND_PREDICTION
from intelligence.registry.persistence import promote
from intelligence.registry.types import STATUS_PRODUCTION
from tests.calibration_fixtures import PR2_VERSION, synthetic_snapshot

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

    def test_non_numeric_row_is_skipped(self):
        """Нечисловой baseline одной строки снимает только её, а не весь прогнозный канал."""
        broken = {**NEW_ROW, "baseline_x50_mm": "н/д", "predicted_model_version": PR2_VERSION}

        self.assertEqual(_score(CURRENT, broken, NEW_ROW), [140.0])

    def test_non_numeric_candidate_is_skipped(self):
        """Нечисловой кандидат пропускается: берётся следующий совместимый, иначе строки нет."""
        row = {**NEW_ROW, "baseline_x50_mm": "н/д"}
        old_row = {**OLD_ROW, "predicted_x50_mm": "н/д"}

        self.assertEqual(sample_baseline(row, "kuzram_residual", CURRENT_BASE), 150.0)
        self.assertIsNone(sample_baseline(old_row, "kuzram_residual", LEGACY_BASE))


TEAM_ID = "drift-cal-base"


def _old_window(dataset_id: str):
    """Снимок до PR 3: только сохранённые прогнозы старой формулы, x50 ~ 60 мм."""
    snapshot = synthetic_snapshot(legacy=True, dataset_id=dataset_id)
    for index, sample in enumerate(snapshot.samples):
        sample.targets["FRAGMENTATION"]["predicted_x50_mm"] = 60.0 + index
    return snapshot


def _current_window(dataset_id: str):
    """Снимок после выката: прогнозы и baseline текущей базы, x50 ~ 155 мм."""
    snapshot = synthetic_snapshot(dataset_id=dataset_id)
    for index, sample in enumerate(snapshot.samples):
        frag = sample.targets["FRAGMENTATION"]
        frag["predicted_x50_mm"] = frag["baseline_x50_mm"] = 155.0 + index
        frag["predicted_model"] = CURRENT_BASE.model
        frag["predicted_model_version"] = CURRENT_BASE.model_version
    return snapshot


class DriftWindowBaseTests(unittest.TestCase):
    """Окно без строк базы калибровки не сравнивается по сырым прогнозам всех баз."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _old_production(self, model_type: str = "kuzram_residual"):
        """Производственный артефакт до PR 3, обученный на старом снимке."""
        training = save_snapshot(TEAM_ID, _old_window("train-old"))
        model = train_from_snapshot(synthetic_snapshot(dataset_id="train-tmp"), model_type=model_type, model_id="cal-old")
        model.baseline_model, model.baseline_model_version = "", ""
        model.training_dataset_id = training.dataset_id
        saved = save_model(TEAM_ID, model)
        promote(TEAM_ID, "calibration", saved.model_id, to_status=STATUS_PRODUCTION, actor="lead@mine", confirm=True)
        return saved

    def test_old_artifact_over_new_window_skips_prediction_channel(self):
        model = self._old_production()
        current = save_snapshot(TEAM_ID, _current_window("now"))

        report = check_production_model(
            TEAM_ID, "calibration", model.model_id, current_dataset_id=current.dataset_id, persist=False
        )

        self.assertFalse([item for item in report.metrics if item.kind == KIND_PREDICTION])
        self.assertFalse(any("predicted_x50_mm" in alert.metric_name for alert in report.alerts))
        self.assertIn(
            f"Нет строк снимка, посчитанных базой калибровки «{LEGACY_BASE.label()}», "
            "— прогнозный канал дрейфа пропущен.",
            report.warnings,
        )

    def test_scoring_failure_does_not_fall_back_to_stored_predictions(self):
        model = self._old_production()
        current = save_snapshot(TEAM_ID, _current_window("now-broken"))

        with patch("intelligence.drift.monitor.score_snapshots", side_effect=RuntimeError("артефакт повреждён")):
            report = check_production_model(
                TEAM_ID, "calibration", model.model_id, current_dataset_id=current.dataset_id, persist=False
            )

        self.assertFalse([item for item in report.metrics if item.kind == KIND_PREDICTION])
        self.assertIn("Прогнозный канал пропущен: артефакт повреждён", report.warnings)

    def test_label_load_failure_does_not_break_check(self):
        """Подпись базы в предупреждении — справка: сбой повторной загрузки артефакта не рушит отчёт."""
        from intelligence.calibration import persistence as calibration_persistence
        from intelligence.drift import monitor

        model = self._old_production()
        current = save_snapshot(TEAM_ID, _current_window("now-label"))
        scoring_calls = []
        real_load, real_score = calibration_persistence.load_model, monitor.score_snapshots

        def counted_score(*args, **kwargs):
            result = real_score(*args, **kwargs)
            scoring_calls.append(1)
            return result

        def load_model(team_id, model_id):
            # Окна обучения и текущее считаются двумя вызовами; ломаем загрузку после них.
            if len(scoring_calls) >= 2:
                raise OSError("файл артефакта недоступен")
            return real_load(team_id, model_id)

        with patch("intelligence.drift.monitor.score_snapshots", side_effect=counted_score), patch(
            "intelligence.calibration.persistence.load_model", side_effect=load_model
        ):
            report = check_production_model(
                TEAM_ID, "calibration", model.model_id, current_dataset_id=current.dataset_id, persist=False
            )

        self.assertFalse([item for item in report.metrics if item.kind == KIND_PREDICTION])
        self.assertIn(
            f"Нет строк снимка, посчитанных базой калибровки «{model.model_id}», "
            "— прогнозный канал дрейфа пропущен.",
            report.warnings,
        )

    def test_windows_of_artifact_base_keep_prediction_channel(self):
        model = self._old_production()
        current = save_snapshot(TEAM_ID, _old_window("now-old"))

        report = check_production_model(
            TEAM_ID, "calibration", model.model_id, current_dataset_id=current.dataset_id, persist=False
        )

        names = {item.name for item in report.metrics if item.kind == KIND_PREDICTION}
        self.assertEqual(names, {"prediction.calibrated_x50_mm"})
        self.assertFalse(any("прогнозный канал" in item for item in report.warnings))


class CompareWindowsFallbackTests(unittest.TestCase):
    def test_stored_predictions_used_without_scores_by_default(self):
        """Без калибровки кусковатости (PPV, исходы) откат на сохранённые прогнозы прежний."""
        metrics = compare_windows([_old_window("a")], [_current_window("b")])

        self.assertIn(
            "FRAGMENTATION.predicted_x50_mm", {item.name for item in metrics if item.kind == KIND_PREDICTION}
        )

    def test_stored_fallback_can_be_disabled(self):
        metrics = compare_windows([_old_window("a")], [_current_window("b")], stored_fallback=False)

        self.assertFalse([item for item in metrics if item.kind == KIND_PREDICTION])


if __name__ == "__main__":
    unittest.main()
