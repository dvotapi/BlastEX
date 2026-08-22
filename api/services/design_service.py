"""Сервис проекта БВР: раскладка сетки и хранение паспортов команды."""
from __future__ import annotations

from Blast import ExplosiveProperties
from api.exceptions import DesignNotFoundError, InvalidDesignError, InvalidGeometryError
from api.schemas.design import (
    BlastDesignSchema,
    ChargeGenerateRequest,
    ChargeGenerateResponse,
    DesignListResponse,
    DesignSummarySchema,
    PatternGenerateRequest,
    PatternGenerateResponse,
)
from design import persistence as design_persistence
from design.charging import apply_charge_rules
from design.export import holes_csv
from design.geometry import block_volume
from design.models import BlastDesign, BlockContour, Hole
from design.pattern import generate_pattern as run_generate_pattern


def generate_pattern(request: PatternGenerateRequest) -> PatternGenerateResponse:
    contour = BlockContour.from_dict(request.contour.model_dump())
    if len(contour.vertices) < 3:
        raise InvalidGeometryError("Контур блока должен содержать не менее трёх точек.")

    existing_holes = [Hole.from_dict(h.model_dump()) for h in request.existing_holes]
    holes = run_generate_pattern(contour, request.params, existing_holes)

    return PatternGenerateResponse(
        holes=[h.to_dict() for h in holes],
        hole_count=len(holes),
        block_volume_m3=round(block_volume(contour), 2),
    )


def generate_charge(request: ChargeGenerateRequest) -> ChargeGenerateResponse:
    holes = [Hole.from_dict(h.model_dump()) for h in request.holes]
    if not holes:
        raise InvalidDesignError("Список скважин пуст — нечего заряжать.")

    explosive = ExplosiveProperties(
        name=request.explosive.name,
        density_t_m3=request.explosive.density_t_m3,
        power_mj_kg=request.explosive.power_mj_kg,
    )
    loads = apply_charge_rules(holes, request.rules, explosive)

    return ChargeGenerateResponse(
        loads=[ld.to_dict() for ld in loads],
        total_charge_kg=round(sum(ld.total_charge_kg for ld in loads), 2),
        total_holes_charged=sum(1 for ld in loads if ld.total_charge_kg > 0),
    )


def list_plans(team_id: str) -> DesignListResponse:
    summaries = design_persistence.list_designs(team_id)
    return DesignListResponse(
        items=[DesignSummarySchema(**s.__dict__) for s in summaries]
    )


def create_plan(team_id: str, schema: BlastDesignSchema) -> BlastDesignSchema:
    design = BlastDesign.from_dict(schema.model_dump())
    design.design_id = ""  # новый паспорт всегда получает свежий id
    saved = design_persistence.save_design(team_id, design)
    return BlastDesignSchema(**saved.to_dict())


def get_plan(team_id: str, design_id: str) -> BlastDesignSchema:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return BlastDesignSchema(**design.to_dict())


def save_plan(team_id: str, design_id: str, schema: BlastDesignSchema) -> BlastDesignSchema:
    if schema.design_id and schema.design_id != design_id:
        raise InvalidDesignError("Идентификатор паспорта в теле запроса не совпадает с адресом.")
    design = BlastDesign.from_dict(schema.model_dump())
    design.design_id = design_id
    saved = design_persistence.save_design(team_id, design)
    return BlastDesignSchema(**saved.to_dict())


def delete_plan(team_id: str, design_id: str) -> None:
    try:
        design_persistence.delete_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc


def rename_plan(team_id: str, design_id: str, name: str) -> BlastDesignSchema:
    try:
        design = design_persistence.rename_design(team_id, design_id, name)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return BlastDesignSchema(**design.to_dict())


def export_plan_csv(team_id: str, design_id: str) -> str:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return holes_csv(design)
