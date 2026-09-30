"""Kuz-Ram: x50 и n по Каннингему — те же, что на листе «Расчёт», — и кривая Розина — Раммлера."""
from __future__ import annotations

from simulation.fragmentation.base import base_parameters, calibration_warnings, region_point
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.distributions import (
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

MODEL_ID = "kuzram"
MODEL_VERSION = "2.0.0"


def predict_kuzram(
    inputs: FragmentationInputs,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
) -> PredictedFragmentation:
    """Прогноз одного региона. Без поправки n негабарит — ровно число predict_point."""
    calibration = calibration or Calibration()
    point = region_point(inputs, settings)
    x50_mm = point.x50_mm
    if calibration.uniformity_n:
        n = calibration.uniformity_n
        oversize = rosin_rammler_oversize_pct(x50_mm, n, inputs.lump_size_mm)
    else:
        n = point.uniformity.value
        oversize = point.oversize_pct
    x20_mm = rosin_rammler_size_mm(0.20, x50_mm, n)
    x80_mm = rosin_rammler_size_mm(0.80, x50_mm, n)
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
