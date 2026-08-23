"""REST routes for ML design recommendation. Never rewrite the approved passport."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.recommendation import (
    DesignRecommendationSchema,
    RecommendationListResponse,
    RecommendationProfilesResponse,
    RecommendationPromoteRequest,
    RecommendationRequest,
)
from api.schemas.scenarios import ScenarioCreateResponse
from api.security import require_internal_access
from api.services import recommendation_service
from design.recommendation.types import PROFILES

router = APIRouter(prefix="/design", tags=["design-recommendation"])


@router.get("/recommend/profiles", response_model=RecommendationProfilesResponse)
def list_profiles(session: dict = Depends(require_internal_access)) -> RecommendationProfilesResponse:
    return RecommendationProfilesResponse(
        items=[item.to_dict() for item in PROFILES.values()],
        auto_applied=False,
        modifies_design=False,
    )


@router.post("/recommend", response_model=DesignRecommendationSchema)
def run_recommendation(
    request: RecommendationRequest,
    session: dict = Depends(require_internal_access),
) -> DesignRecommendationSchema:
    return recommendation_service.run_recommendation(session["org"], request)


@router.post("/recommend/promote", response_model=ScenarioCreateResponse, status_code=201)
def promote_recommendation(
    request: RecommendationPromoteRequest,
    session: dict = Depends(require_internal_access),
) -> ScenarioCreateResponse:
    return recommendation_service.promote_recommendation(session["org"], request)


@router.get("/plans/{design_id}/recommendations", response_model=RecommendationListResponse)
def list_recommendations(
    design_id: str,
    session: dict = Depends(require_internal_access),
) -> RecommendationListResponse:
    return recommendation_service.list_plan_recommendations(session["org"], design_id)


@router.get("/plans/{design_id}/recommendations/{recommendation_id}", response_model=DesignRecommendationSchema)
def get_recommendation(
    design_id: str,
    recommendation_id: str,
    session: dict = Depends(require_internal_access),
) -> DesignRecommendationSchema:
    return recommendation_service.get_plan_recommendation(session["org"], design_id, recommendation_id)
