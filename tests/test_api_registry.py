"""BDX-020: registry API stays human-gated and does not auto-deploy."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidRegistryError, RegistryIsolationError, RegistryNotFoundError
from api.schemas.learning import LearningGlobalTrainRequest, LearningPredictRequest
from api.schemas.registry import RegistryPromoteRequest
from api.services import learning_service, registry_service
from intelligence.datasets.persistence import save_snapshot
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_ID = "api-registry-team"
OTHER_TEAM = "api-registry-other"


class RegistryApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _train_learning(self, team_id: str = TEAM_ID):
        snapshot = save_snapshot(team_id, synthetic_outcome_snapshot(dataset_id=f"{team_id}-snap"))
        trained = learning_service.train_global_model(
            team_id,
            LearningGlobalTrainRequest(dataset_ids=[snapshot.dataset_id], model_type="fragmentation"),
        )
        return trained, snapshot

    def test_list_and_promote_with_actor_and_confirm(self):
        trained, snapshot = self._train_learning()
        listed = registry_service.list_registry_models(TEAM_ID, family="learning")
        self.assertEqual(len(listed.items), 1)
        self.assertFalse(listed.auto_deployed)
        card = listed.items[0]
        self.assertEqual(card.status, "candidate")
        self.assertEqual(card.family, "learning")
        self.assertTrue(card.checksum)
        self.assertEqual(card.lineage.training_dataset_id, snapshot.dataset_id)
        self.assertIn("measured", card.data_roles.values())
        self.assertIn("predicted", card.data_roles.values())
        self.assertIn("designed", card.data_roles.values())
        self.assertIn("executed", card.data_roles.values())

        loaded = registry_service.get_registry_model(TEAM_ID, "learning", trained.model_id)
        self.assertEqual(loaded.model_id, trained.model_id)
        self.assertEqual(loaded.checksum, card.checksum)

        staged = registry_service.promote_registry_model(
            TEAM_ID,
            "learning",
            trained.model_id,
            RegistryPromoteRequest(to_status="staging", confirm=True, note="review"),
            actor="lead@mine",
        )
        self.assertEqual(staged.status, "staging")
        self.assertEqual(staged.source_status, "candidate")
        self.assertEqual(staged.promoted_by, "lead@mine")
        self.assertFalse(staged.auto_deployed)

        production = registry_service.promote_registry_model(
            TEAM_ID,
            "learning",
            trained.model_id,
            RegistryPromoteRequest(to_status="production", confirm=True),
            actor="lead@mine",
        )
        self.assertEqual(production.status, "production")
        self.assertEqual(production.source_status, "production")
        self.assertEqual(production.transitions[-1].actor, "lead@mine")

    def test_missing_confirm_or_actor_is_rejected(self):
        trained, _snapshot = self._train_learning()
        with self.assertRaises(InvalidRegistryError):
            registry_service.promote_registry_model(
                TEAM_ID,
                "learning",
                trained.model_id,
                RegistryPromoteRequest(to_status="production", confirm=False),
                actor="lead@mine",
            )
        with self.assertRaises(InvalidRegistryError):
            registry_service.promote_registry_model(
                TEAM_ID,
                "learning",
                trained.model_id,
                RegistryPromoteRequest(to_status="production", confirm=True),
                actor="auto",
            )
        still = registry_service.get_registry_model(TEAM_ID, "learning", trained.model_id)
        self.assertEqual(still.status, "candidate")

    def test_unknown_model_and_cross_tenant(self):
        trained, _snapshot = self._train_learning()
        with self.assertRaises(RegistryNotFoundError):
            registry_service.get_registry_model(TEAM_ID, "learning", "missing")
        other = registry_service.list_registry_models(OTHER_TEAM)
        self.assertEqual(other.items, [])
        with self.assertRaises((RegistryNotFoundError, RegistryIsolationError)):
            registry_service.promote_registry_model(
                OTHER_TEAM,
                "learning",
                trained.model_id,
                RegistryPromoteRequest(to_status="production", confirm=True),
                actor="other@mine",
            )

    def test_staging_is_not_silent_production(self):
        trained, snapshot = self._train_learning()
        registry_service.promote_registry_model(
            TEAM_ID,
            "learning",
            trained.model_id,
            RegistryPromoteRequest(to_status="staging", confirm=True),
            actor="lead@mine",
        )
        silent = learning_service.predict_learning(
            TEAM_ID,
            LearningPredictRequest(
                model_type="fragmentation",
                scope="global",
                use_production=True,
                features=snapshot.samples[0].features,
            ),
        )
        self.assertFalse(silent.prediction_applied)
        self.assertNotEqual(silent.status, "production")
        self.assertFalse(silent.modifies_design)
        self.assertFalse(silent.auto_approved)

    def test_meta_lists_families_and_statuses(self):
        meta = registry_service.catalog_meta()
        names = [item.name for item in meta.families]
        self.assertEqual(names, ["calibration", "outcomes", "learning"])
        status_names = [item.name for item in meta.statuses]
        self.assertEqual(status_names, ["candidate", "staging", "production", "retired", "archived"])
        self.assertFalse(meta.auto_deployed)
        self.assertIn("staging", meta.statuses[0].allowed_transitions)
