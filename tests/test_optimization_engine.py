"""BDX-017: overlay search reuses the scenario engine and stays deterministic."""
import unittest

from design.models import BlastDesign
from design.optimization.engine import OptimizationError, optimize
from design.optimization.types import KIND_BASELINE, METHOD_DETERMINISTIC_PARETO, VariableBound
from design.scenarios.engine import apply_params, holes_loads_payload
from design.scenarios.types import ScenarioOutcomes, ScenarioParams
from tests.scenario_fixtures import charged_design


def _stub_cost(overlay: BlastDesign, params: ScenarioParams, outcomes: ScenarioOutcomes) -> None:
    # Explicit RUB rates for the test helper — not a unit conversion.
    outcomes.direct_cost_rub = outcomes.drilling_metres * 400.0 + outcomes.explosive_mass_kg * 80.0
    outcomes.total_predicted_cost_rub = outcomes.direct_cost_rub
    outcomes.cost_source = "engineering"


class OptimizationEngineTests(unittest.TestCase):
    def test_search_is_deterministic_and_labels_predicted(self):
        design = charged_design()
        bounds = [
            VariableBound(name="diameter_mm", values=[152, 165]),
            VariableBound(name="burden_b_m", values=[4.0, 4.5]),
            VariableBound(name="spacing_a_m", values=[5.0]),
        ]
        first = optimize(
            design,
            bounds,
            objectives=["cost", "oversize", "drilling_metres", "ppv", "target_x50"],
            target_x50_mm=200.0,
            max_candidates=8,
            cost_fn=_stub_cost,
            run_id="opt-test-1",
        )
        second = optimize(
            design,
            bounds,
            objectives=["cost", "oversize", "drilling_metres", "ppv", "target_x50"],
            target_x50_mm=200.0,
            max_candidates=8,
            cost_fn=_stub_cost,
            run_id="opt-test-2",
        )
        self.assertEqual(first.method, METHOD_DETERMINISTIC_PARETO)
        self.assertFalse(first.uses_rl)
        self.assertFalse(first.replaces_design)
        self.assertFalse(first.modifies_design)
        self.assertEqual(first.source_design_role, "designed")
        self.assertEqual(first.candidate_role, "predicted")
        self.assertGreaterEqual(first.evaluated, 3)
        self.assertTrue(any(item.kind == KIND_BASELINE for item in first.candidates))
        self.assertTrue(first.pareto_front)
        self.assertTrue(all(item.role == "predicted" for item in first.candidates))
        self.assertEqual(
            [item.decision.values for item in first.candidates],
            [item.decision.values for item in second.candidates],
        )
        self.assertEqual(
            {item.candidate_id for item in first.pareto_front},
            {item.candidate_id for item in second.pareto_front},
        )
        for item in first.candidates:
            self.assertIsNotNone(item.objectives.get("cost"))
            self.assertIsNotNone(item.objectives.get("oversize"))
            self.assertIsNotNone(item.objectives.get("drilling_metres"))
            self.assertIsNotNone(item.objectives.get("ppv"))
            self.assertIsNotNone(item.objectives.get("target_x50"))
            if item.outcomes.x50_mm is not None:
                self.assertAlmostEqual(
                    item.objectives["target_x50"],
                    abs(item.outcomes.x50_mm - 200.0),
                    places=6,
                )

    def test_new_knobs_apply_on_overlay_only(self):
        design = charged_design()
        before = holes_loads_payload(design)
        overlay = apply_params(
            design,
            ScenarioParams(
                explosive_key="ПЭВВ ЭВЕРСИН Э-100",
                inclination_deg=10.0,
                delay_interval_ms=25.0,
                stemming_m=2.5,
                subdrill_m=1.2,
            ),
        )
        self.assertEqual(holes_loads_payload(design), before)
        self.assertEqual(overlay.explosive_key, "ПЭВВ ЭВЕРСИН Э-100")
        self.assertTrue(all(abs(hole.angle_deg - 10.0) < 1e-6 for hole in overlay.holes if hole.enabled))
        self.assertAlmostEqual(float((overlay.network.timing_params or {}).get("interval_ms")), 25.0)
        self.assertAlmostEqual(float((overlay.charge_rules or {}).get("stemming_m")), 2.5)
        self.assertAlmostEqual(float((overlay.pattern_params or {}).get("subdrill_m")), 1.2)

    def test_rejects_non_positive_target_x50(self):
        with self.assertRaises(OptimizationError):
            optimize(
                charged_design(),
                [VariableBound(name="diameter_mm", values=[152])],
                target_x50_mm=0.0,
                cost_fn=_stub_cost,
            )


if __name__ == "__main__":
    unittest.main()
