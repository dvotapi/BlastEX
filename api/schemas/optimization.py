"""Pydantic schemas for deterministic multi-objective search (BDX-017)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.design import BlastDesignSchema
from api.schemas.scenarios import DesignScenarioSchema, ScenarioOutcomesSchema, ScenarioParamsSchema
from design.optimization.types import DEFAULT_MAX_CANDIDATES, DEFAULT_OBJECTIVES, DEFAULT_TARGET_X50_MM


class VariableBoundSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1)
    values: list[Any] = Field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = Field(None, gt=0)


class ObjectiveScoreSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    key: str
    value: float | None = None
    unit: str = ""
    role: str = "predicted"
    sense: str = "min"


class DecisionVectorSchema(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class OptimizationCandidateSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    candidate_id: str
    params: ScenarioParamsSchema = Field(default_factory=ScenarioParamsSchema)
    outcomes: ScenarioOutcomesSchema = Field(default_factory=ScenarioOutcomesSchema)
    decision: DecisionVectorSchema = Field(default_factory=DecisionVectorSchema)
    objectives: dict[str, float | None] = Field(default_factory=dict)
    scores: list[ObjectiveScoreSchema] = Field(default_factory=list)
    feasible: bool = True
    on_pareto: bool = False
    pareto_rank: int = 0
    kind: str = "optimization_candidate"
    overlay_revision_sha256: str = ""
    source_revision_sha256: str = ""
    warnings: list[str] = Field(default_factory=list)
    applied_as: str = "optimization_overlay"
    modifies_design: bool = False
    role: str = "predicted"


class VariableAxisSchema(BaseModel):
    name: str
    values: list[Any] = Field(default_factory=list)
    unit: str = ""
    kind: str = "float"


class OptimizationResultSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    design_id: str
    candidates: list[OptimizationCandidateSchema] = Field(default_factory=list)
    pareto_front: list[OptimizationCandidateSchema] = Field(default_factory=list)
    compromise_candidate_id: str | None = None
    objectives: list[str] = Field(default_factory=list)
    target_x50_mm: float = DEFAULT_TARGET_X50_MM
    evaluated: int = 0
    feasible: int = 0
    skipped: int = 0
    method: str = "deterministic_search_pareto"
    uses_rl: bool = False
    replaces_design: bool = False
    modifies_design: bool = False
    applied_as: str = "optimization_overlay"
    source_design_role: str = "designed"
    candidate_role: str = "predicted"
    source_revision_sha256: str = ""
    approved_unchanged: bool = True
    created_at: str = ""
    warnings: list[str] = Field(default_factory=list)
    space: list[VariableAxisSchema] = Field(default_factory=list)


class OptimizationRunSummarySchema(BaseModel):
    run_id: str
    design_id: str
    created_at: str = ""
    evaluated: int = 0
    pareto_count: int = 0
    method: str = "deterministic_search_pareto"
    modifies_design: bool = False
    replaces_design: bool = False


class OptimizationListResponse(BaseModel):
    items: list[OptimizationRunSummarySchema] = Field(default_factory=list)
    design_id: str = ""
    modifies_design: bool = False
    replaces_design: bool = False


class OptimizationConstraintsSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_ppv_mm_s: float | None = Field(None, gt=0)
    max_oversize_pct: float | None = Field(None, ge=0)
    max_cost_rub: float | None = Field(None, gt=0)


class OptimizationRequest(BaseModel):
    design: BlastDesignSchema
    variables: list[VariableBoundSchema] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=lambda: list(DEFAULT_OBJECTIVES))
    target_x50_mm: float = Field(DEFAULT_TARGET_X50_MM, gt=0)
    max_candidates: int = Field(DEFAULT_MAX_CANDIDATES, gt=0, le=200)
    include_baseline: bool = True
    persist: bool = True
    persist_pareto_as_scenarios: bool = False
    params: ScenarioParamsSchema = Field(default_factory=ScenarioParamsSchema)
    constraints: OptimizationConstraintsSchema = Field(default_factory=OptimizationConstraintsSchema)


class OptimizationPromoteRequest(BaseModel):
    design: BlastDesignSchema
    name: str = Field(..., min_length=1)
    params: ScenarioParamsSchema = Field(default_factory=ScenarioParamsSchema)
    persist: bool = True
