"""Сценарии накладывают калибровки только на прогноз той же базы."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.services import scenario_service
from design.scenarios.types import ScenarioOutcomes, ScenarioParams
from intelligence.calibration.base import CURRENT_BASE
from tests.calibration_fixtures import PR2_VERSION
from tests.scenario_fixtures import charged_design


class ScenarioResidualGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, fragmentation_model: str, models: dict, *, load_error: str = ""):
        outcomes = ScenarioOutcomes(
            x50_mm=200.0,
            x50_engineering_mm=200.0,
            oversize_pct=5.0,
            oversize_engineering_pct=5.0,
            ppv_mm_s=4.0,
            ppv_engineering_mm_s=4.0,
        )
        params = ScenarioParams(
            fragmentation_model=fragmentation_model,
            calibration_model_ids={model_type: model_type for model_type in models},
        )

        def load(team_id, model_id):
            if model_id == load_error:
                raise RuntimeError("файл повреждён")
            base = models[model_id]
            return SimpleNamespace(model_type=model_id, baseline_model=base[0], baseline_model_version=base[1])

        def apply(model, *, features, baseline, baseline_source):
            return SimpleNamespace(calibrated=baseline + 1.0)

        with patch("intelligence.calibration.persistence.load_model", side_effect=load), patch(
            "intelligence.calibration.prediction.apply_residual", side_effect=apply
        ):
            scenario_service._apply_ml_overlays("team-ml", charged_design("ml-guard"), params, outcomes)
        return outcomes

    OLD = ("", "")
    NEW = (CURRENT_BASE.model, CURRENT_BASE.model_version)
    PR2 = (CURRENT_BASE.model, PR2_VERSION)

    def test_old_calibration_skips_new_model(self):
        outcomes = self._run("kuzram", {"kuzram_residual": self.OLD})

        self.assertEqual(outcomes.x50_mm, 200.0)
        self.assertTrue(any("переобучить" in item for item in outcomes.warnings))

    def test_old_calibration_keeps_legacy_model(self):
        outcomes = self._run("kuzram_legacy", {"kuzram_residual": self.OLD})

        self.assertEqual(outcomes.x50_mm, 201.0)

    def test_new_x50_calibration_fits_swebrec(self):
        outcomes = self._run("swebrec", {"kuzram_residual": self.NEW})

        self.assertEqual(outcomes.x50_mm, 201.0)

    def test_pr2_x50_calibration_does_not_fit_current_base(self):
        """Калибровка на прогнозах PR 2 (2.0.0) — не старая модель, но x50 текущей базы другой."""
        outcomes = self._run("kuzram", {"kuzram_residual": self.PR2})

        self.assertEqual(outcomes.x50_mm, 200.0)
        self.assertTrue(any("переобучить" in item for item in outcomes.warnings))

    def test_new_oversize_calibration_needs_same_model(self):
        outcomes = self._run("swebrec", {"oversize_residual": self.NEW})

        self.assertEqual(outcomes.oversize_pct, 5.0)
        self.assertTrue(any("переобучить" in item for item in outcomes.warnings))

    def test_broken_fragmentation_calibration_keeps_ppv(self):
        outcomes = self._run(
            "kuzram", {"oversize_residual": self.NEW, "ppv_residual": self.OLD}, load_error="oversize_residual"
        )

        self.assertEqual(outcomes.ppv_mm_s, 5.0)
        self.assertTrue(any("oversize_residual" in item for item in outcomes.warnings))


    def test_artifact_with_unknown_model_is_skipped_keeping_ppv(self):
        outcomes = self._run(
            "kuzram", {"oversize_residual": ("ml-magic", CURRENT_BASE.model_version), "ppv_residual": self.OLD}
        )

        self.assertEqual(outcomes.oversize_pct, 5.0)
        self.assertEqual(outcomes.ppv_mm_s, 5.0)
        self.assertTrue(any("oversize_residual" in item for item in outcomes.warnings))
        self.assertFalse(any("Калибровочный оверлей пропущен" in item for item in outcomes.warnings))


if __name__ == "__main__":
    unittest.main()
