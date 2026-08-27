"""Hole-level snapshot fixtures for BDX-022 spatial ML tests."""
from __future__ import annotations

from design.models import Hole, HoleLoad, Point3
from intelligence.datasets.builder import DatasetSnapshot, TrainingSample
from intelligence.datasets.features import FEATURE_SCHEMA_VERSION
from intelligence.datasets.validation import SampleValidation
from intelligence.spatial.types import (
    METRIC_OVERSIZE,
    METRIC_TOE,
    METRIC_X50,
    ROLE_DESIGNED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
)
from tests.dataset_fixtures import closed_design
from tests.outcome_fixtures import _features


def _hole_row(
    *,
    hole_id: str,
    blast_id: str,
    col: int,
    row: int,
    charge_kg: float,
    burden_m: float,
    powder: float,
    ucs: float,
    predicted_x50: float,
    predicted_oversize: float,
    predicted_toe: float,
    measured_x50: float | None = None,
    measured_oversize: float | None = None,
    measured_toe: float | None = None,
) -> dict:
    x = 4.0 + col * 5.0
    y = 4.0 + row * 4.0
    return {
        "hole_id": hole_id,
        "x": x,
        "y": y,
        "kind": "production",
        "feature_role": ROLE_DESIGNED,
        "features": {
            "x_m": x,
            "y_m": y,
            "burden_m": burden_m,
            "spacing_m": 5.0,
            "diameter_mm": 152.0,
            "length_m": 11.0,
            "subdrill_m": 1.0,
            "charge_kg": charge_kg,
            "stemming_m": 2.5,
            "powder_factor_kg_m3": powder,
            "delay_ms": 25.0,
            "density_kg_m3": 2700.0,
            "ucs_mpa": ucs,
            "wet": 0.0,
        },
        "predicted": {
            METRIC_X50: predicted_x50,
            METRIC_OVERSIZE: predicted_oversize,
            METRIC_TOE: predicted_toe,
        },
        "measured": {
            METRIC_X50: measured_x50,
            METRIC_OVERSIZE: measured_oversize,
            METRIC_TOE: measured_toe,
        },
        "source_blast_id": blast_id,
        "predicted_role": ROLE_PREDICTED,
        "measured_role": ROLE_MEASURED,
    }


def synthetic_spatial_snapshot(
    *,
    n_blasts: int = 4,
    site_id: str = "quarry-1",
    dataset_id: str = "snap-spatial",
    dataset_version: int = 1,
) -> DatasetSnapshot:
    """Several closed blasts, each with a 2x3 hole grid and local labels."""
    samples: list[TrainingSample] = []
    for blast in range(n_blasts):
        ucs = 90.0 + blast * 8.0
        powder = 0.65 + blast * 0.04
        holes = []
        index = 0
        for row in range(2):
            for col in range(3):
                charge = 70.0 + 6.0 * col + blast
                burden = 3.6 + 0.25 * row + 0.05 * blast
                local_x50 = 150.0 + 1.2 * (ucs - 90.0) + 8.0 * (burden - 3.6) - 0.35 * (charge - 70.0)
                local_over = 3.0 + 0.35 * blast + 0.4 * row - 0.05 * col
                local_toe = 0.12 + 0.04 * row + 0.02 * blast
                holes.append(
                    _hole_row(
                        hole_id=f"{row + 1}-{col + 1:02d}",
                        blast_id=f"blast-{blast}",
                        col=col,
                        row=row,
                        charge_kg=charge,
                        burden_m=burden,
                        powder=powder,
                        ucs=ucs,
                        predicted_x50=local_x50 - 6.0,
                        predicted_oversize=max(0.5, local_over - 0.4),
                        predicted_toe=max(0.0, local_toe - 0.03),
                        measured_x50=local_x50,
                        measured_oversize=local_over,
                        measured_toe=local_toe,
                    )
                )
                index += 1
        samples.append(
            TrainingSample(
                source_blast_id=f"blast-{blast}",
                site_id=site_id,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                features=_features(blast, ucs=ucs, powder=powder),
                targets={
                    "FRAGMENTATION": {
                        "x50_mm": 155.0 + 4.0 * blast,
                        "oversize_pct": 3.5 + 0.3 * blast,
                        "predicted_x50_mm": 149.0 + 4.0 * blast,
                        "predicted_oversize_pct": 3.1 + 0.3 * blast,
                    },
                    "BLAST": {"leftover_height_m": 0.15 + 0.05 * blast, "toe_probability": 0.15 + 0.05 * blast},
                },
                provenance={"source_blast_id": f"blast-{blast}", "site_id": site_id},
                validation=SampleValidation(ok=True, closed=True, complete_target_groups=["FRAGMENTATION", "BLAST"]),
                holes=holes,
            )
        )
    return DatasetSnapshot(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        source_blast_ids=[sample.source_blast_id for sample in samples],
        created_at="2024-06-04T00:00:00+00:00",
        site_id=site_id,
        name="synthetic-spatial",
        samples=samples,
        immutable=True,
    )


def multi_hole_design(design_id: str = "spatial-block") -> object:
    """Closed design with a 2x3 production grid for overlay tests."""
    design = closed_design(design_id)
    holes = []
    loads = []
    for row in range(2):
        for col in range(3):
            hole_id = f"{row + 1}-{col + 1:02d}"
            hole = Hole(
                id=hole_id,
                row=row + 1,
                col=col + 1,
                collar=Point3(x=4.0 + col * 5.0, y=4.0 + row * 4.0, z=0.0),
                toe=Point3(x=4.0 + col * 5.0, y=4.0 + row * 4.0, z=-11.0),
                diameter_mm=152.0,
                subdrill_m=1.0,
            )
            holes.append(hole)
            loads.append(
                HoleLoad(
                    hole_id=hole_id,
                    total_charge_kg=72.0 + 5.0 * col,
                    influence_volume_m3=90.0,
                    specific_q_kg_m3=0.70 + 0.04 * col,
                )
            )
    from design.models import Detonator

    design.holes = holes
    design.loads = loads
    design.network.electronic_times_ms = {hole.id: 25.0 + 5.0 * hole.col for hole in holes}
    design.network.detonators = [
        Detonator(id=f"det-{hole.id}", hole_id=hole.id, delay_ms=25.0 + 5.0 * hole.col) for hole in holes
    ]
    if design.as_drilled_holes:
        design.as_drilled_holes[0].design_hole_id = holes[0].id
    if design.as_charged_holes:
        design.as_charged_holes[0].design_hole_id = holes[0].id
    if design.as_fired_holes:
        design.as_fired_holes[0].design_hole_id = holes[0].id
    return design
