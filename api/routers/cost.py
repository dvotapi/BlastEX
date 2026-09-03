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
from api.services.cost_service import (
    calculate_cost,
    calculate_drilling_unit,
    calculate_labor,
    resolve_materials_auto,
)
from api.services.legacy_references import current_legacy_references
from cost.v2.legacy_adapter import LegacyReferences

router = APIRouter(prefix="/cost", tags=["cost"])


@router.post("/calculate", response_model=AggregatedCostResultSchema)
def post_cost_calculate(
    request: CostCalculateRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> AggregatedCostResultSchema:
    return calculate_cost(request, legacy)


@router.post("/drilling-unit", response_model=DrillingUnitCalculateResponse)
def post_drilling_unit(
    request: DrillingUnitCalculateRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> DrillingUnitCalculateResponse:
    return calculate_drilling_unit(request, legacy)


@router.post("/labor", response_model=LaborCalculateResponse)
def post_labor(request: LaborCalculateRequest) -> LaborCalculateResponse:
    return calculate_labor(request)


@router.post("/materials-auto", response_model=MaterialsAutoResponse)
def post_materials_auto(
    request: MaterialsAutoRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> MaterialsAutoResponse:
    return resolve_materials_auto(request, legacy)
