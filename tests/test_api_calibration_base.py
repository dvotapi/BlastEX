"""/calibration/predict без присланного baseline считает его базой артефакта.

Сохранённый в паспорте прогноз берётся, только если посчитан совместимой
моделью; иначе baseline пересчитывается той же функцией, что строит baseline
снимка датасета, — моделью артефакта и настройками сохранённого прогноза,
объекта работ или умолчаниями. Присланный baseline проверяется в
test_api_calibration_provided_baseline.
"""
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from api.schemas.calibration import CalibrationPredictRequest
from api.services import calibration_service
from cost.v2.repository import InMemoryEconomicsRepository
from intelligence.calibration.persistence import new_model_id, save_model
from intelligence.calibration.training import train_from_snapshot
from intelligence.calibration.types import MODEL_SPECS
from intelligence.datasets.baseline import fragmentation_baseline
from simulation.fragmentation.cunningham import KuzRamSettings
from tests.calibration_fixtures import CURRENT_VERSION, PR2_VERSION, synthetic_snapshot
from tests.dataset_fixtures import closed_design

TEAM_ID = "api-cal-base"
OBJECT = "Карьер-1"
X50 = "kuzram_residual"
OVERSIZE = "oversize_residual"


def _repository(rock_factor_correction: float) -> InMemoryEconomicsRepository:
    repository = InMemoryEconomicsRepository()
    block = {**asdict(KuzRamSettings()), "rock_factor_correction": rock_factor_correction}
    repository.save_calc_inputs(TEAM_ID, "tester", OBJECT, {"version": 1, "kuzram": block})
    repository.import_legacy_workspace(
        TEAM_ID, "tester", team_name="Команда", active_scenario_id="drill_blast", active_work_object_name=OBJECT
    )
    return repository


def _with_stored_model(design, model: str, version: str):
    provenance = design.blast_result.basis.predicted_fragmentation.provenance
    provenance.model, provenance.model_version = model, version
    return design


class CalibrationBaseApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.snapshot = synthetic_snapshot()

    def _artifact(
        self,
        model_type: str = X50,
        *,
        legacy: bool = False,
        baseline_model: str = "",
        baseline_model_version: str = "",
    ) -> str:
        model = train_from_snapshot(self.snapshot, model_type=model_type, model_id=new_model_id())
        if legacy:
            # Артефакт до PR 3: без базы, baseline — сохранённый прогноз.
            model.baseline_model = ""
            model.baseline_model_version = ""
            model.baseline_field = MODEL_SPECS[model_type]["baseline_field"]
        if baseline_model:
            model.baseline_model = baseline_model
        if baseline_model_version:
            model.baseline_model_version = baseline_model_version
        return save_model(TEAM_ID, model).model_id

    def _predict(self, model_id: str, model_type: str = X50, *, repository=None, **fields):
        payload = {"features": self.snapshot.samples[-1].features, **fields}
        return calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(model_type=model_type, model_id=model_id, site_id="quarry-1", **payload),
            repository=repository,
        )

    def test_old_artifact_uses_stored_old_prediction(self):
        design = closed_design("cal-old-design")  # сохранённый прогноз kuzram «1», x50 = 150

        result = self._predict(self._artifact(legacy=True), design=design.to_dict())

        self.assertEqual((result.baseline, result.baseline_source), (150.0, "stored_predicted"))
        self.assertTrue(result.calibration_applied)

    def test_old_artifact_recomputes_over_new_prediction(self):
        for version in (PR2_VERSION, CURRENT_VERSION):
            with self.subTest(version=version):
                design = _with_stored_model(closed_design("cal-old-recompute"), "kuzram", version)

                result = self._predict(self._artifact(legacy=True), design=design.to_dict())

                expected = fragmentation_baseline(design, model="kuzram_legacy")["baseline_x50_mm"]
                self.assertAlmostEqual(result.baseline, expected, places=6)
                self.assertEqual(result.baseline_source, "kuzram_legacy")

    def test_new_artifact_recomputes_over_old_or_unknown_prediction(self):
        """Прогноз PR 2 (2.0.0) — не старая модель, но x50 у него другой: поправка к нему не подходит."""
        cases = (("kuzram", "1"), ("abc", CURRENT_VERSION), ("kuzram", PR2_VERSION))
        for model, version in cases:
            with self.subTest(model=model, version=version):
                design = _with_stored_model(closed_design("cal-new-design"), model, version)

                result = self._predict(self._artifact(), design=design.to_dict())

                self.assertAlmostEqual(result.baseline, fragmentation_baseline(design)["baseline_x50_mm"], places=6)
                self.assertNotEqual(result.baseline, 150.0)
                self.assertEqual(result.baseline_source, "kuzram")
                self.assertTrue(result.calibration_applied)

    def test_new_artifact_uses_stored_new_prediction(self):
        design = _with_stored_model(closed_design("cal-new-stored"), "swebrec", CURRENT_VERSION)

        result = self._predict(self._artifact(), design=design.to_dict())

        self.assertEqual((result.baseline, result.baseline_source), (150.0, "stored_predicted"))

    def test_new_oversize_recomputes_over_other_model(self):
        design = _with_stored_model(closed_design("cal-new-oversize"), "swebrec", CURRENT_VERSION)

        result = self._predict(self._artifact(OVERSIZE), OVERSIZE, design=design.to_dict())

        expected = fragmentation_baseline(design)["baseline_oversize_pct"]
        self.assertAlmostEqual(result.baseline, expected, places=6)
        self.assertEqual(result.baseline_source, "kuzram")

    def test_recompute_takes_work_object_settings(self):
        design = closed_design("cal-work-object")
        settings = KuzRamSettings(rock_factor_correction=1.4)

        result = self._predict(self._artifact(), design=design.to_dict(), repository=_repository(1.4))

        expected = fragmentation_baseline(design, fallback_settings=settings)["baseline_x50_mm"]
        self.assertAlmostEqual(result.baseline, expected, places=6)
        self.assertNotAlmostEqual(result.baseline, fragmentation_baseline(design)["baseline_x50_mm"], places=3)

    def test_recompute_ignores_settings_snapshot_of_other_version(self):
        """C(A) прогноза PR 2 подобран под другую формулу: пересчёт берёт настройки объекта работ."""
        design = _with_stored_model(closed_design("cal-pr2-settings"), "kuzram", PR2_VERSION)
        design.blast_result.basis.predicted_fragmentation.provenance.settings = {
            "source": "work_object",
            "work_object_name": OBJECT,
            "values": asdict(KuzRamSettings(rock_factor_correction=1.3)),
            "warnings": [],
        }
        work_object = KuzRamSettings(rock_factor_correction=1.4)
        without_snapshot = _with_stored_model(closed_design("cal-pr2-settings"), "kuzram", PR2_VERSION)

        result = self._predict(self._artifact(), design=design.to_dict(), repository=_repository(1.4))

        expected = fragmentation_baseline(without_snapshot, fallback_settings=work_object)["baseline_x50_mm"]
        self.assertAlmostEqual(result.baseline, expected, places=6)
        self.assertEqual(result.baseline_source, "kuzram")

    def test_recomputed_baseline_of_other_version_is_refused(self):
        """Движок пересчитывает текущей версией модели; артефакт другой версии к ней не применяется."""
        other_version = "2.5.0"  # версия артефакта, заведомо не совпадающая с текущей
        self.assertNotEqual(other_version, CURRENT_VERSION)
        model_id = self._artifact(baseline_model_version=other_version)
        without_stored = closed_design("cal-other-version")
        without_stored.blast_result.basis.predicted_fragmentation = None
        stored_current = _with_stored_model(closed_design("cal-other-version-stored"), "kuzram", CURRENT_VERSION)
        stored_pr2 = _with_stored_model(closed_design("cal-other-version-pr2"), "kuzram", PR2_VERSION)
        cases = (
            ("без прогноза", without_stored),
            (f"прогноз {CURRENT_VERSION}", stored_current),
            (f"прогноз PR 2 {PR2_VERSION}", stored_pr2),
        )
        for name, design in cases:
            with self.subTest(design=name):
                result = self._predict(model_id, design=design.to_dict())

                expected = fragmentation_baseline(design)["baseline_x50_mm"]
                self.assertAlmostEqual(result.baseline, expected, places=6)
                self.assertEqual(result.calibrated, result.baseline)
                self.assertFalse(result.calibration_applied)
                self.assertIn("переобучить", result.warnings[0])
                self.assertIn(f"Kuz-Ram {other_version}", result.warnings[0])
                self.assertIn(f"Kuz-Ram {CURRENT_VERSION}", result.warnings[0])

    def test_unknown_artifact_base_is_refused_not_error(self):
        model_id = self._artifact(baseline_model="no_such_model")
        design = closed_design("cal-unknown-base")
        for fields in (
            {"baseline": 150.0, "baseline_model": "kuzram", "baseline_model_version": CURRENT_VERSION},
            {"design": design.to_dict()},
        ):
            with self.subTest(fields=sorted(fields)):
                result = self._predict(model_id, **fields)

                self.assertFalse(result.calibration_applied)
                self.assertIn("no_such_model", result.warnings[0])
                self.assertIn("переобучить", result.warnings[0])


if __name__ == "__main__":
    unittest.main()
