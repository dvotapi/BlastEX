"""REST routes for immutable training-dataset snapshots. No training."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.datasets import (
    DatasetBuildRequest,
    DatasetListResponse,
    DatasetPreviewRequest,
    DatasetSnapshotSchema,
    SampleValidationSchema,
)
from api.security import require_internal_access
from api.services import dataset_service

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=DatasetListResponse)
def list_datasets(session: dict = Depends(require_internal_access)) -> DatasetListResponse:
    return dataset_service.list_snapshots(session["org"])


@router.post("", response_model=DatasetSnapshotSchema, status_code=201)
def build_dataset(
    request: DatasetBuildRequest,
    session: dict = Depends(require_internal_access),
) -> DatasetSnapshotSchema:
    return dataset_service.build_snapshot_for_team(session["org"], request)


@router.post("/preview", response_model=SampleValidationSchema)
def preview_dataset_sample(request: DatasetPreviewRequest) -> SampleValidationSchema:
    return dataset_service.preview_design(request)


@router.get("/{dataset_id}", response_model=DatasetSnapshotSchema)
def get_dataset(dataset_id: str, session: dict = Depends(require_internal_access)) -> DatasetSnapshotSchema:
    return dataset_service.get_snapshot(session["org"], dataset_id)
