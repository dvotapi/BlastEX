"""REST-роутер рабочего пространства Cost V1: настройки и сценарии сметы в БД,
справочники — из опубликованной ревизии."""
from __future__ import annotations

from dataclasses import asdict, replace

from fastapi import APIRouter, Depends

from api.schemas.cost import DrillingUnitCostInputSchema, FixedCostItemSchema, JobPositionSchema, LaborAssignmentSchema
from api.schemas.references import (
    CatalogItemSchema,
    DrillRigSchema,
    ExplosiveCatalogSchema,
    FixedAssetDepreciationSchema,
    RockSchema,
    WorkObjectSchema,
)
from api.schemas.workspace import (
    DefaultReferencesResponse,
    SaveWorkspaceRequest,
    ScenarioCalcProfileSchema,
    ScenarioListItemSchema,
    SwitchScenarioRequest,
    TeamReferencesSchema,
    TeamSettingsSchema,
    WorkspaceSnapshotSchema,
    WorkspaceStateSchema,
)
from api.security import current_team_id, require_internal_access
from api.services.economics_service import get_economics_repository
from api.services.legacy_references import load_legacy_references
from cost.catalog import DEFAULT_CATALOG, catalog_to_records
from cost.depreciation_data import DEFAULT_DEPRECIATION_ASSETS, depreciation_assets_to_records
from cost.drilling import DrillingUnitCostInput, calculate_drilling_unit_cost
from cost.drilling_data import (
    DEFAULT_DRILL_RIGS,
    DEFAULT_OBJECT_NAME,
    DEFAULT_WORK_OBJECTS,
    drill_rigs_to_records,
    work_objects_to_records,
)
from cost.explosive_data import DEFAULT_EXPLOSIVES, explosives_to_records
from cost.fixed_costs import DEFAULT_FIXED_COSTS, fixed_costs_to_records
from cost.labor import DEFAULT_LABOR_ASSIGNMENTS, DEFAULT_LABOR_CATALOG, labor_catalog_to_records
from cost.persistence import WorkspaceSnapshot, build_default_snapshot
from cost.rock_data import DEFAULT_ROCKS, rocks_to_records
from cost.scenarios import (
    DEFAULT_SCENARIO_ID,
    get_scenario_calc_profile,
    list_scenario_templates,
    normalize_scenario_id,
)
from cost.v2.legacy_adapter import LegacyReferences, resolve_work_object_name
from cost.v2.repository import EconomicsRepository, LegacyWorkspaceSettings

router = APIRouter(tags=["workspace"])

DEFAULT_TEAM_NAME = "Команда по умолчанию"

# Поля сценария, которые правит пользователь; справочные записи снапшота
# сервер каждый раз собирает заново из ревизии и не хранит.
_EDITABLE_SNAPSHOT_FIELDS = (
    "labor_assignment_records",
    "labor_shifts_per_month",
    "drilling_calculator_input",
    "scenario_phase_overrides",
)


def _default_settings() -> LegacyWorkspaceSettings:
    return LegacyWorkspaceSettings(
        team_name=DEFAULT_TEAM_NAME,
        active_scenario_id=DEFAULT_SCENARIO_ID,
        active_work_object_name=DEFAULT_OBJECT_NAME,
    )


def _settings(repository: EconomicsRepository, organization_id: str) -> LegacyWorkspaceSettings:
    stored = repository.get_legacy_workspace(organization_id)
    if stored is None:
        return _default_settings()
    return replace(stored, active_scenario_id=normalize_scenario_id(stored.active_scenario_id))


def _settings_schema(organization_id: str, settings: LegacyWorkspaceSettings) -> TeamSettingsSchema:
    return TeamSettingsSchema(
        team_id=organization_id,
        team_name=settings.team_name,
        active_scenario_id=settings.active_scenario_id,
        active_work_object_name=settings.active_work_object_name,
    )


