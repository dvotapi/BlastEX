"""BDX-017: non-dominated sort and utopia compromise, no scalar RL reward."""
import unittest

from design.optimization.pareto import dominates, mark_pareto, pick_compromise
from design.optimization.types import OptimizationCandidate
from design.scenarios.types import ScenarioOutcomes, ScenarioParams


def _candidate(cid: str, **objectives: float | None) -> OptimizationCandidate:
    return OptimizationCandidate(
        candidate_id=cid,
        params=ScenarioParams(),
        outcomes=ScenarioOutcomes(),
        objectives=dict(objectives),
        feasible=all(value is not None for value in objectives.values()),
    )


class ParetoTests(unittest.TestCase):
    def test_dominates_requires_strict_improvement(self):
        self.assertTrue(dominates([1.0, 2.0], [1.0, 3.0]))
        self.assertFalse(dominates([1.0, 2.0], [1.0, 2.0]))
        self.assertFalse(dominates([1.0, 3.0], [2.0, 2.0]))

    def test_known_two_objective_front(self):
        points = [
            _candidate("a", cost=1, oversize=5),
            _candidate("b", cost=2, oversize=3),
            _candidate("c", cost=3, oversize=2),
            _candidate("d", cost=4, oversize=1),
            _candidate("e", cost=3, oversize=4),
            _candidate("f", cost=5, oversize=5),
        ]
        front = mark_pareto(points, ["cost", "oversize"])
        self.assertEqual({item.candidate_id for item in front}, {"a", "b", "c", "d"})
        self.assertTrue(all(item.on_pareto for item in front))
        self.assertEqual(next(item.pareto_rank for item in points if item.candidate_id == "e"), 2)
        self.assertFalse(next(item for item in points if item.candidate_id == "f").on_pareto)

    def test_missing_objective_is_not_on_front(self):
        points = [
            _candidate("ok", cost=10, oversize=2),
            _candidate("gap", cost=1, oversize=None),
        ]
        front = mark_pareto(points, ["cost", "oversize"])
        self.assertEqual([item.candidate_id for item in front], ["ok"])
        self.assertEqual(points[1].pareto_rank, 0)

    def test_compromise_is_closest_to_utopia(self):
        points = [
            _candidate("cheap", cost=1, oversize=10),
            _candidate("mid", cost=4, oversize=4),
            _candidate("fine", cost=10, oversize=1),
        ]
        mark_pareto(points, ["cost", "oversize"])
        picked = pick_compromise(points, ["cost", "oversize"])
        self.assertIsNotNone(picked)
        self.assertEqual(picked.candidate_id, "mid")


if __name__ == "__main__":
    unittest.main()
