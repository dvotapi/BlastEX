"""REST routes for hole-level spatial ML. Predicted overlay only."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.calibration import AlgorithmListResponse
from api.schemas.spatial import (
    SpatialListResponse,
    SpatialMetaResponse,
    SpatialModelSchema,
    SpatialPredictRequest,
    SpatialPredictResponse,
    SpatialStatusRequest,
    SpatialTrainRequest,
)
from api.security import require_internal_access
from api.services import spatial_service

router = APIRouter(prefix="/spatial", tags=["spatial"])


@router.get("/meta", response_model=SpatialMetaResponse)
def spatial_meta() -> SpatialMetaResponse:
    return spatial_service.catalog_meta()


@router.get("/algorithms", response_model=AlgorithmListResponse)
def list_algorithms() -> AlgorithmListResponse:
    return spatial_service.list_algorithms()


@router.get("/models", response_model=SpatialListResponse)
def list_spatial_models(
    site_id: str = "",
    session: dict = Depends(require_internal_access),
) -> SpatialListResponse:
    return spatial_service.list_spatial_models(str(session["org"]), site_id=site_id)


@router.post("/models", response_model=SpatialModelSchema, status_code=201)
def train_spatial_model(
    request: SpatialTrainRequest,
    session: dict = Depends(require_internal_access),
) -> SpatialModelSchema:
    return spatial_service.train_spatial(str(session["org"]), request)


@router.get("/models/{model_id}", response_model=SpatialModelSchema)
def get_spatial_model(
    model_id: str,
    session: dict = Depends(require_internal_access),
) -> SpatialModelSchema:
    return spatial_service.get_spatial_model(str(session["org"]), model_id)


@router.post("/models/{model_id}/status", response_model=SpatialModelSchema)
def set_spatial_status(
    model_id: str,
    request: SpatialStatusRequest,
    session: dict = Depends(require_internal_access),
) -> SpatialModelSchema:
    return spatial_service.update_status(str(session["org"]), model_id, request)


@router.post("/predict", response_model=SpatialPredictResponse)
def predict_spatial(
    request: SpatialPredictRequest,
    session: dict = Depends(require_internal_access),
) -> SpatialPredictResponse:
    return spatial_service.predict_spatial(str(session["org"]), request)
