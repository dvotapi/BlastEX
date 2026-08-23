import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.outcomes.persistence import (
    ImmutableOutcomeError,
    OutcomeNotFoundError,
    artifact_path,
    list_models,
    load_model,
    outcomes_dir,
    save_model,
    set_status,
)
from intelligence.outcomes.training import train_from_snapshot
from intelligence.outcomes.types import STATUS_CANDIDATE, STATUS_PRODUCTION, STATUS_RETIRED
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_ID = "out-store-team"


class OutcomePersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_artifact_lives_outside_designs(self):
        model = train_from_snapshot(synthetic_outcome_snapshot(), model_type="fragmentation", model_id="m1")
        saved = save_model(TEAM_ID, model)
        folder = outcomes_dir(TEAM_ID)
        self.assertTrue((folder / "m1.json").exists())
        self.assertTrue((folder / "m1.joblib").exists())
        self.assertNotEqual(folder.name, "designs")
        self.assertNotEqual(folder.name, "calibration")
        loaded = load_model(TEAM_ID, saved.model_id)
        self.assertEqual(loaded.site_id, "quarry-1")
        self.assertIn("x50_mm", loaded.estimators)

    def test_save_forces_candidate_even_if_status_was_changed(self):
        model = train_from_snapshot(synthetic_outcome_snapshot(), model_type="oversize")
        model.status = "production"
        saved = save_model(TEAM_ID, model)
        self.assertEqual(saved.status, STATUS_CANDIDATE)

    def test_overwrite_is_rejected(self):
        model = train_from_snapshot(synthetic_outcome_snapshot(), model_type="oversize", model_id="fixed")
        save_model(TEAM_ID, model)
        again = train_from_snapshot(synthetic_outcome_snapshot(), model_type="oversize", model_id="fixed")
        with self.assertRaises(ImmutableOutcomeError):
            save_model(TEAM_ID, again)

    def test_status_change_does_not_rewrite_artifact(self):
        saved = save_model(
            TEAM_ID,
            train_from_snapshot(synthetic_outcome_snapshot(), model_type="vibration", model_id="m-status"),
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
            train_from_snapshot(synthetic_outcome_snapshot(), model_type="toe_risk", model_id="a", model_version=1),
        )
        second = save_model(
            TEAM_ID,
            train_from_snapshot(synthetic_outcome_snapshot(), model_type="toe_risk", model_id="b", model_version=2),
        )
        set_status(TEAM_ID, first.model_id, STATUS_PRODUCTION)
        set_status(TEAM_ID, second.model_id, STATUS_PRODUCTION)
        self.assertEqual(load_model(TEAM_ID, first.model_id).status, STATUS_RETIRED)
        self.assertEqual(load_model(TEAM_ID, second.model_id).status, STATUS_PRODUCTION)
        self.assertTrue(load_model(TEAM_ID, first.model_id).status_updated_at)

    def test_list_filter_and_missing(self):
        save_model(TEAM_ID, train_from_snapshot(synthetic_outcome_snapshot(), model_type="ppv", model_id="p1"))
        save_model(TEAM_ID, train_from_snapshot(synthetic_outcome_snapshot(), model_type="oversize", model_id="o1"))
        items = list_models(TEAM_ID)
        self.assertEqual(len(items), 2)
        only_vib = list_models(TEAM_ID, model_type="vibration")
        self.assertEqual(len(only_vib), 1)
        self.assertEqual(only_vib[0].status, STATUS_CANDIDATE)
        with self.assertRaises(OutcomeNotFoundError):
            load_model(TEAM_ID, "missing")

    def test_tampered_artifact_is_rejected(self):
        save_model(TEAM_ID, train_from_snapshot(synthetic_outcome_snapshot(), model_type="fragmentation", model_id="tamper"))
        path = artifact_path(TEAM_ID, "tamper")
        path.write_bytes(b"not-a-model")
        with self.assertRaises(ImmutableOutcomeError):
            load_model(TEAM_ID, "tamper")


if __name__ == "__main__":
    unittest.main()
