"""До PR 3 ML-калибровки и пространственные признаки живут на старой базе Kuz-Ram 1.0.0.

Калибровки обучены на прогнозах старой модели; поправка, наложенная на
новую формулу, противоречит решению владельца № 3 из спеки.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.services import scenario_service
from design.scenarios.types import ScenarioOutcomes, ScenarioParams
from intelligence.calibration import prediction as calibration_prediction
from intelligence.calibration.types import MODEL_KUZRAM_RESIDUAL
from simulation.fragmentation import engine as fragmentation_engine
from simulation.fragmentation.models import ModelProvenance
from tests.scenario_fixtures import charged_design


class CalibrationBaselineTests(unittest.TestCase):
    def test_empirical_baseline_uses_legacy_model(self):
        with patch.object(fragmentation_engine, "predict_design", wraps=fragmentation_engine.predict_design) as spy:
            value = calibration_prediction._compute_empirical(charged_design("ml-base"), MODEL_KUZRAM_RESIDUAL)

        self.assertIsNotNone(value)
        self.assertEqual(spy.call_args.kwargs["model"], "kuzram_legacy")

    def test_only_old_base_predictions_are_baselines(self):
        old_base = calibration_prediction._old_base
        self.assertTrue(old_base(ModelProvenance(model="kuzram", model_version="1.0.0")))
        self.assertTrue(old_base(ModelProvenance(model="kuzram", model_version="")))
        self.assertTrue(old_base(ModelProvenance(model="kuzram_legacy", model_version="1.0.0")))
        self.assertFalse(old_base(ModelProvenance(model="kuzram", model_version="2.0.0")))
        self.assertFalse(old_base(ModelProvenance(model="swebrec", model_version="2.0.0")))


class SpatialPhysicsTests(unittest.TestCase):
    def test_physics_predictions_use_legacy_model(self):
        from intelligence.spatial.features import extract_hole_observations

        with patch.object(fragmentation_engine, "predict_region", wraps=fragmentation_engine.predict_region) as spy:
            extract_hole_observations(charged_design("ml-spatial"))

        self.assertTrue(spy.call_args_list)
        self.assertEqual({call.kwargs["model"] for call in spy.call_args_list}, {"kuzram_legacy"})


class ScenarioResidualGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, fragmentation_model: str):
        outcomes = ScenarioOutcomes(
            x50_mm=200.0, x50_engineering_mm=200.0, oversize_pct=5.0, oversize_engineering_pct=5.0
        )
        params = ScenarioParams(
            fragmentation_model=fragmentation_model, calibration_model_ids={"kuzram_residual": "cal-1"}
        )
        with patch("intelligence.calibration.persistence.load_model", return_value=object()), patch(
            "intelligence.calibration.prediction.apply_residual", return_value=SimpleNamespace(calibrated=150.0)
        ) as apply:
            scenario_service._apply_ml_overlays("team-ml", charged_design("ml-guard"), params, outcomes)
        return outcomes, apply

    def test_new_model_skips_old_residual(self):
        outcomes, apply = self._run("kuzram")

        apply.assert_not_called()
        self.assertEqual(outcomes.x50_mm, 200.0)
        self.assertTrue(any("переобучить" in item for item in outcomes.warnings))

    def test_legacy_model_keeps_residual(self):
        outcomes, apply = self._run("kuzram_legacy")

        apply.assert_called_once()
        self.assertEqual(outcomes.x50_mm, 150.0)


if __name__ == "__main__":
    unittest.main()
