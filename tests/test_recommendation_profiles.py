"""BDX-018: profile weights pick different overlays, BALANCED reuses utopia."""
import unittest

from design.optimization.pareto import mark_pareto
from design.optimization.types import OptimizationCandidate
from design.recommendation.profiles import pick_for_profile, profile_spec, profile_winners
from design.recommendation.types import (
    PROFILE_BALANCED,
    PROFILE_FINE_FRAGMENTATION,
    PROFILE_LOW_COST,
    PROFILE_LOW_VIBRATION,
)
from design.scenarios.types import ScenarioOutcomes, ScenarioParams


def _candidate(cid: str, **objectives: float | None) -> OptimizationCandidate:
    return OptimizationCandidate(
        candidate_id=cid,
        params=ScenarioParams(),
        outcomes=ScenarioOutcomes(),
        objectives=dict(objectives),
        feasible=all(value is not None for value in objectives.values()),
    )


KEYS = ["cost", "oversize", "drilling_metres", "ppv", "target_x50"]


class RecommendationProfileTests(unittest.TestCase):
    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            profile_spec("GLOBAL_SITE_LEARNING")

    def test_profiles_prefer_their_primary_objective(self):
        points = [
            _candidate("cheap", cost=1, oversize=12, drilling_metres=80, ppv=6, target_x50=40),
            _candidate("fine", cost=12, oversize=1, drilling_metres=90, ppv=6, target_x50=2),
            _candidate("quiet", cost=8, oversize=8, drilling_metres=85, ppv=1, target_x50=20),
            _candidate("mid", cost=6, oversize=6, drilling_metres=82, ppv=4, target_x50=12),
        ]
        mark_pareto(points, KEYS)
        self.assertEqual(pick_for_profile(points, PROFILE_LOW_COST, KEYS).candidate_id, "cheap")
        self.assertEqual(pick_for_profile(points, PROFILE_FINE_FRAGMENTATION, KEYS).candidate_id, "fine")
        self.assertEqual(pick_for_profile(points, PROFILE_LOW_VIBRATION, KEYS).candidate_id, "quiet")
        balanced = pick_for_profile(points, PROFILE_BALANCED, KEYS)
        self.assertEqual(balanced.candidate_id, "mid")

    def test_profile_winners_cover_all_keys(self):
        points = [
            _candidate("a", cost=1, oversize=5, drilling_metres=10, ppv=5, target_x50=5),
            _candidate("b", cost=5, oversize=1, drilling_metres=10, ppv=5, target_x50=1),
        ]
        mark_pareto(points, KEYS)
        winners = profile_winners(points, KEYS)
        self.assertEqual(set(winners), {PROFILE_BALANCED, PROFILE_LOW_COST, PROFILE_FINE_FRAGMENTATION, PROFILE_LOW_VIBRATION})


if __name__ == "__main__":
    unittest.main()
