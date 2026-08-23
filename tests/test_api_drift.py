"""BDX-021: drift API stays alert-only and does not auto-deploy."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import DriftIsolationError, DriftNotFoundError, InvalidDriftError
from api.schemas.drift import DriftAcknowledgeRequest, DriftCheckRequest
from api.schemas.learning import LearningGlobalTrainRequest
from api.schemas.registry import RegistryPromoteRequest
from api.services import drift_service, learning_service, registry_service
from intelligence.datasets.persistence import save_snapshot
from tests.outcome_fixtures import synthetic_outcome_snapshot
from tests.test_drift_engine import _shift_snapshot

TEAM_ID = "api-drift-team"
OTHER_TEAM = "api-drift-other"


class DriftApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _production(self, team_id: str = TEAM_ID):
        snapshot = save_snapshot(team_id, synthetic_outcome_snapshot(dataset_id=f"{team_id}-train"))
        trained = learning_service.train_global_model(
            team_id,
            LearningGlobalTrainRequest(dataset_ids=[snapshot.dataset_id], model_type="fragmentation"),
        )
        production = registry_service.promote_registry_model(
            team_id,
            "learning",
            trained.model_id,
            RegistryPromoteRequest(to_status="production", confirm=True),
            actor="lead@mine",
        )
        return production, snapshot

    def test_check_emits_alerts_without_swapping_live_model(self):
        production, snapshot = self._production()
        current = save_snapshot(TEAM_ID, _shift_snapshot(snapshot, dataset_id="api-now"))
        report = drift_service.run_check(
            TEAM_ID,
            DriftCheckRequest(
                family="learning",
                model_id=production.model_id,
                current_dataset_id=current.dataset_id,
            ),
        )
        self.assertEqual(report.model_id, production.model_id)
        self.assertEqual(report.model_status, "production")
        self.assertFalse(report.auto_deployed)
        self.assertFalse(report.auto_retrained)
        self.assertTrue(report.live_model_unchanged)
        self.assertEqual(report.action, "alert_only")
        self.assertEqual(report.next_step, "human_promote_via_registry")
        self.assertGreaterEqual(len(report.alerts), 1)
        self.assertIn("measured", report.data_roles.values())
        self.assertIn("predicted", report.data_roles.values())
        self.assertIn("designed", report.data_roles.values())
        self.assertIn("executed", report.data_roles.values())

        listed = drift_service.list_drift_reports(TEAM_ID, family="learning")
        self.assertEqual(len(listed.items), 1)
        self.assertFalse(listed.auto_deployed)
        loaded = drift_service.get_drift_report(TEAM_ID, report.report_id)
        self.assertEqual(loaded.report_id, report.report_id)

        alerts = drift_service.list_drift_alerts(TEAM_ID)
        self.assertGreaterEqual(len(alerts.items), 1)
        acked = drift_service.acknowledge_drift_alert(
            TEAM_ID,
            alerts.items[0].alert_id,
            DriftAcknowledgeRequest(confirm=True),
            actor="engineer@site",
        )
        self.assertTrue(acked.acknowledged)
        self.assertFalse(acked.auto_deployed)

        still = registry_service.get_registry_model(TEAM_ID, "learning", production.model_id)
        self.assertEqual(still.status, "production")
        self.assertEqual(still.checksum, production.checksum)

    def test_candidate_and_missing_confirm_are_rejected(self):
        snapshot = save_snapshot(TEAM_ID, synthetic_outcome_snapshot(dataset_id="api-cand"))
        trained = learning_service.train_global_model(
            TEAM_ID,
            LearningGlobalTrainRequest(dataset_ids=[snapshot.dataset_id], model_type="fragmentation"),
        )
        with self.assertRaises(InvalidDriftError):
            drift_service.run_check(
                TEAM_ID,
                DriftCheckRequest(
                    family="learning",
                    model_id=trained.model_id,
                    current_dataset_id=snapshot.dataset_id,
                ),
            )
        still = registry_service.get_registry_model(TEAM_ID, "learning", trained.model_id)
        self.assertEqual(still.status, "candidate")

    def test_cross_tenant_and_unknown(self):
        production, snapshot = self._production()
        current = save_snapshot(TEAM_ID, _shift_snapshot(snapshot, dataset_id="api-iso"))
        report = drift_service.run_check(
            TEAM_ID,
            DriftCheckRequest(
                family="learning",
                model_id=production.model_id,
                current_dataset_id=current.dataset_id,
            ),
        )
        other = drift_service.list_drift_reports(OTHER_TEAM)
        self.assertEqual(other.items, [])
        with self.assertRaises((DriftNotFoundError, DriftIsolationError, InvalidDriftError)):
            drift_service.get_drift_report(OTHER_TEAM, report.report_id)
        with self.assertRaises((DriftNotFoundError, DriftIsolationError, InvalidDriftError)):
            drift_service.run_check(
                OTHER_TEAM,
                DriftCheckRequest(
                    family="learning",
                    model_id=production.model_id,
                    current_dataset_id=current.dataset_id,
                ),
            )

    def test_meta_lists_channels_and_forbids_auto_deploy(self):
        meta = drift_service.catalog_meta()
        names = [item.name for item in meta.kinds]
        self.assertEqual(names, ["feature", "target", "prediction"])
        self.assertFalse(meta.auto_deployed)
        self.assertFalse(meta.auto_retrained)
        self.assertEqual(meta.action, "alert_only")
        self.assertEqual(meta.data_roles["targets"], "measured")
        self.assertEqual(meta.data_roles["predictions"], "predicted")
