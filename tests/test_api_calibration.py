import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidCalibrationError
from api.schemas.calibration import CalibrationPredictRequest, CalibrationStatusRequest, CalibrationTrainRequest
from api.services import calibration_service
from design.persistence import save_design
from intelligence.datasets.builder import build_snapshot
from intelligence.datasets.persistence import save_snapshot
from tests.calibration_fixtures import synthetic_snapshot, varied_closed_designs
from tests.dataset_fixtures import closed_design

TEAM_ID = "api-cal-team"


class CalibrationApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _stored_snapshot(self, snapshot=None):
        return save_snapshot(TEAM_ID, snapshot or synthetic_snapshot())

    def test_train_list_predict_and_status(self):
        snapshot = self._stored_snapshot()
        trained = calibration_service.train_calibration(
            TEAM_ID,
            CalibrationTrainRequest(dataset_id=snapshot.dataset_id, model_type="kuzram_residual"),
        )
        self.assertEqual(trained.status, "candidate")
        self.assertEqual(trained.training_dataset_version, snapshot.dataset_version)
        self.assertTrue(trained.training_date)
        listed = calibration_service.list_calibration_models(TEAM_ID)
        self.assertEqual(len(listed.items), 1)
        loaded = calibration_service.get_calibration_model(TEAM_ID, trained.model_id)
        self.assertEqual(loaded.model_id, trained.model_id)

        prediction = calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(
                model_type="kuzram_residual",
                model_id=trained.model_id,
                site_id="quarry-1",
                baseline=150.0,
                features=snapshot.samples[-1].features,
            ),
        )
        self.assertTrue(prediction.calibration_applied)
        self.assertFalse(prediction.modifies_design)
        self.assertEqual(prediction.applied_as, "recommendation_overlay")
        self.assertEqual(prediction.provenance.model_version, trained.model_version)
        self.assertGreater(prediction.calibrated, prediction.baseline)
        self.assertIsNotNone(prediction.prediction)
        self.assertIn(prediction.confidence, {"high", "medium", "low"})
        self.assertIsInstance(prediction.similarity_score, float)
        self.assertIsInstance(prediction.applicability_warning, str)
        self.assertIsNotNone(prediction.uncertainty.lower)
        self.assertIsNotNone(prediction.uncertainty.upper)

        promoted = calibration_service.update_status(
            TEAM_ID, trained.model_id, CalibrationStatusRequest(status="production")
        )
        self.assertEqual(promoted.status, "production")

        production = calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(
                model_type="kuzram_residual",
                site_id="quarry-1",
                use_production=True,
                baseline=150.0,
                features=snapshot.samples[0].features,
            ),
        )
        self.assertTrue(production.calibration_applied)
        self.assertEqual(production.status, "production")

    def test_candidate_is_not_used_as_silent_production(self):
        snapshot = self._stored_snapshot()
        calibration_service.train_calibration(
            TEAM_ID,
            CalibrationTrainRequest(dataset_id=snapshot.dataset_id, model_type="kuzram_residual"),
        )
        silent = calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(
                model_type="kuzram_residual",
                site_id="quarry-1",
                use_production=True,
                baseline=150.0,
                features=snapshot.samples[0].features,
            ),
        )
        self.assertFalse(silent.calibration_applied)
        self.assertEqual(silent.calibrated, silent.baseline)
        self.assertFalse(silent.modifies_design)

    def test_predict_does_not_mutate_design(self):
        snapshot = self._stored_snapshot()
        trained = calibration_service.train_calibration(
            TEAM_ID,
            CalibrationTrainRequest(dataset_id=snapshot.dataset_id, model_type="kuzram_residual"),
        )
        design = closed_design("live-design")
        before = copy.deepcopy(design.to_dict())
        calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(
                model_type="kuzram_residual",
                model_id=trained.model_id,
                site_id="quarry-1",
                design=design.to_dict(),
                baseline=150.0,
            ),
        )
        self.assertEqual(design.to_dict(), before)

    def test_train_from_closed_blast_snapshot(self):
        designs = varied_closed_designs(6)
        for design in designs:
            save_design(TEAM_ID, design)
        snapshot = save_snapshot(
            TEAM_ID,
            build_snapshot(designs, site_id="quarry-1", dataset_id="from-closed", dataset_version=1),
        )
        self.assertGreaterEqual(snapshot.sample_count, 6)
        trained = calibration_service.train_calibration(
            TEAM_ID,
            CalibrationTrainRequest(dataset_id=snapshot.dataset_id, model_type="oversize_residual"),
        )
        self.assertEqual(trained.status, "candidate")
        self.assertEqual(trained.sample_count, snapshot.sample_count)

    def test_empty_dataset_id_is_invalid(self):
        with self.assertRaises(InvalidCalibrationError):
            calibration_service.train_calibration(
                TEAM_ID, CalibrationTrainRequest(dataset_id="  ", model_type="kuzram_residual")
            )

    def test_algorithms_endpoint_lists_sklearn_defaults(self):
        listed = calibration_service.list_algorithms()
        names = {item.name for item in listed.items}
        self.assertIn("random_forest", names)
        self.assertIn("extra_trees", names)
        self.assertEqual(listed.default, "random_forest")


if __name__ == "__main__":
    unittest.main()
