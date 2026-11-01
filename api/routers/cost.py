"""REST-роутер сметного расчёта."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.cost import (
    AggregatedCostResultSchema,
    CostCalculateRequest,
    LaborCalculateRequest,
    LaborCalculateResponse,
    MaterialsAutoRequest,
    MaterialsAutoResponse,
)
from api.services.cost_service import (
    calculate_cost,
    calculate_labor,
    resolve_drilling_price_source,
    resolve_materials_auto,
)
from api.security import current_team_id
from api.services.economics_service import get_economics_repository
from api.services.legacy_references import current_legacy_references
from cost.v2.legacy_adapter import LegacyReferences
from cost.v2.repository import EconomicsRepository

router = APIRouter(prefix="/cost", tags=["cost"])


@router.post("/calculate", response_model=AggregatedCostResultSchema)
def post_cost_calculate(
    request: CostCalculateRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
    organization_id: str = Depends(current_team_id),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> AggregatedCostResultSchema:
    source = resolve_drilling_price_source(request, repository, organization_id)
    return calculate_cost(request, legacy, source)


@router.post("/labor", response_model=LaborCalculateResponse)
def post_labor(request: LaborCalculateRequest) -> LaborCalculateResponse:
    return calculate_labor(request)


@router.post("/materials-auto", response_model=MaterialsAutoResponse)
def post_materials_auto(
    request: MaterialsAutoRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> MaterialsAutoResponse:
    return resolve_materials_auto(request, legacy)
