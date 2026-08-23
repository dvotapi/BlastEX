"""Kuz-Ram: Kuznetsov x50 plus Cunningham uniformity and Rosin–Rammler."""
from __future__ import annotations

from simulation.fragmentation.distributions import (
    distribution_curve,
    rosin_rammler_oversize_pct,
    rosin_rammler_passing,
    rosin_rammler_size_mm,
)
from simulation.fragmentation.kuznetsov import kuznetsov_x50_mm, rock_factor_A
from simulation.fragmentation.models import (
    Calibration,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)
from simulation.fragmentation.units import length_m_from_mm, relative_weight_strength

MODEL_ID = "kuzram"
MODEL_VERSION = "1.0.0"

# Cunningham n is clamped so a very tight B/d ratio cannot go negative.
MIN_UNIFORMITY_N = 0.8


def cunningham_uniformity_n(
    burden_m: float,
    diameter_m: float,
    spacing_to_burden: float,
    drill_deviation_m: float = 0.0,
) -> float:
    """Cunningham uniformity index n.

    n = (2.2 − 14 B/d) × (1 + (S/B − 1)/2) × (1 − W/B)

    ``W`` here is drilling accuracy (m), not burden. Burden is ``B``.
    Matches ``Blast.py`` when ``drill_deviation_m`` is 0.
    """
    if diameter_m <= 0:
        return MIN_UNIFORMITY_N
    n = (2.2 - 14.0 * (burden_m / diameter_m)) * (1.0 + (spacing_to_burden - 1.0) / 2.0)
    if burden_m > 0.0 and drill_deviation_m > 0.0:
        n *= max(0.0, 1.0 - drill_deviation_m / burden_m)
    return max(MIN_UNIFORMITY_N, n)


def spacing_to_burden_ratio(spacing_m: float, burden_m: float, fallback: float = 1.25) -> float:
    if burden_m <= 0:
        return fallback
    return spacing_m / burden_m


def kuzram_parameters(inputs: FragmentationInputs, calibration: Calibration | None = None) -> dict[str, float]:
    """Rock factor, RE weight, Cunningham n and charged diameter in metres."""
    calibration = calibration or Calibration()
    factor_A = calibration.rock_factor_A or rock_factor_A(inputs.rock_ucs_mpa, inputs.rock_density_t_m3)
    re_weight = relative_weight_strength(inputs.explosive_energy_mj_kg)
    diameter_m = length_m_from_mm(inputs.diameter_mm) * inputs.hole_oversize_coeff
    ratio = spacing_to_burden_ratio(inputs.spacing_m, inputs.burden_m)
    n = calibration.uniformity_n or cunningham_uniformity_n(
        inputs.burden_m,
        diameter_m,
        ratio,
        drill_deviation_m=calibration.drill_deviation_m or 0.0,
    )
    x50_mm = kuznetsov_x50_mm(factor_A, inputs.powder_factor_kg_m3, inputs.charge_mass_kg, re_weight)
    return {
        "rock_factor_A": factor_A,
        "re_weight": re_weight,
        "uniformity_n": n,
        "diameter_m": diameter_m,
        "spacing_to_burden": ratio,
        "x50_mm": x50_mm,
    }


def predict_kuzram(inputs: FragmentationInputs, calibration: Calibration | None = None) -> PredictedFragmentation:
    """Kuz-Ram prediction for one influence region."""
    calibration = calibration or Calibration()
    params = kuzram_parameters(inputs, calibration)
    x50_mm = params["x50_mm"]
    n = params["uniformity_n"]
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
            parameters={
                "rock_factor_A": params["rock_factor_A"],
                "re_weight": params["re_weight"],
                "uniformity_n": n,
                "diameter_m": params["diameter_m"],
                "spacing_to_burden": params["spacing_to_burden"],
                "distribution": "rosin_rammler",
            },
            calibration=calibration.to_dict(),
        ),
    )
