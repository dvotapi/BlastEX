"""BDX-019: one tenant must not read or write another tenant's learning data."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.datasets.persistence import save_snapshot
from intelligence.learning.isolation import CrossTenantError, IsolationError
from intelligence.learning.persistence import (
    LearningNotFoundError,
    list_models,
    load_model,
    save_model,
    set_status,
)
from intelligence.learning.training import train_global, train_site
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_A = "tenant-alpha"
TEAM_B = "tenant-beta"


class LearningIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _saved_global(self, team_id: str, *, model_id: str, site_id: str = "quarry-1"):
        snapshot = save_snapshot(
            team_id,
            synthetic_outcome_snapshot(site_id=site_id, dataset_id=f"{team_id}-{site_id}"),
        )
        model = train_global(
            [snapshot],
            team_id=team_id,
            model_type="fragmentation",
            model_id=model_id,
        )
        return save_model(team_id, model), snapshot

    def test_cross_tenant_read_fails(self):
        saved, _snapshot = self._saved_global(TEAM_A, model_id="alpha-g")
        with self.assertRaises(LearningNotFoundError):
            load_model(TEAM_B, saved.model_id)
        self.assertEqual(list_models(TEAM_B), [])
        self.assertEqual(len(list_models(TEAM_A)), 1)

    def test_cross_tenant_write_fails(self):
        saved, _snapshot = self._saved_global(TEAM_A, model_id="alpha-write")
        loaded = load_model(TEAM_A, saved.model_id)
        with self.assertRaises(CrossTenantError):
            save_model(TEAM_B, loaded)
        with self.assertRaises(LearningNotFoundError):
            set_status(TEAM_B, saved.model_id, "production")

    def test_team_b_cannot_train_from_team_a_snapshot_id(self):
        _model, snapshot = self._saved_global(TEAM_A, model_id="alpha-data")
        from intelligence.datasets.persistence import DatasetNotFoundError, load_snapshot

        with self.assertRaises(DatasetNotFoundError):
            load_snapshot(TEAM_B, snapshot.dataset_id)

    def test_site_model_does_not_list_other_tenant_sites(self):
        prior, _snap = self._saved_global(TEAM_A, model_id="alpha-prior", site_id="quarry-1")
        site_snap = save_snapshot(
            TEAM_A, synthetic_outcome_snapshot(n=8, site_id="quarry-1", dataset_id="alpha-site")
        )
        adapted = save_model(
            TEAM_A,
            train_site(
                [site_snap],
                team_id=TEAM_A,
                site_id="quarry-1",
                model_type="fragmentation",
                prior=prior,
                model_id="alpha-site-m",
            ),
        )
        self.assertEqual(adapted.team_id, TEAM_A)
        self.assertEqual(adapted.site_id, "quarry-1")
        listed_b = list_models(TEAM_B)
        self.assertEqual(listed_b, [])
        with self.assertRaises(LearningNotFoundError):
            load_model(TEAM_B, adapted.model_id)

    def test_copied_metadata_still_rejects_foreign_team(self):
        saved, _snapshot = self._saved_global(TEAM_A, model_id="copied")
        src_dir = Path(self._tmp.name) / "teams" / TEAM_A / "learning"
        dst_dir = Path(self._tmp.name) / "teams" / TEAM_B / "learning"
        dst_dir.mkdir(parents=True, exist_ok=True)
        for name in ("copied.json", "copied.joblib"):
            (dst_dir / name).write_bytes((src_dir / name).read_bytes())
        with self.assertRaises(CrossTenantError):
            load_model(TEAM_B, "copied")

    def test_site_cannot_absorb_another_site_snapshot(self):
        other = synthetic_outcome_snapshot(site_id="foreign-site", dataset_id="xx")
        with self.assertRaises(IsolationError):
            train_site(
                [other],
                team_id=TEAM_A,
                site_id="quarry-1",
                model_type="oversize",
            )


if __name__ == "__main__":
    unittest.main()
