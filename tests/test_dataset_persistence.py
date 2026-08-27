import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from design.models import BlastDesign, BlockContour, Point3
from design.persistence import designs_dir, save_design
from intelligence.datasets.builder import build_snapshot
from intelligence.datasets.persistence import (
    ImmutableDatasetError,
    datasets_dir,
    list_snapshots,
    load_snapshot,
    save_snapshot,
)
from tests.dataset_fixtures import closed_design

TEAM_ID = "dataset-team"


class DatasetPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_snapshot_is_stored_apart_from_designs(self):
        design = save_design(TEAM_ID, closed_design())
        snapshot = build_snapshot([design], site_id="quarry-1", dataset_id="", dataset_version=1, name="v1")
        saved = save_snapshot(TEAM_ID, snapshot)
        self.assertTrue(saved.dataset_id)
        design_files = {path.name for path in designs_dir(TEAM_ID).glob("*.json")}
        dataset_files = {path.name for path in datasets_dir(TEAM_ID).glob("*.json")}
        self.assertIn(f"{design.design_id}.json", design_files)
        self.assertIn(f"{saved.dataset_id}.json", dataset_files)
        self.assertFalse(design_files & dataset_files)

    def test_overwrite_is_rejected(self):
        snapshot = build_snapshot([closed_design()], site_id="quarry-1", dataset_id="fixed-id", dataset_version=1)
        save_snapshot(TEAM_ID, snapshot)
        with self.assertRaises(ImmutableDatasetError):
            save_snapshot(TEAM_ID, snapshot)

    def test_live_design_change_does_not_change_snapshot(self):
        design = save_design(TEAM_ID, closed_design("live-1"))
        snapshot = save_snapshot(
            TEAM_ID,
            build_snapshot([design], site_id="quarry-1", dataset_id="snap-1", dataset_version=1),
        )
        design.rock_name = "сланец"
        design.blast_result.fragmentation.x50_mm = 12.0
        save_design(TEAM_ID, design)
        loaded = load_snapshot(TEAM_ID, snapshot.dataset_id)
        self.assertEqual(loaded.samples[0].features["SITE"]["rock_name"], "гранит")
        self.assertAlmostEqual(loaded.samples[0].targets["FRAGMENTATION"]["x50_mm"], 170.0)

    def test_list_and_integrity(self):
        save_snapshot(
            TEAM_ID,
            build_snapshot([closed_design()], site_id="quarry-1", dataset_id="snap-a", dataset_version=1),
        )
        items = list_snapshots(TEAM_ID)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].site_id, "quarry-1")
        self.assertTrue(items[0].immutable)
        path = datasets_dir(TEAM_ID) / "snap-a.json"
        text = path.read_text(encoding="utf-8").replace("гранит", "XXXXXX", 1)
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ImmutableDatasetError):
            load_snapshot(TEAM_ID, "snap-a")

    def test_open_design_is_not_a_snapshot(self):
        open_design = BlastDesign(
            design_id="open-1",
            contour=BlockContour(vertices=[Point3(x=0, y=0, z=0), Point3(x=4, y=0, z=0), Point3(x=4, y=4, z=0)]),
        )
        save_design(TEAM_ID, open_design)
        snapshot = build_snapshot([open_design], site_id="quarry-1", dataset_id="snap-open", dataset_version=1)
        self.assertEqual(snapshot.sample_count, 0)
        self.assertEqual(snapshot.rejected_count, 1)


if __name__ == "__main__":
    unittest.main()
