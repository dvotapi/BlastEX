"""REST-роутеры справочников."""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas.references import (
    CatalogItemSchema,
    CatalogListResponse,
    DrillRigListResponse,
    DrillRigSchema,
    WorkObjectListResponse,
    WorkObjectSchema,
)
from cost.catalog import DEFAULT_CATALOG
from cost.drilling_data import (
    DEFAULT_DRILL_RIGS,
    DEFAULT_OBJECT_NAME,
    DEFAULT_RIG_NAME,
    DEFAULT_WORK_OBJECTS,
    drill_rigs_from_records,
    work_objects_from_records,
)
from cost.persistence import DEFAULT_TEAM_ID, load_team_references

router = APIRouter(prefix="/references", tags=["references"])


def _team_work_objects(team_id: str):
    refs = load_team_references(team_id)
    objects = work_objects_from_records(refs.work_object_records)
    return objects or list(DEFAULT_WORK_OBJECTS)


def _team_drill_rigs(team_id: str):
    refs = load_team_references(team_id)
    rigs = drill_rigs_from_records(refs.drill_rig_records)
    return rigs or list(DEFAULT_DRILL_RIGS)


@router.get("/work-objects", response_model=WorkObjectListResponse)
def list_work_objects(
    team_id: str = Query(DEFAULT_TEAM_ID, description="ID команды (файл data/teams/{id}/references.json)"),
) -> WorkObjectListResponse:
    items = _team_work_objects(team_id)
    default_name = DEFAULT_OBJECT_NAME if any(o.name == DEFAULT_OBJECT_NAME for o in items) else items[0].name
    return WorkObjectListResponse(
        items=[WorkObjectSchema.model_validate(obj) for obj in items],
        default_name=default_name,
    )


@router.get("/drill-rigs", response_model=DrillRigListResponse)
def list_drill_rigs(
    team_id: str = Query(DEFAULT_TEAM_ID, description="ID команды (файл data/teams/{id}/references.json)"),
) -> DrillRigListResponse:
    items = _team_drill_rigs(team_id)
    default_name = DEFAULT_RIG_NAME if any(r.name == DEFAULT_RIG_NAME for r in items) else items[0].name
    return DrillRigListResponse(
        items=[DrillRigSchema.model_validate(rig) for rig in items],
        default_name=default_name,
    )


@router.get("/catalog", response_model=CatalogListResponse)
def list_catalog() -> CatalogListResponse:
    return CatalogListResponse(
        items=[CatalogItemSchema.model_validate(item) for item in DEFAULT_CATALOG],
    )
