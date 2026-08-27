"""BDX-022: overlay is predicted-only and never writes designed charges."""
import unittest

from intelligence.spatial.prediction import apply_model
from intelligence.spatial.training import train_from_snapshot
from intelligence.spatial.types import ROLE_PREDICTED, SPATIAL_MAP_METRICS
from tests.spatial_fixtures import multi_hole_design, synthetic_spatial_snapshot


class SpatialPredictionTests(unittest.TestCase):
    def test_overlay_keeps_predicted_role_and_does_not_write_design(self):
        snapshot = synthetic_spatial_snapshot()
        model = train_from_snapshot(snapshot, team_id="spatial-pred")
        design = multi_hole_design()
        before_holes = [hole.to_dict() for hole in design.holes]
        before_loads = [load.to_dict() for load in design.loads]
        overlay = apply_model(
            design,
            model=model,
            site_id="quarry-1",
            block={"x50_mm": 160.0, "oversize_pct": 4.0, "toe_probability": 0.2},
        )
        self.assertEqual(overlay.role, ROLE_PREDICTED)
        self.assertFalse(overlay.modifies_design)
        self.assertEqual(overlay.applied_as, "predicted_overlay")
        self.assertEqual(len(overlay.holes), 6)
        self.assertEqual(len(overlay.neighborhoods), 6)
        self.assertTrue(overlay.prediction_applied)
        self.assertTrue(all(item.role == ROLE_PREDICTED for item in overlay.holes))
        self.assertTrue(all(item.x50_mm is not None for item in overlay.holes))
        self.assertEqual([hole.to_dict() for hole in design.holes], before_holes)
        self.assertEqual([load.to_dict() for load in design.loads], before_loads)
        payload = overlay.to_dict()
        self.assertFalse(payload["modifies_design"])
        self.assertEqual(payload["role"], ROLE_PREDICTED)

    def test_physics_fallback_without_model(self):
        design = multi_hole_design()
        before = [load.to_dict() for load in design.loads]
        overlay = apply_model(
            design,
            model=None,
            site_id="quarry-1",
            block={"x50_mm": 150.0, "oversize_pct": 3.5, "toe_probability": 0.18},
        )
        self.assertTrue(overlay.prediction_applied)
        self.assertEqual(overlay.role, ROLE_PREDICTED)
        self.assertFalse(overlay.modifies_design)
        self.assertTrue(overlay.holes)
        self.assertEqual([load.to_dict() for load in design.loads], before)
        self.assertTrue(any("физик" in item.lower() or "не выбрана" in item.lower() for item in overlay.warnings))

    def test_maps_expose_hole_metrics(self):
        overlay = apply_model(
            multi_hole_design(),
            model=None,
            block={"x50_mm": 150.0, "oversize_pct": 3.5, "toe_probability": 0.18},
        )
        self.assertEqual(overlay.maps["metrics"], list(SPATIAL_MAP_METRICS))
        self.assertEqual(overlay.maps["units"]["x50"], "mm")
        self.assertEqual(overlay.maps["units"]["oversize"], "%")
        self.assertEqual(overlay.maps["role"], ROLE_PREDICTED)
        self.assertEqual(len(overlay.maps["holes"]), 6)