def _scenario_snapshot(
    repository: EconomicsRepository,
    organization_id: str,
    scenario_id: str,
    legacy: LegacyReferences,
) -> WorkspaceSnapshot:
    snapshot = build_default_snapshot(scenario_id)
    stored = repository.get_legacy_scenario(organization_id, scenario_id)
    if stored:
        # Запись сценария означает, что пользователь его сохранял: его правимые
        # поля побеждают, даже если пусты (снятые назначения персонала — это
        # решение, а не отсутствие данных). Значения по умолчанию остаются
        # только у сценария, который ни разу не сохраняли.
        editable = {key: stored[key] for key in _EDITABLE_SNAPSHOT_FIELDS if key in stored}
        snapshot = WorkspaceSnapshot.from_dict({**snapshot.to_dict(), **editable, "scenario_id": scenario_id})
    return replace(
        snapshot,
        cost_catalog_records=catalog_to_records(list(legacy.catalog)),
        fixed_cost_records=fixed_costs_to_records(list(legacy.fixed_costs)),
        labor_catalog_records=labor_catalog_to_records(list(legacy.labor_catalog)),
    )


def _references_schema(legacy: LegacyReferences) -> TeamReferencesSchema:
    return TeamReferencesSchema(
        work_object_records=work_objects_to_records(legacy.work_objects),
        drill_rig_records=drill_rigs_to_records(legacy.drill_rigs),
        rock_records=rocks_to_records(legacy.rocks),
        explosive_records=explosives_to_records(legacy.explosives),
        depreciation_asset_records=depreciation_assets_to_records(legacy.depreciation_assets),
    )


def _drilling_price_per_m(snapshot: WorkspaceSnapshot, legacy: LegacyReferences, work_object_name: str) -> float:
    from cost.strategies.common import apply_work_object_to_drilling_input

    drilling_dict = dict(snapshot.drilling_calculator_input) or DrillingUnitCostInput().__dict__
    drilling_input = DrillingUnitCostInput(**drilling_dict)
    drilling_input = apply_work_object_to_drilling_input(drilling_input, work_object_name)
    return calculate_drilling_unit_cost(
        drilling_input, work_objects=list(legacy.work_objects), drill_rigs=list(legacy.drill_rigs)
    ).price_per_m


def _load_state(repository: EconomicsRepository, organization_id: str) -> WorkspaceStateSchema:
    legacy = load_legacy_references(repository, organization_id)
    stored_settings = _settings(repository, organization_id)
    settings = replace(
        stored_settings,
        # Разрешаем один раз на загрузку состояния, чтобы список объектов,
        # выбранное значение и цена бурения говорили об одном объекте.
        active_work_object_name=resolve_work_object_name(
            legacy, stored_settings.active_work_object_name
        ),
    )
    snapshot = _scenario_snapshot(repository, organization_id, settings.active_scenario_id, legacy)
    return WorkspaceStateSchema(
        settings=_settings_schema(organization_id, settings),
        snapshot=WorkspaceSnapshotSchema(**asdict(snapshot)),
        references=_references_schema(legacy),
        drilling_price_per_m=_drilling_price_per_m(snapshot, legacy, settings.active_work_object_name),
        warnings=list(legacy.warnings),
    )


def _user_id(session: dict) -> str:
    return str(session.get("sub") or "unknown")


