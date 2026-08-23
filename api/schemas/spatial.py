"""Pydantic schemas for hole-level spatial ML (BDX-022). Predicted overlay only."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.design import BlastDesignSchema


class SpatialMetricSchema(BaseModel):
    name: str
    unit: str = ""
    label: str = ""
    role: str = "predicted"


class SpatialMetaResponse(BaseModel):
    metrics: list[SpatialMetricSchema] = Field(default_factory=list)
    map_metrics: list[SpatialMetricSchema] = Field(default_factory=list)
    data_roles: dict[str, str] = Field(default_factory=dict)
    applied_as: str = "predicted_overlay"
    modifies_design: bool = False
    role: str = "predicted"


class SpatialModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    team_id: str = ""
    site_id: str = ""
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "candidate"
    algorithm: str = "random_forest"
    feature_names: list[str] = Field(default_factory=list)
    target_names: list[str] = Field(default_factory=list)
    class_name: str = "SpatialHoleModel"
    sample_count: int = 0
    hole_count: int = 0
    source_blast_ids: list[str] = Field(default_factory=list)
    artifact_sha256: str = ""
    status_updated_at: str = ""
    neighbor_k: int = 4
    data_roles: dict[str, str] = Field(default_factory=dict)


class SpatialSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    team_id: str = ""
    site_id: str = ""
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "candidate"
    algorithm: str = "random_forest"
    class_name: str = "SpatialHoleModel"
    hole_count: int = 0
    sample_count: int = 0


class SpatialListResponse(BaseModel):
    items: list[SpatialSummarySchema] = Field(default_factory=list)
    modifies_design: bool = False


class SpatialTrainRequest(BaseModel):
    dataset_id: str
    site_id: str = ""
    algorithm: str = "random_forest"
    neighbor_k: int = 4


class SpatialStatusRequest(BaseModel):
    status: str


class SpatialHoleSchema(BaseModel):
    hole_id: str
    x: float
    y: float
    kind: str = "production"
    x50_mm: float | None = None
    oversize_pct: float | None = None
    toe_probability: float | None = None
    residual_x50_mm: float | None = None
    residual_oversize_pct: float | None = None
    residual_toe: float | None = None
    measured_x50_mm: float | None = None
    measured_oversize_pct: float | None = None
    measured_toe_probability: float | None = None
    residual_vs_measured_x50_mm: float | None = None
    residual_vs_measured_oversize_pct: float | None = None
    residual_vs_measured_toe: float | None = None
    neighbor_ids: list[str] = Field(default_factory=list)
    role: str = "predicted"
    units: dict[str, str] = Field(default_factory=dict)


class SpatialNeighborhoodSchema(BaseModel):
    hole_id: str
    member_ids: list[str] = Field(default_factory=list)
    x: float
    y: float
    x50_mm: float | None = None
    oversize_pct: float | None = None
    toe_probability: float | None = None
    residual_x50_mm: float | None = None
    residual_oversize_pct: float | None = None
    residual_toe: float | None = None
    role: str = "predicted"
    units: dict[str, str] = Field(default_factory=dict)


class SpatialProvenanceSchema(BaseModel):
    model_id: str = ""
    team_id: str = ""
    site_id: str = ""
    model_version: int = 0
    training_dataset_version: int = 0
    feature_schema_version: str = ""
    algorithm: str = ""
    status: str = ""
    applied_as: str = "predicted_overlay"
    modifies_design: bool = False
    role: str = "predicted"


class SpatialPredictResponse(BaseModel):
    holes: list[SpatialHoleSchema] = Field(default_factory=list)
    neighborhoods: list[SpatialNeighborhoodSchema] = Field(default_factory=list)
    maps: dict[str, Any] = Field(default_factory=dict)
    block: dict[str, Any] = Field(default_factory=dict)
    model_id: str = ""
    team_id: str = ""
    site_id: str = ""
    model_version: int = 0
    training_dataset_version: int = 0
    feature_schema_version: str = ""
    algorithm: str = ""
    status: str = ""
    hole_count: int = 0
    applied_as: str = "predicted_overlay"
    modifies_design: bool = False
    prediction_applied: bool = True
    warnings: list[str] = Field(default_factory=list)
    role: str = "predicted"
    data_roles: dict[str, str] = Field(default_factory=dict)
    provenance: SpatialProvenanceSchema = Field(default_factory=SpatialProvenanceSchema)


class SpatialPredictRequest(BaseModel):
    design: BlastDesignSchema
    model_id: str = ""
    site_id: str = ""
    use_production: bool = False
    block: dict[str, Any] = Field(default_factory=dict)
    neighbor_k: int | None = None
