"""REST-роутер сметного расчёта."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.cost import (
    AggregatedCostResultSchema,
    CostCalculateRequest,
    DrillingUnitCalculateRequest,
    DrillingUnitCalculateResponse,
    LaborCalculateRequest,
    LaborCalculateResponse,
    MaterialsAutoRequest,
    MaterialsAutoResponse,
)
from api.security import current_team_id
from api.services.cost_service import (
    calculate_cost,
    calculate_drilling_unit,
    calculate_labor,
    resolve_materials_auto,
)

router = APIRouter(prefix="/cost", tags=["cost"])


@router.post("/calculate", response_model=AggregatedCostResultSchema)
def post_cost_calculate(request: CostCalculateRequest) -> AggregatedCostResultSchema:
    return calculate_cost(request)


@router.post("/drilling-unit", response_model=DrillingUnitCalculateResponse)
def post_drilling_unit(
    request: DrillingUnitCalculateRequest,
    team_id: str = Depends(current_team_id),
) -> DrillingUnitCalculateResponse:
    return calculate_drilling_unit(request, team_id)


@router.post("/labor", response_model=LaborCalculateResponse)
def post_labor(request: LaborCalculateRequest) -> LaborCalculateResponse:
    return calculate_labor(request)


@router.post("/materials-auto", response_model=MaterialsAutoResponse)
def post_materials_auto(
    request: MaterialsAutoRequest,
    team_id: str = Depends(current_team_id),
) -> MaterialsAutoResponse:
    return resolve_materials_auto(request, team_id)
