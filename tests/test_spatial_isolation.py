"""BDX-022: spatial models stay inside the tenant that owns them."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.datasets.persistence import save_snapshot
from intelligence.learning.isolation import CrossTenantError, IsolationError
from intelligence.spatial.persistence import (
    ImmutableSpatialError,
    SpatialNotFoundError,
    list_models,
    load_model,
    save_model,
    set_status,
)
from intelligence.spatial.training import train_from_snapshot
from intelligence.spatial.types import STATUS_PRODUCTION
from tests.spatial_fixtures import synthetic_spatial_snapshot

TEAM_A = "spatial-alpha"
TEAM_B = "spatial-beta"


class SpatialIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _train(self, team_id: str, *, model_id: str, dataset_id: str):
        snapshot = save_snapshot(
            team_id,
            synthetic_spatial_snapshot(site_id="quarry-1", dataset_id=dataset_id),
        )
        model = train_from_snapshot(
            snapshot,
            team_id=team_id,
            model_id=model_id,
        )
        return save_model(team_id, model)

    def test_other_tenant_cannot_see_or_load_foreign_model(self):
        saved = self._train(TEAM_A, model_id="alpha-spatial", dataset_id="alpha-holes")
        self.assertEqual(saved.team_id, TEAM_A)
        self.assertEqual(list_models(TEAM_B), [])
        with self.assertRaises((SpatialNotFoundError, CrossTenantError)):
            load_model(TEAM_B, saved.model_id)

    def test_artifact_is_write_once(self):
        saved = self._train(TEAM_A, model_id="once-spatial", dataset_id="once-holes")
        again = train_from_snapshot(
            synthetic_spatial_snapshot(dataset_id="once-holes"),
            team_id=TEAM_A,
            model_id=saved.model_id,
        )
        with self.assertRaises(ImmutableSpatialError):
            save_model(TEAM_A, again)

    def test_empty_team_is_rejected(self):
        with self.assertRaises(IsolationError):
            list_models("")
        with self.assertRaises(IsolationError):
            list_models("  ")

    def test_status_change_does_not_rewrite_artifact(self):
        saved = self._train(TEAM_A, model_id="status-spatial", dataset_id="status-holes")
        promoted = set_status(TEAM_A, saved.model_id, STATUS_PRODUCTION)
        self.assertEqual(promoted.status, STATUS_PRODUCTION)
        self.assertEqual(promoted.artifact_sha256, saved.artifact_sha256)
        loaded = load_model(TEAM_A, saved.model_id)
        self.assertEqual(loaded.status, STATUS_PRODUCTION)
