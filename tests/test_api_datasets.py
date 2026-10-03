import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import ImmutableDatasetError, InvalidDesignError
from api.schemas.datasets import DatasetBuildRequest, DatasetPreviewRequest
from api.services import dataset_service
from design.persistence import save_design
from intelligence.datasets.baseline import baseline_settings, fragmentation_baseline
from tests.dataset_fixtures import closed_design

TEAM_ID = "api-dataset-team"


class DatasetApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_preview_accepts_closed_blast(self):
        result = dataset_service.preview_design(
            DatasetPreviewRequest(site_id="quarry-1", design=closed_design().to_dict())
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.closed)
        self.assertIn("FRAGMENTATION", result.complete_target_groups)

    def test_preview_does_not_compute_baseline(self):
        with patch(
            "intelligence.datasets.builder.fragmentation_baseline", wraps=fragmentation_baseline
        ) as baseline_spy, patch(
            "intelligence.datasets.builder.baseline_settings", wraps=baseline_settings
        ) as settings_spy:
            result = dataset_service.preview_design(
                DatasetPreviewRequest(site_id="quarry-1", design=closed_design().to_dict())
            )

        self.assertTrue(result.ok)
        baseline_spy.assert_not_called()
        settings_spy.assert_not_called()

    def test_build_list_and_get_snapshot(self):
        saved = save_design(TEAM_ID, closed_design("api-blast"))
        built = dataset_service.build_snapshot_for_team(
            TEAM_ID,
            DatasetBuildRequest(site_id="quarry-1", name="первый", design_ids=[saved.design_id]),
        )
        self.assertEqual(built.site_id, "quarry-1")
        self.assertEqual(built.dataset_version, 1)
        self.assertEqual(built.source_blast_ids, [saved.design_id])
        self.assertEqual(built.sample_count, 1)
        self.assertTrue(built.immutable)
        self.assertEqual(built.samples[0].provenance["source_blast_id"], saved.design_id)
        listed = dataset_service.list_snapshots(TEAM_ID)
        self.assertEqual(len(listed.items), 1)
        self.assertEqual(listed.items[0].dataset_id, built.dataset_id)
        loaded = dataset_service.get_snapshot(TEAM_ID, built.dataset_id)
        self.assertEqual(loaded.feature_schema_version, built.feature_schema_version)
        self.assertAlmostEqual(loaded.samples[0].targets["FRAGMENTATION"]["x50_mm"], 170.0)

    def test_list_keeps_fragmentation_base(self):
        """Список снимков отдаёт базу baseline: по нему видно, какой моделью посчитаны строки."""
        from intelligence.calibration.base import CURRENT_BASE

        saved = save_design(TEAM_ID, closed_design("list-base"))
        built = dataset_service.build_snapshot_for_team(
            TEAM_ID, DatasetBuildRequest(site_id="quarry-1", design_ids=[saved.design_id])
        )

        listed = dataset_service.list_snapshots(TEAM_ID)

        self.assertEqual(built.fragmentation_base, CURRENT_BASE.to_dict())
        self.assertEqual(listed.items[0].fragmentation_base, CURRENT_BASE.to_dict())
        self.assertEqual(listed.model_dump()["items"][0]["fragmentation_base"], CURRENT_BASE.to_dict())

    def test_list_old_snapshot_without_base(self):
        """Снимок до PR 3 в списке — с пустой базой, а не ошибкой."""
        import json

        from intelligence.datasets.persistence import dataset_path

        saved = save_design(TEAM_ID, closed_design("list-old"))
        built = dataset_service.build_snapshot_for_team(
            TEAM_ID, DatasetBuildRequest(site_id="quarry-1", design_ids=[saved.design_id])
        )
        path = dataset_path(TEAM_ID, built.dataset_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("fragmentation_base")
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        listed = dataset_service.list_snapshots(TEAM_ID)

        self.assertEqual(listed.items[0].fragmentation_base, {})

    def test_second_snapshot_increments_version(self):
        save_design(TEAM_ID, closed_design("api-blast-2"))
        first = dataset_service.build_snapshot_for_team(TEAM_ID, DatasetBuildRequest(site_id="quarry-1"))
        second = dataset_service.build_snapshot_for_team(TEAM_ID, DatasetBuildRequest(site_id="quarry-1"))
        self.assertEqual(first.dataset_version, 1)
        self.assertEqual(second.dataset_version, 2)
        self.assertNotEqual(first.dataset_id, second.dataset_id)

    def test_empty_site_id_is_invalid(self):
        with self.assertRaises(InvalidDesignError):
            dataset_service.build_snapshot_for_team(TEAM_ID, DatasetBuildRequest(site_id="  "))

    def test_snapshot_cannot_be_overwritten_through_store(self):
        save_design(TEAM_ID, closed_design("api-blast-3"))
        built = dataset_service.build_snapshot_for_team(TEAM_ID, DatasetBuildRequest(site_id="quarry-1"))
        from intelligence.datasets.builder import DatasetSnapshot
        from intelligence.datasets.persistence import save_snapshot

        clone = DatasetSnapshot.from_dict(built.model_dump())
        with self.assertRaises(ImmutableDatasetError):
            try:
                save_snapshot(TEAM_ID, clone)
            except Exception as exc:
                from intelligence.datasets.persistence import ImmutableDatasetError as StoreError

                if isinstance(exc, StoreError):
                    raise ImmutableDatasetError(str(exc)) from exc
                raise


if __name__ == "__main__":
    unittest.main()
