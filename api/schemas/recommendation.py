"""Pydantic schemas for ML design recommendation (BDX-018)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.calibration import PredictionExplanationSchema, UncertaintyIntervalSchema
from api.schemas.design import BlastDesignSchema
from api.schemas.optimization import OptimizationCandidateSchema, VariableBoundSchema
from api.schemas.scenarios import ScenarioParamsSchema
from design.recommendation.types import (
    DEFAULT_MAX_CANDIDATES,
    DEFAULT_TARGET_X50_MM,
    PROFILE_BALANCED,
    PROFILE_KEYS,
)


class RecommendationReasonSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str
    title: str
    detail: str
    metric: str = ""
    unit: str = ""
    baseline: float | None = None
    recommended: float | None = None
    delta: float | None = None
    role: str = "predicted"


class RecommendationAssessmentSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    target_name: str
    target_label: str = ""
    unit: str = ""
    prediction: float | None = None
    uncertainty: UncertaintyIntervalSchema = Field(default_factory=UncertaintyIntervalSchema)
    confidence: str = "low"
    confidence_label: str = ""
    similarity_score: float = 0.0
    applicability_warning: str = ""
    comparable_count: int = 0
    in_domain: bool = False
    sample_count: int = 0
    extrapolated_features: list[str] = Field(default_factory=list)
    explanation: PredictionExplanationSchema = Field(default_factory=PredictionExplanationSchema)
    model_id: str = ""
    model_available: bool = False
    role: str = "predicted"


class DesignRecommendationSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    recommendation_id: str
    design_id: str
    profile: str
    suggested: OptimizationCandidateSchema | None = None
    baseline: OptimizationCandidateSchema | None = None
    alternatives: list[OptimizationCandidateSchema] = Field(default_factory=list)
    profile_picks: dict[str, str] = Field(default_factory=dict)
    reasons: list[RecommendationReasonSchema] = Field(default_factory=list)
    assessments: list[RecommendationAssessmentSchema] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    target_x50_mm: float = DEFAULT_TARGET_X50_MM
    search_run_id: str = ""
    evaluated: int = 0
    pareto_count: int = 0
    method: str = "profile_weighted_pareto"
    auto_applied: bool = False
    approved: bool = False
    replaces_design: bool = False
    modifies_design: bool = False
    applied_as: str = "recommendation_overlay"
    source_design_role: str = "designed"
    suggested_role: str = "predicted"
    engineer_decides: bool = True
    source_revision_sha256: str = ""
    approved_unchanged: bool = True
    created_at: str = ""
    warnings: list[str] = Field(default_factory=list)


class RecommendationSummarySchema(BaseModel):
    recommendation_id: str
    design_id: str
    profile: str = ""
    created_at: str = ""
    evaluated: int = 0
    pareto_count: int = 0
    method: str = "profile_weighted_pareto"
    auto_applied: bool = False
    approved: bool = False
    modifies_design: bool = False
    replaces_design: bool = False


class RecommendationListResponse(BaseModel):
    items: list[RecommendationSummarySchema] = Field(default_factory=list)
    design_id: str = ""
    modifies_design: bool = False
    replaces_design: bool = False
    auto_applied: bool = False


class RecommendationConstraintsSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_ppv_mm_s: float | None = Field(None, gt=0)
    max_oversize_pct: float | None = Field(None, ge=0)
    max_cost_rub: float | None = Field(None, gt=0)


class RecommendationRequest(BaseModel):
    design: BlastDesignSchema
    profile: str = Field(PROFILE_BALANCED, min_length=1)
    variables: list[VariableBoundSchema] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    target_x50_mm: float = Field(DEFAULT_TARGET_X50_MM, gt=0)
    max_candidates: int = Field(DEFAULT_MAX_CANDIDATES, gt=0, le=200)
    persist: bool = True
    persist_as_scenario: bool = False
    params: ScenarioParamsSchema = Field(default_factory=ScenarioParamsSchema)
    constraints: RecommendationConstraintsSchema = Field(default_factory=RecommendationConstraintsSchema)

    def normalized_profile(self) -> str:
        token = self.profile.strip().upper().replace(" ", "_").replace("-", "_")
        return token if token in PROFILE_KEYS else self.profile


class RecommendationPromoteRequest(BaseModel):
    design: BlastDesignSchema
    name: str = Field(..., min_length=1)
    params: ScenarioParamsSchema = Field(default_factory=ScenarioParamsSchema)
    persist: bool = True


class RecommendationProfilesResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    auto_applied: bool = False
    modifies_design: bool = False
