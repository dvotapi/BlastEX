"""BDX-022: hole-level predicted maps keep units and predicted role."""
import unittest

from intelligence.spatial.maps import spatial_maps
from intelligence.spatial.types import ROLE_PREDICTED, HolePrediction, SPATIAL_MAP_METRICS


class SpatialMapTests(unittest.TestCase):
    def test_map_payload_matches_fragmentation_shape(self):
        holes = [
            HolePrediction(hole_id="1-01", x=0.0, y=0.0, x50_mm=140.0, oversize_pct=3.0, toe_probability=0.1, residual_x50_mm=-5.0),
            HolePrediction(hole_id="1-02", x=5.0, y=0.0, x50_mm=160.0, oversize_pct=5.0, toe_probability=0.2, residual_x50_mm=5.0),
        ]
        payload = spatial_maps(holes)
        self.assertEqual(payload["metrics"], list(SPATIAL_MAP_METRICS))
        self.assertEqual(payload["role"], ROLE_PREDICTED)
        self.assertEqual(payload["units"]["x50"], "mm")
        self.assertEqual(payload["units"]["residual_x50"], "mm")
        self.assertEqual(payload["units"]["oversize"], "%")
        self.assertEqual(payload["stats"]["x50"]["min"], 140.0)
        self.assertEqual(payload["stats"]["x50"]["max"], 160.0)
        self.assertEqual(payload["holes"][0]["hole_id"], "1-01")
        self.assertEqual(payload["holes"][0]["role"], ROLE_PREDICTED)
