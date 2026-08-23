"""BDX-019: learned artifacts stay in the team store and cannot be overwritten."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.learning.isolation import CrossTenantError
from intelligence.learning.persistence import (
    ImmutableLearningError,
    LearningNotFoundError,
    artifact_path,
    learning_dir,
    list_models,
    load_model,
    save_model,
    set_status,
)
from intelligence.learning.training import train_global, train_site
from intelligence.learning.types import SCOPE_GLOBAL, SCOPE_SITE, STATUS_CANDIDATE, STATUS_PRODUCTION, STATUS_RETIRED
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_ID = "learn-store-team"


class LearningPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_artifact_lives_outside_designs_and_keeps_keys(self):
        model = train_global(
            [synthetic_outcome_snapshot()],
            team_id=TEAM_ID,
            model_type="fragmentation",
            model_id="g1",
        )
        saved = save_model(TEAM_ID, model)
        folder = learning_dir(TEAM_ID)
        self.assertTrue((folder / "g1.json").exists())
        self.assertTrue((folder / "g1.joblib").exists())
        self.assertNotEqual(folder.name, "designs")
        self.assertNotEqual(folder.name, "outcomes")
        loaded = load_model(TEAM_ID, saved.model_id)
        self.assertEqual(loaded.team_id, TEAM_ID)
        self.assertEqual(loaded.scope, SCOPE_GLOBAL)
        self.assertEqual(loaded.isolation.team_id, TEAM_ID)

    def test_save_forces_candidate(self):
        model = train_site(
            [synthetic_outcome_snapshot()],
            team_id=TEAM_ID,
            site_id="quarry-1",
            model_type="oversize",
        )
        model.status = "production"
        saved = save_model(TEAM_ID, model)
        self.assertEqual(saved.status, STATUS_CANDIDATE)

    def test_overwrite_is_rejected(self):
        model = train_global(
            [synthetic_outcome_snapshot()],
            team_id=TEAM_ID,
            model_type="oversize",
            model_id="fixed",
        )
        save_model(TEAM_ID, model)
        again = train_global(
            [synthetic_outcome_snapshot()],
            team_id=TEAM_ID,
            model_type="oversize",
            model_id="fixed",
        )
        with self.assertRaises(ImmutableLearningError):
            save_model(TEAM_ID, again)

    def test_status_change_does_not_rewrite_artifact(self):
        saved = save_model(
            TEAM_ID,
            train_site(
                [synthetic_outcome_snapshot()],
                team_id=TEAM_ID,
                site_id="quarry-1",
                model_type="vibration",
                model_id="m-status",
            ),
        )
        digest = saved.artifact_sha256
        blob = artifact_path(TEAM_ID, saved.model_id).read_bytes()
        promoted = set_status(TEAM_ID, saved.model_id, STATUS_PRODUCTION)
        self.assertEqual(promoted.status, STATUS_PRODUCTION)
        self.assertEqual(promoted.artifact_sha256, digest)
        self.assertEqual(artifact_path(TEAM_ID, saved.model_id).read_bytes(), blob)
        self.assertEqual(promoted.scope, SCOPE_SITE)

    def test_promoting_one_site_model_retires_previous_production(self):
        first = save_model(
            TEAM_ID,
            train_site(
                [synthetic_outcome_snapshot()],
                team_id=TEAM_ID,
                site_id="quarry-1",
                model_type="toe_risk",
                model_id="a",
                model_version=1,
            ),
        )
        second = save_model(
            TEAM_ID,
            train_site(
                [synthetic_outcome_snapshot()],
                team_id=TEAM_ID,
                site_id="quarry-1",
                model_type="toe_risk",
                model_id="b",
                model_version=2,
            ),
        )
        set_status(TEAM_ID, first.model_id, STATUS_PRODUCTION)
        set_status(TEAM_ID, second.model_id, STATUS_PRODUCTION)
        self.assertEqual(load_model(TEAM_ID, first.model_id).status, STATUS_RETIRED)
        self.assertEqual(load_model(TEAM_ID, second.model_id).status, STATUS_PRODUCTION)

    def test_list_filters_and_missing(self):
        save_model(
            TEAM_ID,
            train_global(
                [synthetic_outcome_snapshot()],
                team_id=TEAM_ID,
                model_type="fragmentation",
                model_id="g-frag",
            ),
        )
        save_model(
            TEAM_ID,
            train_site(
                [synthetic_outcome_snapshot()],
                team_id=TEAM_ID,
                site_id="quarry-1",
                model_type="oversize",
                model_id="s-over",
            ),
        )
        self.assertEqual(len(list_models(TEAM_ID)), 2)
        only_global = list_models(TEAM_ID, scope=SCOPE_GLOBAL)
        self.assertEqual(len(only_global), 1)
        self.assertEqual(only_global[0].status, STATUS_CANDIDATE)
        with self.assertRaises(LearningNotFoundError):
            load_model(TEAM_ID, "missing")

    def test_wrong_team_cannot_save_foreign_model(self):
        model = train_global(
            [synthetic_outcome_snapshot()],
            team_id="team-a",
            model_type="oversize",
            model_id="stolen",
        )
        with self.assertRaises(CrossTenantError):
            save_model("team-b", model)


if __name__ == "__main__":
    unittest.main()
