"""BDX-024: official passport assembles designed + predicted + cost + vibration + frag."""
import unittest

from design.as_charged import record_as_charged
from design.as_drilled import record_as_drilled
from design.blast_result import (
    ActualCost,
    BlastResult,
    ComparisonBasis,
    MeasuredMuckpile,
    MeasuredVibration,
    PlannedCost,
    PredictedVibrationSnapshot,
    record_blast_result,
)
from design.models import AsChargedHole, AsDrilledHole, Point3, ROLE_DESIGNED, ROLE_EXECUTED, ROLE_MEASURED, ROLE_PREDICTED
from design.reporting.engine import build_passport
from simulation.fragmentation.models import MeasuredFragmentation, ModelProvenance, PredictedFragmentation
from tests.scenario_fixtures import charged_design


class ReportingEngineTests(unittest.TestCase):
    def test_designed_predicted_and_holes_are_present(self):
        design = charged_design("passport-engine")
        document = build_passport(design, lump_size_mm=400.0)
        self.assertEqual(document.designed.role, ROLE_DESIGNED)
        self.assertEqual(document.predicted.role, ROLE_PREDICTED)
        self.assertGreater(document.designed.hole_count, 0)
        self.assertGreater(document.designed.explosive_mass_kg, 0.0)
        self.assertAlmostEqual(document.designed.spacing_a_m, 5.0)
        self.assertAlmostEqual(document.designed.burden_b_m, 4.0)
        self.assertEqual(document.designed.diameter_mm, 152.0)
        self.assertIsNotNone(document.predicted.x50_mm)
        self.assertIsNotNone(document.predicted.x80_mm)
        self.assertIsNotNone(document.predicted.oversize_pct)
        self.assertIsNotNone(document.predicted.ppv_mm_s)
        self.assertIsNotNone(document.predicted.throw_m)
        self.assertEqual(len(document.holes), len(design.holes))
        keys = [row.key for row in document.comparison]
        self.assertIn("x50_mm", keys)
        self.assertIn("ppv_mm_s", keys)
        self.assertIn("total_amount_rub", keys)
        self.assertFalse(document.approved)
        self.assertFalse(document.auto_approved)
        self.assertFalse(document.design_rewritten)

    def test_planned_cost_stays_designed_not_predicted(self):
        design = charged_design("passport-cost")
        document = build_passport(
            design,
            include_predictions=False,
            planned_cost={"total_amount_rub": 1_500_000.0, "cost_per_m3": 75.0},
        )
        self.assertEqual(document.planned_cost.role, ROLE_DESIGNED)
        self.assertEqual(document.planned_cost.total_amount_rub, 1_500_000.0)
        cost_row = next(row for row in document.comparison if row.key == "total_amount_rub")
        self.assertEqual(cost_row.designed, 1_500_000.0)
        self.assertIsNone(cost_row.predicted)
        self.assertIsNone(cost_row.measured)

    def test_measured_and_executed_fill_their_own_columns(self):
        design = charged_design("passport-measured")
        hole = design.holes[0]
        record_as_drilled(
            design,
            AsDrilledHole(
                design_hole_id=hole.id,
                actual_collar=Point3(x=hole.collar.x + 0.3, y=hole.collar.y, z=hole.collar.z),
                actual_toe=Point3(x=hole.toe.x + 0.3, y=hole.toe.y, z=hole.toe.z),
                actual_depth=11.0,
                actual_diameter=165.0,
            ),
        )
        record_as_charged(
            design,
            AsChargedHole(design_hole_id=hole.id, charge_mass_kg=88.0, explosive_product="АНФО"),
        )
        record_blast_result(
            design,
            BlastResult(
                design_id=design.design_id,
                fragmentation=MeasuredFragmentation(x50_mm=210.0, x80_mm=390.0, oversize_pct=6.2),
                vibration=MeasuredVibration(ppv_mm_s=5.1, receptor_id="R-office"),
                muckpile=MeasuredMuckpile(throw_m=14.0, volume_m3=2600.0),
                cost_actual=ActualCost(total_amount_rub=1_800_000.0, cost_per_m3=90.0),
            ),
            basis=ComparisonBasis(
                predicted_fragmentation=PredictedFragmentation(
                    x20_mm=90.0,
                    x50_mm=170.0,
                    x80_mm=320.0,
                    oversize_pct=3.4,
                    powder_factor_kg_m3=0.7,
                    provenance=ModelProvenance(model="kuzram", model_version="1"),
                ),
                predicted_vibration=[PredictedVibrationSnapshot(receptor_id="R-office", ppv_mm_s=3.8)],
                planned_cost=PlannedCost(total_amount_rub=1_500_000.0, cost_per_m3=75.0),
            ),
        )
        document = build_passport(design, include_predictions=True)
        self.assertEqual(document.executed.role, ROLE_EXECUTED)
        self.assertEqual(document.executed.as_drilled_count, 1)
        self.assertEqual(document.executed.as_charged_count, 1)
        self.assertAlmostEqual(document.executed.explosive_mass_kg, 88.0)
        self.assertEqual(document.measured.role, ROLE_MEASURED)
        self.assertEqual(document.measured.x50_mm, 210.0)
        self.assertEqual(document.measured.ppv_mm_s, 5.1)
        self.assertEqual(document.measured.cost_rub, 1_800_000.0)
        self.assertEqual(document.predicted.x50_mm, 170.0)
        self.assertNotEqual(document.predicted.x50_mm, document.measured.x50_mm)
        self.assertEqual(document.planned_cost.total_amount_rub, 1_500_000.0)
        hole_row = next(row for row in document.holes if row.hole_id == hole.id)
        self.assertEqual(hole_row.executed_diameter_mm, 165.0)
        self.assertEqual(hole_row.executed_charge_kg, 88.0)
        self.assertNotEqual(hole_row.designed_diameter_mm, hole_row.executed_diameter_mm)

    def test_rejects_non_positive_lump_size(self):
        with self.assertRaises(ValueError):
            build_passport(charged_design(), lump_size_mm=0.0)


if __name__ == "__main__":
    unittest.main()
