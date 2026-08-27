"""REST routes for two-level learning. Overlay recommendations only."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.calibration import AlgorithmListResponse
from api.schemas.learning import (
    LearningGlobalTrainRequest,
    LearningListResponse,
    LearningModelSchema,
    LearningPredictRequest,
    LearningPredictResponse,
    LearningSiteTrainRequest,
    LearningStatusRequest,
)
from api.schemas.outcomes import OutcomeModelTypeListResponse
from api.security import require_internal_access
from api.services import learning_service

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/algorithms", response_model=AlgorithmListResponse)
def list_algorithms() -> AlgorithmListResponse:
    return learning_service.list_algorithms()


@router.get("/model-types", response_model=OutcomeModelTypeListResponse)
def list_model_types() -> OutcomeModelTypeListResponse:
    return learning_service.list_learning_types()


@router.get("/models", response_model=LearningListResponse)
def list_learning_models(
    model_type: str = "",
    scope: str = "",
    site_id: str = "",
    session: dict = Depends(require_internal_access),
) -> LearningListResponse:
    return learning_service.list_learning_models(
        session["org"], model_type=model_type, scope=scope, site_id=site_id
    )


@router.post("/global", response_model=LearningModelSchema, status_code=201)
def train_global_model(
    request: LearningGlobalTrainRequest,
    session: dict = Depends(require_internal_access),
) -> LearningModelSchema:
    return learning_service.train_global_model(session["org"], request)


@router.post("/site", response_model=LearningModelSchema, status_code=201)
def train_site_model(
    request: LearningSiteTrainRequest,
    session: dict = Depends(require_internal_access),
) -> LearningModelSchema:
    return learning_service.train_site_model(session["org"], request)


@router.get("/models/{model_id}", response_model=LearningModelSchema)
def get_learning_model(
    model_id: str,
    session: dict = Depends(require_internal_access),
) -> LearningModelSchema:
    return learning_service.get_learning_model(session["org"], model_id)


@router.post("/models/{model_id}/status", response_model=LearningModelSchema)
def set_learning_status(
    model_id: str,
    request: LearningStatusRequest,
    session: dict = Depends(require_internal_access),
) -> LearningModelSchema:
    return learning_service.update_status(session["org"], model_id, request)


@router.post("/predict", response_model=LearningPredictResponse)
def predict_learning(
    request: LearningPredictRequest,
    session: dict = Depends(require_internal_access),
) -> LearningPredictResponse:
    return learning_service.predict_learning(session["org"], request)
