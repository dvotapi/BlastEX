"""REST-роутеры справочников (командные, привязаны к team_id из сессии)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

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
from api.security import current_team_id, require_reference_editor
from cost.catalog import DEFAULT_CATALOG, catalog_from_records
from cost.depreciation_data import DEFAULT_DEPRECIATION_ASSETS, depreciation_assets_from_records, depreciation_assets_to_records
from cost.drilling_data import (
    DEFAULT_DRILL_RIGS,
    DEFAULT_OBJECT_NAME,
    DEFAULT_RIG_NAME,
    DEFAULT_WORK_OBJECTS,
    drill_rigs_from_records,
    drill_rigs_to_records,
    work_objects_from_records,
    work_objects_to_records,
)
from cost.explosive_data import DEFAULT_EXPLOSIVE_KEY, DEFAULT_EXPLOSIVES, explosives_from_records, explosives_to_records
from cost.persistence import load_team_references, load_team_settings, save_team_references
from cost.rock_data import DEFAULT_ROCK_NAME, DEFAULT_ROCKS, rocks_from_records, rocks_to_records

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
def list_work_objects(team_id: str = Depends(current_team_id)) -> WorkObjectListResponse:
    items = _team_work_objects(team_id)
    default_name = DEFAULT_OBJECT_NAME if any(o.name == DEFAULT_OBJECT_NAME for o in items) else items[0].name
    return WorkObjectListResponse(
        items=[WorkObjectSchema.model_validate(obj) for obj in items],
        default_name=default_name,
    )


@router.put("/work-objects", response_model=WorkObjectListResponse)
def put_work_objects(
    payload: list[WorkObjectSchema],
    team_id: str = Depends(current_team_id),
    _editor: dict = Depends(require_reference_editor),
) -> WorkObjectListResponse:
    refs = load_team_references(team_id)
    objects = work_objects_from_records([item.model_dump() for item in payload]) or list(DEFAULT_WORK_OBJECTS)
    refs.work_object_records = work_objects_to_records(objects)
    save_team_references(team_id, refs)
    return list_work_objects(team_id)


@router.get("/drill-rigs", response_model=DrillRigListResponse)
def list_drill_rigs(team_id: str = Depends(current_team_id)) -> DrillRigListResponse:
    items = _team_drill_rigs(team_id)
    default_name = DEFAULT_RIG_NAME if any(r.name == DEFAULT_RIG_NAME for r in items) else items[0].name
    return DrillRigListResponse(
        items=[DrillRigSchema.model_validate(rig) for rig in items],
        default_name=default_name,
    )


@router.put("/drill-rigs", response_model=DrillRigListResponse)
def put_drill_rigs(
    payload: list[DrillRigSchema],
    team_id: str = Depends(current_team_id),
    _editor: dict = Depends(require_reference_editor),
) -> DrillRigListResponse:
    refs = load_team_references(team_id)
    rigs = drill_rigs_from_records([item.model_dump() for item in payload]) or list(DEFAULT_DRILL_RIGS)
    refs.drill_rig_records = drill_rigs_to_records(rigs)
    save_team_references(team_id, refs)
    return list_drill_rigs(team_id)


@router.get("/rocks", response_model=RockListResponse)
def list_rocks(team_id: str = Depends(current_team_id)) -> RockListResponse:
    items = _team_rocks(team_id)
    default_name = DEFAULT_ROCK_NAME if any(r.name == DEFAULT_ROCK_NAME for r in items) else items[0].name
    return RockListResponse(
        items=[RockSchema.model_validate(rock) for rock in items],
        default_name=default_name,
    )


@router.put("/rocks", response_model=RockListResponse)
def put_rocks(
    payload: list[RockSchema],
    team_id: str = Depends(current_team_id),
    _editor: dict = Depends(require_reference_editor),
) -> RockListResponse:
    refs = load_team_references(team_id)
    rocks = rocks_from_records([item.model_dump() for item in payload]) or list(DEFAULT_ROCKS)
    refs.rock_records = rocks_to_records(rocks)
    save_team_references(team_id, refs)
    return list_rocks(team_id)


@router.get("/explosives", response_model=ExplosiveListResponse)
def list_explosives(team_id: str = Depends(current_team_id)) -> ExplosiveListResponse:
    items = _team_explosives(team_id)
    default_key = DEFAULT_EXPLOSIVE_KEY if any(e.key == DEFAULT_EXPLOSIVE_KEY for e in items) else items[0].key
    return ExplosiveListResponse(
        items=[ExplosiveCatalogSchema.model_validate(item) for item in items],
        default_key=default_key,
    )


@router.put("/explosives", response_model=ExplosiveListResponse)
def put_explosives(
    payload: list[ExplosiveCatalogSchema],
    team_id: str = Depends(current_team_id),
    _editor: dict = Depends(require_reference_editor),
) -> ExplosiveListResponse:
    refs = load_team_references(team_id)
    items = explosives_from_records([item.model_dump() for item in payload]) or list(DEFAULT_EXPLOSIVES)
    refs.explosive_records = explosives_to_records(items)
    save_team_references(team_id, refs)
    return list_explosives(team_id)


@router.get("/depreciation-assets", response_model=FixedAssetDepreciationListResponse)
def list_depreciation_assets(team_id: str = Depends(current_team_id)) -> FixedAssetDepreciationListResponse:
    items = _team_depreciation_assets(team_id)
    return FixedAssetDepreciationListResponse(
        items=[FixedAssetDepreciationSchema.model_validate(asset) for asset in items],
    )


@router.put("/depreciation-assets", response_model=FixedAssetDepreciationListResponse)
def put_depreciation_assets(
    payload: list[FixedAssetDepreciationSchema],
    team_id: str = Depends(current_team_id),
    _editor: dict = Depends(require_reference_editor),
) -> FixedAssetDepreciationListResponse:
    refs = load_team_references(team_id)
    assets = depreciation_assets_from_records(
        [item.model_dump() for item in payload]
    ) or list(DEFAULT_DEPRECIATION_ASSETS)
    refs.depreciation_asset_records = depreciation_assets_to_records(assets)
    save_team_references(team_id, refs)
    return list_depreciation_assets(team_id)


@router.get("/catalog", response_model=CatalogListResponse)
def list_catalog(team_id: str = Depends(current_team_id)) -> CatalogListResponse:
    """Номенклатура и цены — часть снапшота активного сценария команды."""
    from cost.persistence import load_scenario_snapshot

    settings = load_team_settings(team_id)
    snapshot = load_scenario_snapshot(team_id, settings.active_scenario_id)
    items = catalog_from_records(snapshot.cost_catalog_records) or list(DEFAULT_CATALOG)
    return CatalogListResponse(items=[CatalogItemSchema.model_validate(item) for item in items])
