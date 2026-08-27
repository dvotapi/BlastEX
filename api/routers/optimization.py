"""REST routes for deterministic Pareto search. Never rewrite the approved passport."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.optimization import (
    OptimizationListResponse,
    OptimizationPromoteRequest,
    OptimizationRequest,
    OptimizationResultSchema,
)
from api.schemas.scenarios import DesignScenarioSchema, ScenarioCreateResponse
from api.security import require_internal_access
from api.services import optimization_service

router = APIRouter(prefix="/design", tags=["design-optimization"])


@router.post("/optimize", response_model=OptimizationResultSchema)
def run_optimization(
    request: OptimizationRequest,
    session: dict = Depends(require_internal_access),
) -> OptimizationResultSchema:
    return optimization_service.run_optimization(session["org"], request)


@router.post("/optimize/promote", response_model=ScenarioCreateResponse, status_code=201)
def promote_candidate(
    request: OptimizationPromoteRequest,
    session: dict = Depends(require_internal_access),
) -> DesignScenarioSchema:
    return optimization_service.promote_candidate(session["org"], request)


@router.get("/plans/{design_id}/optimizations", response_model=OptimizationListResponse)
def list_runs(
    design_id: str,
    session: dict = Depends(require_internal_access),
) -> OptimizationListResponse:
    return optimization_service.list_plan_runs(session["org"], design_id)


@router.get("/plans/{design_id}/optimizations/{run_id}", response_model=OptimizationResultSchema)
def get_run(
    design_id: str,
    run_id: str,
    session: dict = Depends(require_internal_access),
) -> OptimizationResultSchema:
    return optimization_service.get_plan_run(session["org"], design_id, run_id)
