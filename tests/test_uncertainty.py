"""BDX-014: intervals, confidence, similarity and out-of-domain flags."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence.calibration.persistence import load_model, save_model
from intelligence.calibration.prediction import apply_residual
from intelligence.calibration.training import train_from_snapshot
from intelligence.outcomes.prediction import apply_model
from intelligence.outcomes.training import train_from_snapshot as train_outcome
from intelligence.uncertainty.domain import check_domain, compute_feature_ranges, format_applicability_warning
from intelligence.uncertainty.types import FeatureRange
from tests.calibration_fixtures import _features as cal_features
from tests.calibration_fixtures import synthetic_snapshot
from tests.outcome_fixtures import _features as out_features
from tests.outcome_fixtures import synthetic_outcome_snapshot

TEAM_ID = "uncert-team"
DIAMETER_KEY = "GEOMETRY.mean_diameter_mm"


def _set_diameter(features: dict, diameter: float) -> dict:
    payload = copy.deepcopy(features)
    payload.setdefault("GEOMETRY", {})
    payload["GEOMETRY"]["mean_diameter_mm"] = float(diameter)
    return payload


def _snapshot_diameter_range(kind: str = "outcome", n: int = 8, dmin: float = 152.0, dmax: float = 229.0):
    diameters = [dmin + (dmax - dmin) * index / (n - 1) for index in range(n)]
    if kind == "calibration":
        snapshot = synthetic_snapshot(n=n)
        for index, sample in enumerate(snapshot.samples):
            sample.features = _set_diameter(cal_features(index, ucs=80.0 + index * 10.0, powder=0.6 + index * 0.04), diameters[index])
        return snapshot
    snapshot = synthetic_outcome_snapshot(n=n)
    for index, sample in enumerate(snapshot.samples):
        sample.features = _set_diameter(out_features(index, ucs=80.0 + index * 10.0, powder=0.6 + index * 0.04), diameters[index])
    return snapshot


def _required_fields(payload: dict) -> None:
    for key in ("prediction", "uncertainty", "confidence", "similarity_score", "applicability_warning"):
        if key not in payload:
            raise AssertionError(f"missing {key}")


class DomainCheckTests(unittest.TestCase):
    def test_diameter_311_is_extrapolated_when_history_is_152_229(self):
        ranges = {
            DIAMETER_KEY: FeatureRange(name=DIAMETER_KEY, min=152.0, max=229.0, mean=190.0, std=25.0),
        }
        inside = check_domain([180.0], [DIAMETER_KEY], ranges)
        outside = check_domain([311.0], [DIAMETER_KEY], ranges)
        self.assertTrue(inside.in_domain)
        self.assertFalse(outside.in_domain)
        self.assertEqual(outside.violations[0].feature, DIAMETER_KEY)
        warning = format_applicability_warning(outside)
        self.assertIn("311", warning)
        self.assertIn("152", warning)
        self.assertIn("229", warning)
        self.assertIn("диаметр", warning)
        self.assertIn("вне области применимости", warning)
        self.assertEqual(format_applicability_warning(inside), "")

    def test_constant_training_diameter_still_flags_311(self):
        ranges = compute_feature_ranges([[152.0], [152.0], [152.0]], [DIAMETER_KEY])
        self.assertAlmostEqual(ranges[DIAMETER_KEY].min, 152.0)
        self.assertAlmostEqual(ranges[DIAMETER_KEY].max, 152.0)
        self.assertTrue(check_domain([152.0], [DIAMETER_KEY], ranges).in_domain)
        self.assertFalse(check_domain([311.0], [DIAMETER_KEY], ranges).in_domain)


class OutcomeUncertaintyTests(unittest.TestCase):
    def test_in_domain_vs_extrapolated_diameter(self):
        snapshot = _snapshot_diameter_range("outcome")
        model = train_outcome(snapshot, model_type="fragmentation")
        self.assertIn(DIAMETER_KEY, model.feature_ranges)
        self.assertAlmostEqual(model.feature_ranges[DIAMETER_KEY]["min"], 152.0)
        self.assertAlmostEqual(model.feature_ranges[DIAMETER_KEY]["max"], 229.0)
        self.assertTrue(model.training_matrix)

        in_features = snapshot.samples[3].features
        ood_features = _set_diameter(in_features, 311.0)
        inside = apply_model(model, features=in_features)
        outside = apply_model(model, features=ood_features)

        _required_fields(inside.to_dict())
        _required_fields(outside.to_dict())
        self.assertTrue(inside.in_domain)
        self.assertEqual(inside.applicability_warning, "")
        self.assertIn(inside.confidence, {"high", "medium"})
        self.assertGreaterEqual(inside.comparable_count, 1)
        self.assertGreater(inside.similarity_score, 0.5)
        self.assertLessEqual(inside.uncertainty["lower"], inside.prediction)
        self.assertGreaterEqual(inside.uncertainty["upper"], inside.prediction)

        self.assertFalse(outside.in_domain)
        self.assertIn("311", outside.applicability_warning)
        self.assertIn("диаметр", outside.applicability_warning)
        self.assertIn("152", outside.applicability_warning)
        self.assertIn("229", outside.applicability_warning)
        self.assertEqual(outside.confidence, "low")
        self.assertLess(outside.similarity_score, inside.similarity_score)
        self.assertIn(DIAMETER_KEY, outside.extrapolated_features)
        inside_width = inside.uncertainty["upper"] - inside.uncertainty["lower"]
        outside_width = outside.uncertainty["upper"] - outside.uncertainty["lower"]
        self.assertGreater(outside_width, inside_width)
        self.assertLessEqual(outside.uncertainty["lower"], outside.prediction)
        self.assertGreaterEqual(outside.uncertainty["upper"], outside.prediction)
        self.assertIn("x50_mm", inside.predictions)
        self.assertTrue(inside.predictions["x50_mm"].uncertainty)
        self.assertTrue(outside.warnings[0])

    def test_ucs_extrapolation_is_flagged(self):
        snapshot = synthetic_outcome_snapshot(n=8)
        model = train_outcome(snapshot, model_type="oversize")
        features = copy.deepcopy(snapshot.samples[0].features)
        features["GEOLOGY"]["mean_ucs_mpa"] = 400.0
        prediction = apply_model(model, features=features)
        self.assertFalse(prediction.in_domain)
        self.assertIn("UCS", prediction.applicability_warning)
        self.assertEqual(prediction.confidence, "low")


class CalibrationUncertaintyTests(unittest.TestCase):
    def test_in_domain_vs_extrapolated_diameter(self):
        snapshot = _snapshot_diameter_range("calibration")
        model = train_from_snapshot(snapshot, model_type="kuzram_residual")
        self.assertAlmostEqual(model.feature_ranges[DIAMETER_KEY]["min"], 152.0)
        self.assertAlmostEqual(model.feature_ranges[DIAMETER_KEY]["max"], 229.0)

        in_features = snapshot.samples[2].features
        ood_features = _set_diameter(in_features, 311.0)
        inside = apply_residual(model, features=in_features, baseline=150.0)
        outside = apply_residual(model, features=ood_features, baseline=150.0)

        _required_fields(inside.to_dict())
        _required_fields(outside.to_dict())
        self.assertTrue(inside.in_domain)
        self.assertEqual(inside.applicability_warning, "")
        self.assertAlmostEqual(inside.prediction, inside.calibrated)
        self.assertFalse(outside.in_domain)
        self.assertEqual(outside.confidence, "low")
        self.assertIn("311", outside.applicability_warning)
        self.assertGreater(
            outside.uncertainty["upper"] - outside.uncertainty["lower"],
            inside.uncertainty["upper"] - inside.uncertainty["lower"],
        )


class UncertaintyPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_saved_model_keeps_feature_ranges_for_domain_check(self):
        snapshot = _snapshot_diameter_range("calibration")
        model = train_from_snapshot(snapshot, model_type="kuzram_residual", model_id="u1")
        saved = save_model(TEAM_ID, model)
        loaded = load_model(TEAM_ID, saved.model_id)
        self.assertAlmostEqual(loaded.feature_ranges[DIAMETER_KEY]["min"], 152.0)
        self.assertEqual(len(loaded.training_matrix), len(snapshot.samples))
        outside = apply_residual(
            loaded,
            features=_set_diameter(snapshot.samples[0].features, 311.0),
            baseline=150.0,
        )
        self.assertFalse(outside.in_domain)
        self.assertIn("диаметр", outside.applicability_warning)


if __name__ == "__main__":
    unittest.main()
