"""BDX-017: optimization result round-trip never claims to modify the design."""
import unittest

from design.optimization.types import (
    APPLIED_AS,
    KIND_CANDIDATE,
    OptimizationCandidate,
    OptimizationResult,
)
from design.scenarios.types import ScenarioOutcomes, ScenarioParams


class OptimizationModelTests(unittest.TestCase):
    def test_round_trip_forces_recommendation_flags(self):
        candidate = OptimizationCandidate(
            candidate_id="cand-0001",
            params=ScenarioParams(diameter_mm=165.0, burden_b_m=4.5),
            outcomes=ScenarioOutcomes(drilling_metres=90.0, oversize_pct=3.2, ppv_mm_s=2.1),
            objectives={"cost": 1000.0, "oversize": 3.2},
            on_pareto=True,
            kind=KIND_CANDIDATE,
        )
        result = OptimizationResult(
            run_id="opt-a",
            design_id="blast-1",
            candidates=[candidate],
            pareto_front=[candidate],
            compromise_candidate_id="cand-0001",
            evaluated=1,
            feasible=1,
        )
        restored = OptimizationResult.from_dict(
            {
                **result.to_dict(),
                "modifies_design": True,
                "replaces_design": True,
                "uses_rl": True,
            }
        )
        self.assertFalse(restored.modifies_design)
        self.assertFalse(restored.replaces_design)
        self.assertFalse(restored.uses_rl)
        self.assertTrue(restored.approved_unchanged)
        self.assertEqual(restored.applied_as, APPLIED_AS)
        self.assertEqual(restored.candidates[0].params.diameter_mm, 165.0)
        self.assertEqual(restored.compromise_candidate_id, "cand-0001")


if __name__ == "__main__":
    unittest.main()
