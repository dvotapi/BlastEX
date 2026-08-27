import copy
import unittest

from intelligence.outcomes.features import (
    feature_column_names,
    target_table,
    toe_probability_from_targets,
)
from intelligence.outcomes.prediction import apply_model
from intelligence.outcomes.training import train_from_snapshot
from intelligence.outcomes.types import (
    CLASS_FRAGMENTATION,
    CLASS_OVERSIZE,
    CLASS_TOE_RISK,
    CLASS_VIBRATION,
    MODEL_FRAGMENTATION,
    MODEL_OVERSIZE,
    MODEL_TOE_RISK,
    MODEL_VIBRATION,
    STATUS_CANDIDATE,
    normalize_model_type,
)
from tests.outcome_fixtures import synthetic_outcome_snapshot


class OutcomeTypeTests(unittest.TestCase):
    def test_class_name_aliases(self):
        self.assertEqual(normalize_model_type("FragmentationModel"), MODEL_FRAGMENTATION)
        self.assertEqual(normalize_model_type("VibrationModel"), MODEL_VIBRATION)
        self.assertEqual(normalize_model_type("OversizeModel"), MODEL_OVERSIZE)
        self.assertEqual(normalize_model_type("ToeRiskModel"), MODEL_TOE_RISK)

    def test_unknown_type_lists_specialised_models(self):
        with self.assertRaises(ValueError) as ctx:
            normalize_model_type("universal_net")
        self.assertIn(CLASS_FRAGMENTATION, str(ctx.exception))


class OutcomeFeatureTests(unittest.TestCase):
    def test_feature_columns_do_not_include_baseline(self):
        names = feature_column_names()
        self.assertNotIn("baseline", names)
        self.assertGreaterEqual(len(names), 16)

    def test_table_keeps_only_rows_with_measured_target(self):
        snapshot = synthetic_outcome_snapshot(n=8)
        snapshot.samples[0].targets["FRAGMENTATION"]["x50_mm"] = None
        table = target_table(snapshot, "fragmentation", "x50_mm")
        self.assertEqual(len(table.y), 7)
        self.assertEqual(len(table.feature_names), len(feature_column_names()))

    def test_toe_probability_from_leftover_height(self):
        self.assertAlmostEqual(
            toe_probability_from_targets({"BLAST": {"leftover_height_m": 0.4}}),
            0.4,
        )
        self.assertAlmostEqual(
            toe_probability_from_targets({"BLAST": {"leftover_height_m": 2.5}}),
            1.0,
        )
        self.assertAlmostEqual(
            toe_probability_from_targets({"BLAST": {"toe_condition": "minor"}}),
            0.35,
        )


