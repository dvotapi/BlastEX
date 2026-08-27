"""REST routes for residual site calibration. Overlay recommendations only."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.calibration import (
    AlgorithmListResponse,
    CalibrationListResponse,
    CalibrationModelSchema,
    CalibrationPredictRequest,
    CalibrationPredictResponse,
    CalibrationStatusRequest,
    CalibrationTrainRequest,
)
from api.security import require_internal_access
from api.services import calibration_service

router = APIRouter(prefix="/calibration", tags=["calibration"])


@router.get("/algorithms", response_model=AlgorithmListResponse)
def list_algorithms() -> AlgorithmListResponse:
    return calibration_service.list_algorithms()


@router.get("/models", response_model=CalibrationListResponse)
def list_calibration_models(session: dict = Depends(require_internal_access)) -> CalibrationListResponse:
    return calibration_service.list_calibration_models(session["org"])


@router.post("/models", response_model=CalibrationModelSchema, status_code=201)
def train_calibration_model(
    request: CalibrationTrainRequest,
    session: dict = Depends(require_internal_access),
) -> CalibrationModelSchema:
    return calibration_service.train_calibration(session["org"], request)


@router.get("/models/{model_id}", response_model=CalibrationModelSchema)
def get_calibration_model(
    model_id: str,
    session: dict = Depends(require_internal_access),
) -> CalibrationModelSchema:
    return calibration_service.get_calibration_model(session["org"], model_id)


@router.post("/models/{model_id}/status", response_model=CalibrationModelSchema)
def set_calibration_status(
    model_id: str,
    request: CalibrationStatusRequest,
    session: dict = Depends(require_internal_access),
) -> CalibrationModelSchema:
    return calibration_service.update_status(session["org"], model_id, request)


@router.post("/predict", response_model=CalibrationPredictResponse)
def predict_with_calibration(
    request: CalibrationPredictRequest,
    session: dict = Depends(require_internal_access),
) -> CalibrationPredictResponse:
    return calibration_service.predict_calibration(session["org"], request)
