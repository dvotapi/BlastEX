import unittest

from design.blast_result import (
    ROLE_DESIGNED,
    ActualCost,
    BlastResult,
    ComparisonBasis,
    DesignedBackbreak,
    DesignedMuckpile,
    FlyrockObservation,
    MeasuredBackbreak,
    MeasuredMuckpile,
    MeasuredToeCondition,
    MeasuredVibration,
    PlannedCost,
    PredictedVibrationSnapshot,
    SecondaryBreaking,
    merge_basis,
    normalize_result,
    record_blast_result,
)
from design.models import (
    ROLE_MEASURED,
    ROLE_PREDICTED,
    BlastDesign,
    Hole,
    HoleLoad,
    Point3,
    VibrationMeasurement,
)
from simulation.fragmentation.models import (
    DesignedFragmentationTarget,
    MeasuredFragmentation,
    ModelProvenance,
    PredictedFragmentation,
)


def _design() -> BlastDesign:
    hole = Hole(
        id="1-01",
        row=1,
        col=1,
        collar=Point3(x=0.0, y=0.0, z=0.0),
        toe=Point3(x=0.0, y=0.0, z=-10.0),
        diameter_mm=152.0,
    )
    return BlastDesign(
        design_id="br-1",
        holes=[hole],
        loads=[HoleLoad(hole_id="1-01", total_charge_kg=70.0)],
    )


def _predicted() -> PredictedFragmentation:
    return PredictedFragmentation(
        x20_mm=80.0,
        x50_mm=150.0,
        x80_mm=280.0,
        oversize_pct=4.0,
        powder_factor_kg_m3=0.7,
        provenance=ModelProvenance(model="kuzram", model_version="1"),
    )


