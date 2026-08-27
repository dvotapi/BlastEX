"""Pydantic schemas for two-level learning (BDX-019)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.calibration import PredictionExplanationSchema, UncertaintyIntervalSchema
from api.schemas.design import BlastDesignSchema


class IsolationKeysSchema(BaseModel):
    team_id: str = ""
    site_id: str = ""
    scope: str = ""


class LearningTargetPredictionSchema(BaseModel):
    target_name: str
    value: float | None = None
    prediction: float | None = None
    global_value: float | None = None
    residual_value: float | None = None
    unit: str = ""
    label: str = ""
    model_type: str = ""
    prediction_applied: bool = False
    role: str = "predicted"
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


class LearningModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    team_id: str
    site_id: str
    scope: str
    isolation: IsolationKeysSchema = Field(default_factory=IsolationKeysSchema)
    model_type: str
    class_name: str = ""
    model_version: int
    training_dataset_id: str
    training_dataset_ids: list[str] = Field(default_factory=list)
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
    source_site_ids: list[str] = Field(default_factory=list)
    artifact_sha256: str = ""
    status_updated_at: str = ""
    feature_ranges: dict[str, dict[str, float]] = Field(default_factory=dict)
    prior_model_id: str = ""
    prior_team_id: str = ""
    prior_scope: str = ""
    adaptation: str = "direct"
    data_roles: dict[str, str] = Field(default_factory=dict)
    auto_approved: bool = False


class LearningSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    team_id: str
    site_id: str
    scope: str
    model_type: str
    class_name: str = ""
    model_version: int
    training_dataset_id: str
    training_dataset_ids: list[str] = Field(default_factory=list)
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    status: str = "candidate"
    algorithm: str = "random_forest"
    primary_target: str = ""
    target_names: list[str] = Field(default_factory=list)
    sample_count: int = 0
    prior_model_id: str = ""
    adaptation: str = ""
    source_site_ids: list[str] = Field(default_factory=list)


class LearningListResponse(BaseModel):
    items: list[LearningSummarySchema] = Field(default_factory=list)
    auto_approved: bool = False


class LearningGlobalTrainRequest(BaseModel):
    dataset_ids: list[str] = Field(default_factory=list)
    model_type: str
    algorithm: str = "random_forest"


class LearningSiteTrainRequest(BaseModel):
    dataset_ids: list[str] = Field(default_factory=list)
    site_id: str
    model_type: str
    algorithm: str = "random_forest"
    prior_model_id: str = ""


class LearningStatusRequest(BaseModel):
    status: str


class LearningPredictRequest(BaseModel):
    model_type: str
    model_id: str = ""
    site_id: str = ""
    scope: str = ""
    use_production: bool = False
    features: dict[str, Any] | None = None
    design: BlastDesignSchema | None = None


class LearningProvenanceSchema(BaseModel):
    team_id: str = ""
    site_id: str = ""
    scope: str = ""
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
    auto_approved: bool = False
    role: str = "recommendation_overlay"
    prediction_role: str = "predicted"
    primary_target: str = ""
    prior_model_id: str = ""
    adaptation: str = ""
    data_roles: dict[str, str] = Field(default_factory=dict)


class LearningPredictResponse(BaseModel):
    predicted: float | None = None
    prediction: float | None = None
    predictions: dict[str, LearningTargetPredictionSchema] = Field(default_factory=dict)
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
    team_id: str = ""
    site_id: str = ""
    scope: str = ""
    isolation: IsolationKeysSchema = Field(default_factory=IsolationKeysSchema)
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
    auto_approved: bool = False
    warnings: list[str] = Field(default_factory=list)
    role: str = "recommendation_overlay"
    prior_model_id: str = ""
    adaptation: str = ""
    data_roles: dict[str, str] = Field(default_factory=dict)
    provenance: LearningProvenanceSchema