@router.get("/workspace", response_model=WorkspaceStateSchema)
def get_workspace(
    organization_id: str = Depends(current_team_id),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> WorkspaceStateSchema:
    return _load_state(repository, organization_id)


@router.put("/workspace/snapshot", response_model=WorkspaceStateSchema)
def put_workspace_snapshot(
    payload: SaveWorkspaceRequest,
    organization_id: str = Depends(current_team_id),
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> WorkspaceStateSchema:
    scenario_id = normalize_scenario_id(payload.snapshot.scenario_id)
    user_id = _user_id(session)
    settings = _settings(repository, organization_id)
    # Сохранение делает сценарий из payload активным.
    repository.import_legacy_scenarios(
        organization_id,
        user_id,
        {
            scenario_id: {
                "scenario_id": scenario_id,
                "labor_assignment_records": payload.snapshot.labor_assignment_records,
                "labor_shifts_per_month": payload.snapshot.labor_shifts_per_month,
                "drilling_calculator_input": payload.snapshot.drilling_calculator_input,
                "scenario_phase_overrides": payload.snapshot.scenario_phase_overrides,
            }
        },
        reference_revision_id=settings.reference_revision_id,
    )
    repository.import_legacy_workspace(
        organization_id,
        user_id,
        team_name=settings.team_name,
        active_scenario_id=scenario_id,
        active_work_object_name=payload.active_work_object_name or settings.active_work_object_name,
        reference_revision_id=settings.reference_revision_id,
    )
    return _load_state(repository, organization_id)


@router.put("/workspace/active-scenario", response_model=WorkspaceStateSchema)
def put_active_scenario(
    payload: SwitchScenarioRequest,
    organization_id: str = Depends(current_team_id),
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> WorkspaceStateSchema:
    settings = _settings(repository, organization_id)
    repository.import_legacy_workspace(
        organization_id,
        _user_id(session),
        team_name=settings.team_name,
        active_scenario_id=normalize_scenario_id(payload.scenario_id),
        active_work_object_name=settings.active_work_object_name,
        reference_revision_id=settings.reference_revision_id,
    )
    return _load_state(repository, organization_id)


@router.get("/workspace/defaults", response_model=DefaultReferencesResponse)
def workspace_defaults() -> DefaultReferencesResponse:
    """Значения Cost V1 по умолчанию — для кнопок «Сбросить …» на вкладках расчёта."""
    return DefaultReferencesResponse(
        rocks=[RockSchema.model_validate(r) for r in DEFAULT_ROCKS],
        explosives=[ExplosiveCatalogSchema.model_validate(e) for e in DEFAULT_EXPLOSIVES],
        depreciation_assets=[
            FixedAssetDepreciationSchema.model_validate(a) for a in DEFAULT_DEPRECIATION_ASSETS
        ],
        work_objects=[WorkObjectSchema.model_validate(o) for o in DEFAULT_WORK_OBJECTS],
        drill_rigs=[DrillRigSchema.model_validate(r) for r in DEFAULT_DRILL_RIGS],
        catalog=[CatalogItemSchema.model_validate(i) for i in DEFAULT_CATALOG],
        fixed_costs=[FixedCostItemSchema.model_validate(i) for i in DEFAULT_FIXED_COSTS],
        labor_catalog=[JobPositionSchema.model_validate(i) for i in DEFAULT_LABOR_CATALOG],
        labor_assignments=[
            LaborAssignmentSchema.model_validate(i) for i in DEFAULT_LABOR_ASSIGNMENTS
        ],
        drilling_unit_cost_input=DrillingUnitCostInputSchema.model_validate(
            DrillingUnitCostInput().__dict__
        ),
    )


@router.get("/scenarios", response_model=list[ScenarioListItemSchema])
def list_scenarios() -> list[ScenarioListItemSchema]:
    items: list[ScenarioListItemSchema] = []
    for template in list_scenario_templates():
        profile = get_scenario_calc_profile(template.id)
        items.append(
            ScenarioListItemSchema(
                id=template.id,
                name=template.name,
                description=template.description,
                phases=[asdict(phase) for phase in template.phases],
                calc_profile=ScenarioCalcProfileSchema(
                    mode=profile.mode,
                    explosive_basis=profile.explosive_basis,
                    manual_type=profile.manual_type,
                    ui_caption=profile.ui_caption,
                    needs_blast_optimization=profile.needs_blast_optimization,
                    needs_bvr_geometry=profile.needs_bvr_geometry,
                    needs_charge_design=profile.needs_charge_design,
                    is_manual_input=profile.is_manual_input,
                ),
            )
        )
    return items
