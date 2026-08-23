"""BDX-018: reasons show profile, deltas in declared units, and no-apply rule."""
import unittest

from design.optimization.types import DecisionVector, OptimizationCandidate
from design.recommendation.types import (
    PROFILE_FINE_FRAGMENTATION,
    REASON_DECISION,
    REASON_DELTA,
    REASON_PARAM,
    REASON_PROFILE,
    REASON_UNCERTAINTY,
    RecommendationAssessment,
)
from design.recommendation.profiles import profile_spec
from design.recommendation.why import build_reasons
from design.scenarios.types import ScenarioOutcomes, ScenarioParams
from intelligence.explainability.types import RecommendationHint, empty_explanation


class RecommendationWhyTests(unittest.TestCase):
    def test_reasons_include_profile_deltas_and_decision(self):
        baseline = OptimizationCandidate(
            candidate_id="cand-0001",
            params=ScenarioParams(diameter_mm=152.0, burden_b_m=4.0, spacing_a_m=5.0),
            outcomes=ScenarioOutcomes(
                drilling_metres=100.0,
                oversize_pct=8.0,
                ppv_mm_s=4.0,
                x50_mm=240.0,
                total_predicted_cost_rub=200000.0,
            ),
            decision=DecisionVector(values={}),
        )
        suggested = OptimizationCandidate(
            candidate_id="cand-0002",
            params=ScenarioParams(diameter_mm=165.0, burden_b_m=3.5, spacing_a_m=5.0),
            outcomes=ScenarioOutcomes(
                drilling_metres=110.0,
                oversize_pct=3.0,
                ppv_mm_s=3.5,
                x50_mm=190.0,
                total_predicted_cost_rub=180000.0,
            ),
            decision=DecisionVector(values={"diameter_mm": 165.0, "burden_b_m": 3.5}),
        )
        reasons = build_reasons(
            profile=profile_spec(PROFILE_FINE_FRAGMENTATION),
            suggested=suggested,
            baseline=baseline,
            assessments=[],
        )
        kinds = [item.kind for item in reasons]
        self.assertIn(REASON_PROFILE, kinds)
        self.assertIn(REASON_PARAM, kinds)
        self.assertIn(REASON_DELTA, kinds)
        self.assertIn(REASON_UNCERTAINTY, kinds)
        self.assertEqual(kinds[-1], REASON_DECISION)
        x50 = next(item for item in reasons if item.metric == "x50_mm")
        self.assertEqual(x50.unit, "мм")
        self.assertAlmostEqual(x50.delta, -50.0)
        self.assertIn("мм", x50.detail)
        self.assertNotIn("convert", x50.detail.lower())
        decision = reasons[-1]
        self.assertIn("не применяется", decision.detail.lower() + decision.title.lower())
        self.assertTrue(any("модели не подключены" in item.detail.lower() for item in reasons))

    def test_model_assessment_adds_confidence_and_explanation(self):
        explanation = empty_explanation(target_name="x50_mm", target_label="X50", unit="мм")
        explanation.recommendation_summary = "Снижение ЛНС: ожидаемый X50 −34 мм"
        explanation.recommendations = [
            RecommendationHint(
                feature="GEOMETRY.mean_burden_m",
                label="ЛНС",
                label_en="Burden",
                action="reduce",
                action_label="Снижение ЛНС",
                delta=-34.0,
                unit="мм",
                target_name="x50_mm",
                target_label="X50",
                step=-0.4,
                summary="Снижение ЛНС: ожидаемый X50 −34 мм",
            )
        ]
        assessment = RecommendationAssessment(
            target_name="x50_mm",
            target_label="X50",
            unit="мм",
            prediction=190.0,
            uncertainty={"std": 8.0, "lower": 170.0, "upper": 210.0, "method": "ensemble_trees"},
            confidence="medium",
            confidence_label="Средняя",
            similarity_score=0.62,
            applicability_warning="",
            comparable_count=7,
            in_domain=True,
            sample_count=12,
            explanation=explanation.to_dict(),
            model_id="out-1",
            model_available=True,
        )
        suggested = OptimizationCandidate(
            candidate_id="cand-0002",
            params=ScenarioParams(burden_b_m=3.5),
            outcomes=ScenarioOutcomes(x50_mm=190.0),
            decision=DecisionVector(values={"burden_b_m": 3.5}),
        )
        reasons = build_reasons(
            profile=profile_spec(PROFILE_FINE_FRAGMENTATION),
            suggested=suggested,
            baseline=None,
            assessments=[assessment],
        )
        texts = " ".join(item.detail for item in reasons)
        self.assertIn("сходство 62 %", texts)
        self.assertIn("−34 мм", texts)
        self.assertTrue(any(item.kind == "explanation" for item in reasons))


if __name__ == "__main__":
    unittest.main()
