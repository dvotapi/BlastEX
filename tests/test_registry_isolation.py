"""BDX-020: registry cards stay inside the tenant that owns the artifact."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.datasets.persistence import save_snapshot
from intelligence.learning.isolation import CrossTenantError, IsolationError
from intelligence.learning.persistence import save_model as save_learning
from intelligence.learning.training import train_global
from intelligence.registry.catalog import RegistryNotFoundError
from intelligence.registry.persistence import get_record, list_records, promote
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_A = "registry-alpha"
TEAM_B = "registry-beta"


class RegistryIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _saved(self, team_id: str, *, model_id: str):
        snapshot = save_snapshot(
            team_id,
            synthetic_outcome_snapshot(site_id="quarry-1", dataset_id=f"{team_id}-snap"),
        )
        model = train_global(
            [snapshot],
            team_id=team_id,
            model_type="fragmentation",
            model_id=model_id,
        )
        return save_learning(team_id, model)

    def test_other_tenant_does_not_see_or_promote_foreign_card(self):
        saved = self._saved(TEAM_A, model_id="alpha-reg")
        self.assertEqual(len(list_records(TEAM_A)), 1)
        self.assertEqual(list_records(TEAM_B), [])
        with self.assertRaises(RegistryNotFoundError):
            get_record(TEAM_B, "learning", saved.model_id)
        with self.assertRaises((RegistryNotFoundError, CrossTenantError, IsolationError)):
            promote(
                TEAM_B,
                "learning",
                saved.model_id,
                to_status="production",
                actor="intruder@other",
                confirm=True,
            )
        still = get_record(TEAM_A, "learning", saved.model_id)
        self.assertEqual(still.status, "candidate")
        self.assertEqual(still.team_id, TEAM_A)

    def test_empty_team_is_rejected(self):
        with self.assertRaises(IsolationError):
            list_records("")
        with self.assertRaises(IsolationError):
            get_record("  ", "learning", "any")
