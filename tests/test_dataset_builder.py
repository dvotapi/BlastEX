import copy
import unittest

from intelligence.datasets.builder import (
    FEATURE_SCHEMA_VERSION,
    build_sample,
    build_snapshot,
    next_dataset_version,
)
from intelligence.datasets.features import FEATURE_GROUPS
from intelligence.datasets.targets import TARGET_GROUPS
from tests.dataset_fixtures import closed_design


class DatasetBuilderTests(unittest.TestCase):
    def test_snapshot_stores_required_metadata(self):
        first = closed_design("blast-a")
        second = closed_design("blast-b")
        snapshot = build_snapshot(
            [first, second],
            site_id="quarry-1",
            dataset_id="ds-1",
            dataset_version=1,
            name="июнь",
            created_at="2024-06-02T00:00:00+00:00",
        )
        self.assertEqual(snapshot.feature_schema_version, FEATURE_SCHEMA_VERSION)
        self.assertEqual(snapshot.dataset_version, 1)
        self.assertEqual(snapshot.source_blast_ids, ["blast-a", "blast-b"])
        self.assertEqual(snapshot.created_at, "2024-06-02T00:00:00+00:00")
        self.assertEqual(snapshot.site_id, "quarry-1")
        self.assertEqual(snapshot.sample_count, 2)
        self.assertTrue(snapshot.immutable)
        payload = snapshot.to_dict()
        self.assertEqual(payload["feature_schema_version"], FEATURE_SCHEMA_VERSION)
        self.assertEqual(payload["dataset_version"], 1)
        self.assertEqual(payload["source_blast_ids"], ["blast-a", "blast-b"])
        self.assertEqual(payload["created_at"], "2024-06-02T00:00:00+00:00")
        self.assertEqual(payload["site_id"], "quarry-1")

    def test_incomplete_blast_is_listed_not_included(self):
        good = closed_design("blast-ok")
        bad = closed_design("blast-bad")
        bad.blast_result = None
        snapshot = build_snapshot([good, bad], site_id="quarry-1", dataset_id="ds-2", dataset_version=1)
        self.assertEqual(snapshot.source_blast_ids, ["blast-ok"])
        self.assertEqual(snapshot.rejected_count, 1)
        self.assertEqual(snapshot.rejected[0]["source_blast_id"], "blast-bad")

    def test_snapshot_is_a_deep_copy(self):
        design = closed_design("blast-live")
        snapshot = build_snapshot([design], site_id="quarry-1", dataset_id="ds-3", dataset_version=1)
        original_x50 = snapshot.samples[0].targets["FRAGMENTATION"]["x50_mm"]
        design.blast_result.fragmentation.x50_mm = 999.0
        design.rock_name = "changed"
        self.assertAlmostEqual(snapshot.samples[0].targets["FRAGMENTATION"]["x50_mm"], original_x50)
        self.assertEqual(snapshot.samples[0].features["SITE"]["rock_name"], "гранит")

    def test_mutating_snapshot_dict_does_not_alias_internal_state(self):
        snapshot = build_snapshot([closed_design()], site_id="quarry-1", dataset_id="ds-4", dataset_version=1)
        payload = snapshot.to_dict()
        payload["samples"][0]["targets"]["FRAGMENTATION"]["x50_mm"] = 1.0
        payload["source_blast_ids"].append("injected")
        self.assertAlmostEqual(snapshot.samples[0].targets["FRAGMENTATION"]["x50_mm"], 170.0)
        self.assertEqual(snapshot.source_blast_ids, ["blast-closed"])

    def test_sample_contains_all_groups_and_provenance(self):
        sample = build_sample(closed_design(), site_id="quarry-1")
        self.assertEqual(set(sample.features), set(FEATURE_GROUPS))
        self.assertEqual(set(sample.targets), set(TARGET_GROUPS))
        self.assertEqual(sample.provenance["source_blast_id"], "blast-closed")
        restored = copy.deepcopy(sample.to_dict())
        self.assertEqual(restored["provenance"]["feature_schema_version"], FEATURE_SCHEMA_VERSION)

    def test_next_dataset_version_increments(self):
        self.assertEqual(next_dataset_version([]), 1)
        self.assertEqual(next_dataset_version([1, 3]), 4)

    def test_missing_site_id_raises(self):
        with self.assertRaises(ValueError):
            build_snapshot([closed_design()], site_id="", dataset_id="ds-x", dataset_version=1)


if __name__ == "__main__":
    unittest.main()
