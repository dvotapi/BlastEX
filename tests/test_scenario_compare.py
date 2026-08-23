"""BDX-016: side-by-side comparison table, not an optimiser."""
import unittest

from design.scenarios.compare import compare_scenarios
from design.scenarios.types import DesignScenario, ScenarioOutcomes, ScenarioParams


def _scenario(scenario_id: str, name: str, **outcomes) -> DesignScenario:
    return DesignScenario(
        scenario_id=scenario_id,
        design_id="blast-1",
        name=name,
        params=ScenarioParams(),
        outcomes=ScenarioOutcomes(**outcomes),
    )


class ScenarioCompareTests(unittest.TestCase):
    def test_table_has_required_metrics_and_marks_lower_cost(self):
        table = compare_scenarios(
            [
                _scenario(
                    "a",
                    "Сценарий A",
                    drilling_metres=110.0,
                    explosive_mass_kg=820.0,
                    powder_factor_kg_m3=0.65,
                    x50_mm=200.0,
                    x80_mm=390.0,
                    oversize_pct=3.8,
                    mic_kg=88.0,
                    ppv_mm_s=3.4,
                    direct_cost_rub=180000.0,
                    total_predicted_cost_rub=240000.0,
                ),
                _scenario(
                    "b",
                    "Сценарий B",
                    drilling_metres=95.0,
                    explosive_mass_kg=700.0,
                    powder_factor_kg_m3=0.58,
                    x50_mm=230.0,
                    x80_mm=440.0,
                    oversize_pct=5.1,
                    mic_kg=76.0,
                    ppv_mm_s=2.9,
                    direct_cost_rub=150000.0,
                    total_predicted_cost_rub=210000.0,
                ),
            ]
        )
        keys = [row["key"] for row in table["rows"]]
        self.assertIn("drilling_metres", keys)
        self.assertIn("explosive_mass_kg", keys)
        self.assertIn("x50_mm", keys)
        self.assertIn("x80_mm", keys)
        self.assertIn("oversize_pct", keys)
        self.assertIn("mic_kg", keys)
        self.assertIn("ppv_mm_s", keys)
        self.assertIn("direct_cost_rub", keys)
        self.assertIn("total_predicted_cost_rub", keys)
        cost_row = next(row for row in table["rows"] if row["key"] == "total_predicted_cost_rub")
        self.assertEqual(cost_row["best_scenario_id"], "b")
        self.assertEqual(cost_row["label"], "Прогнозная смета")
        self.assertFalse(table["is_optimiser"])
        self.assertFalse(table["modifies_design"])


if __name__ == "__main__":
    unittest.main()