class OutcomeTrainingTests(unittest.TestCase):
    def test_trained_fragmentation_model_has_metadata_and_candidate_status(self):
        snapshot = synthetic_outcome_snapshot(dataset_version=4)
        model = train_from_snapshot(snapshot, model_type="FragmentationModel", model_version=2)
        self.assertEqual(model.site_id, "quarry-1")
        self.assertEqual(model.model_type, MODEL_FRAGMENTATION)
        self.assertEqual(model.class_name, CLASS_FRAGMENTATION)
        self.assertEqual(model.model_version, 2)
        self.assertEqual(model.training_dataset_version, 4)
        self.assertEqual(model.training_dataset_id, "snap-outcomes")
        self.assertTrue(model.feature_schema_version)
        self.assertTrue(model.training_date)
        self.assertIn("mae", model.metrics)
        self.assertEqual(model.status, STATUS_CANDIDATE)
        self.assertEqual(model.algorithm, "random_forest")
        self.assertGreaterEqual(model.sample_count, 4)
        self.assertIn("x50_mm", model.estimators)
        self.assertIn("x80_mm", model.estimators)
        self.assertEqual(set(model.target_names), {"x50_mm", "x80_mm"})

    def test_all_four_specialised_types_train(self):
        snapshot = synthetic_outcome_snapshot()
        fragmentation = train_from_snapshot(snapshot, model_type="fragmentation")
        vibration = train_from_snapshot(snapshot, model_type="vibration")
        oversize = train_from_snapshot(snapshot, model_type="oversize")
        toe = train_from_snapshot(snapshot, model_type="toe_risk")
        self.assertEqual(fragmentation.class_name, CLASS_FRAGMENTATION)
        self.assertEqual(vibration.class_name, CLASS_VIBRATION)
        self.assertEqual(oversize.class_name, CLASS_OVERSIZE)
        self.assertEqual(toe.class_name, CLASS_TOE_RISK)
        self.assertEqual(oversize.primary_target, "oversize_pct")
        self.assertIn("max_ppv_mm_s", vibration.target_names)
        self.assertIn("toe_probability", toe.target_names)
        for model in (fragmentation, vibration, oversize, toe):
            self.assertEqual(model.status, STATUS_CANDIDATE)
            self.assertGreaterEqual(model.sample_count, 4)

    def test_too_few_samples_are_rejected(self):
        with self.assertRaises(ValueError):
            train_from_snapshot(synthetic_outcome_snapshot(n=2), model_type="oversize")

    def test_mutable_snapshot_is_rejected(self):
        snapshot = synthetic_outcome_snapshot()
        snapshot.immutable = False
        with self.assertRaises(ValueError):
            train_from_snapshot(snapshot, model_type="fragmentation")

    def test_site_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            train_from_snapshot(
                synthetic_outcome_snapshot(),
                model_type="fragmentation",
                site_id="other",
            )

    def test_extra_trees_algorithm(self):
        model = train_from_snapshot(
            synthetic_outcome_snapshot(),
            model_type="oversize",
            algorithm="extra_trees",
        )
        self.assertEqual(model.algorithm, "extra_trees")


class OutcomePredictionTests(unittest.TestCase):
    def test_point_prediction_exposes_version_and_does_not_mutate_features(self):
        snapshot = synthetic_outcome_snapshot(n=8)
        model = train_from_snapshot(snapshot, model_type="fragmentation", model_version=3)
        features = copy.deepcopy(snapshot.samples[-1].features)
        original = copy.deepcopy(features)
        prediction = apply_model(model, features=features)
        self.assertEqual(features, original)
        self.assertFalse(prediction.modifies_design)
        self.assertEqual(prediction.applied_as, "recommendation_overlay")
        self.assertEqual(prediction.model_version, 3)
        self.assertEqual(prediction.status, STATUS_CANDIDATE)
        self.assertTrue(prediction.prediction_applied)
        self.assertIn("provenance", prediction.to_dict())
        self.assertIn("x50_mm", prediction.predictions)
        self.assertIn("x80_mm", prediction.predictions)
        self.assertGreater(prediction.predictions["x50_mm"].value, 0)
        self.assertGreater(prediction.predictions["x80_mm"].value, prediction.predictions["x50_mm"].value)
        payload = prediction.to_dict()
        for key in ("prediction", "uncertainty", "confidence", "similarity_score", "applicability_warning"):
            self.assertIn(key, payload)
        self.assertEqual(payload["prediction"], prediction.predicted)
        self.assertLessEqual(payload["uncertainty"]["lower"], payload["prediction"])
        self.assertGreaterEqual(payload["uncertainty"]["upper"], payload["prediction"])

    def test_candidate_warning_is_present(self):
        model = train_from_snapshot(synthetic_outcome_snapshot(), model_type="oversize")
        prediction = apply_model(model, features=synthetic_outcome_snapshot().samples[0].features)
        self.assertTrue(any("candidate" in item for item in prediction.warnings))
        self.assertTrue(any("не изменяет" in item.lower() or "не утверждает" in item for item in prediction.warnings))

    def test_toe_risk_is_clamped_to_unit_interval(self):
        model = train_from_snapshot(synthetic_outcome_snapshot(), model_type="toe_risk")
        prediction = apply_model(model, features=synthetic_outcome_snapshot().samples[-1].features)
        value = prediction.predictions["toe_probability"].value
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 1.0)

    def test_oversize_is_clamped(self):
        model = train_from_snapshot(synthetic_outcome_snapshot(), model_type="oversize")
        prediction = apply_model(model, features=synthetic_outcome_snapshot().samples[0].features)
        value = prediction.predictions["oversize_pct"].value
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 100.0)


if __name__ == "__main__":
    unittest.main()
