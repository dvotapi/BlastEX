"""Swebrec (Оухтерлони) поверх x50 общей базы Каннингема."""
from __future__ import annotations

from simulation.fragmentation.base import base_parameters, calibration_warnings, region_point
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.distributions import (
    DEFAULT_SWEBREC_B,
    default_xmax_mm,
    distribution_curve,
    swebrec_oversize_pct,
    swebrec_passing,
    swebrec_size_mm,
)
from simulation.fragmentation.models import (
    Calibration,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)

MODEL_ID = "swebrec"
MODEL_VERSION = "2.1.0"


def predict_swebrec(
    inputs: FragmentationInputs,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
) -> PredictedFragmentation:
    """Кривая Swebrec с x50 общей базы; xmax — наибольший размер призмы ЛНС × шаг."""
    calibration = calibration or Calibration()
    point = region_point(inputs, settings)
    x50_mm = point.x50_mm
    xmax_mm = calibration.xmax_mm or default_xmax_mm(inputs.burden_m, inputs.spacing_m, x50_mm)
    if xmax_mm <= x50_mm:
        xmax_mm = default_xmax_mm(inputs.burden_m, inputs.spacing_m, x50_mm)
    b = calibration.swebrec_b or DEFAULT_SWEBREC_B
    x20_mm = swebrec_size_mm(0.20, x50_mm, xmax_mm, b)
    x80_mm = swebrec_size_mm(0.80, x50_mm, xmax_mm, b)
    oversize = swebrec_oversize_pct(inputs.lump_size_mm, x50_mm, xmax_mm, b)
    curve = distribution_curve(
        lambda size: swebrec_passing(size, x50_mm, xmax_mm, b),
        extra_sizes_mm=(x20_mm, x50_mm, x80_mm, inputs.lump_size_mm, xmax_mm),
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
            parameters={
                **base_parameters(point, inputs),
                "swebrec_b": b,
                "xmax_mm": xmax_mm,
                "distribution": "swebrec",
            },
            calibration=calibration.to_dict(),
        ),
        warnings=[*point.warnings, *calibration_warnings(calibration)],
    )
