"""Assemble the official blast passport. Never writes or approves the design."""
from __future__ import annotations

from api.exceptions import DesignNotFoundError, InvalidDesignError
from api.schemas.reporting import PassportBuildRequest, PassportDocumentSchema, PassportRolesResponse
from design import persistence as design_persistence
from design.models import BlastDesign
from design.reporting.engine import build_passport
from design.reporting.html import passport_html, render_passport_html
from design.reporting.types import roles_payload


def list_roles() -> PassportRolesResponse:
    return PassportRolesResponse(**roles_payload())


def _document_from_design(design: BlastDesign, request: PassportBuildRequest | None = None) -> PassportDocumentSchema:
    kwargs: dict = {}
    if request is not None:
        kwargs = {
            "lump_size_mm": request.lump_size_mm,
            "max_oversize_pct": request.max_oversize_pct,
            "fragmentation_model": request.fragmentation_model,
            "include_predictions": request.include_predictions,
            "planned_cost": request.planned_cost.model_dump() if request.planned_cost else None,
            "predicted_cost": request.predicted_cost.model_dump() if request.predicted_cost else None,
        }
    try:
        document = build_passport(design, **kwargs)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    payload = document.to_dict()
    if payload.get("approved") or payload.get("auto_approved"):
        raise InvalidDesignError("Паспорт не должен утверждаться автоматически.")
    return PassportDocumentSchema(**payload)


def build_from_request(request: PassportBuildRequest) -> PassportDocumentSchema:
    design = BlastDesign.from_dict(request.design.model_dump())
    before_holes = [hole.to_dict() for hole in design.holes]
    before_loads = [load.to_dict() for load in design.loads]
    document = _document_from_design(design, request)
    if [hole.to_dict() for hole in design.holes] != before_holes:
        raise InvalidDesignError("Сборка паспорта не должна менять проектные скважины.")
    if [load.to_dict() for load in design.loads] != before_loads:
        raise InvalidDesignError("Сборка паспорта не должна менять проектный заряд.")
    return document


def render_from_request(request: PassportBuildRequest) -> str:
    design = BlastDesign.from_dict(request.design.model_dump())
    try:
        return passport_html(
            design,
            lump_size_mm=request.lump_size_mm,
            max_oversize_pct=request.max_oversize_pct,
            fragmentation_model=request.fragmentation_model,
            include_predictions=request.include_predictions,
            planned_cost=request.planned_cost.model_dump() if request.planned_cost else None,
            predicted_cost=request.predicted_cost.model_dump() if request.predicted_cost else None,
        )
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc


def get_plan_passport(team_id: str, design_id: str) -> PassportDocumentSchema:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return _document_from_design(design)


def export_plan_passport_html(team_id: str, design_id: str) -> str:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    document = build_passport(design)
    return render_passport_html(document)
