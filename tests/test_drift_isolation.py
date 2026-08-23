"""BDX-021: drift reports stay inside the tenant that owns the model."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.datasets.persistence import save_snapshot
from intelligence.drift.monitor import DriftCheckError, check_production_model
from intelligence.drift.persistence import (
    acknowledge_alert,
    get_alert,
    get_report,
    list_alerts,
    list_reports,
)
from intelligence.learning.isolation import CrossTenantError, IsolationError
from intelligence.learning.persistence import save_model as save_learning
from intelligence.learning.training import train_global
from intelligence.registry.persistence import promote
from intelligence.registry.types import STATUS_PRODUCTION
from tests.outcome_fixtures import synthetic_outcome_snapshot
from tests.test_drift_engine import _shift_snapshot

TEAM_A = "drift-alpha"
TEAM_B = "drift-beta"


class DriftIsolationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _production(self, team_id: str, *, model_id: str, dataset_id: str):
        snapshot = save_snapshot(
            team_id,
            synthetic_outcome_snapshot(site_id="quarry-1", dataset_id=dataset_id),
        )
        model = save_learning(
            team_id,
            train_global(
                [snapshot],
                team_id=team_id,
                model_type="fragmentation",
                model_id=model_id,
            ),
        )
        promote(
            team_id,
            "learning",
            model.model_id,
            to_status=STATUS_PRODUCTION,
            actor=f"lead@{team_id}",
            confirm=True,
        )
        return model, snapshot

    def test_other_tenant_cannot_see_or_check_foreign_model(self):
        model, snapshot = self._production(TEAM_A, model_id="alpha-live", dataset_id="alpha-train")
        drifted = save_snapshot(TEAM_A, _shift_snapshot(snapshot, dataset_id="alpha-now"))
        report = check_production_model(
            TEAM_A,
            "learning",
            model.model_id,
            current_dataset_id=drifted.dataset_id,
        )
        self.assertEqual(report.team_id, TEAM_A)
        self.assertEqual(list_reports(TEAM_B), [])
        self.assertEqual(list_alerts(TEAM_B), [])
        with self.assertRaises((DriftCheckError, CrossTenantError)):
            check_production_model(
                TEAM_B,
                "learning",
                model.model_id,
                current_dataset_id=drifted.dataset_id,
            )
        with self.assertRaises((Exception,)):
            get_report(TEAM_B, report.report_id)
        if report.alerts:
            with self.assertRaises((Exception,)):
                get_alert(TEAM_B, report.alerts[0].alert_id)
            with self.assertRaises((CrossTenantError, Exception)):
                acknowledge_alert(TEAM_B, report.alerts[0].alert_id, actor="intruder@other")
            still = get_alert(TEAM_A, report.alerts[0].alert_id)
            self.assertFalse(still.acknowledged)
            self.assertFalse(still.auto_deployed)

    def test_empty_team_is_rejected(self):
        with self.assertRaises(IsolationError):
            list_reports("")
        with self.assertRaises(IsolationError):
            list_alerts("  ")

    def test_acknowledge_is_human_only_and_does_not_deploy(self):
        model, snapshot = self._production(TEAM_A, model_id="alpha-ack", dataset_id="ack-train")
        drifted = save_snapshot(TEAM_A, _shift_snapshot(snapshot, dataset_id="ack-now"))
        report = check_production_model(
            TEAM_A,
            "learning",
            model.model_id,
            current_dataset_id=drifted.dataset_id,
        )
        self.assertTrue(report.alerts)
        alert = report.alerts[0]
        from intelligence.drift.persistence import InvalidDriftError

        with self.assertRaises(InvalidDriftError):
            acknowledge_alert(TEAM_A, alert.alert_id, actor="auto")
        acked = acknowledge_alert(TEAM_A, alert.alert_id, actor="engineer@site")
        self.assertTrue(acked.acknowledged)
        self.assertEqual(acked.acknowledged_by, "engineer@site")
        self.assertFalse(acked.auto_deployed)
        self.assertFalse(acked.auto_retrained)
        self.assertTrue(acked.live_model_unchanged)
        from intelligence.registry.persistence import get_record

        live = get_record(TEAM_A, "learning", model.model_id)
        self.assertEqual(live.status, STATUS_PRODUCTION)
        self.assertEqual(live.checksum, report.model_checksum)
