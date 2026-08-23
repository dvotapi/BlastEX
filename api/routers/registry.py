"""REST routes for the formal model registry. Promotion is human-gated."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.registry import (
    RegistryListResponse,
    RegistryMetaResponse,
    RegistryPromoteRequest,
    RegistryRecordSchema,
)
from api.security import require_internal_access
from api.services import registry_service

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/meta", response_model=RegistryMetaResponse)
def registry_meta() -> RegistryMetaResponse:
    return registry_service.catalog_meta()


@router.get("/models", response_model=RegistryListResponse)
def list_registry_models(
    family: str = "",
    status: str = "",
    site_id: str = "",
    session: dict = Depends(require_internal_access),
) -> RegistryListResponse:
    return registry_service.list_registry_models(
        str(session["org"]), family=family, status=status, site_id=site_id
    )


@router.get("/models/{family}/{model_id}", response_model=RegistryRecordSchema)
def get_registry_model(
    family: str,
    model_id: str,
    session: dict = Depends(require_internal_access),
) -> RegistryRecordSchema:
    return registry_service.get_registry_model(str(session["org"]), family, model_id)


@router.post("/models/{family}/{model_id}/promote", response_model=RegistryRecordSchema)
def promote_registry_model(
    family: str,
    model_id: str,
    request: RegistryPromoteRequest,
    session: dict = Depends(require_internal_access),
) -> RegistryRecordSchema:
    return registry_service.promote_registry_model(
        str(session["org"]),
        family,
        model_id,
        request,
        actor=str(session.get("sub") or ""),
    )
