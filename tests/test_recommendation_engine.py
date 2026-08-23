"""BDX-018: profile overlay reuses the scenario search and stays a suggestion."""
import unittest

from design.models import BlastDesign
from design.optimization.types import KIND_BASELINE, VariableBound
from design.recommendation.engine import RecommendationError, recommend
from design.recommendation.types import (
    APPLIED_AS,
    METHOD_PROFILE_PARETO,
    PROFILE_BALANCED,
    PROFILE_FINE_FRAGMENTATION,
    PROFILE_LOW_COST,
    PROFILE_LOW_VIBRATION,
)
from design.scenarios.engine import holes_loads_payload
from design.scenarios.types import ScenarioOutcomes, ScenarioParams
from tests.scenario_fixtures import charged_design


def _stub_cost(overlay: BlastDesign, params: ScenarioParams, outcomes: ScenarioOutcomes) -> None:
    outcomes.direct_cost_rub = outcomes.drilling_metres * 400.0 + outcomes.explosive_mass_kg * 80.0
    outcomes.total_predicted_cost_rub = outcomes.direct_cost_rub
    outcomes.cost_source = "engineering"


class RecommendationEngineTests(unittest.TestCase):
    def test_recommend_is_deterministic_and_not_applied(self):
        design = charged_design()
        before = holes_loads_payload(design)
        bounds = [
            VariableBound(name="diameter_mm", values=[152, 165]),
            VariableBound(name="burden_b_m", values=[4.0, 4.5]),
            VariableBound(name="spacing_a_m", values=[5.0]),
        ]
        first = recommend(
            design,
            PROFILE_BALANCED,
            bounds,
            target_x50_mm=200.0,
            max_candidates=8,
            cost_fn=_stub_cost,
            recommendation_id="rec-test-1",
        )
        second = recommend(
            design,
            PROFILE_BALANCED,
            bounds,
            target_x50_mm=200.0,
            max_candidates=8,
            cost_fn=_stub_cost,
            recommendation_id="rec-test-2",
        )
        self.assertEqual(holes_loads_payload(design), before)
        self.assertEqual(first.method, METHOD_PROFILE_PARETO)
        self.assertEqual(first.applied_as, APPLIED_AS)
        self.assertFalse(first.auto_applied)
        self.assertFalse(first.approved)
        self.assertFalse(first.modifies_design)
        self.assertFalse(first.replaces_design)
        self.assertTrue(first.engineer_decides)
        self.assertEqual(first.source_design_role, "designed")
        self.assertEqual(first.suggested_role, "predicted")
        self.assertIsNotNone(first.suggested)
        self.assertIsNotNone(first.baseline)
        self.assertEqual(first.baseline.kind, KIND_BASELINE)
        self.assertGreaterEqual(first.evaluated, 3)
        self.assertGreaterEqual(first.pareto_count, 1)
        self.assertEqual(first.suggested.candidate_id, second.suggested.candidate_id)
        self.assertEqual(first.profile_picks[PROFILE_BALANCED], first.suggested.candidate_id)
        self.assertTrue(any(item.kind == "decision" for item in first.reasons))
        self.assertTrue(all(item.role in {"predicted", "designed"} for item in first.reasons))

    def test_profiles_can_diverge_on_the_same_search(self):
        design = charged_design()
        bounds = [
            VariableBound(name="diameter_mm", values=[152, 165]),
            VariableBound(name="burden_b_m", values=[3.5, 4.5]),
            VariableBound(name="spacing_a_m", values=[4.5, 5.5]),
        ]
        picks = {}
        for profile in (PROFILE_LOW_COST, PROFILE_FINE_FRAGMENTATION, PROFILE_LOW_VIBRATION):
            result = recommend(
                design,
                profile,
                bounds,
                target_x50_mm=200.0,
                max_candidates=12,
                cost_fn=_stub_cost,
            )
            self.assertFalse(result.auto_applied)
            picks[profile] = result.suggested.candidate_id if result.suggested else None
        self.assertTrue(any(picks[PROFILE_LOW_COST] != other for other in picks.values()))

    def test_assess_fn_attaches_uncertainty_without_mutating_design(self):
        design = charged_design()
        before = holes_loads_payload(design)

        def assess(overlay: BlastDesign, params: ScenarioParams):
            from design.recommendation.types import RecommendationAssessment

            self.assertNotEqual(id(overlay), id(design))
            return [
                RecommendationAssessment(
                    target_name="x50_mm",
                    target_label="X50",
                    unit="мм",
                    prediction=188.0,
                    uncertainty={"std": 6.0, "lower": 170.0, "upper": 210.0, "method": "ensemble_trees"},
                    confidence="medium",
                    confidence_label="Средняя",
                    similarity_score=0.7,
                    comparable_count=5,
                    in_domain=True,
                    sample_count=9,
                    model_id="out-x50",
                    model_available=True,
                )
            ]

        result = recommend(
            design,
            PROFILE_BALANCED,
            [
                VariableBound(name="diameter_mm", values=[152, 165]),
                VariableBound(name="burden_b_m", values=[4.0]),
                VariableBound(name="spacing_a_m", values=[5.0]),
            ],
            cost_fn=_stub_cost,
            assess_fn=assess,
        )
        self.assertEqual(holes_loads_payload(design), before)
        self.assertEqual(len(result.assessments), 1)
        self.assertEqual(result.assessments[0].unit, "мм")
        self.assertTrue(any(item.kind == "uncertainty" for item in result.reasons))
        self.assertIn("70 %", " ".join(item.detail for item in result.reasons))

    def test_rejects_non_positive_target_x50(self):
        with self.assertRaises(RecommendationError):
            recommend(charged_design(), PROFILE_BALANCED, target_x50_mm=0.0, cost_fn=_stub_cost)


if __name__ == "__main__":
    unittest.main()
