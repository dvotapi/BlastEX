"""
Геометрия заряда одной скважины — совместимость с прежним API.

Расчёт перенесён в cost.geometry (этап 1 сметы).
"""
from __future__ import annotations

from Blast import ExplosiveProperties
from cost.geometry import (
    calculate_hole_geometry,
    charge_diameter_m,
    linear_capacity_kg_per_m,
)
from cost.models import HoleGeometry

HoleChargeResult = HoleGeometry


def calculate_hole_charge(
    *,
    grid_a_m: float,
    grid_b_m: float,
    depth_m: float,
    overdrill_m: float,
    undercharge_m: float,
    crown_mm: float,
    hole_oversize_coeff: float,
    explosive: ExplosiveProperties,
    explosive_label: str | None = None,
) -> HoleChargeResult:
    return calculate_hole_geometry(
        grid_a_m=grid_a_m,
        grid_b_m=grid_b_m,
        depth_m=depth_m,
        overdrill_m=overdrill_m,
        undercharge_m=undercharge_m,
        crown_mm=crown_mm,
        hole_oversize_coeff=hole_oversize_coeff,
        explosive=explosive,
        explosive_label=explosive_label,
    )


__all__ = [
    "HoleChargeResult",
    "calculate_hole_charge",
    "charge_diameter_m",
    "linear_capacity_kg_per_m",
]
