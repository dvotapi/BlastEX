"""Closed-blast fixtures for BDX-011 dataset tests."""
from __future__ import annotations

from design.blast_result import (
    ActualCost,
    BlastResult,
    ComparisonBasis,
    MeasuredBackbreak,
    MeasuredMuckpile,
    MeasuredToeCondition,
    MeasuredVibration,
    PlannedCost,
)
from design.models import (
    ROLE_EXECUTED,
    ROLE_MEASURED,
    AsChargedHole,
    AsDrilledHole,
    AsFiredHole,
    BenchSurface,
    BlastDesign,
    BlastDomain,
    BlockContour,
    DataProvenance,
    Detonator,
    Hole,
    HoleLoad,
    InitiationNetwork,
    Point3,
    Receptor,
    RockPropertySet,
    default_vibration_model,
)
from simulation.fragmentation.models import (
    DesignedFragmentationTarget,
    MeasuredFragmentation,
    ModelProvenance,
    PredictedFragmentation,
)

def executed_provenance() -> DataProvenance:
    return DataProvenance(
        source="field",
        method="logger",
        timestamp="2024-06-01T08:00:00+00:00",
        role=ROLE_EXECUTED,
    )


def measured_provenance() -> DataProvenance:
    return DataProvenance(
        source="field",
        method="sieve",
        timestamp="2024-06-01T16:00:00+00:00",
        role=ROLE_MEASURED,
    )


def closed_design(design_id: str = "blast-closed") -> BlastDesign:
    hole = Hole(
        id="1-01",
        row=1,
        col=1,
        collar=Point3(x=2.0, y=2.0, z=0.0),
        toe=Point3(x=2.0, y=2.0, z=-11.0),
        diameter_mm=152.0,
        subdrill_m=1.0,
    )
    return BlastDesign(
        design_id=design_id,
        name="Закрытый блок",
        updated_at="2024-06-01T12:00:00+00:00",
        rock_name="гранит",
        explosive_key="anfo",
        contour=BlockContour(
            vertices=[Point3(x=x, y=y, z=0.0) for x, y in ((0, 0), (20, 0), (20, 16), (0, 16))],
            free_faces=[[0, 1]],
            bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=75.0),
            name="Уступ 10",
        ),
        holes=[hole],
        loads=[
            HoleLoad(
                hole_id=hole.id,
                total_charge_kg=80.0,
                influence_volume_m3=100.0,
                specific_q_kg_m3=0.8,
            )
        ],
        pattern_params={"pattern": "rectangular", "spacing_a_m": 5.0, "burden_b_m": 4.0},
        domains=[
            BlastDomain(
                id="dom-1",
                name="гранит",
                properties=RockPropertySet(
                    density_kg_m3=2700.0,
                    ucs_mpa=120.0,
                    rqd_pct=68.0,
                    fracturing="moderate",
                    blastability="medium",
                    water_condition="dry",
                ),
                provenance=DataProvenance(source="core", method="lab", timestamp="2024-05-01T00:00:00+00:00"),
            )
        ],
        network=InitiationNetwork(
            system="electronic",
            timing_mode="row",
            detonators=[Detonator(id="det-1", hole_id=hole.id, delay_ms=25.0)],
            electronic_times_ms={hole.id: 25.0},
        ),
        receptors=[
            Receptor(id="R-1", name="Офис", location=Point3(x=80.0, y=10.0, z=0.0), ppv_limit_mm_s=10.0)
        ],
        vibration_models=[default_vibration_model()],
        as_drilled_holes=[
            AsDrilledHole(
                design_hole_id=hole.id,
                actual_collar=Point3(x=2.2, y=2.1, z=0.0),
                actual_toe=Point3(x=2.3, y=2.1, z=-11.2),
                actual_depth=11.2,
                actual_diameter=152.0,
                provenance=executed_provenance(),
            )
        ],
        as_charged_holes=[
            AsChargedHole(
                design_hole_id=hole.id,
                charge_mass_kg=78.0,
                stemming_length_m=2.4,
                explosive_product="anfo",
                provenance=executed_provenance(),
            )
        ],
        as_fired_holes=[
            AsFiredHole(
                design_hole_id=hole.id,
                detonator=Detonator(id="det-1", hole_id=hole.id, delay_ms=25.0),
                programmed_time_ms=25.0,
                verified_time_ms=27.0,
                provenance=executed_provenance(),
            )
        ],
        blast_result=BlastResult(
            design_id=design_id,
            fragmentation=MeasuredFragmentation(
                x20_mm=90.0, x50_mm=170.0, x80_mm=320.0, oversize_pct=6.0, source="image", method="split"
            ),
            vibration=MeasuredVibration(ppv_mm_s=4.8, frequency_hz=16.0, receptor_id="R-1", source="seismograph"),
            muckpile=MeasuredMuckpile(length_m=40.0, width_m=16.0, height_m=6.0, volume_m3=2100.0, throw_m=11.0),
            backbreak=MeasuredBackbreak(max_m=1.1, mean_m=0.5, crest_loss_m=0.2),
            toe_condition=MeasuredToeCondition(condition="minor", leftover_height_m=0.3),
            cost_actual=ActualCost(total_amount_rub=1_900_000.0, cost_per_m3=95.0, secondary_breaking_rub=40_000.0),
            basis=ComparisonBasis(
                predicted_fragmentation=PredictedFragmentation(
                    x20_mm=80.0,
                    x50_mm=150.0,
                    x80_mm=280.0,
                    oversize_pct=4.0,
                    powder_factor_kg_m3=0.8,
                    provenance=ModelProvenance(model="kuzram", model_version="1"),
                ),
                designed_fragmentation=DesignedFragmentationTarget(lump_size_mm=400.0, max_oversize_pct=5.0),
                planned_cost=PlannedCost(total_amount_rub=1_700_000.0, cost_per_m3=85.0),
            ),
            recorded_at="2024-06-01T16:00:00+00:00",
            provenance=measured_provenance(),
        ),
    )
