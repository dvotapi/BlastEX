"""BDX-016: overlay engine clones the passport and evaluates engineering outcomes."""
import unittest

from design.scenarios.engine import (
    InvalidScenarioParamsError,
    apply_params,
    build_and_evaluate,
    clone_design,
    holes_loads_payload,
    revision_sha256,
)
from design.scenarios.types import ScenarioParams
from tests.scenario_fixtures import charged_design


class ScenarioEngineTests(unittest.TestCase):
    def test_clone_is_independent(self):
        design = charged_design()
        copy = clone_design(design)
        copy.holes[0].diameter_mm = 311.0
        copy.loads[0].total_charge_kg = 0.0
        self.assertNotEqual(copy.holes[0].diameter_mm, design.holes[0].diameter_mm)
        self.assertNotEqual(copy.loads[0].total_charge_kg, design.loads[0].total_charge_kg)

    def test_wider_grid_reduces_holes_and_metres(self):
        design = charged_design()
        before = holes_loads_payload(design)
        overlay, outcomes, source_hash, overlay_hash = build_and_evaluate(
            design,
            ScenarioParams(diameter_mm=165.0, spacing_a_m=6.0, burden_b_m=5.5),
        )
        self.assertEqual(holes_loads_payload(design), before)
        self.assertEqual(revision_sha256(design), source_hash)
        self.assertNotEqual(overlay_hash, source_hash)
        self.assertLess(outcomes.hole_count, len(design.holes))
        self.assertLess(outcomes.drilling_metres, sum(h.length_m for h in design.holes))
        self.assertGreater(outcomes.explosive_mass_kg, 0.0)
        self.assertIsNotNone(outcomes.x50_mm)
        self.assertIsNotNone(outcomes.x80_mm)
        self.assertIsNotNone(outcomes.oversize_pct)
        self.assertIsNotNone(outcomes.mic_kg)
        self.assertIsNotNone(outcomes.ppv_mm_s)
        self.assertEqual(outcomes.diameter_mm, 165.0)
        self.assertEqual(outcomes.spacing_a_m, 6.0)
        self.assertEqual(outcomes.burden_b_m, 5.5)
        self.assertTrue(all(hole.diameter_mm == 165.0 for hole in overlay.holes if hole.enabled))

    def test_target_powder_factor_scales_charge(self):
        design = charged_design()
        overlay = apply_params(design, ScenarioParams(powder_factor_kg_m3=0.65, spacing_a_m=5.0, burden_b_m=4.0))
        qs = [load.specific_q_kg_m3 for load in overlay.loads if load.total_charge_kg > 0]
        self.assertTrue(qs)
        for value in qs:
            self.assertAlmostEqual(value, 0.65, places=3)
        self.assertEqual(design.loads[0].total_charge_kg, charged_design().loads[0].total_charge_kg)

    def test_rejects_non_positive_diameter(self):
        with self.assertRaises(InvalidScenarioParamsError):
            apply_params(charged_design(), ScenarioParams(diameter_mm=0.0))


if __name__ == "__main__":
    unittest.main()
