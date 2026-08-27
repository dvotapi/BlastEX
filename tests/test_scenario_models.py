"""BDX-016: scenario entity round-trip and metric helpers."""
import unittest

from design.scenarios.types import (
    KIND_OVERLAY,
    DesignScenario,
    ScenarioOutcomes,
    ScenarioParams,
)


class ScenarioModelTests(unittest.TestCase):
    def test_round_trip_keeps_params_and_outcomes(self):
        scenario = DesignScenario(
            scenario_id="scn-a",
            design_id="blast-1",
            name="Сценарий A",
            params=ScenarioParams(
                diameter_mm=165.0,
                spacing_a_m=6.0,
                burden_b_m=5.0,
                powder_factor_kg_m3=0.65,
                explosive_key="ПВВ Гранулит-РП",
                inclination_deg=10.0,
                delay_interval_ms=25.0,
            ),
            outcomes=ScenarioOutcomes(
                drilling_metres=120.0,
                explosive_mass_kg=800.0,
                powder_factor_kg_m3=0.65,
                hole_count=12,
                x50_mm=210.0,
                x80_mm=410.0,
                oversize_pct=4.2,
                mic_kg=90.0,
                ppv_mm_s=3.1,
                direct_cost_rub=150000.0,
                total_predicted_cost_rub=210000.0,
            ),
        )
        restored = DesignScenario.from_dict(scenario.to_dict())
        self.assertEqual(restored.scenario_id, "scn-a")
        self.assertEqual(restored.name, "Сценарий A")
        self.assertEqual(restored.kind, KIND_OVERLAY)
        self.assertFalse(restored.modifies_design)
        self.assertEqual(restored.applied_as, "scenario_overlay")
        self.assertEqual(restored.params.diameter_mm, 165.0)
        self.assertEqual(restored.params.spacing_a_m, 6.0)
        self.assertEqual(restored.params.explosive_key, "ПВВ Гранулит-РП")
        self.assertEqual(restored.params.inclination_deg, 10.0)
        self.assertEqual(restored.params.delay_interval_ms, 25.0)
        self.assertEqual(restored.outcomes.x50_mm, 210.0)
        self.assertEqual(restored.outcomes.metric_value("total_predicted_cost_rub"), 210000.0)

    def test_from_dict_forces_modifies_design_false(self):
        restored = DesignScenario.from_dict(
            {
                "scenario_id": "x",
                "design_id": "d",
                "name": "A",
                "modifies_design": True,
                "kind": "unknown",
            }
        )
        self.assertFalse(restored.modifies_design)
        self.assertEqual(restored.kind, KIND_OVERLAY)


if __name__ == "__main__":
    unittest.main()
