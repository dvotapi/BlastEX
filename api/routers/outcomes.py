"""REST routes for specialised blast-outcome models. Overlay recommendations only."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.calibration import AlgorithmListResponse
from api.schemas.outcomes import (
    OutcomeListResponse,
    OutcomeModelSchema,
    OutcomeModelTypeListResponse,
    OutcomePanelResponse,
    OutcomePredictAllRequest,
    OutcomePredictRequest,
    OutcomePredictResponse,
    OutcomeStatusRequest,
    OutcomeTrainRequest,
)
from api.security import require_internal_access
from api.services import outcome_service

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


@router.get("/algorithms", response_model=AlgorithmListResponse)
def list_algorithms() -> AlgorithmListResponse:
    return outcome_service.list_algorithms()


@router.get("/model-types", response_model=OutcomeModelTypeListResponse)
def list_model_types() -> OutcomeModelTypeListResponse:
    return outcome_service.list_outcome_types()


@router.get("/models", response_model=OutcomeListResponse)
def list_outcome_models(
    model_type: str = "",
    session: dict = Depends(require_internal_access),
) -> OutcomeListResponse:
    return outcome_service.list_outcome_models(session["org"], model_type)


@router.post("/models", response_model=OutcomeModelSchema, status_code=201)
def train_outcome_model(
    request: OutcomeTrainRequest,
    session: dict = Depends(require_internal_access),
) -> OutcomeModelSchema:
    return outcome_service.train_outcome(session["org"], request)


@router.get("/models/{model_id}", response_model=OutcomeModelSchema)
def get_outcome_model(
    model_id: str,
    session: dict = Depends(require_internal_access),
) -> OutcomeModelSchema:
    return outcome_service.get_outcome_model(session["org"], model_id)


@router.post("/models/{model_id}/status", response_model=OutcomeModelSchema)
def set_outcome_status(
    model_id: str,
    request: OutcomeStatusRequest,
    session: dict = Depends(require_internal_access),
) -> OutcomeModelSchema:
    return outcome_service.update_status(session["org"], model_id, request)


@router.post("/predict", response_model=OutcomePredictResponse)
def predict_outcome(
    request: OutcomePredictRequest,
    session: dict = Depends(require_internal_access),
) -> OutcomePredictResponse:
    return outcome_service.predict_outcome(session["org"], request)


@router.post("/predict-all", response_model=OutcomePanelResponse)
def predict_all_outcomes(
    request: OutcomePredictAllRequest,
    session: dict = Depends(require_internal_access),
) -> OutcomePanelResponse:
    return outcome_service.predict_panel(session["org"], request)
