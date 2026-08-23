"""BDX-022: hole / neighborhood features stay designed and do not write the design."""
import copy
import unittest

from design.models import ROLE_DESIGNED, ROLE_EXECUTED
from intelligence.datasets.builder import build_sample
from intelligence.spatial.features import extract_hole_observations
from intelligence.spatial.types import HOLE_FEATURE_NAMES, ROLE_PREDICTED
from tests.spatial_fixtures import multi_hole_design


class SpatialHoleFeatureTests(unittest.TestCase):
    def test_extracts_one_row_per_enabled_hole(self):
        design = multi_hole_design()
        rows = extract_hole_observations(design, site_id="quarry-1")
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(item.feature_role == ROLE_DESIGNED for item in rows))
        first = rows[0]
        for name in HOLE_FEATURE_NAMES:
            self.assertIn(name, first.features)
        self.assertIn("rel_charge_kg", first.features)
        self.assertTrue(first.neighbor_ids)

    def test_relative_features_sum_near_zero(self):
        rows = extract_hole_observations(multi_hole_design(), site_id="quarry-1")
        rel = sum(item.features["rel_charge_kg"] for item in rows)
        self.assertAlmostEqual(rel, 0.0, places=6)

    def test_extraction_does_not_mutate_designed_charges(self):
        design = multi_hole_design()
        before_holes = [hole.to_dict() for hole in design.holes]
        before_loads = [load.to_dict() for load in design.loads]
        extract_hole_observations(design, site_id="quarry-1")
        self.assertEqual([hole.to_dict() for hole in design.holes], before_holes)
        self.assertEqual([load.to_dict() for load in design.loads], before_loads)

    def test_executed_charge_is_context_only(self):
        design = multi_hole_design()
        rows = extract_hole_observations(design, site_id="quarry-1")
        charged = next(item for item in rows if item.hole_id == design.as_charged_holes[0].design_hole_id)
        self.assertIn("charge_kg", charged.executed)
        self.assertNotEqual(charged.feature_role, ROLE_EXECUTED)
        self.assertEqual(charged.features.get("charge_kg"), next(load.total_charge_kg for load in design.loads if load.hole_id == charged.hole_id))

    def test_physics_predictions_are_predicted_role(self):
        rows = extract_hole_observations(multi_hole_design(), site_id="quarry-1")
        predicted = [item for item in rows if item.predicted.get("x50_mm") is not None]
        self.assertTrue(predicted)
        self.assertEqual(ROLE_PREDICTED, "predicted")

    def test_snapshot_sample_freezes_hole_rows(self):
        design = multi_hole_design()
        sample = build_sample(design, site_id="quarry-1")
        self.assertGreaterEqual(len(sample.holes), 6)
        self.assertEqual(sample.holes[0]["feature_role"], ROLE_DESIGNED)
        design.loads[0].total_charge_kg = 1.0
        self.assertNotEqual(sample.holes[0]["features"]["charge_kg"], 1.0)

    def test_mutating_source_after_extract_does_not_alias(self):
        design = multi_hole_design()
        rows = extract_hole_observations(design, site_id="quarry-1")
        snapshot = copy.deepcopy(rows[0].features)
        design.loads[0].total_charge_kg = 999.0
        self.assertEqual(rows[0].features, snapshot)
