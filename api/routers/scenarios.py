"""REST routes for design-scenario overlays. Never rewrite the approved passport."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.scenarios import (
    DesignScenarioSchema,
    ScenarioCompareRequest,
    ScenarioCompareResponse,
    ScenarioCreateRequest,
    ScenarioCreateResponse,
    ScenarioListResponse,
)
from api.security import require_internal_access
from api.services.economics_service import get_economics_repository
from api.services import scenario_service
from cost.v2.repository import EconomicsRepository

router = APIRouter(prefix="/design", tags=["design-scenarios"])


@router.post("/scenarios", response_model=ScenarioCreateResponse, status_code=201)
def create_scenario(
    request: ScenarioCreateRequest,
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> ScenarioCreateResponse:
    return scenario_service.create_scenario(session["org"], request, repository=repository)


@router.post("/scenarios/compare", response_model=ScenarioCompareResponse)
def compare_scenarios(
    request: ScenarioCompareRequest,
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> ScenarioCompareResponse:
    return scenario_service.compare_plan_scenarios(session["org"], request, repository=repository)


@router.get("/plans/{design_id}/scenarios", response_model=ScenarioListResponse)
def list_scenarios(
    design_id: str,
    session: dict = Depends(require_internal_access),
) -> ScenarioListResponse:
    return scenario_service.list_plan_scenarios(session["org"], design_id)


@router.get("/plans/{design_id}/scenarios/{scenario_id}", response_model=DesignScenarioSchema)
def get_scenario(
    design_id: str,
    scenario_id: str,
    session: dict = Depends(require_internal_access),
) -> DesignScenarioSchema:
    return scenario_service.get_plan_scenario(session["org"], design_id, scenario_id)
