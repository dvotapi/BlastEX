"""REST-роутер проектирования БВР: раскладка сетки и паспорта блока."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from api.schemas.design import (
    BlastDesignSchema,
    DesignListResponse,
    PatternGenerateRequest,
    PatternGenerateResponse,
)
from api.security import require_internal_access
from api.services import design_service

router = APIRouter(prefix="/design", tags=["design"])


@router.post("/pattern", response_model=PatternGenerateResponse)
def post_pattern(request: PatternGenerateRequest) -> PatternGenerateResponse:
    return design_service.generate_pattern(request)


@router.get("/plans", response_model=DesignListResponse)
def list_plans(session: dict = Depends(require_internal_access)) -> DesignListResponse:
    return design_service.list_plans(session["org"])


@router.post("/plans", response_model=BlastDesignSchema, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: BlastDesignSchema, session: dict = Depends(require_internal_access)
) -> BlastDesignSchema:
    return design_service.create_plan(session["org"], body)


@router.get("/plans/{design_id}", response_model=BlastDesignSchema)
def get_plan(design_id: str, session: dict = Depends(require_internal_access)) -> BlastDesignSchema:
    return design_service.get_plan(session["org"], design_id)


@router.put("/plans/{design_id}", response_model=BlastDesignSchema)
def save_plan(
    design_id: str,
    body: BlastDesignSchema,
    session: dict = Depends(require_internal_access),
) -> BlastDesignSchema:
    return design_service.save_plan(session["org"], design_id, body)


@router.delete("/plans/{design_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(design_id: str, session: dict = Depends(require_internal_access)) -> None:
    design_service.delete_plan(session["org"], design_id)


@router.get("/plans/{design_id}/export.csv")
def export_plan_csv(
    design_id: str, session: dict = Depends(require_internal_access)
) -> Response:
    csv_text = design_service.export_plan_csv(session["org"], design_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{design_id}.csv"'},
    )
