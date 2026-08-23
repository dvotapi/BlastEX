"""BDX-022: spatial API stays a predicted overlay and does not rewrite the passport."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidSpatialError, SpatialIsolationError, SpatialNotFoundError
from api.schemas.design import BlastDesignSchema
from api.schemas.spatial import SpatialPredictRequest, SpatialStatusRequest, SpatialTrainRequest
from api.services import spatial_service
from intelligence.datasets.persistence import save_snapshot
from tests.spatial_fixtures import multi_hole_design, synthetic_spatial_snapshot

TEAM_ID = "api-spatial-team"
OTHER_TEAM = "api-spatial-other"


class SpatialApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _snapshot(self, team_id: str = TEAM_ID, dataset_id: str = "api-spatial"):
        return save_snapshot(team_id, synthetic_spatial_snapshot(dataset_id=dataset_id))

    def test_train_predict_does_not_modify_design(self):
        snapshot = self._snapshot()
        trained = spatial_service.train_spatial(
            TEAM_ID,
            SpatialTrainRequest(dataset_id=snapshot.dataset_id, site_id="quarry-1"),
        )
        self.assertEqual(trained.status, "candidate")
        self.assertEqual(trained.class_name, "SpatialHoleModel")
        self.assertGreaterEqual(trained.hole_count, 24)
        listed = spatial_service.list_spatial_models(TEAM_ID)
        self.assertEqual(len(listed.items), 1)
        self.assertFalse(listed.modifies_design)

        design = multi_hole_design("api-block")
        before = [load.to_dict() for load in design.loads]
        overlay = spatial_service.predict_spatial(
            TEAM_ID,
            SpatialPredictRequest(
                design=BlastDesignSchema(**design.to_dict()),
                model_id=trained.model_id,
                site_id="quarry-1",
                block={"x50_mm": 158.0, "oversize_pct": 3.8, "toe_probability": 0.16},
            ),
        )
        self.assertEqual(overlay.role, "predicted")
        self.assertFalse(overlay.modifies_design)
        self.assertEqual(overlay.applied_as, "predicted_overlay")
        self.assertGreaterEqual(overlay.hole_count, 6)
        self.assertEqual(overlay.maps["units"]["x50"], "mm")
        self.assertIn("predicted", overlay.data_roles.values())
        self.assertIn("designed", overlay.data_roles.values())
        self.assertEqual([load.to_dict() for load in design.loads], before)

        promoted = spatial_service.update_status(
            TEAM_ID,
            trained.model_id,
            SpatialStatusRequest(status="production"),
        )
        self.assertEqual(promoted.status, "production")

    def test_cross_tenant_and_unknown(self):
        snapshot = self._snapshot()
        trained = spatial_service.train_spatial(
            TEAM_ID,
            SpatialTrainRequest(dataset_id=snapshot.dataset_id),
        )
        other = spatial_service.list_spatial_models(OTHER_TEAM)
        self.assertEqual(other.items, [])
        with self.assertRaises((SpatialNotFoundError, SpatialIsolationError, InvalidSpatialError)):
            spatial_service.get_spatial_model(OTHER_TEAM, trained.model_id)

    def test_meta_lists_predicted_metrics(self):
        meta = spatial_service.catalog_meta()
        names = [item.name for item in meta.metrics]
        self.assertIn("x50_mm", names)
        self.assertIn("residual_x50_mm", names)
        self.assertFalse(meta.modifies_design)
        self.assertEqual(meta.role, "predicted")
        self.assertEqual(meta.data_roles["predictions"], "predicted")
        self.assertEqual(meta.data_roles["targets"], "measured")
        self.assertEqual(meta.map_metrics[0].role, "predicted")
