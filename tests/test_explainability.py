"""BDX-015: feature importance, SHAP-style drivers and recommendation deltas."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.tree import DecisionTreeRegressor

from api.schemas.calibration import CalibrationPredictRequest, CalibrationTrainRequest
from api.schemas.outcomes import OutcomePredictRequest, OutcomeTrainRequest
from api.services import calibration_service, outcome_service
from intelligence.calibration.prediction import apply_residual, baseline_without_model
from intelligence.calibration.training import train_from_snapshot
from intelligence.datasets.builder import DatasetSnapshot, TrainingSample
from intelligence.datasets.features import FEATURE_SCHEMA_VERSION
from intelligence.datasets.persistence import save_snapshot
from intelligence.datasets.validation import SampleValidation
from intelligence.explainability.labels import feature_label_en, format_expected_delta
from intelligence.explainability.shap_values import local_shap_values, tree_path_contributions
from intelligence.explainability.types import METHOD_NONE, METHOD_TREE_PATH, empty_explanation
from intelligence.outcomes.prediction import apply_model, empty_prediction
from intelligence.outcomes.training import train_from_snapshot as train_outcome
from tests.calibration_fixtures import synthetic_snapshot
from tests.outcome_fixtures import synthetic_outcome_snapshot

BURDEN = "GEOMETRY.mean_burden_m"
POWDER = "CHARGING.mean_powder_factor_kg_m3"
UCS = "GEOLOGY.mean_ucs_mpa"


def _base_features(index: int, *, burden: float, powder: float, ucs: float) -> dict:
    return {
        "SITE": {"site_id": "quarry-1", "design_id": f"blast-{index}"},
        "GEOLOGY": {
            "mean_density_kg_m3": 2700.0,
            "mean_ucs_mpa": ucs,
            "mean_rqd_pct": 55.0,
        },
        "GEOMETRY": {
            "mean_spacing_m": 5.0,
            "mean_burden_m": burden,
            "mean_diameter_mm": 165.0,
            "mean_depth_m": 12.0,
            "mean_subdrill_m": 1.0,
        },
        "CHARGING": {
            "mean_charge_kg": 90.0,
            "mean_powder_factor_kg_m3": powder,
            "mean_stemming_m": 2.4,
        },
        "TIMING": {"mean_delay_ms": 25.0},
        "EXECUTION": {"mean_collar_offset_m": 0.15, "fired_coverage": 1.0},
        "ENVIRONMENT": {
            "wet_hole_fraction": 0.1,
            "nearest_receptor_distance_m": 90.0,
            "vibration_model_k": 500.0,
            "vibration_model_n": 1.6,
        },
    }


def explained_outcome_snapshot(*, n: int = 27, site_id: str = "quarry-1") -> DatasetSnapshot:
    samples: list[TrainingSample] = []
    index = 0
    for burden in (3.0, 4.0, 5.2):
        for powder in (0.40, 0.60, 0.85):
            for ucs in (70.0, 100.0, 130.0):
                x50 = 45.0 * burden - 110.0 * powder + 0.9 * ucs + 10.0
                samples.append(
                    TrainingSample(
                        source_blast_id=f"blast-{index}",
                        site_id=site_id,
                        feature_schema_version=FEATURE_SCHEMA_VERSION,
                        features=_base_features(index, burden=burden, powder=powder, ucs=ucs),
                        targets={
                            "FRAGMENTATION": {
                                "x50_mm": x50,
                                "x80_mm": x50 * 1.8,
                                "oversize_pct": max(0.5, 2.0 * burden - 4.0 * powder),
                            },
                            "VIBRATION": {
                                "ppv_mm_s": 3.0 + 0.4 * burden,
                                "max_ppv_mm_s": 3.0 + 0.4 * burden,
                                "frequency_hz": 12.0,
                            },
                            "BLAST": {"leftover_height_m": 0.05 * burden, "toe_condition": "minor"},
                            "PERFORMANCE": {"leftover_height_m": 0.05 * burden},
                        },
                        provenance={"source_blast_id": f"blast-{index}", "site_id": site_id},
                        validation=SampleValidation(
                            ok=True,
                            closed=True,
                            complete_target_groups=["FRAGMENTATION", "VIBRATION", "BLAST"],
                        ),
                    )
                )
                index += 1
                if index >= n:
                    break
            if index >= n:
                break
        if index >= n:
            break
    return DatasetSnapshot(
        dataset_id="snap-explain",
        dataset_version=1,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        source_blast_ids=[sample.source_blast_id for sample in samples],
        created_at="2024-06-04T00:00:00+00:00",
        site_id=site_id,
        name="explained-outcomes",
        samples=samples,
        immutable=True,
    )


def explained_calibration_snapshot(*, n: int = 27, site_id: str = "quarry-1") -> DatasetSnapshot:
    samples: list[TrainingSample] = []
    index = 0
    for burden in (3.0, 4.0, 5.2):
        for powder in (0.45, 0.60, 0.80):
            for ucs in (70.0, 95.0, 120.0):
                baseline = 150.0
                residual = 22.0 * (burden - 4.0) - 50.0 * (powder - 0.6) + 0.4 * (ucs - 90.0)
                samples.append(
                    TrainingSample(
                        source_blast_id=f"blast-{index}",
                        site_id=site_id,
                        feature_schema_version=FEATURE_SCHEMA_VERSION,
                        features=_base_features(index, burden=burden, powder=powder, ucs=ucs),
                        targets={
                            "FRAGMENTATION": {
                                "x50_mm": baseline + residual,
                                "predicted_x50_mm": baseline,
                                "oversize_pct": 4.0,
                                "predicted_oversize_pct": 4.0,
                            },
                            "VIBRATION": {
                                "ppv_mm_s": 5.0,
                                "max_ppv_mm_s": 5.0,
                                "predicted_max_ppv_mm_s": 5.0,
                            },
                        },
                        provenance={"source_blast_id": f"blast-{index}", "site_id": site_id},
                        validation=SampleValidation(
                            ok=True,
                            closed=True,
                            complete_target_groups=["FRAGMENTATION", "VIBRATION"],
                        ),
                    )
                )
                index += 1
                if index >= n:
                    break
            if index >= n:
                break
        if index >= n:
            break
    return DatasetSnapshot(
        dataset_id="snap-explain-cal",
        dataset_version=1,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        source_blast_ids=[sample.source_blast_id for sample in samples],
        created_at="2024-06-04T00:00:00+00:00",
        site_id=site_id,
        name="explained-calibration",
        samples=samples,
        immutable=True,
    )


class TreePathShapTests(unittest.TestCase):
    def test_path_values_sum_to_prediction_minus_expected(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(40, 3))
        y = 2.0 * X[:, 0] - 1.5 * X[:, 1] + 0.5 * X[:, 2]
        tree = DecisionTreeRegressor(max_depth=4, random_state=0)
        tree.fit(X, y)
        vector = X[3]
        contrib, expected, reconstructed = tree_path_contributions(tree, vector)
        pred = float(tree.predict(vector.reshape(1, -1))[0])
        self.assertAlmostEqual(reconstructed, pred, places=6)
        self.assertAlmostEqual(expected + float(np.sum(contrib)), pred, places=6)

    def test_forest_local_shap_uses_tree_path_method(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(60, 4))
        y = 3.0 * X[:, 0] + 0.1 * X[:, 1]
        forest = RandomForestRegressor(n_estimators=12, max_depth=4, random_state=0)
        forest.fit(X, y)
        contrib, expected, method = local_shap_values(forest, X[0], training_matrix=X.tolist())
        pred = float(forest.predict(X[0].reshape(1, -1))[0])
        self.assertEqual(method, METHOD_TREE_PATH)
        self.assertAlmostEqual(expected + float(np.sum(contrib)), pred, places=5)


class ExplainEstimatorTests(unittest.TestCase):
    def test_empty_without_estimator(self):
        payload = empty_explanation(target_name="x50_mm", target_label="X50", unit="mm")
        self.assertEqual(payload.method, METHOD_NONE)
        self.assertEqual(payload.drivers, [])
        self.assertEqual(payload.to_dict()["recommendations"], [])

    def test_english_burden_label(self):
        self.assertEqual(feature_label_en(BURDEN), "Burden")
        self.assertEqual(feature_label_en(POWDER), "Powder Factor")
        self.assertEqual(feature_label_en(UCS), "UCS")
        self.assertIn("−34", format_expected_delta(-34.0, "mm"))


class OutcomeExplainabilityTests(unittest.TestCase):
    def test_x50_drivers_include_burden_powder_ucs(self):
        snapshot = explained_outcome_snapshot()
        model = train_outcome(snapshot, model_type="fragmentation")
        features = snapshot.samples[-1].features
        prediction = apply_model(model, features=features)
        payload = prediction.to_dict()
        self.assertIn("explanation", payload)
        explanation = payload["explanation"]
        self.assertEqual(explanation["method"], METHOD_TREE_PATH)
        self.assertEqual(explanation["target_label"], "X50")
        names = [item["feature"] for item in explanation["drivers"]]
        labels = [item["label"] for item in explanation["drivers"]]
        self.assertTrue({BURDEN, POWDER, UCS} & set(names))
        self.assertTrue({"ЛНС", "удельный расход", "UCS"} & set(labels))
        self.assertGreater(sum(item["share_pct"] for item in explanation["drivers"]), 50)
        self.assertIn("Основные драйверы X50", explanation["summary"])
        self.assertIn("%", explanation["summary"])
        x50 = payload["predictions"]["x50_mm"]["explanation"]
        self.assertEqual(x50["drivers"][0]["feature"], explanation["drivers"][0]["feature"])

    def test_reducing_burden_lowers_expected_x50(self):
        snapshot = explained_outcome_snapshot()
        model = train_outcome(snapshot, model_type="fragmentation")
        features = snapshot.samples[-2].features
        prediction = apply_model(model, features=features)
        hints = prediction.explanation.recommendations
        self.assertTrue(hints)
        burden_hint = next((item for item in hints if item.feature == BURDEN), None)
        self.assertIsNotNone(burden_hint)
        assert burden_hint is not None
        self.assertEqual(burden_hint.action, "reduce")
        self.assertLess(burden_hint.delta, 0)
        self.assertIn("ЛНС", burden_hint.summary)
        self.assertIn("X50", burden_hint.summary)
        self.assertIn("ожидаемый", burden_hint.summary)

    def test_empty_prediction_has_blank_explanation(self):
        payload = empty_prediction(model_type="fragmentation").to_dict()
        self.assertEqual(payload["explanation"]["method"], METHOD_NONE)
        self.assertEqual(payload["explanation"]["drivers"], [])


class CalibrationExplainabilityTests(unittest.TestCase):
    def test_calibrated_overlay_exposes_drivers_and_deltas(self):
        snapshot = explained_calibration_snapshot()
        model = train_from_snapshot(snapshot, model_type="kuzram_residual")
        prediction = apply_residual(
            model,
            features=snapshot.samples[-1].features,
            baseline=150.0,
        )
        payload = prediction.to_dict()
        explanation = payload["explanation"]
        self.assertEqual(explanation["method"], METHOD_TREE_PATH)
        self.assertEqual(explanation["target_label"], "X50")
        self.assertTrue(explanation["drivers"])
        names = {item["feature"] for item in explanation["drivers"]}
        self.assertTrue({BURDEN, POWDER, UCS} & names)
        burden_hint = next(
            (item for item in explanation["recommendations"] if item["feature"] == BURDEN),
            None,
        )
        self.assertIsNotNone(burden_hint)
        assert burden_hint is not None
        self.assertEqual(burden_hint["action"], "reduce")
        self.assertLess(burden_hint["delta"], 0)
        self.assertIn("ЛНС", burden_hint["summary"])

    def test_baseline_without_model_has_blank_explanation(self):
        payload = baseline_without_model(
            baseline=150.0,
            model_type="kuzram_residual",
            site_id="quarry-1",
        ).to_dict()
        self.assertEqual(payload["explanation"]["method"], METHOD_NONE)


class ExplainabilityApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_outcome_predict_schema_includes_drivers(self):
        snapshot = save_snapshot("explain-team", explained_outcome_snapshot())
        trained = outcome_service.train_outcome(
            "explain-team",
            OutcomeTrainRequest(
                dataset_id=snapshot.dataset_id,
                model_type="fragmentation",
            ),
        )
        prediction = outcome_service.predict_outcome(
            "explain-team",
            OutcomePredictRequest(
                model_type="fragmentation",
                model_id=trained.model_id,
                site_id="quarry-1",
                features=snapshot.samples[-1].features,
            ),
        )
        self.assertTrue(prediction.explanation.drivers)
        self.assertIn(prediction.explanation.method, {METHOD_TREE_PATH, "permutation"})
        self.assertTrue(prediction.predictions["x50_mm"].explanation.drivers)
        shares = [item.share_pct for item in prediction.explanation.drivers]
        self.assertGreater(max(shares), 10)

    def test_calibration_predict_schema_includes_explanation(self):
        snapshot = save_snapshot("explain-team-c", explained_calibration_snapshot())
        trained = calibration_service.train_calibration(
            "explain-team-c",
            CalibrationTrainRequest(dataset_id=snapshot.dataset_id, model_type="kuzram_residual"),
        )
        prediction = calibration_service.predict_calibration(
            "explain-team-c",
            CalibrationPredictRequest(
                model_type="kuzram_residual",
                model_id=trained.model_id,
                site_id="quarry-1",
                baseline=150.0,
                features=snapshot.samples[-1].features,
            ),
        )
        self.assertTrue(prediction.calibration_applied)
        self.assertTrue(prediction.explanation.drivers)
        self.assertTrue(prediction.explanation.summary)


class ExistingSnapshotStillExplains(unittest.TestCase):
    def test_synthetic_outcome_snapshot_returns_explanation_fields(self):
        snapshot = synthetic_outcome_snapshot()
        model = train_outcome(snapshot, model_type="fragmentation")
        prediction = apply_model(model, features=snapshot.samples[0].features)
        payload = prediction.to_dict()
        self.assertIn("explanation", payload)
        self.assertIn("drivers", payload["explanation"])
        self.assertIn("recommendations", payload["explanation"])

    def test_synthetic_calibration_snapshot_returns_explanation_fields(self):
        snapshot = synthetic_snapshot()
        model = train_from_snapshot(snapshot, model_type="kuzram_residual")
        prediction = apply_residual(model, features=snapshot.samples[0].features, baseline=150.0)
        self.assertTrue(prediction.explanation.drivers or prediction.explanation.method != METHOD_NONE)


if __name__ == "__main__":
    unittest.main()
