"""Pydantic-схемы технологического расчёта BlastEngine."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RockPropertiesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., examples=["Габбро-диабаз"])
    density_t_m3: float = Field(..., gt=0, examples=[2.9])
    ucs_mpa: float = Field(..., gt=0, examples=[168])
    fissuring_ff: float = Field(..., ge=0, examples=[2.2])


class ExplosivePropertiesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., examples=["ЭВЕРСИН Э-100"])
    density_t_m3: float = Field(..., gt=0, examples=[1.12])
    power_mj_kg: float = Field(..., gt=0, examples=[2.99])


class TargetParamsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lump_size_mm: float = Field(..., gt=0, examples=[400])
    hole_diameter_mm: float = Field(0, ge=0)
    overdrill_m: float = Field(1.0, ge=0)
    hole_oversize_coeff: float = Field(1.05, ge=1.0, le=1.5)
    spacing_coeff_m: float = Field(1.25, gt=0)
    bench_height_m: float = Field(10.0, gt=0)


class BlastOptimizeRequest(BaseModel):
    rock: RockPropertiesSchema
    explosive: ExplosivePropertiesSchema
    target: TargetParamsSchema
    crown_diameters_mm: list[float] = Field(
        default_factory=lambda: [110, 115, 122, 125, 130, 140, 152, 165, 171, 220, 250],
        min_length=1,
    )
    max_oversize_threshold_pct: float = Field(5.0, gt=0, le=30)


class BlastOptimizeVariant(BaseModel):
    crown_mm: float
    specific_q_kg_m3: float
    line_of_least_resistance_m: float
    grid_a_m: float
    grid_b_m: float
    grid_label: str
    x50_mm: float
    oversize_pct: float
    target_q_kg_m3: float | None = None


class BlastOptimizeResponse(BaseModel):
    variants: list[BlastOptimizeVariant]
    max_oversize_threshold_pct: float
    rock_name: str
    explosive_name: str
