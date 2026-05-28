"""REST-роутер сметного расчёта."""
from __future__ import annotations

from fastapi import APIRouter

from api.schemas.cost import AggregatedCostResultSchema, CostCalculateRequest
from api.services.cost_service import calculate_cost

router = APIRouter(prefix="/cost", tags=["cost"])


@router.post("/calculate", response_model=AggregatedCostResultSchema)
def post_cost_calculate(request: CostCalculateRequest) -> AggregatedCostResultSchema:
    return calculate_cost(request)
