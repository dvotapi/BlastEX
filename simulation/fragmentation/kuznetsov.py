"""Кузнецов: x50 по Каннингему (общая база с листом «Расчёт») и Розин — Раммлер с фиксированным n."""
from __future__ import annotations

from simulation.fragmentation.base import base_parameters, calibration_warnings, region_point
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.distributions import (
    DEFAULT_KUZNETSOV_N,
    distribution_curve,
    rosin_rammler_oversize_pct,
    rosin_rammler_passing,
    rosin_rammler_size_mm,
)
from simulation.fragmentation.models import (
    Calibration,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)

MODEL_ID = "kuznetsov"
MODEL_VERSION = "2.1.0"


def predict_kuznetsov(
    inputs: FragmentationInputs,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
) -> PredictedFragmentation:
    """x50 общей базы и кривая Розина — Раммлера с n = 1 (или из калибровки)."""
    calibration = calibration or Calibration()
    point = region_point(inputs, settings)
    x50_mm = point.x50_mm
    n = calibration.uniformity_n or DEFAULT_KUZNETSOV_N
    x20_mm = rosin_rammler_size_mm(0.20, x50_mm, n)
    x80_mm = rosin_rammler_size_mm(0.80, x50_mm, n)
    oversize = rosin_rammler_oversize_pct(x50_mm, n, inputs.lump_size_mm)
    curve = distribution_curve(
        lambda size: rosin_rammler_passing(size, x50_mm, n),
        extra_sizes_mm=(x20_mm, x50_mm, x80_mm, inputs.lump_size_mm),
    )
    return PredictedFragmentation(
        x20_mm=round(x20_mm, 1),
        x50_mm=round(x50_mm, 1),
        x80_mm=round(x80_mm, 1),
        oversize_pct=round(oversize, 2),
        powder_factor_kg_m3=round(inputs.powder_factor_kg_m3, 4),
        curve=curve,
        provenance=ModelProvenance(
            model=MODEL_ID,
            model_version=MODEL_VERSION,
            inputs=inputs.to_dict(),
            parameters={**base_parameters(point, inputs), "uniformity_n": n, "distribution": "rosin_rammler"},
            calibration=calibration.to_dict(),
        ),
        warnings=[*point.warnings, *calibration_warnings(calibration)],
    )
