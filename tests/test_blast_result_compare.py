import unittest

from design.blast_result import (
    ActualCost,
    BlastResult,
    ComparisonBasis,
    DesignedBackbreak,
    DesignedMuckpile,
    MeasuredBackbreak,
    MeasuredMuckpile,
    MeasuredToeCondition,
    MeasuredVibration,
    PlannedCost,
    PredictedVibrationSnapshot,
    compare_result,
    record_blast_result,
)
from design.models import BlastDesign, Hole, HoleLoad, Point3
from simulation.fragmentation.models import (
    ROLE_MEASURED,
    ROLE_PREDICTED,
    DesignedFragmentationTarget,
    MeasuredFragmentation,
    ModelProvenance,
    PredictedFragmentation,
)


def _design() -> BlastDesign:
    return BlastDesign(
        design_id="cmp-1",
        holes=[
            Hole(
                id="1-01",
                row=1,
                col=1,
                collar=Point3(x=0.0, y=0.0, z=0.0),
                toe=Point3(x=0.0, y=0.0, z=-10.0),
                diameter_mm=152.0,
            )
        ],
        loads=[HoleLoad(hole_id="1-01", total_charge_kg=70.0)],
    )


def _predicted() -> PredictedFragmentation:
    return PredictedFragmentation(
        x20_mm=80.0,
        x50_mm=160.0,
        x80_mm=300.0,
        oversize_pct=3.5,
        powder_factor_kg_m3=0.72,
        provenance=ModelProvenance(model="kuzram", model_version="1"),
    )


class BlastResultCompareTests(unittest.TestCase):
    def test_predicted_vs_measured_and_cost_deltas(self):
        design = _design()
        hole_before = design.holes[0].to_dict()
        load_before = design.loads[0].to_dict()
        record_blast_result(
            design,
            BlastResult(
                design_id="cmp-1",
                fragmentation=MeasuredFragmentation(x20_mm=90.0, x50_mm=190.0, x80_mm=360.0, oversize_pct=6.0),
                vibration=MeasuredVibration(ppv_mm_s=4.8, frequency_hz=16.0, receptor_id="R-1"),
                muckpile=MeasuredMuckpile(length_m=45.0, width_m=20.0, height_m=7.0, volume_m3=2500.0, throw_m=14.0),
                backbreak=MeasuredBackbreak(max_m=1.2, mean_m=0.7),
                toe_condition=MeasuredToeCondition(condition="minor", leftover_height_m=0.35),
                cost_actual=ActualCost(total_amount_rub=1_800_000.0, cost_per_m3=90.0, variable_total_rub=1_100_000.0),
            ),
            basis=ComparisonBasis(
                predicted_fragmentation=_predicted(),
                predicted_vibration=[PredictedVibrationSnapshot(receptor_id="R-1", ppv_mm_s=3.9, receptor_name="Офис")],
                planned_cost=PlannedCost(total_amount_rub=1_500_000.0, cost_per_m3=75.0, variable_total_rub=900_000.0),
                designed_fragmentation=DesignedFragmentationTarget(lump_size_mm=400.0, max_oversize_pct=5.0),
                designed_muckpile=DesignedMuckpile(length_m=40.0, width_m=18.0, height_m=6.0, volume_m3=2200.0, throw_m=10.0),
                designed_backbreak=DesignedBackbreak(max_m=0.6, mean_m=0.3),
                designed_toe_condition="clean",
            ),
        )
        report = compare_result(design)
        self.assertTrue(report["has_result"])
        self.assertEqual(report["result"]["fragmentation"]["role"], ROLE_MEASURED)
        self.assertEqual(report["result"]["basis"]["predicted_fragmentation"]["role"], ROLE_PREDICTED)

        p50 = next(row for row in report["predicted_vs_measured"] if row["metric"] == "p50_mm")
        self.assertAlmostEqual(p50["predicted"], 160.0)
        self.assertAlmostEqual(p50["measured"], 190.0)
        self.assertAlmostEqual(p50["measured_minus_predicted"], 30.0)

        ppv = next(row for row in report["predicted_vs_measured"] if row["metric"] == "ppv_mm_s")
        self.assertAlmostEqual(ppv["predicted"], 3.9)
        self.assertAlmostEqual(ppv["measured"], 4.8)
        freq = next(row for row in report["predicted_vs_measured"] if row["metric"] == "frequency_hz")
        self.assertAlmostEqual(freq["measured"], 16.0)
        self.assertIsNone(freq["predicted"])

        oversize = next(row for row in report["designed_vs_actual"] if row["metric"] == "oversize_pct")
        self.assertAlmostEqual(oversize["designed"], 5.0)
        self.assertAlmostEqual(oversize["actual"], 6.0)
        p80 = next(row for row in report["designed_vs_actual"] if row["metric"] == "p80_mm")
        self.assertAlmostEqual(p80["designed"], 400.0)
        self.assertAlmostEqual(p80["actual"], 360.0)

        length = next(row for row in report["designed_vs_actual"] if row["metric"] == "length_m")
        self.assertAlmostEqual(length["designed"], 40.0)
        self.assertAlmostEqual(length["actual"], 45.0)
        toe = next(row for row in report["designed_vs_actual"] if row["metric"] == "toe_condition")
        self.assertTrue(toe["mismatch"])
        self.assertEqual(toe["designed"], "clean")
        self.assertEqual(toe["actual"], "minor")

        total = next(row for row in report["planned_vs_actual_cost"] if row["metric"] == "total_amount_rub")
        self.assertAlmostEqual(total["designed"], 1_500_000.0)
        self.assertAlmostEqual(total["actual"], 1_800_000.0)
        self.assertAlmostEqual(total["actual_minus_designed"], 300_000.0)

        self.assertEqual(design.holes[0].to_dict(), hole_before)
        self.assertEqual(design.loads[0].to_dict(), load_before)
        self.assertAlmostEqual(design.blast_result.basis.predicted_fragmentation.x50_mm, 160.0)

    def test_compare_empty_design_does_not_invent_result(self):
        design = _design()
        report = compare_result(design)
        self.assertFalse(report["has_result"])
        self.assertTrue(report["warnings"])
        self.assertIsNone(report["result"])
        self.assertIsNone(design.blast_result)

    def test_compare_does_not_mutate_predicted_snapshot(self):
        design = _design()
        predicted = _predicted()
        record_blast_result(
            design,
            BlastResult(design_id="cmp-1", fragmentation=MeasuredFragmentation(x50_mm=200.0)),
            basis=ComparisonBasis(predicted_fragmentation=predicted),
        )
        before = design.blast_result.basis.predicted_fragmentation.to_dict()
        compare_result(design)
        self.assertEqual(design.blast_result.basis.predicted_fragmentation.to_dict(), before)
        self.assertEqual(design.blast_result.basis.predicted_fragmentation.role, ROLE_PREDICTED)
        self.assertEqual(design.blast_result.fragmentation.role, ROLE_MEASURED)


if __name__ == "__main__":
    unittest.main()
