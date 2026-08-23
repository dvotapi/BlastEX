"""Tiny synthetic snapshots for specialised outcome-model tests (sklearn RF)."""
from __future__ import annotations

from intelligence.datasets.builder import DatasetSnapshot, TrainingSample
from intelligence.datasets.features import FEATURE_SCHEMA_VERSION
from intelligence.datasets.validation import SampleValidation
from tests.dataset_fixtures import closed_design


def _features(index: int, *, ucs: float, powder: float, k: float = 500.0) -> dict:
    return {
        "SITE": {"site_id": "quarry-1", "design_id": f"blast-{index}"},
        "GEOLOGY": {
            "mean_density_kg_m3": 2700.0,
            "mean_ucs_mpa": ucs,
            "mean_rqd_pct": 60.0 + index,
        },
        "GEOMETRY": {
            "mean_spacing_m": 5.0,
            "mean_burden_m": 4.0,
            "mean_diameter_mm": 152.0,
            "mean_depth_m": 11.0,
            "mean_subdrill_m": 1.0,
        },
        "CHARGING": {
            "mean_charge_kg": 80.0 + index,
            "mean_powder_factor_kg_m3": powder,
            "mean_stemming_m": 2.5,
        },
        "TIMING": {"mean_delay_ms": 25.0},
        "EXECUTION": {"mean_collar_offset_m": 0.2, "fired_coverage": 1.0},
        "ENVIRONMENT": {
            "wet_hole_fraction": 0.1,
            "nearest_receptor_distance_m": 80.0,
            "vibration_model_k": k,
            "vibration_model_n": 1.6,
        },
    }


def synthetic_outcome_snapshot(
    *,
    n: int = 8,
    site_id: str = "quarry-1",
    dataset_id: str = "snap-outcomes",
    dataset_version: int = 1,
) -> DatasetSnapshot:
    samples: list[TrainingSample] = []
    for index in range(n):
        ucs = 80.0 + index * 10.0
        powder = 0.6 + index * 0.04
        leftover = 0.1 + 0.12 * index
        samples.append(
            TrainingSample(
                source_blast_id=f"blast-{index}",
                site_id=site_id,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                features=_features(index, ucs=ucs, powder=powder),
                targets={
                    "FRAGMENTATION": {
                        "x50_mm": 140.0 + 1.8 * (ucs - 80.0),
                        "x80_mm": 280.0 + 2.4 * (ucs - 80.0),
                        "oversize_pct": 3.5 + 0.4 * index,
                    },
                    "VIBRATION": {
                        "ppv_mm_s": 4.0 + 0.35 * index,
                        "max_ppv_mm_s": 4.0 + 0.35 * index,
                        "frequency_hz": 12.0 + 0.6 * index,
                        "max_frequency_hz": 12.0 + 0.6 * index,
                    },
                    "BLAST": {
                        "leftover_height_m": leftover,
                        "toe_condition": "minor" if leftover < 0.4 else "present",
                        "backbreak_max_m": 0.4 + 0.1 * index,
                        "muckpile_throw_m": 8.0 + 0.5 * index,
                    },
                    "PERFORMANCE": {
                        "leftover_height_m": leftover,
                        "secondary_breaking_volume_m3": 5.0 + index,
                    },
                    "ECONOMICS": {
                        "total_amount_rub": 1_800_000.0 + 20_000.0 * index,
                    },
                },
                provenance={"source_blast_id": f"blast-{index}", "site_id": site_id},
                validation=SampleValidation(
                    ok=True,
                    closed=True,
                    complete_target_groups=["FRAGMENTATION", "VIBRATION", "BLAST"],
                ),
            )
        )
    return DatasetSnapshot(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        source_blast_ids=[sample.source_blast_id for sample in samples],
        created_at="2024-06-03T00:00:00+00:00",
        site_id=site_id,
        name="synthetic-outcomes",
        samples=samples,
        immutable=True,
    )


def varied_closed_outcome_designs(n: int = 6):
    designs = []
    for index in range(n):
        design = closed_design(f"closed-out-{index}")
        design.domains[0].properties.ucs_mpa = 90.0 + index * 6
        design.blast_result.fragmentation.x50_mm = 150.0 + 4.0 * index
        design.blast_result.fragmentation.x80_mm = 300.0 + 8.0 * index
        design.blast_result.fragmentation.oversize_pct = 4.0 + 0.6 * index
        design.blast_result.vibration.ppv_mm_s = 3.5 + 0.4 * index
        design.blast_result.vibration.frequency_hz = 14.0 + 0.5 * index
        design.blast_result.toe_condition.leftover_height_m = 0.15 + 0.1 * index
        design.blast_result.toe_condition.condition = "minor" if index < 3 else "present"
        designs.append(design)
    return designs
