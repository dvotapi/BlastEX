"""BDX-022: training reads immutable snapshots only."""
import unittest

from intelligence.spatial.training import assert_snapshot_only, train_from_snapshot
from intelligence.spatial.types import STATUS_CANDIDATE
from tests.spatial_fixtures import synthetic_spatial_snapshot


class SpatialTrainingTests(unittest.TestCase):
    def test_trained_model_is_candidate_with_residual_targets(self):
        snapshot = synthetic_spatial_snapshot(dataset_version=3)
        model = train_from_snapshot(snapshot, team_id="spatial-train", model_version=2)
        self.assertEqual(model.team_id, "spatial-train")
        self.assertEqual(model.site_id, "quarry-1")
        self.assertEqual(model.model_version, 2)
        self.assertEqual(model.training_dataset_id, "snap-spatial")
        self.assertEqual(model.training_dataset_version, 3)
        self.assertEqual(model.status, STATUS_CANDIDATE)
        self.assertGreaterEqual(model.hole_count, 24)
        self.assertTrue(model.estimators)
        self.assertIn("residual_x50_mm", model.estimators)
        self.assertIn("mae", model.metrics)

    def test_mutable_snapshot_is_rejected(self):
        snapshot = synthetic_spatial_snapshot()
        snapshot.immutable = False
        with self.assertRaises(ValueError) as ctx:
            train_from_snapshot(snapshot, team_id="spatial-train")
        self.assertIn("неизменяемому", str(ctx.exception))

    def test_live_design_is_not_a_training_source(self):
        with self.assertRaises(ValueError) as ctx:
            assert_snapshot_only(object())
        self.assertIn("снимку", str(ctx.exception))

    def test_empty_team_is_rejected(self):
        snapshot = synthetic_spatial_snapshot()
        with self.assertRaises(ValueError):
            train_from_snapshot(snapshot, team_id="")
