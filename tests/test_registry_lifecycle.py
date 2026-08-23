"""BDX-020: human-gated transitions, checksum and dataset lineage."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.calibration.persistence import save_model as save_calibration
from intelligence.calibration.training import train_from_snapshot
from intelligence.datasets.persistence import save_snapshot
from intelligence.learning.persistence import save_model as save_learning
from intelligence.learning.training import train_global
from intelligence.outcomes.persistence import save_model as save_outcome
from intelligence.outcomes.training import train_from_snapshot as train_outcome
from intelligence.registry.lifecycle import InvalidPromotionError, plan_promotion
from intelligence.registry.persistence import get_record, list_records, promote
from intelligence.registry.types import (
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    STATUS_ARCHIVED,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    STATUS_RETIRED,
    STATUS_STAGING,
    allowed_transitions,
    effective_status,
    source_status_for,
)
from tests.calibration_fixtures import synthetic_snapshot
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_ID = "registry-team"


class RegistryLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calibration(self):
        snapshot = save_snapshot(TEAM_ID, synthetic_snapshot())
        model = train_from_snapshot(snapshot, model_type="kuzram_residual", model_id="cal-1")
        return save_calibration(TEAM_ID, model), snapshot

    def _outcome(self):
        snapshot = save_snapshot(TEAM_ID, synthetic_outcome_snapshot(dataset_id="out-snap"))
        model = train_outcome(snapshot, model_type="fragmentation", model_id="out-1")
        return save_outcome(TEAM_ID, model), snapshot

    def _learning(self):
        snapshot = save_snapshot(TEAM_ID, synthetic_outcome_snapshot(dataset_id="learn-snap"))
        model = train_global(
            [snapshot],
            team_id=TEAM_ID,
            model_type="fragmentation",
            model_id="learn-1",
        )
        return save_learning(TEAM_ID, model), snapshot

    def test_allowed_graph_is_candidate_to_staging_or_production_then_retired_or_archived(self):
        self.assertEqual(
            allowed_transitions(STATUS_CANDIDATE),
            [STATUS_STAGING, STATUS_PRODUCTION, STATUS_RETIRED, STATUS_ARCHIVED],
        )
        self.assertEqual(
            allowed_transitions(STATUS_STAGING),
            [STATUS_PRODUCTION, STATUS_RETIRED, STATUS_ARCHIVED],
        )
        self.assertEqual(allowed_transitions(STATUS_PRODUCTION), [STATUS_RETIRED, STATUS_ARCHIVED])
        self.assertEqual(allowed_transitions(STATUS_RETIRED), [STATUS_ARCHIVED])
        self.assertEqual(allowed_transitions(STATUS_ARCHIVED), [])

    def test_staging_is_never_source_production(self):
        self.assertEqual(source_status_for(STATUS_STAGING), STATUS_CANDIDATE)
        self.assertEqual(effective_status(STATUS_CANDIDATE, STATUS_STAGING), STATUS_STAGING)
        self.assertEqual(effective_status(STATUS_PRODUCTION, STATUS_STAGING), STATUS_PRODUCTION)

    def test_plan_promotion_requires_human_actor_and_confirm(self):
        with self.assertRaises(InvalidPromotionError):
            plan_promotion(
                from_status=STATUS_CANDIDATE,
                to_status=STATUS_PRODUCTION,
                actor="auto",
                confirm=True,
            )
        with self.assertRaises(InvalidPromotionError):
            plan_promotion(
                from_status=STATUS_CANDIDATE,
                to_status=STATUS_PRODUCTION,
                actor="engineer@site",
                confirm=False,
            )
        event = plan_promotion(
            from_status=STATUS_CANDIDATE,
            to_status=STATUS_STAGING,
            actor="engineer@site",
            confirm=True,
            note="review",
        )
        self.assertEqual(event.actor, "engineer@site")
        self.assertFalse(event.auto_deployed)
        self.assertTrue(event.confirm)

    def test_illegal_transition_is_rejected(self):
        with self.assertRaises(InvalidPromotionError):
            plan_promotion(
                from_status=STATUS_ARCHIVED,
                to_status=STATUS_PRODUCTION,
                actor="engineer@site",
                confirm=True,
            )
        with self.assertRaises(InvalidPromotionError):
            plan_promotion(
                from_status=STATUS_PRODUCTION,
                to_status=STATUS_STAGING,
                actor="engineer@site",
                confirm=True,
            )

    def test_catalog_wraps_existing_families_with_checksum_and_lineage(self):
        cal, cal_snap = self._calibration()
        out, out_snap = self._outcome()
        learned, learn_snap = self._learning()
        items = list_records(TEAM_ID)
        self.assertEqual(len(items), 3)
        families = {item.family for item in items}
        self.assertEqual(families, {"calibration", "outcomes", "learning"})
        for item in items:
            self.assertEqual(item.status, STATUS_CANDIDATE)
            self.assertTrue(item.checksum)
            self.assertTrue(item.lineage.training_dataset_id)
            self.assertGreaterEqual(item.lineage.training_dataset_version, 1)
            self.assertEqual(item.data_roles["training_targets"], ROLE_MEASURED)
            self.assertEqual(item.data_roles["prediction"], ROLE_PREDICTED)
            self.assertEqual(item.data_roles["design"], ROLE_DESIGNED)
            self.assertEqual(item.data_roles["execution"], ROLE_EXECUTED)
            self.assertFalse(item.auto_deployed)
            self.assertEqual(item.promoted_by, "")
        cal_card = get_record(TEAM_ID, "calibration", cal.model_id)
        self.assertEqual(cal_card.checksum, cal.artifact_sha256)
        self.assertEqual(cal_card.lineage.training_dataset_id, cal_snap.dataset_id)
        self.assertEqual(cal_card.lineage.training_dataset_version, cal_snap.dataset_version)
        out_card = get_record(TEAM_ID, "outcomes", out.model_id)
        self.assertEqual(out_card.checksum, out.artifact_sha256)
        self.assertEqual(out_card.lineage.training_dataset_id, out_snap.dataset_id)
        learn_card = get_record(TEAM_ID, "learning", learned.model_id)
        self.assertEqual(learn_card.checksum, learned.artifact_sha256)
        self.assertIn(learn_snap.dataset_id, learn_card.lineage.training_dataset_ids)

    def test_human_promotion_candidate_staging_production_retired_archived(self):
        model, _snapshot = self._learning()
        staged = promote(
            TEAM_ID,
            "learning",
            model.model_id,
            to_status=STATUS_STAGING,
            actor="anna@mine",
            confirm=True,
            note="hold for review",
        )
        self.assertEqual(staged.status, STATUS_STAGING)
        self.assertEqual(staged.source_status, STATUS_CANDIDATE)
        self.assertEqual(staged.promoted_by, "anna@mine")
        self.assertTrue(staged.promoted_at)
        self.assertEqual(staged.transitions[-1].note, "hold for review")
        self.assertFalse(staged.auto_deployed)

        production = promote(
            TEAM_ID,
            "learning",
            model.model_id,
            to_status=STATUS_PRODUCTION,
            actor="anna@mine",
            confirm=True,
        )
        self.assertEqual(production.status, STATUS_PRODUCTION)
        self.assertEqual(production.source_status, STATUS_PRODUCTION)

        retired = promote(
            TEAM_ID,
            "learning",
            model.model_id,
            to_status=STATUS_RETIRED,
            actor="anna@mine",
            confirm=True,
        )
        self.assertEqual(retired.status, STATUS_RETIRED)
        archived = promote(
            TEAM_ID,
            "learning",
            model.model_id,
            to_status=STATUS_ARCHIVED,
            actor="anna@mine",
            confirm=True,
        )
        self.assertEqual(archived.status, STATUS_ARCHIVED)
        self.assertEqual(archived.source_status, STATUS_RETIRED)
        self.assertEqual(len(archived.transitions), 4)

    def test_training_does_not_auto_promote(self):
        model, _snapshot = self._calibration()
        card = get_record(TEAM_ID, "calibration", model.model_id)
        self.assertEqual(card.status, STATUS_CANDIDATE)
        self.assertEqual(card.promoted_by, "")
        self.assertEqual(card.transitions, [])
        with self.assertRaises(InvalidPromotionError):
            promote(
                TEAM_ID,
                "calibration",
                model.model_id,
                to_status=STATUS_PRODUCTION,
                actor="system",
                confirm=True,
            )
        still = get_record(TEAM_ID, "calibration", model.model_id)
        self.assertEqual(still.status, STATUS_CANDIDATE)

    def test_new_production_retires_previous_of_same_slot(self):
        first, _ = self._outcome()
        snapshot = save_snapshot(TEAM_ID, synthetic_outcome_snapshot(n=8, dataset_id="out-snap-2"))
        second = save_outcome(
            TEAM_ID,
            train_outcome(snapshot, model_type="fragmentation", model_id="out-2", model_version=2),
        )
        promote(
            TEAM_ID, "outcomes", first.model_id,
            to_status=STATUS_PRODUCTION, actor="lead@mine", confirm=True,
        )
        promote(
            TEAM_ID, "outcomes", second.model_id,
            to_status=STATUS_PRODUCTION, actor="lead@mine", confirm=True,
        )
        self.assertEqual(get_record(TEAM_ID, "outcomes", first.model_id).status, STATUS_RETIRED)
        self.assertEqual(get_record(TEAM_ID, "outcomes", second.model_id).status, STATUS_PRODUCTION)
