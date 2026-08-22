import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from design.models import BenchSurface, BlockContour, BlastDesign, Point3
from design.persistence import (
    DesignNotFoundError,
    delete_design,
    list_designs,
    load_design,
    rename_design,
    save_design,
)

TEAM_ID = "test-team"


class DesignPersistenceRoundTripTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _sample_design(self) -> BlastDesign:
        return BlastDesign(
            design_id="",
            name="Тестовый блок",
            contour=BlockContour(
                vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (10, 0), (10, 10), (0, 10)]],
                bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
            ),
        )

    def test_save_assigns_id_and_round_trips(self):
        design = self._sample_design()
        saved = save_design(TEAM_ID, design)
        self.assertTrue(saved.design_id)
        self.assertTrue(saved.updated_at)

        loaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(loaded.name, "Тестовый блок")
        self.assertEqual(len(loaded.contour.vertices), 4)
        self.assertEqual(loaded.version, saved.version)

    def test_list_designs_returns_summary(self):
        saved = save_design(TEAM_ID, self._sample_design())
        summaries = list_designs(TEAM_ID)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].design_id, saved.design_id)
        self.assertEqual(summaries[0].name, "Тестовый блок")

    def test_rename_updates_name(self):
        saved = save_design(TEAM_ID, self._sample_design())
        renamed = rename_design(TEAM_ID, saved.design_id, "Новое имя")
        self.assertEqual(renamed.name, "Новое имя")
        self.assertEqual(load_design(TEAM_ID, saved.design_id).name, "Новое имя")

    def test_delete_removes_design(self):
        saved = save_design(TEAM_ID, self._sample_design())
        delete_design(TEAM_ID, saved.design_id)
        with self.assertRaises(DesignNotFoundError):
            load_design(TEAM_ID, saved.design_id)

    def test_load_missing_raises(self):
        with self.assertRaises(DesignNotFoundError):
            load_design(TEAM_ID, "no-such-id")

    def test_path_traversal_id_rejected(self):
        with self.assertRaises(DesignNotFoundError):
            load_design(TEAM_ID, "../secret")
        with self.assertRaises(DesignNotFoundError):
            delete_design(TEAM_ID, "../../outside")

    def test_designs_are_isolated_per_team(self):
        save_design(TEAM_ID, self._sample_design())
        self.assertEqual(list_designs("another-team"), [])


if __name__ == "__main__":
    unittest.main()
