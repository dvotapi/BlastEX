"""Assemble the official blast passport. Never writes or approves the design."""
from __future__ import annotations

from typing import Any

from api.exceptions import DesignNotFoundError, InvalidDesignError
from api.schemas.reporting import PassportBuildRequest, PassportDocumentSchema, PassportRolesResponse
from cost.v2.repository import EconomicsRepository
from design import persistence as design_persistence
from design.models import BlastDesign
from design.reporting.engine import DEFAULT_FRAG_MODEL, build_passport, needs_kuzram_settings
from design.reporting.html import passport_html, render_passport_html
from design.reporting.types import roles_payload


def list_roles() -> PassportRolesResponse:
    return PassportRolesResponse(**roles_payload())


def _settings_kwargs(
    design: BlastDesign,
    request: PassportBuildRequest | None,
    *,
    organization_id: str | None,
    repository: EconomicsRepository | None,
) -> dict[str, Any]:
    """Настройки Kuz-Ram для прогноза паспорта; не читаются, когда не нужны."""
    from api.services.fragmentation_settings import resolve_kuzram_settings

    model = request.fragmentation_model if request is not None else DEFAULT_FRAG_MODEL
    if not needs_kuzram_settings(design, model):
        return {}
    resolved = resolve_kuzram_settings(
        explicit=request.kuzram.to_settings() if request is not None and request.kuzram is not None else None,
        work_object_name=(request.work_object_name if request is not None else "") or "",
        organization_id=organization_id,
        repository=repository,
    )
    return {"kuzram_settings": resolved.settings, "kuzram_settings_source": resolved.source_payload()}


def _document_from_design(
    design: BlastDesign,
    request: PassportBuildRequest | None = None,
    *,
    organization_id: str | None = None,
    repository: EconomicsRepository | None = None,
) -> PassportDocumentSchema:
    kwargs: dict = _settings_kwargs(design, request, organization_id=organization_id, repository=repository)
    if request is not None:
        kwargs.update(
            {
                "lump_size_mm": request.lump_size_mm,
                "max_oversize_pct": request.max_oversize_pct,
                "fragmentation_model": request.fragmentation_model,
                "include_predictions": request.include_predictions,
                "planned_cost": request.planned_cost.model_dump() if request.planned_cost else None,
                "predicted_cost": request.predicted_cost.model_dump() if request.predicted_cost else None,
            }
        )
    try:
        document = build_passport(design, **kwargs)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    payload = document.to_dict()
    if payload.get("approved") or payload.get("auto_approved"):
        raise InvalidDesignError("Паспорт не должен утверждаться автоматически.")
    return PassportDocumentSchema(**payload)


def build_from_request(
    request: PassportBuildRequest,
    *,
    organization_id: str | None = None,
    repository: EconomicsRepository | None = None,
) -> PassportDocumentSchema:
    design = BlastDesign.from_dict(request.design.model_dump())
    before_holes = [hole.to_dict() for hole in design.holes]
    before_loads = [load.to_dict() for load in design.loads]
    document = _document_from_design(design, request, organization_id=organization_id, repository=repository)
    if [hole.to_dict() for hole in design.holes] != before_holes:
        raise InvalidDesignError("Сборка паспорта не должна менять проектные скважины.")
    if [load.to_dict() for load in design.loads] != before_loads:
        raise InvalidDesignError("Сборка паспорта не должна менять проектный заряд.")
    return document


def render_from_request(
    request: PassportBuildRequest,
    *,
    organization_id: str | None = None,
    repository: EconomicsRepository | None = None,
) -> str:
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
            **_settings_kwargs(design, request, organization_id=organization_id, repository=repository),
        )
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc


def get_plan_passport(
    team_id: str, design_id: str, *, repository: EconomicsRepository | None = None
) -> PassportDocumentSchema:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return _document_from_design(design, organization_id=team_id, repository=repository)


def export_plan_passport_html(
    team_id: str, design_id: str, *, repository: EconomicsRepository | None = None
) -> str:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    document = build_passport(design, **_settings_kwargs(design, None, organization_id=team_id, repository=repository))
    return render_passport_html(document)
