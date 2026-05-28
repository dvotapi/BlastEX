"""REST-роутер технологического расчёта."""
from __future__ import annotations

from fastapi import APIRouter

from api.schemas.blast import BlastOptimizeRequest, BlastOptimizeResponse
from api.services.blast_service import optimize_blast

router = APIRouter(prefix="/blast", tags=["blast"])


@router.post("/optimize", response_model=BlastOptimizeResponse)
def post_blast_optimize(request: BlastOptimizeRequest) -> BlastOptimizeResponse:
    return optimize_blast(request)
