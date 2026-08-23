"""Pydantic schemas for specialised outcome-prediction models (BDX-013)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.calibration import UncertaintyIntervalSchema
from api.schemas.design import BlastDesignSchema


class OutcomeTargetInfoSchema(BaseModel):
    name: str
    unit: str = ""
    label: str = ""


class OutcomeModelTypeSchema(BaseModel):
    name: str
    class_name: str
    label: str
    label_en: str = ""
    primary_target: str
    targets: list[OutcomeTargetInfoSchema] = Field(default_factory=list)


class OutcomeModelTypeListResponse(BaseModel):
    items: list[OutcomeModelTypeSchema] = Field(default_factory=list)


class OutcomeModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    site_id: str
    model_type: str
    class_name: str = ""
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
    primary_target: str = ""
    sample_count: int = 0
    source_blast_ids: list[str] = Field(default_factory=list)
    artifact_sha256: str = ""
    status_updated_at: str = ""
    feature_ranges: dict[str, dict[str, float]] = Field(default_factory=dict)


class OutcomeSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    site_id: str
    model_type: str
    class_name: str = ""
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "candidate"
    algorithm: str = "random_forest"
    primary_target: str = ""
    target_names: list[str] = Field(default_factory=list)
    sample_count: int = 0


class OutcomeListResponse(BaseModel):
    items: list[OutcomeSummarySchema] = Field(default_factory=list)


class OutcomeTrainRequest(BaseModel):
    dataset_id: str
    model_type: str
    algorithm: str = "random_forest"
    site_id: str = ""


class OutcomeStatusRequest(BaseModel):
    status: str


class OutcomePredictRequest(BaseModel):
    model_type: str
    model_id: str = ""
    site_id: str = ""
    use_production: bool = False
    features: dict[str, Any] | None = None
    design: BlastDesignSchema | None = None


class OutcomePredictAllRequest(BaseModel):
    site_id: str = ""
    use_production: bool = True
    model_ids: dict[str, str] = Field(default_factory=dict)
    features: dict[str, Any] | None = None
    design: BlastDesignSchema | None = None


class OutcomeProvenanceSchema(BaseModel):
    site_id: str = ""
    model_id: str = ""
    model_type: str = ""
    class_name: str = ""
    model_version: int = 0
    training_dataset_version: int = 0
    feature_schema_version: str = ""
    training_date: str = ""
    algorithm: str = ""
    status: str = ""
    applied_as: str = "recommendation_overlay"
    modifies_design: bool = False
    role: str = "recommendation_overlay"
    primary_target: str = ""


class OutcomeTargetPredictionSchema(BaseModel):
    target_name: str
    value: float | None = None
    prediction: float | None = None
    unit: str = ""
    label: str = ""
    model_type: str = ""
    prediction_applied: bool = False
    uncertainty: UncertaintyIntervalSchema = Field(default_factory=UncertaintyIntervalSchema)
    confidence: str = ""
    confidence_label: str = ""
    similarity_score: float = 0.0
    applicability_warning: str = ""
    comparable_count: int = 0
    in_domain: bool = True
    sample_count: int = 0
    extrapolated_features: list[str] = Field(default_factory=list)


class OutcomePredictResponse(BaseModel):
    predicted: float | None = None
    prediction: float | None = None
    predictions: dict[str, OutcomeTargetPredictionSchema] = Field(default_factory=dict)
    uncertainty: UncertaintyIntervalSchema = Field(default_factory=UncertaintyIntervalSchema)
    confidence: str = ""
    confidence_label: str = ""
    similarity_score: float = 0.0
    applicability_warning: str = ""
    comparable_count: int = 0
    in_domain: bool = True
    sample_count: int = 0
    extrapolated_features: list[str] = Field(default_factory=list)
    model_id: str = ""
    site_id: str = ""
    model_type: str
    class_name: str = ""
    model_version: int = 0
    training_dataset_version: int = 0
    feature_schema_version: str = ""
    training_date: str = ""
    algorithm: str = ""
    status: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    primary_target: str = ""
    unit: str = ""
    applied_as: str = "recommendation_overlay"
    modifies_design: bool = False
    prediction_applied: bool = False
    warnings: list[str] = Field(default_factory=list)
    role: str = "recommendation_overlay"
    provenance: OutcomeProvenanceSchema


class OutcomePanelResponse(BaseModel):
    applied_as: str = "recommendation_overlay"
    modifies_design: bool = False
    role: str = "recommendation_overlay"
    x50_mm: OutcomeTargetPredictionSchema | None = None
    x80_mm: OutcomeTargetPredictionSchema | None = None
    oversize_pct: OutcomeTargetPredictionSchema | None = None
    ppv: OutcomeTargetPredictionSchema | None = None
    frequency_hz: OutcomeTargetPredictionSchema | None = None
    toe_risk: OutcomeTargetPredictionSchema | None = None
    models: dict[str, OutcomePredictResponse] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    applicability_warning: str = ""
