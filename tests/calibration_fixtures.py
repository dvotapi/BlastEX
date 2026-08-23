"""Tiny synthetic snapshots for residual-calibration tests (sklearn RF)."""
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


def synthetic_snapshot(
    *,
    n: int = 8,
    site_id: str = "quarry-1",
    dataset_id: str = "snap-ml",
    dataset_version: int = 1,
    model_type: str = "kuzram_residual",
) -> DatasetSnapshot:
    samples: list[TrainingSample] = []
    for index in range(n):
        ucs = 80.0 + index * 10.0
        powder = 0.6 + index * 0.04
        baseline_x50 = 150.0
        measured_x50 = baseline_x50 + 1.5 * (ucs - 80.0)
        baseline_oversize = 4.0
        measured_oversize = baseline_oversize + 0.3 * index
        baseline_ppv = 5.0
        measured_ppv = baseline_ppv + 0.25 * index
        samples.append(
            TrainingSample(
                source_blast_id=f"blast-{index}",
                site_id=site_id,
                feature_schema_version=FEATURE_SCHEMA_VERSION,
                features=_features(index, ucs=ucs, powder=powder),
                targets={
                    "FRAGMENTATION": {
                        "x50_mm": measured_x50,
                        "oversize_pct": measured_oversize,
                        "predicted_x50_mm": baseline_x50,
                        "predicted_oversize_pct": baseline_oversize,
                    },
                    "VIBRATION": {
                        "ppv_mm_s": measured_ppv,
                        "max_ppv_mm_s": measured_ppv,
                        "predicted_max_ppv_mm_s": baseline_ppv,
                    },
                },
                provenance={"source_blast_id": f"blast-{index}", "site_id": site_id},
                validation=SampleValidation(ok=True, closed=True, complete_target_groups=["FRAGMENTATION", "VIBRATION"]),
            )
        )
    return DatasetSnapshot(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        source_blast_ids=[sample.source_blast_id for sample in samples],
        created_at="2024-06-02T00:00:00+00:00",
        site_id=site_id,
        name="synthetic",
        samples=samples,
        immutable=True,
    )


def varied_closed_designs(n: int = 6):
    from design.blast_result import PredictedVibrationSnapshot

    designs = []
    for index in range(n):
        design = closed_design(f"closed-{index}")
        design.domains[0].properties.ucs_mpa = 90.0 + index * 6
        design.blast_result.fragmentation.x50_mm = 150.0 + 3.0 * index
        design.blast_result.fragmentation.oversize_pct = 4.0 + 0.5 * index
        design.blast_result.basis.predicted_vibration = [
            PredictedVibrationSnapshot(receptor_id="R-1", ppv_mm_s=3.5, receptor_name="Офис")
        ]
        design.blast_result.vibration.ppv_mm_s = 3.5 + 0.4 * index
        designs.append(design)
    return designs
