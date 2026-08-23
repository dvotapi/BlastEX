import copy
import unittest

from intelligence.datasets.features import FEATURE_GROUPS, extract_features
from tests.dataset_fixtures import closed_design


class DatasetFeatureTests(unittest.TestCase):
    def test_extracts_all_feature_groups(self):
        features = extract_features(closed_design(), site_id="quarry-1")
        self.assertEqual(tuple(features), FEATURE_GROUPS)
        self.assertEqual(features["SITE"]["site_id"], "quarry-1")
        self.assertEqual(features["SITE"]["rock_name"], "гранит")
        self.assertEqual(features["GEOLOGY"]["domain_count"], 1)
        self.assertAlmostEqual(features["GEOLOGY"]["mean_ucs_mpa"], 120.0)
        self.assertEqual(features["GEOMETRY"]["enabled_hole_count"], 1)
        self.assertAlmostEqual(features["GEOMETRY"]["mean_spacing_m"], 5.0)
        self.assertAlmostEqual(features["CHARGING"]["total_charge_kg"], 80.0)
        self.assertEqual(features["TIMING"]["system"], "electronic")
        self.assertEqual(features["EXECUTION"]["as_drilled_count"], 1)
        self.assertEqual(features["EXECUTION"]["as_charged_count"], 1)
        self.assertEqual(features["EXECUTION"]["as_fired_count"], 1)
        self.assertGreater(features["EXECUTION"]["mean_collar_offset_m"], 0.0)
        self.assertEqual(features["ENVIRONMENT"]["receptor_count"], 1)
        self.assertGreater(features["ENVIRONMENT"]["nearest_receptor_distance_m"], 0.0)

    def test_extraction_does_not_mutate_design(self):
        design = closed_design()
        before = copy.deepcopy(design.to_dict())
        extract_features(design, site_id="quarry-1")
        self.assertEqual(design.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
