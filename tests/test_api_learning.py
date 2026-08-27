"""BDX-019: global/site learning API stays a candidate overlay."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidLearningError, LearningIsolationError, LearningNotFoundError
from api.schemas.learning import (
    LearningGlobalTrainRequest,
    LearningPredictRequest,
    LearningSiteTrainRequest,
    LearningStatusRequest,
)
from api.services import learning_service
from intelligence.datasets.persistence import save_snapshot
from tests.dataset_fixtures import closed_design
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_ID = "api-learn-team"


class LearningApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _store(self, snapshot=None):
        return save_snapshot(TEAM_ID, snapshot or synthetic_outcome_snapshot())

    def test_train_global_adapt_site_predict_and_status(self):
        global_snap = self._store(synthetic_outcome_snapshot(site_id="quarry-1", dataset_id="g-snap"))
        site_snap = self._store(synthetic_outcome_snapshot(n=8, site_id="quarry-1", dataset_id="s-snap"))
        trained = learning_service.train_global_model(
            TEAM_ID,
            LearningGlobalTrainRequest(dataset_ids=[global_snap.dataset_id], model_type="fragmentation"),
        )
        self.assertEqual(trained.status, "candidate")
        self.assertEqual(trained.scope, "global")
        self.assertEqual(trained.team_id, TEAM_ID)
        self.assertFalse(trained.auto_approved)
        listed = learning_service.list_learning_models(TEAM_ID, scope="global")
        self.assertEqual(len(listed.items), 1)
        loaded = learning_service.get_learning_model(TEAM_ID, trained.model_id)
        self.assertEqual(loaded.isolation.team_id, TEAM_ID)

        adapted = learning_service.train_site_model(
            TEAM_ID,
            LearningSiteTrainRequest(
                dataset_ids=[site_snap.dataset_id],
                site_id="quarry-1",
                model_type="fragmentation",
                prior_model_id=trained.model_id,
            ),
        )
        self.assertEqual(adapted.scope, "site")
        self.assertEqual(adapted.site_id, "quarry-1")
        self.assertEqual(adapted.prior_model_id, trained.model_id)
        self.assertEqual(adapted.status, "candidate")
        self.assertEqual(adapted.adaptation, "residual")

        prediction = learning_service.predict_learning(
            TEAM_ID,
            LearningPredictRequest(
                model_type="fragmentation",
                model_id=adapted.model_id,
                site_id="quarry-1",
                features=site_snap.samples[-1].features,
            ),
        )
        self.assertTrue(prediction.prediction_applied)
        self.assertFalse(prediction.modifies_design)
        self.assertFalse(prediction.auto_approved)
        self.assertEqual(prediction.applied_as, "recommendation_overlay")
        self.assertIsNotNone(prediction.predictions["x50_mm"].global_value)
        self.assertEqual(prediction.data_roles["prediction"], "predicted")
        self.assertEqual(prediction.data_roles["training_targets"], "measured")
        self.assertTrue(prediction.explanation.drivers)

        promoted = learning_service.update_status(
            TEAM_ID, adapted.model_id, LearningStatusRequest(status="production")
        )
        self.assertEqual(promoted.status, "production")

        production = learning_service.predict_learning(
            TEAM_ID,
            LearningPredictRequest(
                model_type="fragmentation",
                site_id="quarry-1",
                scope="site",
                use_production=True,
                features=site_snap.samples[0].features,
            ),
        )
        self.assertTrue(production.prediction_applied)
        self.assertEqual(production.status, "production")

    def test_candidate_is_not_used_as_silent_production(self):
        snapshot = self._store()
        learning_service.train_site_model(
            TEAM_ID,
            LearningSiteTrainRequest(
                dataset_ids=[snapshot.dataset_id],
                site_id="quarry-1",
                model_type="oversize",
            ),
        )
        silent = learning_service.predict_learning(
            TEAM_ID,
            LearningPredictRequest(
                model_type="oversize",
                site_id="quarry-1",
                scope="site",
                use_production=True,
                features=snapshot.samples[0].features,
            ),
        )
        self.assertFalse(silent.prediction_applied)
        self.assertIsNone(silent.predicted)
        self.assertFalse(silent.modifies_design)
        self.assertFalse(silent.auto_approved)

    def test_predict_does_not_mutate_design(self):
        snapshot = self._store()
        trained = learning_service.train_global_model(
            TEAM_ID,
            LearningGlobalTrainRequest(dataset_ids=[snapshot.dataset_id], model_type="vibration"),
        )
        design = closed_design("live-design")
        before = copy.deepcopy(design.to_dict())
        learning_service.predict_learning(
            TEAM_ID,
            LearningPredictRequest(
                model_type="vibration",
                model_id=trained.model_id,
                design=design.to_dict(),
            ),
        )
        self.assertEqual(design.to_dict(), before)

    def test_empty_dataset_ids_are_invalid(self):
        with self.assertRaises(InvalidLearningError):
            learning_service.train_global_model(
                TEAM_ID, LearningGlobalTrainRequest(dataset_ids=["  "], model_type="fragmentation")
            )

    def test_foreign_snapshot_id_does_not_train(self):
        other = save_snapshot("other-team", synthetic_outcome_snapshot(dataset_id="secret"))
        from api.exceptions import DatasetNotFoundError

        with self.assertRaises(DatasetNotFoundError):
            learning_service.train_global_model(
                TEAM_ID,
                LearningGlobalTrainRequest(dataset_ids=[other.dataset_id], model_type="fragmentation"),
            )

    def test_site_mismatch_is_isolation_error(self):
        snapshot = self._store(synthetic_outcome_snapshot(site_id="pit-9", dataset_id="pit"))
        with self.assertRaises(LearningIsolationError):
            learning_service.train_site_model(
                TEAM_ID,
                LearningSiteTrainRequest(
                    dataset_ids=[snapshot.dataset_id],
                    site_id="quarry-1",
                    model_type="oversize",
                ),
            )

    def test_missing_model_and_algorithms(self):
        with self.assertRaises(LearningNotFoundError):
            learning_service.get_learning_model(TEAM_ID, "missing")
        types = learning_service.list_learning_types()
        names = {item.name for item in types.items}
        self.assertIn("fragmentation", names)
        listed = learning_service.list_algorithms()
        self.assertIn("random_forest", {item.name for item in listed.items})


if __name__ == "__main__":
    unittest.main()
