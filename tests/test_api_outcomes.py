import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidOutcomeError
from api.schemas.outcomes import (
    OutcomePredictAllRequest,
    OutcomePredictRequest,
    OutcomeStatusRequest,
    OutcomeTrainRequest,
)
from api.services import outcome_service
from design.persistence import save_design
from intelligence.datasets.builder import build_snapshot
from intelligence.datasets.persistence import save_snapshot
from tests.dataset_fixtures import closed_design
from tests.outcome_fixtures import synthetic_outcome_snapshot, varied_closed_outcome_designs

TEAM_ID = "api-out-team"


class OutcomeApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _stored_snapshot(self, snapshot=None):
        return save_snapshot(TEAM_ID, snapshot or synthetic_outcome_snapshot())

    def test_train_list_predict_and_status(self):
        snapshot = self._stored_snapshot()
        trained = outcome_service.train_outcome(
            TEAM_ID,
            OutcomeTrainRequest(dataset_id=snapshot.dataset_id, model_type="fragmentation"),
        )
        self.assertEqual(trained.status, "candidate")
        self.assertEqual(trained.class_name, "FragmentationModel")
        self.assertEqual(trained.training_dataset_version, snapshot.dataset_version)
        self.assertTrue(trained.training_date)
        listed = outcome_service.list_outcome_models(TEAM_ID)
        self.assertEqual(len(listed.items), 1)
        loaded = outcome_service.get_outcome_model(TEAM_ID, trained.model_id)
        self.assertEqual(loaded.model_id, trained.model_id)

        prediction = outcome_service.predict_outcome(
            TEAM_ID,
            OutcomePredictRequest(
                model_type="fragmentation",
                model_id=trained.model_id,
                site_id="quarry-1",
                features=snapshot.samples[-1].features,
            ),
        )
        self.assertTrue(prediction.prediction_applied)
        self.assertFalse(prediction.modifies_design)
        self.assertEqual(prediction.applied_as, "recommendation_overlay")
        self.assertEqual(prediction.provenance.model_version, trained.model_version)
        self.assertIsNotNone(prediction.predicted)
        self.assertIn("x50_mm", prediction.predictions)
        self.assertIn("x80_mm", prediction.predictions)
        self.assertIsNotNone(prediction.prediction)
        self.assertIn(prediction.confidence, {"high", "medium", "low"})
        self.assertIsInstance(prediction.similarity_score, float)
        self.assertIsInstance(prediction.applicability_warning, str)
        self.assertIsNotNone(prediction.uncertainty.lower)
        self.assertIsNotNone(prediction.uncertainty.upper)
        self.assertTrue(prediction.explanation.drivers)
        self.assertTrue(prediction.predictions["x50_mm"].explanation.drivers)
        self.assertIn("X50", prediction.explanation.summary)

        promoted = outcome_service.update_status(
            TEAM_ID, trained.model_id, OutcomeStatusRequest(status="production")
        )
        self.assertEqual(promoted.status, "production")

        production = outcome_service.predict_outcome(
            TEAM_ID,
            OutcomePredictRequest(
                model_type="fragmentation",
                site_id="quarry-1",
                use_production=True,
                features=snapshot.samples[0].features,
            ),
        )
        self.assertTrue(production.prediction_applied)
        self.assertEqual(production.status, "production")

    def test_candidate_is_not_used_as_silent_production(self):
        snapshot = self._stored_snapshot()
        outcome_service.train_outcome(
            TEAM_ID,
            OutcomeTrainRequest(dataset_id=snapshot.dataset_id, model_type="oversize"),
        )
        silent = outcome_service.predict_outcome(
            TEAM_ID,
            OutcomePredictRequest(
                model_type="oversize",
                site_id="quarry-1",
                use_production=True,
                features=snapshot.samples[0].features,
            ),
        )
        self.assertFalse(silent.prediction_applied)
        self.assertIsNone(silent.predicted)
        self.assertFalse(silent.modifies_design)

    def test_predict_does_not_mutate_design(self):
        snapshot = self._stored_snapshot()
        trained = outcome_service.train_outcome(
            TEAM_ID,
            OutcomeTrainRequest(dataset_id=snapshot.dataset_id, model_type="vibration"),
        )
        design = closed_design("live-design")
        before = copy.deepcopy(design.to_dict())
        outcome_service.predict_outcome(
            TEAM_ID,
            OutcomePredictRequest(
                model_type="vibration",
                model_id=trained.model_id,
                site_id="quarry-1",
                design=design.to_dict(),
            ),
        )
        self.assertEqual(design.to_dict(), before)

    def test_predict_all_panel_uses_explicit_model_ids(self):
        snapshot = self._stored_snapshot()
        ids = {}
        for model_type in ("fragmentation", "vibration", "oversize", "toe_risk"):
            trained = outcome_service.train_outcome(
                TEAM_ID,
                OutcomeTrainRequest(dataset_id=snapshot.dataset_id, model_type=model_type),
            )
            ids[model_type] = trained.model_id
        panel = outcome_service.predict_panel(
            TEAM_ID,
            OutcomePredictAllRequest(
                site_id="quarry-1",
                use_production=False,
                model_ids=ids,
                features=snapshot.samples[-1].features,
            ),
        )
        self.assertFalse(panel.modifies_design)
        self.assertEqual(panel.applied_as, "recommendation_overlay")
        self.assertTrue(panel.x50_mm.prediction_applied)
        self.assertTrue(panel.x80_mm.prediction_applied)
        self.assertTrue(panel.oversize_pct.prediction_applied)
        self.assertTrue(panel.ppv.prediction_applied)
        self.assertTrue(panel.toe_risk.prediction_applied)
        self.assertGreater(panel.x50_mm.value, 0)
        self.assertGreaterEqual(panel.toe_risk.value, 0.0)
        self.assertLessEqual(panel.toe_risk.value, 1.0)
        self.assertIsNotNone(panel.x50_mm.uncertainty.lower)
        self.assertIsNotNone(panel.x50_mm.uncertainty.upper)
        self.assertIn(panel.x50_mm.confidence, {"high", "medium", "low"})
        self.assertTrue(panel.x50_mm.explanation.drivers)
        self.assertTrue(panel.models["fragmentation"].explanation.drivers)

    def test_train_from_closed_blast_snapshot(self):
        designs = varied_closed_outcome_designs(6)
        for design in designs:
            save_design(TEAM_ID, design)
        snapshot = save_snapshot(
            TEAM_ID,
            build_snapshot(designs, site_id="quarry-1", dataset_id="from-closed-out", dataset_version=1),
        )
        self.assertGreaterEqual(snapshot.sample_count, 6)
        trained = outcome_service.train_outcome(
            TEAM_ID,
            OutcomeTrainRequest(dataset_id=snapshot.dataset_id, model_type="ToeRiskModel"),
        )
        self.assertEqual(trained.status, "candidate")
        self.assertEqual(trained.class_name, "ToeRiskModel")
        self.assertGreaterEqual(trained.sample_count, 6)

    def test_empty_dataset_id_is_invalid(self):
        with self.assertRaises(InvalidOutcomeError):
            outcome_service.train_outcome(
                TEAM_ID, OutcomeTrainRequest(dataset_id="  ", model_type="fragmentation")
            )

    def test_model_types_and_algorithms(self):
        types = outcome_service.list_outcome_types()
        names = {item.name for item in types.items}
        self.assertEqual(names, {"fragmentation", "vibration", "oversize", "toe_risk"})
        classes = {item.class_name for item in types.items}
        self.assertIn("FragmentationModel", classes)
        listed = outcome_service.list_algorithms()
        algo_names = {item.name for item in listed.items}
        self.assertIn("random_forest", algo_names)
        self.assertIn("extra_trees", algo_names)
        self.assertEqual(listed.default, "random_forest")

    def test_predict_flags_extrapolated_diameter(self):
        snapshot = self._stored_snapshot()
        trained = outcome_service.train_outcome(
            TEAM_ID,
            OutcomeTrainRequest(dataset_id=snapshot.dataset_id, model_type="fragmentation"),
        )
        features = copy.deepcopy(snapshot.samples[0].features)
        features["GEOMETRY"]["mean_diameter_mm"] = 311.0
        prediction = outcome_service.predict_outcome(
            TEAM_ID,
            OutcomePredictRequest(
                model_type="fragmentation",
                model_id=trained.model_id,
                site_id="quarry-1",
                features=features,
            ),
        )
        self.assertFalse(prediction.in_domain)
        self.assertEqual(prediction.confidence, "low")
        self.assertIn("диаметр", prediction.applicability_warning)
        self.assertIn("311", prediction.applicability_warning)


if __name__ == "__main__":
    unittest.main()
