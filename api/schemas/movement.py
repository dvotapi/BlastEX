"""Pydantic schemas for the BDX-023 movement / heave estimate overlay."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.design import BlastDesignSchema


class MovementMeasuredSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str = "measured"
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    volume_m3: float | None = None
    throw_m: float | None = None
    notes: str = ""


class MovementPredictRequest(BaseModel):
    design: BlastDesignSchema
    measured: list[MovementMeasuredSchema] = Field(default_factory=list)


class MovementModelInfoSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    version: str
    label: str
    kind: str = "empirical_kinematic_estimate"
    label_ru: str = "оценка"
    label_en: str = "estimate"
    disclaimer: str = ""
    is_physics_simulation: bool = False


class MovementModelsResponse(BaseModel):
    models: list[MovementModelInfoSchema]
    kind: str = "empirical_kinematic_estimate"
    label_ru: str = "оценка"
    label_en: str = "estimate"
    disclaimer: str = ""
    is_physics_simulation: bool = False


class MovementMuckpileSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str = "predicted"
    length_m: float = 0.0
    width_m: float = 0.0
    height_m: float = 0.0
    volume_m3: float = 0.0
    throw_m: float = 0.0
    heave_m: float = 0.0
    swell_factor: float = 1.0
    in_situ_volume_m3: float = 0.0
    centroid_x: float = 0.0
    centroid_y: float = 0.0
    envelope: list[dict[str, float]] = Field(default_factory=list)
    notes: str = ""
    kind: str = "empirical_kinematic_estimate"
    label_ru: str = "оценка"
    label_en: str = "estimate"
    disclaimer: str = ""
    is_physics_simulation: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)


class MovementHoleSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    hole_id: str
    role: str = "predicted"
    x: float = 0.0
    y: float = 0.0
    dx_m: float = 0.0
    dy_m: float = 0.0
    dz_m: float = 0.0
    throw_m: float = 0.0
    heave_m: float = 0.0
    direction_deg: float = 0.0
    swell_factor: float = 1.0
    predicted_x: float = 0.0
    predicted_y: float = 0.0
    predicted_z: float = 0.0
    hole_kind: str = "production"
    kind: str = "empirical_kinematic_estimate"
    is_physics_simulation: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class MovementMapsSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    metrics: list[str] = Field(default_factory=list)
    role: str = "predicted"
    holes: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, dict[str, float]] = Field(default_factory=dict)


class MovementPredictResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    model_version: str
    role: str = "predicted"
    kind: str = "empirical_kinematic_estimate"
    label_ru: str = "оценка"
    label_en: str = "estimate"
    disclaimer: str
    is_physics_simulation: bool = False
    prediction_applied: bool = True
    design_rewritten: bool = False
    muckpile: MovementMuckpileSchema
    holes: list[MovementHoleSchema] = Field(default_factory=list)
    maps: MovementMapsSchema
    warnings: list[str] = Field(default_factory=list)
    measured: list[MovementMeasuredSchema] = Field(default_factory=list)
    map_metrics: list[str] = Field(default_factory=list)
