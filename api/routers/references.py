"""REST-роутеры справочников."""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas.references import (
    CatalogItemSchema,
    CatalogListResponse,
    DrillRigListResponse,
    DrillRigSchema,
    ExplosiveCatalogSchema,
    ExplosiveListResponse,
    FixedAssetDepreciationListResponse,
    FixedAssetDepreciationSchema,
    RockListResponse,
    RockSchema,
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
from cost.depreciation_data import DEFAULT_DEPRECIATION_ASSETS, depreciation_assets_from_records
from cost.explosive_data import DEFAULT_EXPLOSIVE_KEY, DEFAULT_EXPLOSIVES, explosives_from_records
from cost.persistence import DEFAULT_TEAM_ID, load_team_references
from cost.rock_data import DEFAULT_ROCK_NAME, DEFAULT_ROCKS, rocks_from_records

router = APIRouter(prefix="/references", tags=["references"])


def _team_work_objects(team_id: str):
    refs = load_team_references(team_id)
    objects = work_objects_from_records(refs.work_object_records)
    return objects or list(DEFAULT_WORK_OBJECTS)


def _team_drill_rigs(team_id: str):
    refs = load_team_references(team_id)
    rigs = drill_rigs_from_records(refs.drill_rig_records)
    return rigs or list(DEFAULT_DRILL_RIGS)


def _team_rocks(team_id: str):
    refs = load_team_references(team_id)
    rocks = rocks_from_records(refs.rock_records)
    return rocks or list(DEFAULT_ROCKS)


def _team_explosives(team_id: str):
    refs = load_team_references(team_id)
    items = explosives_from_records(refs.explosive_records)
    return items or list(DEFAULT_EXPLOSIVES)


def _team_depreciation_assets(team_id: str):
    refs = load_team_references(team_id)
    assets = depreciation_assets_from_records(refs.depreciation_asset_records)
    return assets or list(DEFAULT_DEPRECIATION_ASSETS)


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


@router.get("/rocks", response_model=RockListResponse)
def list_rocks(
    team_id: str = Query(DEFAULT_TEAM_ID, description="ID команды (файл data/teams/{id}/references.json)"),
) -> RockListResponse:
    items = _team_rocks(team_id)
    default_name = DEFAULT_ROCK_NAME if any(r.name == DEFAULT_ROCK_NAME for r in items) else items[0].name
    return RockListResponse(
        items=[RockSchema.model_validate(rock) for rock in items],
        default_name=default_name,
    )


@router.get("/explosives", response_model=ExplosiveListResponse)
def list_explosives(
    team_id: str = Query(DEFAULT_TEAM_ID, description="ID команды (файл data/teams/{id}/references.json)"),
) -> ExplosiveListResponse:
    items = _team_explosives(team_id)
    default_key = DEFAULT_EXPLOSIVE_KEY if any(e.key == DEFAULT_EXPLOSIVE_KEY for e in items) else items[0].key
    return ExplosiveListResponse(
        items=[ExplosiveCatalogSchema.model_validate(item) for item in items],
        default_key=default_key,
    )


@router.get("/depreciation-assets", response_model=FixedAssetDepreciationListResponse)
def list_depreciation_assets(
    team_id: str = Query(DEFAULT_TEAM_ID, description="ID команды (файл data/teams/{id}/references.json)"),
) -> FixedAssetDepreciationListResponse:
    items = _team_depreciation_assets(team_id)
    return FixedAssetDepreciationListResponse(
        items=[FixedAssetDepreciationSchema.model_validate(asset) for asset in items],
    )


@router.get("/catalog", response_model=CatalogListResponse)
def list_catalog() -> CatalogListResponse:
    return CatalogListResponse(
        items=[CatalogItemSchema.model_validate(item) for item in DEFAULT_CATALOG],
    )
