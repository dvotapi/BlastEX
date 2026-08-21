"""REST-роутер рабочего пространства команды: справочники, снапшот сценария, сценарии."""
from __future__ import annotations

from dataclasses import asdict

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
from api.security import current_team_id
from cost.catalog import DEFAULT_CATALOG
from cost.depreciation_data import DEFAULT_DEPRECIATION_ASSETS
from cost.drilling import calculate_drilling_unit_cost, DrillingUnitCostInput
from cost.drilling_data import (
    DEFAULT_DRILL_RIGS,
    DEFAULT_WORK_OBJECTS,
    drill_rigs_from_records,
    find_object,
    work_objects_from_records,
)
from cost.explosive_data import DEFAULT_EXPLOSIVES
from cost.fixed_costs import DEFAULT_FIXED_COSTS
from cost.labor import DEFAULT_LABOR_ASSIGNMENTS, DEFAULT_LABOR_CATALOG
from cost.rock_data import DEFAULT_ROCKS
from cost.persistence import (
    bootstrap_team_scenarios,
    load_scenario_snapshot,
    load_team_references,
    load_team_settings,
    save_scenario_snapshot,
    save_team_references,
    save_team_settings,
    TeamReferences,
    TeamSettings,
    WorkspaceSnapshot,
)
from cost.scenarios import (
    get_scenario_calc_profile,
    list_scenario_templates,
    normalize_scenario_id,
)

router = APIRouter(tags=["workspace"])


def _settings_schema(settings: TeamSettings) -> TeamSettingsSchema:
    return TeamSettingsSchema(
        team_id=settings.team_id,
        team_name=settings.team_name,
        active_scenario_id=settings.active_scenario_id,
        active_work_object_name=settings.active_work_object_name,
    )


def _snapshot_schema(snapshot: WorkspaceSnapshot) -> WorkspaceSnapshotSchema:
    return WorkspaceSnapshotSchema(**asdict(snapshot))


def _references_schema(refs: TeamReferences) -> TeamReferencesSchema:
    data = asdict(refs)
    data.pop("version", None)
    return TeamReferencesSchema(**data)


def _drilling_price_per_m(snapshot: WorkspaceSnapshot, refs: TeamReferences, work_object_name: str) -> float:
    from cost.strategies.common import apply_work_object_to_drilling_input

    drilling_dict = dict(snapshot.drilling_calculator_input) or DrillingUnitCostInput().__dict__
    drilling_input = DrillingUnitCostInput(**drilling_dict)
    work_objects = work_objects_from_records(refs.work_object_records) or list(DEFAULT_WORK_OBJECTS)
    work_object = find_object(work_object_name, work_objects) or work_objects[0]
    drill_rigs = drill_rigs_from_records(refs.drill_rig_records) or list(DEFAULT_DRILL_RIGS)
    drilling_input = apply_work_object_to_drilling_input(drilling_input, work_object.name)
    return calculate_drilling_unit_cost(
        drilling_input, work_objects=work_objects, drill_rigs=drill_rigs
    ).price_per_m


def _load_state(team_id: str) -> WorkspaceStateSchema:
    bootstrap_team_scenarios(team_id)
    settings = load_team_settings(team_id)
    snapshot = load_scenario_snapshot(team_id, settings.active_scenario_id)
    refs = load_team_references(team_id)
    return WorkspaceStateSchema(
        settings=_settings_schema(settings),
        snapshot=_snapshot_schema(snapshot),
        references=_references_schema(refs),
        drilling_price_per_m=_drilling_price_per_m(
            snapshot, refs, settings.active_work_object_name
        ),
    )


@router.get("/workspace", response_model=WorkspaceStateSchema)
def get_workspace(team_id: str = Depends(current_team_id)) -> WorkspaceStateSchema:
    return _load_state(team_id)


@router.put("/workspace/snapshot", response_model=WorkspaceStateSchema)
def put_workspace_snapshot(
    payload: SaveWorkspaceRequest,
    team_id: str = Depends(current_team_id),
) -> WorkspaceStateSchema:
    settings = load_team_settings(team_id)
    scenario_id = normalize_scenario_id(payload.snapshot.scenario_id)

    snapshot = WorkspaceSnapshot(
        scenario_id=scenario_id,
        cost_catalog_records=payload.snapshot.cost_catalog_records,
        fixed_cost_records=payload.snapshot.fixed_cost_records,
        labor_catalog_records=payload.snapshot.labor_catalog_records,
        labor_assignment_records=payload.snapshot.labor_assignment_records,
        labor_shifts_per_month=payload.snapshot.labor_shifts_per_month,
        drilling_calculator_input=payload.snapshot.drilling_calculator_input,
        scenario_phase_overrides=payload.snapshot.scenario_phase_overrides,
    )
    save_scenario_snapshot(team_id, snapshot)

    refs = TeamReferences(
        work_object_records=payload.references.work_object_records,
        drill_rig_records=payload.references.drill_rig_records,
        rock_records=payload.references.rock_records,
        explosive_records=payload.references.explosive_records,
        depreciation_asset_records=payload.references.depreciation_asset_records,
    )
    save_team_references(team_id, refs)

    settings.active_scenario_id = scenario_id
    if payload.active_work_object_name:
        settings.active_work_object_name = payload.active_work_object_name
    save_team_settings(settings)

    return _load_state(team_id)


@router.put("/workspace/active-scenario", response_model=WorkspaceStateSchema)
def put_active_scenario(
    payload: SwitchScenarioRequest,
    team_id: str = Depends(current_team_id),
) -> WorkspaceStateSchema:
    settings = load_team_settings(team_id)
    settings.active_scenario_id = normalize_scenario_id(payload.scenario_id)
    save_team_settings(settings)
    return _load_state(team_id)


@router.get("/workspace/defaults", response_model=DefaultReferencesResponse)
def workspace_defaults() -> DefaultReferencesResponse:
    """Дефолтные значения справочников и снапшота — для кнопок «Сбросить …»."""
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

