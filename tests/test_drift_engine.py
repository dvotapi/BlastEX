"""BDX-021: feature / target / prediction drift vs the training snapshot."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.datasets.builder import DatasetSnapshot
from intelligence.datasets.persistence import save_snapshot
from intelligence.drift.extract import feature_series, target_series
from intelligence.drift.monitor import DriftCheckError, check_production_model, compare_windows
from intelligence.drift.statistics import compare_series, unit_from_name
from intelligence.drift.types import (
    KIND_FEATURE,
    KIND_PREDICTION,
    KIND_TARGET,
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    SEVERITY_ALERT,
    SEVERITY_OK,
)
from intelligence.learning.persistence import save_model as save_learning
from intelligence.learning.training import train_global
from intelligence.registry.persistence import get_record, promote
from intelligence.registry.types import STATUS_PRODUCTION
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_ID = "drift-engine-team"


def _shift_snapshot(snapshot: DatasetSnapshot, *, dataset_id: str, scale: float = 2.5) -> DatasetSnapshot:
    clone = DatasetSnapshot.from_dict(snapshot.to_dict())
    clone.dataset_id = dataset_id
    clone.dataset_version = snapshot.dataset_version + 1
    clone.name = f"{snapshot.name}-shifted"
    for sample in clone.samples:
        geo = sample.features.setdefault("GEOMETRY", {})
        if geo.get("mean_diameter_mm") is not None:
            geo["mean_diameter_mm"] = float(geo["mean_diameter_mm"]) * scale
        charge = sample.features.setdefault("CHARGING", {})
        if charge.get("mean_powder_factor_kg_m3") is not None:
            charge["mean_powder_factor_kg_m3"] = float(charge["mean_powder_factor_kg_m3"]) * scale
        frag = sample.targets.setdefault("FRAGMENTATION", {})
        if frag.get("x50_mm") is not None:
            frag["x50_mm"] = float(frag["x50_mm"]) * scale
        if frag.get("predicted_x50_mm") is not None:
            frag["predicted_x50_mm"] = float(frag["predicted_x50_mm"]) * scale
    return clone


class DriftEngineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _promoted_learning(self, *, dataset_id: str = "train-snap"):
        snapshot = save_snapshot(TEAM_ID, synthetic_outcome_snapshot(dataset_id=dataset_id, n=8))
        model = save_learning(
            TEAM_ID,
            train_global(
                [snapshot],
                team_id=TEAM_ID,
                model_type="fragmentation",
                model_id="learn-drift-1",
            ),
        )
        promote(
            TEAM_ID,
            "learning",
            model.model_id,
            to_status=STATUS_PRODUCTION,
            actor="lead@mine",
            confirm=True,
        )
        return get_record(TEAM_ID, "learning", model.model_id), snapshot

    def test_identical_windows_are_ok(self):
        snapshot = synthetic_outcome_snapshot(n=8)
        metrics = compare_windows([snapshot], [snapshot])
        self.assertTrue(metrics)
        self.assertTrue(all(item.severity == SEVERITY_OK for item in metrics))
        kinds = {item.kind for item in metrics}
        self.assertIn(KIND_FEATURE, kinds)
        self.assertIn(KIND_TARGET, kinds)
        roles = {item.role for item in metrics}
        self.assertIn(ROLE_DESIGNED, roles)
        self.assertIn(ROLE_EXECUTED, roles)
        self.assertIn(ROLE_MEASURED, roles)

    def test_feature_and_target_shift_raises_alerts(self):
        baseline = synthetic_outcome_snapshot(n=8, dataset_id="base")
        current = _shift_snapshot(baseline, dataset_id="now")
        metrics = compare_windows([baseline], [current])
        by_name = {item.name: item for item in metrics}
        diameter = by_name["GEOMETRY.mean_diameter_mm"]
        self.assertEqual(diameter.kind, KIND_FEATURE)
        self.assertEqual(diameter.role, ROLE_DESIGNED)
        self.assertEqual(diameter.unit, "mm")
        self.assertEqual(diameter.severity, SEVERITY_ALERT)
        x50 = by_name["FRAGMENTATION.x50_mm"]
        self.assertEqual(x50.kind, KIND_TARGET)
        self.assertEqual(x50.role, ROLE_MEASURED)
        self.assertEqual(x50.unit, "mm")
        self.assertEqual(x50.severity, SEVERITY_ALERT)

    def test_prediction_channel_uses_predicted_role(self):
        baseline = synthetic_outcome_snapshot(n=8, dataset_id="base")
        current = _shift_snapshot(baseline, dataset_id="now")
        metrics = compare_windows(
            [baseline],
            [current],
            baseline_scores={"prediction.x50_mm": [140.0 + i for i in range(8)]},
            current_scores={"prediction.x50_mm": [400.0 + i for i in range(8)]},
        )
        pred = next(item for item in metrics if item.kind == KIND_PREDICTION)
        self.assertEqual(pred.role, ROLE_PREDICTED)
        self.assertEqual(pred.unit, "mm")
        self.assertEqual(pred.severity, SEVERITY_ALERT)

    def test_measured_targets_ignore_predicted_columns(self):
        snapshot = synthetic_outcome_snapshot(n=8)
        measured = target_series([snapshot])
        self.assertIn("FRAGMENTATION.x50_mm", measured)
        self.assertNotIn("FRAGMENTATION.predicted_x50_mm", measured)
        features = feature_series([snapshot])
        self.assertEqual(features["EXECUTION.mean_collar_offset_m"]["role"], ROLE_EXECUTED)
        self.assertEqual(features["GEOMETRY.mean_diameter_mm"]["role"], ROLE_DESIGNED)

    def test_no_silent_unit_conversion(self):
        self.assertEqual(unit_from_name("FRAGMENTATION.x50_mm"), "mm")
        self.assertEqual(unit_from_name("FRAGMENTATION.x50_m"), "m")
        millimetres = compare_series(
            "x50_mm",
            [150.0] * 8,
            [150.0] * 8,
            kind=KIND_TARGET,
            role=ROLE_MEASURED,
            unit="mm",
        )
        self.assertIsNotNone(millimetres)
        self.assertEqual(millimetres.unit, "mm")
        self.assertAlmostEqual(millimetres.baseline_mean, 150.0)
        # 0.150 "metres" is not treated as 150 mm.
        self.assertNotAlmostEqual(millimetres.baseline_mean, 0.150)

    def test_check_requires_production_and_does_not_swap_live_model(self):
        card, snapshot = self._promoted_learning()
        drifted = save_snapshot(TEAM_ID, _shift_snapshot(snapshot, dataset_id="live-window"))
        report = check_production_model(
            TEAM_ID,
            "learning",
            card.model_id,
            current_dataset_id=drifted.dataset_id,
        )
        self.assertGreaterEqual(len(report.alerts), 1)
        self.assertFalse(report.auto_deployed)
        self.assertFalse(report.auto_retrained)
        self.assertTrue(report.live_model_unchanged)
        self.assertEqual(report.action, "alert_only")
        self.assertEqual(report.next_step, "human_promote_via_registry")
        self.assertEqual(report.training_dataset_ids, [snapshot.dataset_id])
        self.assertEqual(report.model_status, STATUS_PRODUCTION)
        after = get_record(TEAM_ID, "learning", card.model_id)
        self.assertEqual(after.status, STATUS_PRODUCTION)
        self.assertEqual(after.checksum, card.checksum)
        self.assertEqual(after.promoted_by, "lead@mine")

    def test_candidate_is_rejected(self):
        snapshot = save_snapshot(TEAM_ID, synthetic_outcome_snapshot(dataset_id="cand-snap"))
        model = save_learning(
            TEAM_ID,
            train_global(
                [snapshot],
                team_id=TEAM_ID,
                model_type="fragmentation",
                model_id="still-candidate",
            ),
        )
        with self.assertRaises(DriftCheckError):
            check_production_model(
                TEAM_ID,
                "learning",
                model.model_id,
                current_dataset_id=snapshot.dataset_id,
            )
        self.assertEqual(get_record(TEAM_ID, "learning", model.model_id).status, "candidate")

    def test_training_still_requires_immutable_snapshot(self):
        live = synthetic_outcome_snapshot(dataset_id="mutable")
        live.immutable = False
        with self.assertRaises(DriftCheckError):
            from intelligence.drift.monitor import _require_immutable

            _require_immutable(live)
