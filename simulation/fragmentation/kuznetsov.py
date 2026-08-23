"""Kuznetsov median fragment size.

The historical formula yields centimetres. This module converts to millimetres
explicitly so callers never mix cm and mm. Rock factor A matches ``Blast.py``.
"""
from __future__ import annotations

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
from simulation.fragmentation.units import (
    KUZNETSOV_TNT_INDEX,
    fragment_mm_from_cm,
    relative_weight_strength,
)

MODEL_ID = "kuznetsov"
MODEL_VERSION = "1.0.0"


def rock_factor_A(ucs_mpa: float, density_t_m3: float) -> float:
    """Lilly-style rock factor used by BlastEX.

    A = 0.12 × (UCS_MPa / 20 + density_t/m³ × 2.5 + 7)

    Density must already be tonnes per cubic metre. Convert from kg/m³ with
    ``density_t_m3_from_kg_m3`` before calling.
    """
    index = float(ucs_mpa) / 20.0 + float(density_t_m3) * 2.5 + 7.0
    return 0.12 * index


def kuznetsov_energy_index(re_weight: float) -> float:
    """E in the original Kuznetsov (115/E) term: E = 115 × RE_weight."""
    return float(re_weight) * KUZNETSOV_TNT_INDEX


def kuznetsov_x50_mm(
    rock_factor_A: float,
    powder_factor_kg_m3: float,
    charge_mass_kg: float,
    re_weight: float,
) -> float:
    """Median size in millimetres.

    x50_cm = A × q^{-0.8} × Q^{1/6} × RE^{-19/30}

    The RE term is (115/E)^{19/30} with E = 115 × RE, i.e. RE^{-19/30}.
    ``q`` is kg/m³, ``Q`` is kg. Result is converted cm → mm (×10).
    """
    if rock_factor_A <= 0:
        raise ValueError("Rock factor A must be positive.")
    if powder_factor_kg_m3 <= 0:
        raise ValueError("Powder factor q must be positive, kg/m³.")
    if charge_mass_kg <= 0:
        raise ValueError("Charge mass Q must be positive, kg.")
    if re_weight <= 0:
        raise ValueError("Relative weight strength must be positive.")

    x50_cm = (
        float(rock_factor_A)
        * powder_factor_kg_m3 ** (-0.8)
        * charge_mass_kg ** (1.0 / 6.0)
        * re_weight ** (-19.0 / 30.0)
    )
    return fragment_mm_from_cm(x50_cm)


def kuznetsov_x50_mm_from_energy(
    rock_factor_A: float,
    powder_factor_kg_m3: float,
    charge_mass_kg: float,
    energy_mj_kg: float,
) -> float:
    """Same as ``kuznetsov_x50_mm`` with Q_exp in MJ/kg instead of RE_weight."""
    return kuznetsov_x50_mm(
        rock_factor_A,
        powder_factor_kg_m3,
        charge_mass_kg,
        relative_weight_strength(energy_mj_kg),
    )


def predict_kuznetsov(inputs: FragmentationInputs, calibration: Calibration | None = None) -> PredictedFragmentation:
    """Kuznetsov x50 plus a default Rosin–Rammler curve (n=1 unless calibrated)."""
    calibration = calibration or Calibration()
    factor_A = calibration.rock_factor_A or rock_factor_A(inputs.rock_ucs_mpa, inputs.rock_density_t_m3)
    re_weight = relative_weight_strength(inputs.explosive_energy_mj_kg)
    x50_mm = kuznetsov_x50_mm(factor_A, inputs.powder_factor_kg_m3, inputs.charge_mass_kg, re_weight)
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
            parameters={
                "rock_factor_A": factor_A,
                "re_weight": re_weight,
                "uniformity_n": n,
                "distribution": "rosin_rammler",
            },
            calibration=calibration.to_dict(),
        ),
    )
