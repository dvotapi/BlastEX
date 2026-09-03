"""Pydantic-схемы рабочего пространства команды (справочники, сценарии, снапшот)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.schemas.cost import DrillingUnitCostInputSchema, FixedCostItemSchema, JobPositionSchema, LaborAssignmentSchema
from api.schemas.references import (
    CatalogItemSchema,
    DrillRigSchema,
    ExplosiveCatalogSchema,
    FixedAssetDepreciationSchema,
    RockSchema,
    WorkObjectSchema,
)


class TeamSettingsSchema(BaseModel):
    team_id: str
    team_name: str
    active_scenario_id: str
    active_work_object_name: str


class WorkspaceSnapshotSchema(BaseModel):
    """Зеркало cost.persistence.WorkspaceSnapshot — записи не типизируются строго,
    как и в самом персистентном слое (санитайзеры cost/*_data.py делают это при чтении)."""

    scenario_id: str
    updated_at: str = ""
    cost_catalog_records: list[dict[str, Any]] = Field(default_factory=list)
    fixed_cost_records: list[dict[str, Any]] = Field(default_factory=list)
    labor_catalog_records: list[dict[str, Any]] = Field(default_factory=list)
    labor_assignment_records: list[dict[str, Any]] = Field(default_factory=list)
    labor_shifts_per_month: float = 5.0
    drilling_calculator_input: dict[str, Any] = Field(default_factory=dict)
    scenario_phase_overrides: dict[str, bool] = Field(default_factory=dict)


class TeamReferencesSchema(BaseModel):
    """Справочники Cost V1, собранные сервером из опубликованной ревизии
    (только чтение)."""

    work_object_records: list[dict[str, Any]] = Field(default_factory=list)
    drill_rig_records: list[dict[str, Any]] = Field(default_factory=list)
    rock_records: list[dict[str, Any]] = Field(default_factory=list)
    explosive_records: list[dict[str, Any]] = Field(default_factory=list)
    depreciation_asset_records: list[dict[str, Any]] = Field(default_factory=list)


class WorkspaceStateSchema(BaseModel):
    """Полное состояние рабочего пространства команды для загрузки во фронтенд."""

    settings: TeamSettingsSchema
    snapshot: WorkspaceSnapshotSchema
    references: TeamReferencesSchema
    drilling_price_per_m: float = 0.0
    # Чего не хватило в ревизии и что взято взамен: пользователь должен видеть,
    # что смета частично считается на значениях по умолчанию.
    warnings: list[str] = Field(default_factory=list)


class SaveWorkspaceRequest(BaseModel):
    """Сохранение сценария сметы. Справочные записи в `snapshot` игнорируются:
    их источник — опубликованная ревизия."""

    snapshot: WorkspaceSnapshotSchema
    active_work_object_name: str = ""


class SwitchScenarioRequest(BaseModel):
    scenario_id: str


class ScenarioPhaseSchema(BaseModel):
    id: str
    name: str
    enabled: bool = True
    modules: list[str] = Field(default_factory=list)
    volume_source: str = "block_m3"


class ScenarioCalcProfileSchema(BaseModel):
    mode: str
    explosive_basis: str = "none"
    manual_type: str = ""
    ui_caption: str = ""
    needs_blast_optimization: bool
    needs_bvr_geometry: bool
    needs_charge_design: bool
    is_manual_input: bool


class ScenarioListItemSchema(BaseModel):
    id: str
    name: str
    description: str
    phases: list[ScenarioPhaseSchema]
    calc_profile: ScenarioCalcProfileSchema



class DefaultReferencesResponse(BaseModel):
    """Данные для кнопок «Сбросить …» во всех справочниках."""

    rocks: list[RockSchema]
    explosives: list[ExplosiveCatalogSchema]
    depreciation_assets: list[FixedAssetDepreciationSchema]
    work_objects: list[WorkObjectSchema]
    drill_rigs: list[DrillRigSchema]
    catalog: list[CatalogItemSchema]
    fixed_costs: list[FixedCostItemSchema]
    labor_catalog: list[JobPositionSchema]
    labor_assignments: list[LaborAssignmentSchema]
    drilling_unit_cost_input: DrillingUnitCostInputSchema
