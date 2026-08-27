"""BDX-019: global prior plus site residual, snapshots only, candidate status."""
import copy
import unittest

from intelligence.learning.isolation import IsolationError
from intelligence.learning.prediction import apply_model
from intelligence.learning.training import train_global, train_site
from intelligence.learning.types import (
    ADAPTATION_DIRECT,
    ADAPTATION_RESIDUAL,
    GLOBAL_SITE_ID,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    SCOPE_GLOBAL,
    SCOPE_SITE,
    STATUS_CANDIDATE,
)
from tests.dataset_fixtures import closed_design
from tests.outcome_fixtures import synthetic_outcome_snapshot


class LearningTrainingTests(unittest.TestCase):
    def test_global_prior_stores_isolation_keys_and_stays_candidate(self):
        quarry = synthetic_outcome_snapshot(site_id="quarry-1", dataset_id="snap-q1")
        pit = synthetic_outcome_snapshot(n=8, site_id="pit-2", dataset_id="snap-p2")
        model = train_global(
            [quarry, pit],
            team_id="acme",
            model_type="fragmentation",
            model_version=1,
        )
        self.assertEqual(model.team_id, "acme")
        self.assertEqual(model.site_id, GLOBAL_SITE_ID)
        self.assertEqual(model.scope, SCOPE_GLOBAL)
        self.assertEqual(model.isolation.team_id, "acme")
        self.assertEqual(model.status, STATUS_CANDIDATE)
        self.assertEqual(model.adaptation, ADAPTATION_DIRECT)
        self.assertFalse(model.to_dict()["auto_approved"])
        self.assertEqual(set(model.source_site_ids), {"quarry-1", "pit-2"})
        self.assertEqual(model.to_dict()["data_roles"]["training_targets"], ROLE_MEASURED)
        self.assertIn("x50_mm", model.estimators)

    def test_site_adapter_starts_from_global_prior_without_foreign_blasts(self):
        global_snap = synthetic_outcome_snapshot(n=8, site_id="quarry-1", dataset_id="g1")
        site_snap = synthetic_outcome_snapshot(n=8, site_id="pit-2", dataset_id="s2")
        prior = train_global([global_snap], team_id="acme", model_type="oversize")
        adapted = train_site(
            [site_snap],
            team_id="acme",
            site_id="pit-2",
            model_type="oversize",
            prior=prior,
        )
        self.assertEqual(adapted.scope, SCOPE_SITE)
        self.assertEqual(adapted.team_id, "acme")
        self.assertEqual(adapted.site_id, "pit-2")
        self.assertEqual(adapted.prior_model_id, prior.model_id)
        self.assertEqual(adapted.prior_team_id, "acme")
        self.assertEqual(adapted.adaptation, ADAPTATION_RESIDUAL)
        self.assertEqual(adapted.status, STATUS_CANDIDATE)
        self.assertEqual(adapted.source_site_ids, ["pit-2"])
        self.assertTrue(all(item.startswith("blast-") for item in adapted.source_blast_ids))
        self.assertTrue(adapted.prior_estimators)
        self.assertNotIn("quarry-1", adapted.source_site_ids)

    def test_site_without_prior_trains_direct_on_site_snapshot(self):
        snapshot = synthetic_outcome_snapshot(site_id="quarry-1")
        model = train_site(
            [snapshot],
            team_id="acme",
            site_id="quarry-1",
            model_type="vibration",
        )
        self.assertEqual(model.adaptation, ADAPTATION_DIRECT)
        self.assertEqual(model.prior_model_id, "")
        self.assertEqual(model.site_id, "quarry-1")
        self.assertIn("max_ppv_mm_s", model.estimators)

    def test_live_design_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            train_global([closed_design()], team_id="acme", model_type="fragmentation")
        self.assertIn("снимку", str(ctx.exception).lower())

    def test_mutable_snapshot_is_rejected(self):
        snapshot = synthetic_outcome_snapshot()
        snapshot.immutable = False
        with self.assertRaises(ValueError):
            train_site([snapshot], team_id="acme", site_id="quarry-1", model_type="oversize")

    def test_site_snapshot_from_another_site_is_rejected(self):
        foreign = synthetic_outcome_snapshot(site_id="other-pit", dataset_id="foreign")
        with self.assertRaises(IsolationError):
            train_site(
                [foreign],
                team_id="acme",
                site_id="quarry-1",
                model_type="fragmentation",
            )

    def test_prior_from_another_team_is_rejected(self):
        prior = train_global(
            [synthetic_outcome_snapshot()],
            team_id="team-a",
            model_type="oversize",
        )
        with self.assertRaises(IsolationError):
            train_site(
                [synthetic_outcome_snapshot(site_id="quarry-1")],
                team_id="team-b",
                site_id="quarry-1",
                model_type="oversize",
                prior=prior,
            )


class LearningPredictionTests(unittest.TestCase):
    def test_site_prediction_adds_residual_and_does_not_mutate_features(self):
        prior = train_global(
            [synthetic_outcome_snapshot(n=8, site_id="quarry-1")],
            team_id="acme",
            model_type="fragmentation",
        )
        site = train_site(
            [synthetic_outcome_snapshot(n=8, site_id="quarry-1")],
            team_id="acme",
            site_id="quarry-1",
            model_type="fragmentation",
            prior=prior,
        )
        features = copy.deepcopy(synthetic_outcome_snapshot().samples[-1].features)
        original = copy.deepcopy(features)
        prediction = apply_model(site, features=features)
        self.assertEqual(features, original)
        self.assertFalse(prediction.modifies_design)
        self.assertFalse(prediction.auto_approved)
        self.assertEqual(prediction.applied_as, "recommendation_overlay")
        self.assertEqual(prediction.team_id, "acme")
        self.assertEqual(prediction.site_id, "quarry-1")
        payload = prediction.to_dict()
        self.assertEqual(payload["data_roles"]["prediction"], ROLE_PREDICTED)
        self.assertIn("x50_mm", prediction.predictions)
        self.assertIsNotNone(prediction.predictions["x50_mm"].global_value)
        self.assertIsNotNone(prediction.predictions["x50_mm"].residual_value)
        self.assertGreater(prediction.predictions["x50_mm"].value, 0)
        self.assertTrue(any("candidate" in item for item in prediction.warnings))
        self.assertTrue(any("не утверждает" in item for item in prediction.warnings))
        self.assertIn("uncertainty", payload)
        self.assertIn("explanation", payload)

    def test_global_prediction_has_no_residual_component(self):
        model = train_global(
            [synthetic_outcome_snapshot()],
            team_id="acme",
            model_type="oversize",
        )
        prediction = apply_model(model, features=synthetic_outcome_snapshot().samples[0].features)
        item = prediction.predictions["oversize_pct"]
        self.assertIsNone(item.global_value)
        self.assertIsNone(item.residual_value)
        self.assertGreaterEqual(item.value, 0.0)
        self.assertLessEqual(item.value, 100.0)
        self.assertEqual(prediction.scope, SCOPE_GLOBAL)


if __name__ == "__main__":
    unittest.main()
