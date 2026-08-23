"""BDX-018: recommendation round-trip never claims to apply or approve."""
import unittest

from design.optimization.types import KIND_CANDIDATE, OptimizationCandidate
from design.recommendation.types import (
    APPLIED_AS,
    METHOD_PROFILE_PARETO,
    PROFILE_LOW_COST,
    DesignRecommendation,
    RecommendationReason,
)
from design.scenarios.types import ScenarioOutcomes, ScenarioParams


class RecommendationModelTests(unittest.TestCase):
    def test_round_trip_forces_recommendation_flags(self):
        candidate = OptimizationCandidate(
            candidate_id="cand-0002",
            params=ScenarioParams(diameter_mm=165.0, burden_b_m=4.5),
            outcomes=ScenarioOutcomes(drilling_metres=90.0, oversize_pct=3.2, ppv_mm_s=2.1),
            objectives={"cost": 1000.0, "oversize": 3.2},
            on_pareto=True,
            kind=KIND_CANDIDATE,
        )
        result = DesignRecommendation(
            recommendation_id="rec-a",
            design_id="blast-1",
            profile=PROFILE_LOW_COST,
            suggested=candidate,
            reasons=[RecommendationReason(kind="profile", title="Профиль", detail="test")],
            evaluated=4,
            pareto_count=2,
        )
        restored = DesignRecommendation.from_dict(
            {
                **result.to_dict(),
                "modifies_design": True,
                "replaces_design": True,
                "auto_applied": True,
                "approved": True,
                "engineer_decides": False,
                "source_design_role": "predicted",
            }
        )
        self.assertFalse(restored.modifies_design)
        self.assertFalse(restored.replaces_design)
        self.assertFalse(restored.auto_applied)
        self.assertFalse(restored.approved)
        self.assertTrue(restored.engineer_decides)
        self.assertTrue(restored.approved_unchanged)
        self.assertEqual(restored.applied_as, APPLIED_AS)
        self.assertEqual(restored.method, METHOD_PROFILE_PARETO)
        self.assertEqual(restored.source_design_role, "designed")
        self.assertEqual(restored.suggested_role, "predicted")
        self.assertEqual(restored.profile, PROFILE_LOW_COST)
        self.assertEqual(restored.suggested.params.diameter_mm, 165.0)
        self.assertEqual(restored.reasons[0].role, "predicted")


if __name__ == "__main__":
    unittest.main()
