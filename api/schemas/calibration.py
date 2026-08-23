"""Pydantic schemas for site residual-calibration models (BDX-012)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.design import BlastDesignSchema


class UncertaintyIntervalSchema(BaseModel):
    std: float | None = None
    lower: float | None = None
    upper: float | None = None
    method: str = "none"


class FeatureDriverSchema(BaseModel):
    feature: str = ""
    label: str = ""
    label_en: str = ""
    share_pct: float = 0.0
    importance_pct: float = 0.0
    shap_value: float = 0.0
    direction: str = "neutral"


class RecommendationHintSchema(BaseModel):
    feature: str = ""
    label: str = ""
    label_en: str = ""
    action: str = ""
    action_label: str = ""
    delta: float = 0.0
    unit: str = ""
    target_name: str = ""
    target_label: str = ""
    step: float = 0.0
    summary: str = ""


class PredictionExplanationSchema(BaseModel):
    method: str = "none"
    expected_value: float | None = None
    drivers: list[FeatureDriverSchema] = Field(default_factory=list)
    recommendations: list[RecommendationHintSchema] = Field(default_factory=list)
    target_name: str = ""
    target_label: str = ""
    unit: str = ""
    summary: str = ""
    recommendation_summary: str = ""


class CalibrationMetricsSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    n_samples: int = 0
    mae: float | None = None
    rmse: float | None = None
    r2: float | None = None
    baseline_mae: float | None = None
    calibrated_mae: float | None = None
    metrics_split: str = "in_sample"


class CalibrationModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    site_id: str
    model_type: str
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "candidate"
    algorithm: str = "random_forest"
    feature_names: list[str] = Field(default_factory=list)
    target_name: str = ""
    baseline_field: str = ""
    measured_field: str = ""
    sample_count: int = 0
    source_blast_ids: list[str] = Field(default_factory=list)
    artifact_sha256: str = ""
    status_updated_at: str = ""
    feature_ranges: dict[str, dict[str, float]] = Field(default_factory=dict)


class CalibrationSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    site_id: str
    model_type: str
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "candidate"
    algorithm: str = "random_forest"
    sample_count: int = 0


class CalibrationListResponse(BaseModel):
    items: list[CalibrationSummarySchema] = Field(default_factory=list)


class CalibrationTrainRequest(BaseModel):
    dataset_id: str
    model_type: str
    algorithm: str = "random_forest"
    site_id: str = ""


class CalibrationStatusRequest(BaseModel):
    status: str


class CalibrationPredictRequest(BaseModel):
    model_type: str
    model_id: str = ""
    site_id: str = ""
    use_production: bool = False
    baseline: float | None = None
    features: dict[str, Any] | None = None
    design: BlastDesignSchema | None = None


class CalibrationProvenanceSchema(BaseModel):
    site_id: str = ""
    model_id: str = ""
    model_type: str = ""
    model_version: int = 0
    training_dataset_version: int = 0
    feature_schema_version: str = ""
    training_date: str = ""
    algorithm: str = ""
    status: str = ""
    applied_as: str = "recommendation_overlay"
    modifies_design: bool = False
    baseline_source: str = ""
    role: str = "recommendation_overlay"


class CalibrationPredictResponse(BaseModel):
    baseline: float
    residual: float
    calibrated: float
    prediction: float | None = None
    uncertainty: UncertaintyIntervalSchema = Field(default_factory=UncertaintyIntervalSchema)
    confidence: str = ""
    confidence_label: str = ""
    similarity_score: float = 0.0
    applicability_warning: str = ""
    comparable_count: int = 0
    in_domain: bool = True
    sample_count: int = 0
    extrapolated_features: list[str] = Field(default_factory=list)
    explanation: PredictionExplanationSchema = Field(default_factory=PredictionExplanationSchema)
    model_id: str = ""
    site_id: str = ""
    model_type: str
    model_version: int = 0
    training_dataset_version: int = 0
    feature_schema_version: str = ""
    training_date: str = ""
    algorithm: str = ""
    status: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    applied_as: str = "recommendation_overlay"
    modifies_design: bool = False
    calibration_applied: bool = False
    baseline_source: str = ""
    unit: str = ""
    warnings: list[str] = Field(default_factory=list)
    role: str = "recommendation_overlay"
    provenance: CalibrationProvenanceSchema


class AlgorithmInfoSchema(BaseModel):
    name: str
    label: str
    kind: str
    available: bool


class AlgorithmListResponse(BaseModel):
    items: list[AlgorithmInfoSchema] = Field(default_factory=list)
    default: str = "random_forest"
