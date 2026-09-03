"""REST-роутеры справочников Cost V1: только чтение из опубликованной ревизии.

Редактирование — публикация ревизии на странице «Справочники»
(`/economics/references/publish`); отдельной записи у этих маршрутов нет.
"""
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
from api.services.legacy_references import current_legacy_references
from cost.drilling_data import DEFAULT_OBJECT_NAME, DEFAULT_RIG_NAME
from cost.explosive_data import DEFAULT_EXPLOSIVE_KEY
from cost.rock_data import DEFAULT_ROCK_NAME
from cost.v2.legacy_adapter import LegacyReferences

router = APIRouter(prefix="/references", tags=["references"])


@router.get("/work-objects", response_model=WorkObjectListResponse)
def list_work_objects(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> WorkObjectListResponse:
    items = list(legacy.work_objects)
    default_name = DEFAULT_OBJECT_NAME if any(o.name == DEFAULT_OBJECT_NAME for o in items) else items[0].name
    return WorkObjectListResponse(
        items=[WorkObjectSchema.model_validate(obj) for obj in items],
        default_name=default_name,
    )


@router.get("/drill-rigs", response_model=DrillRigListResponse)
def list_drill_rigs(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> DrillRigListResponse:
    items = list(legacy.drill_rigs)
    default_name = DEFAULT_RIG_NAME if any(r.name == DEFAULT_RIG_NAME for r in items) else items[0].name
    return DrillRigListResponse(
        items=[DrillRigSchema.model_validate(rig) for rig in items],
        default_name=default_name,
    )


@router.get("/rocks", response_model=RockListResponse)
def list_rocks(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> RockListResponse:
    items = list(legacy.rocks)
    default_name = DEFAULT_ROCK_NAME if any(r.name == DEFAULT_ROCK_NAME for r in items) else items[0].name
    return RockListResponse(
        items=[RockSchema.model_validate(rock) for rock in items],
        default_name=default_name,
    )


@router.get("/explosives", response_model=ExplosiveListResponse)
def list_explosives(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> ExplosiveListResponse:
    items = list(legacy.explosives)
    default_key = DEFAULT_EXPLOSIVE_KEY if any(e.key == DEFAULT_EXPLOSIVE_KEY for e in items) else items[0].key
    return ExplosiveListResponse(
        items=[ExplosiveCatalogSchema.model_validate(item) for item in items],
        default_key=default_key,
    )


@router.get("/depreciation-assets", response_model=FixedAssetDepreciationListResponse)
def list_depreciation_assets(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> FixedAssetDepreciationListResponse:
    return FixedAssetDepreciationListResponse(
        items=[FixedAssetDepreciationSchema.model_validate(asset) for asset in legacy.depreciation_assets],
    )


@router.get("/catalog", response_model=CatalogListResponse)
def list_catalog(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> CatalogListResponse:
    """Номенклатура и цены из разделов «Материалы» и «Стоимость материалов»."""

    return CatalogListResponse(items=[CatalogItemSchema.model_validate(item) for item in legacy.catalog])
