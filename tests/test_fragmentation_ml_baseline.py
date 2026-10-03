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

    @staticmethod
    def _outcomes() -> ScenarioOutcomes:
        return ScenarioOutcomes(
            x50_mm=200.0,
            x50_engineering_mm=200.0,
            oversize_pct=5.0,
            oversize_engineering_pct=5.0,
            ppv_mm_s=4.0,
            ppv_engineering_mm_s=4.0,
        )

    @staticmethod
    def _artifact(model_type: str, base: tuple[str, str]):
        return SimpleNamespace(model_type=model_type, baseline_model=base[0], baseline_model_version=base[1])

    @staticmethod
    def _apply(model, *, features, baseline, baseline_source):
        return SimpleNamespace(calibrated=baseline + 1.0)

    def _run(self, fragmentation_model: str, models: dict, *, load_error: str = "", types: dict | None = None):
        """models: слот → база артефакта; types: слот → тип загруженного артефакта, если он другой."""
        outcomes = self._outcomes()
        params = ScenarioParams(
            fragmentation_model=fragmentation_model,
            calibration_model_ids={model_type: model_type for model_type in models},
        )

        def load(team_id, model_id):
            if model_id == load_error:
                raise RuntimeError("файл повреждён")
            return self._artifact((types or {}).get(model_id, model_id), models[model_id])

        with patch("intelligence.calibration.persistence.load_model", side_effect=load), patch(
            "intelligence.calibration.prediction.apply_residual", side_effect=self._apply
        ):
            scenario_service._apply_ml_overlays("team-ml", charged_design("ml-guard"), params, outcomes)
        return outcomes

    def _run_production(self, fragmentation_model: str, models: dict):
        """Режим production: калибровки площадки ищет production_model, а не id из запроса."""
        outcomes = self._outcomes()
        params = ScenarioParams(
            fragmentation_model=fragmentation_model, use_production_overlays=True, site_id="quarry-1"
        )

        def production(team_id, site_id, model_type):
            base = models.get(model_type)
            return None if base is None else self._artifact(model_type, base)

        with patch("intelligence.calibration.persistence.production_model", side_effect=production), patch(
            "intelligence.calibration.prediction.apply_residual", side_effect=self._apply
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
        self.assertTrue(any("Калибровка негабарита обучена на кривой" in item for item in outcomes.warnings))

    def _assert_no_service_names(self, outcomes):
        for item in outcomes.warnings:
            for name in ("oversize_residual", "kuzram_residual", "ppv_residual", "Доступны"):
                self.assertNotIn(name, item)

    def test_broken_fragmentation_calibration_keeps_ppv(self):
        outcomes = self._run(
            "kuzram", {"oversize_residual": self.NEW, "ppv_residual": self.OLD}, load_error="oversize_residual"
        )

        self.assertEqual(outcomes.ppv_mm_s, 5.0)
        self.assertIn("Калибровка «негабарит» пропущена: файл повреждён", outcomes.warnings)
        self._assert_no_service_names(outcomes)

    def test_artifact_with_unknown_model_is_skipped_keeping_ppv(self):
        outcomes = self._run(
            "kuzram", {"oversize_residual": ("ml-magic", CURRENT_BASE.model_version), "ppv_residual": self.OLD}
        )

        self.assertEqual(outcomes.oversize_pct, 5.0)
        self.assertEqual(outcomes.ppv_mm_s, 5.0)
        self.assertIn("Калибровка «негабарит» пропущена: в артефакте неизвестная модель базы.", outcomes.warnings)
        self._assert_no_service_names(outcomes)
        self.assertFalse(any("Калибровочный оверлей пропущен" in item for item in outcomes.warnings))

    def test_artifact_of_other_type_in_slot_is_skipped(self):
        """Калибровка x50, выбранная в слот PPV, не правит PPV и не обходит проверку базы."""
        outcomes = self._run(
            "kuzram",
            {"ppv_residual": self.NEW, "kuzram_residual": self.NEW},
            types={"ppv_residual": "kuzram_residual"},
        )

        self.assertEqual(outcomes.ppv_mm_s, 4.0)
        self.assertEqual(outcomes.x50_mm, 201.0)
        self.assertIn("Калибровка «PPV» пропущена: выбрана калибровка «x50».", outcomes.warnings)
        self._assert_no_service_names(outcomes)

    def test_production_old_calibration_refused_on_new_model_keeping_ppv(self):
        outcomes = self._run_production("kuzram", {"kuzram_residual": self.OLD, "ppv_residual": self.OLD})

        self.assertEqual(outcomes.x50_mm, 200.0)
        self.assertEqual(outcomes.ppv_mm_s, 5.0)
        self.assertTrue(any("переобучить" in item for item in outcomes.warnings))

    def test_production_old_calibration_applied_on_legacy_model(self):
        outcomes = self._run_production("kuzram_legacy", {"kuzram_residual": self.OLD})

        self.assertEqual(outcomes.x50_mm, 201.0)
        self.assertFalse(any("переобучить" in item for item in outcomes.warnings))

    def test_production_same_refusal_of_x50_and_oversize_is_shown_once(self):
        outcomes = self._run_production("kuzram", {"kuzram_residual": self.OLD, "oversize_residual": self.OLD})

        refusals = [item for item in outcomes.warnings if "переобучить" in item]
        self.assertEqual(len(refusals), 1)
        self.assertEqual((outcomes.x50_mm, outcomes.oversize_pct), (200.0, 5.0))


if __name__ == "__main__":
    unittest.main()
