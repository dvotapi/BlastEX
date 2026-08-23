import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.calibration.persistence import (
    CalibrationNotFoundError,
    ImmutableCalibrationError,
    artifact_path,
    calibration_dir,
    list_models,
    load_model,
    save_model,
    set_status,
)
from intelligence.calibration.training import train_from_snapshot
from intelligence.calibration.types import STATUS_CANDIDATE, STATUS_PRODUCTION, STATUS_RETIRED
from tests.calibration_fixtures import synthetic_snapshot

TEAM_ID = "cal-store-team"


class CalibrationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_artifact_lives_outside_designs(self):
        model = train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id="m1")
        saved = save_model(TEAM_ID, model)
        folder = calibration_dir(TEAM_ID)
        self.assertTrue((folder / "m1.json").exists())
        self.assertTrue((folder / "m1.joblib").exists())
        self.assertNotEqual(folder.name, "designs")
        loaded = load_model(TEAM_ID, saved.model_id)
        self.assertEqual(loaded.site_id, "quarry-1")
        self.assertIsNotNone(loaded.estimator)

    def test_overwrite_is_rejected(self):
        model = train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id="fixed")
        save_model(TEAM_ID, model)
        again = train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id="fixed")
        with self.assertRaises(ImmutableCalibrationError):
            save_model(TEAM_ID, again)

    def test_status_change_does_not_rewrite_artifact(self):
        saved = save_model(
            TEAM_ID,
            train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id="m-status"),
        )
        digest = saved.artifact_sha256
        blob = artifact_path(TEAM_ID, saved.model_id).read_bytes()
        promoted = set_status(TEAM_ID, saved.model_id, STATUS_PRODUCTION)
        self.assertEqual(promoted.status, STATUS_PRODUCTION)
        self.assertEqual(promoted.artifact_sha256, digest)
        self.assertEqual(artifact_path(TEAM_ID, saved.model_id).read_bytes(), blob)
        self.assertEqual(load_model(TEAM_ID, saved.model_id).training_dataset_version, saved.training_dataset_version)

    def test_promoting_one_model_retires_previous_production(self):
        first = save_model(
            TEAM_ID,
            train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id="a", model_version=1),
        )
        second = save_model(
            TEAM_ID,
            train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id="b", model_version=2),
        )
        set_status(TEAM_ID, first.model_id, STATUS_PRODUCTION)
        set_status(TEAM_ID, second.model_id, STATUS_PRODUCTION)
        self.assertEqual(load_model(TEAM_ID, first.model_id).status, STATUS_RETIRED)
        self.assertEqual(load_model(TEAM_ID, second.model_id).status, STATUS_PRODUCTION)
        self.assertEqual(load_model(TEAM_ID, first.model_id).status_updated_at != "", True)

    def test_list_and_missing(self):
        save_model(TEAM_ID, train_from_snapshot(synthetic_snapshot(), model_type="ppv_residual", model_id="p1"))
        items = list_models(TEAM_ID)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, STATUS_CANDIDATE)
        with self.assertRaises(CalibrationNotFoundError):
            load_model(TEAM_ID, "missing")

    def test_tampered_artifact_is_rejected(self):
        save_model(TEAM_ID, train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id="tamper"))
        path = artifact_path(TEAM_ID, "tamper")
        path.write_bytes(b"not-a-model")
        with self.assertRaises(ImmutableCalibrationError):
            load_model(TEAM_ID, "tamper")


if __name__ == "__main__":
    unittest.main()
