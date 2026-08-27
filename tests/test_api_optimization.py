"""BDX-017: optimize / list / promote API."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidOptimizationError
from api.schemas.design import BlastDesignSchema
from api.schemas.optimization import OptimizationPromoteRequest, OptimizationRequest, VariableBoundSchema
from api.schemas.scenarios import ScenarioParamsSchema
from api.services import optimization_service
from design.optimization.types import DEFAULT_OBJECTIVES
from design.persistence import save_design
from tests.scenario_fixtures import charged_design

TEAM_ID = "opt-api-team"


class OptimizationApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _plan(self):
        return save_design(TEAM_ID, charged_design("opt-api-design"))

    def test_optimize_lists_and_promotes(self):
        design = self._plan()
        payload = BlastDesignSchema(**design.to_dict())
        result = optimization_service.run_optimization(
            TEAM_ID,
            OptimizationRequest(
                design=payload,
                variables=[
                    VariableBoundSchema(name="diameter_mm", values=[152, 165]),
                    VariableBoundSchema(name="burden_b_m", values=[4.0]),
                    VariableBoundSchema(name="spacing_a_m", values=[5.0, 5.5]),
                    VariableBoundSchema(name="explosive_key", values=["ПВВ Гранулит-РП"]),
                    VariableBoundSchema(name="inclination_deg", values=[0.0]),
                    VariableBoundSchema(name="delay_interval_ms", values=[25.0]),
                ],
                objectives=list(DEFAULT_OBJECTIVES),
                target_x50_mm=200.0,
                max_candidates=8,
                persist=True,
            ),
        )
        self.assertGreaterEqual(result.evaluated, 3)
        self.assertIn("cost", result.objectives)
        self.assertIn("oversize", result.objectives)
        self.assertIn("drilling_metres", result.objectives)
        self.assertIn("ppv", result.objectives)
        self.assertIn("target_x50", result.objectives)
        self.assertTrue(result.pareto_front)
        self.assertIsNotNone(result.compromise_candidate_id)
        self.assertFalse(result.uses_rl)
        self.assertFalse(result.replaces_design)
        for item in result.candidates:
            self.assertGreater(item.outcomes.drilling_metres, 0.0)
            self.assertIsNotNone(item.outcomes.oversize_pct)
            self.assertIsNotNone(item.outcomes.ppv_mm_s)
            self.assertIsNotNone(item.outcomes.x50_mm)
            self.assertIsNotNone(item.outcomes.total_predicted_cost_rub)

        listed = optimization_service.list_plan_runs(TEAM_ID, design.design_id)
        self.assertEqual(len(listed.items), 1)
        self.assertEqual(listed.items[0].run_id, result.run_id)
        loaded = optimization_service.get_plan_run(TEAM_ID, design.design_id, result.run_id)
        self.assertEqual(loaded.run_id, result.run_id)
        self.assertEqual(len(loaded.pareto_front), len(result.pareto_front))

        pick = result.pareto_front[0]
        promoted = optimization_service.promote_candidate(
            TEAM_ID,
            OptimizationPromoteRequest(
                design=payload,
                name="С Парето",
                params=ScenarioParamsSchema(**pick.params.model_dump()),
            ),
        )
        self.assertEqual(promoted.name, "С Парето")
        self.assertFalse(promoted.modifies_design)

    def test_empty_design_is_rejected(self):
        from design.models import BlastDesign

        with self.assertRaises(InvalidOptimizationError):
            optimization_service.run_optimization(
                TEAM_ID,
                OptimizationRequest(
                    design=BlastDesignSchema(**BlastDesign(design_id="empty").to_dict()),
                    variables=[VariableBoundSchema(name="diameter_mm", values=[152])],
                ),
            )


if __name__ == "__main__":
    unittest.main()