class BlastResultModelTests(unittest.TestCase):
    def test_round_trip_forces_measured_role(self):
        item = BlastResult(
            design_id="br-1",
            fragmentation=MeasuredFragmentation(x20_mm=90.0, x50_mm=170.0, x80_mm=310.0, oversize_pct=6.5, source="sieve"),
            vibration=MeasuredVibration(ppv_mm_s=3.4, frequency_hz=18.0, receptor_id="R-1"),
            muckpile=MeasuredMuckpile(length_m=42.0, width_m=18.0, height_m=6.0, volume_m3=2100.0, throw_m=12.0),
            backbreak=MeasuredBackbreak(max_m=1.4, mean_m=0.8, crest_loss_m=0.3),
            toe_condition=MeasuredToeCondition(condition="minor", leftover_height_m=0.4),
            flyrock_observations=[FlyrockObservation(max_range_m=80.0, count=2)],
            secondary_breaking=SecondaryBreaking(volume_m3=40.0, hours=3.0, cost_rub=120000.0, method="hammer"),
            cost_actual=ActualCost(total_amount_rub=1_850_000.0, cost_per_m3=92.0),
        )
        restored = BlastResult.from_dict(item.to_dict())
        self.assertEqual(restored.role, ROLE_MEASURED)
        self.assertEqual(restored.fragmentation.role, ROLE_MEASURED)
        self.assertEqual(restored.vibration.role, ROLE_MEASURED)
        self.assertAlmostEqual(restored.fragmentation.x50_mm, 170.0)
        self.assertAlmostEqual(restored.vibration.frequency_hz, 18.0)
        self.assertEqual(restored.toe_condition.condition, "minor")
        self.assertEqual(restored.muckpile.role, ROLE_MEASURED)
        self.assertEqual(restored.cost_actual.role, ROLE_MEASURED)

    def test_p20_aliases_load_as_x20(self):
        measured = MeasuredFragmentation.from_dict({"P20": 70, "P50": 140, "P80": 250, "oversize": 8})
        self.assertEqual(measured.role, ROLE_MEASURED)
        self.assertAlmostEqual(measured.x20_mm, 70.0)
        self.assertAlmostEqual(measured.x50_mm, 140.0)
        self.assertAlmostEqual(measured.x80_mm, 250.0)
        self.assertAlmostEqual(measured.oversize_pct, 8.0)
        payload = measured.to_dict()
        self.assertEqual(payload["p50_mm"], payload["x50_mm"])
        self.assertEqual(payload["role"], ROLE_MEASURED)

    def test_normalize_keeps_predicted_in_basis_only(self):
        predicted = _predicted()
        item = BlastResult(
            design_id="br-1",
            fragmentation=MeasuredFragmentation(x50_mm=200.0, x80_mm=360.0),
            basis=ComparisonBasis(predicted_fragmentation=predicted),
        )
        normalized = normalize_result(item)
        self.assertEqual(normalized.fragmentation.role, ROLE_MEASURED)
        self.assertEqual(normalized.basis.predicted_fragmentation.role, ROLE_PREDICTED)
        self.assertAlmostEqual(normalized.basis.predicted_fragmentation.x50_mm, 150.0)
        self.assertAlmostEqual(normalized.fragmentation.x50_mm, 200.0)
        self.assertNotEqual(normalized.fragmentation.x50_mm, normalized.basis.predicted_fragmentation.x50_mm)

    def test_record_does_not_overwrite_designed_or_predicted(self):
        design = _design()
        hole_before = design.holes[0].to_dict()
        load_before = design.loads[0].to_dict()
        predicted = _predicted()
        recorded = record_blast_result(
            design,
            BlastResult(
                design_id="br-1",
                fragmentation=MeasuredFragmentation(x20_mm=95.0, x50_mm=180.0, x80_mm=330.0, oversize_pct=7.0),
            ),
            basis=ComparisonBasis(
                predicted_fragmentation=predicted,
                planned_cost=PlannedCost(total_amount_rub=1_600_000.0),
                designed_fragmentation=DesignedFragmentationTarget(lump_size_mm=400.0, max_oversize_pct=5.0),
            ),
        )
        self.assertEqual(design.holes[0].to_dict(), hole_before)
        self.assertEqual(design.loads[0].to_dict(), load_before)
        self.assertAlmostEqual(design.loads[0].total_charge_kg, 70.0)
        self.assertEqual(recorded.role, ROLE_MEASURED)
        self.assertEqual(design.blast_result.basis.predicted_fragmentation.role, ROLE_PREDICTED)
        self.assertAlmostEqual(design.blast_result.basis.predicted_fragmentation.x50_mm, 150.0)
        self.assertAlmostEqual(design.blast_result.fragmentation.x50_mm, 180.0)
        self.assertTrue(recorded.recorded_at)

        second = record_blast_result(
            design,
            BlastResult(
                design_id="br-1",
                fragmentation=MeasuredFragmentation(x50_mm=190.0, x80_mm=340.0, oversize_pct=8.0),
                cost_actual=ActualCost(total_amount_rub=1_720_000.0),
            ),
        )
        self.assertEqual(design.holes[0].to_dict(), hole_before)
        self.assertAlmostEqual(second.basis.predicted_fragmentation.x50_mm, 150.0)
        self.assertEqual(second.basis.predicted_fragmentation.role, ROLE_PREDICTED)
        self.assertAlmostEqual(second.fragmentation.x50_mm, 190.0)
        self.assertEqual(second.fragmentation.role, ROLE_MEASURED)
        self.assertAlmostEqual(second.cost_actual.total_amount_rub, 1_720_000.0)
        self.assertEqual(second.cost_actual.role, ROLE_MEASURED)
        self.assertEqual(second.basis.planned_cost.role, ROLE_DESIGNED)

    def test_legacy_design_without_blast_result_loads(self):
        design = BlastDesign.from_dict(
            {
                "design_id": "legacy-br",
                "holes": [],
                "contour": {"vertices": [], "free_faces": [], "bench": {}, "name": "Блок"},
            }
        )
        self.assertIsNone(design.blast_result)
        self.assertEqual(design.to_dict()["blast_result"], None)

    def test_merge_basis_does_not_copy_measured_into_predicted(self):
        existing = ComparisonBasis(predicted_fragmentation=_predicted())
        incoming = ComparisonBasis()
        merged = merge_basis(existing, incoming)
        self.assertEqual(merged.predicted_fragmentation.role, ROLE_PREDICTED)
        self.assertAlmostEqual(merged.predicted_fragmentation.x80_mm, 280.0)

    def test_vibration_measurement_keeps_frequency(self):
        item = VibrationMeasurement(id="VM-1", receptor_id="R-1", ppv_mm_s=2.2, frequency_hz=12.5)
        restored = VibrationMeasurement.from_dict(item.to_dict())
        self.assertEqual(restored.role, ROLE_MEASURED)
        self.assertAlmostEqual(restored.frequency_hz, 12.5)

    def test_designed_muckpile_role_stays_designed(self):
        designed = DesignedMuckpile.from_dict({"length_m": 40, "width_m": 16, "role": "measured"})
        self.assertEqual(designed.role, ROLE_DESIGNED)
        measured = MeasuredMuckpile.from_dict({"length_m": 44, "role": "predicted"})
        self.assertEqual(measured.role, ROLE_MEASURED)
        backbreak = DesignedBackbreak.from_dict({"max_m": 0.5, "role": "measured"})
        self.assertEqual(backbreak.role, ROLE_DESIGNED)
        snapshot = PredictedVibrationSnapshot.from_dict({"receptor_id": "R-1", "ppv_mm_s": 4.1, "role": "measured"})
        self.assertEqual(snapshot.role, ROLE_PREDICTED)


if __name__ == "__main__":
    unittest.main()
