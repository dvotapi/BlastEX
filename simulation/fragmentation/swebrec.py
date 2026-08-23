"""Swebrec size distribution (Ouchterlony) on top of a Kuznetsov median."""
from __future__ import annotations

from simulation.fragmentation.distributions import (
    DEFAULT_SWEBREC_B,
    distribution_curve,
    swebrec_oversize_pct,
    swebrec_passing,
    swebrec_size_mm,
)
from simulation.fragmentation.kuznetsov import kuznetsov_x50_mm, rock_factor_A
from simulation.fragmentation.models import (
    Calibration,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)
from simulation.fragmentation.units import length_mm_from_m, relative_weight_strength

MODEL_ID = "swebrec"
MODEL_VERSION = "1.0.0"


def default_xmax_mm(burden_m: float, spacing_m: float, x50_mm: float) -> float:
    """Largest free dimension of the burden prism, millimetres.

    Falls back to 2 × x50 when the prism is degenerate so x50 < xmax.
    """
    prism_mm = length_mm_from_m(max(burden_m, spacing_m, 0.0))
    floor = max(x50_mm * 2.0, x50_mm + 1.0)
    return max(prism_mm, floor)


def predict_swebrec(inputs: FragmentationInputs, calibration: Calibration | None = None) -> PredictedFragmentation:
    """Swebrec prediction for one influence region."""
    calibration = calibration or Calibration()
    factor_A = calibration.rock_factor_A or rock_factor_A(inputs.rock_ucs_mpa, inputs.rock_density_t_m3)
    re_weight = relative_weight_strength(inputs.explosive_energy_mj_kg)
    x50_mm = kuznetsov_x50_mm(factor_A, inputs.powder_factor_kg_m3, inputs.charge_mass_kg, re_weight)
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
                "rock_factor_A": factor_A,
                "re_weight": re_weight,
                "swebrec_b": b,
                "xmax_mm": xmax_mm,
                "distribution": "swebrec",
            },
            calibration=calibration.to_dict(),
        ),
    )
