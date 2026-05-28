"""Pydantic-схемы сметного расчёта."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.references import CatalogItemSchema


class HoleGeometrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grid_a_m: float = Field(..., gt=0)
    grid_b_m: float = Field(..., gt=0)
    depth_m: float = Field(..., gt=0)
    overdrill_m: float = Field(0, ge=0)
    undercharge_m: float = Field(0, ge=0)
    charge_length_m: float = Field(0, ge=0)
    charge_diameter_m: float = Field(0, ge=0)
    capacity_kg_per_m: float = Field(0, ge=0)
    charge_mass_kg: float = Field(0, ge=0)
    yield_m3: float = Field(0, ge=0)
    specific_q_kg_m3: float = Field(0, ge=0)
    explosive_name: str = ""
    explosive_label: str = ""


class InitiationConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    intermediate_detonators_per_hole: int = Field(1, ge=1, le=2)
    nsi_per_hole: int = Field(1, ge=1, le=2)
    nsi_length_1_m: float = Field(12.0, gt=0)
    nsi_length_2_m: float = Field(6.0, ge=0)
    detonator_delay_ms: int = Field(500, ge=0)


class BlockGeometrySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    block_volume_m3: float = Field(0, ge=0)
    yield_per_hole_m3: float = Field(0, ge=0)
    hole_count: int = Field(0, ge=0)
    additional_holes_pct: float = Field(0, ge=0)
    additional_holes: int = Field(0, ge=0)
    total_holes: int = Field(0, ge=0)
    drilling_footage_m: float = Field(0, ge=0)
    total_charge_mass_kg: float = Field(0, ge=0)
    specific_q_kg_m3: float = Field(0, ge=0)
    intermediate_detonators_per_hole: int = Field(0, ge=0)
    nsi_per_hole: int = Field(0, ge=0)
    nsi_length_1_m: float = Field(0, ge=0)
    nsi_length_2_m: float = Field(0, ge=0)
    detonator_delay_ms: int = Field(0, ge=0)
    total_intermediate_detonators: int = Field(0, ge=0)
    total_downhole_nsi: int = Field(0, ge=0)
    total_nsi_length_m: float = Field(0, ge=0)
    total_boosters: int = Field(0, ge=0)
    total_surface_nsi: int = Field(0, ge=0)
    total_start_nsi: int = Field(0, ge=0)


class MaterialsSelectionSchema(BaseModel):
    explosive_id: str
    detonator_id: str
    downhole_nsi1_id: str
    downhole_nsi2_id: str | None = None
    surface_nsi_id: str = ""
    start_nsi_id: str = ""


class BlockCalculationInputSchema(BaseModel):
    hole: HoleGeometrySchema
    block: BlockGeometrySchema
    initiation: InitiationConfigSchema
    explosive_key: str = ""
    hole_depth_m: float = Field(0, ge=0)
    materials_selection: MaterialsSelectionSchema | None = None
    production_volume_tons: float = Field(0, ge=0)
    rock_density_t_m3: float = Field(2.65, gt=0)


class ManualScenarioInputSchema(BaseModel):
    """Упрощённый ввод для сценариев без геометрии БВР."""

    block_volume_m3: float = Field(0, ge=0)
    total_holes: int = Field(0, ge=0)
    drilling_footage_m: float = Field(0, ge=0)
    total_charge_mass_kg: float = Field(0, ge=0)
    production_volume_tons: float = Field(0, ge=0)
    explosive_key: str = ""


class DrillingUnitCostInputSchema(BaseModel):
    volume_m: float = Field(2343.688167787891, gt=0)
    crown_mm: float = Field(152.0, gt=0)
    rig_name: str = "JK 830-3"
    tech_speed_m_h: float = Field(12.0, gt=0)
    nonproductive_h_per_shift: float = Field(1.0, ge=0)
    object_name: str = ""
    mobilization_km: float | None = None
    diesel_price_ton_rub: float | None = None
    profit_factor: float = Field(1.2, gt=0)


class LaborFOTSettingsSchema(BaseModel):
    shifts_per_month: float = Field(5.0, gt=0)
    net_to_gross_factor: float = Field(0.85, gt=0, le=1)
    accident_rate: float = Field(0.0042, ge=0)
    social_rate: float = Field(0.30, ge=0)
    vacation_reserve_divisor: float = Field(5.0, gt=0)


class JobPositionSchema(BaseModel):
    id: str
    name: str
    fixed_salary_monthly: float = Field(..., ge=0)
    piece_rate_per_m3: float = Field(..., ge=0)


class LaborAssignmentSchema(BaseModel):
    id: str
    position_id: str
    headcount: float = Field(..., gt=0)
    volume_m3: float = Field(..., ge=0)
    employee_shifts: float = Field(1.0, gt=0)


class FixedCostItemSchema(BaseModel):
    id: str
    section: str
    name: str
    amount_rub: float = Field(..., ge=0)
    note: str = ""
    enabled: bool = True


class CalculationContextInputSchema(BaseModel):
    """Переопределения контекста сметы; пустые поля — значения по умолчанию."""

    catalog: list[CatalogItemSchema] | None = None
    labor_catalog: list[JobPositionSchema] | None = None
    labor_assignments: list[LaborAssignmentSchema] | None = None
    fixed_costs_items: list[FixedCostItemSchema] | None = None
    drilling_input: DrillingUnitCostInputSchema | None = None
    labor_settings: LaborFOTSettingsSchema | None = None
    scenario_phase_overrides: dict[str, bool] = Field(default_factory=dict)


class CostCalculateRequest(BaseModel):
    scenario_id: str = Field(..., examples=["drill_blast"])
    work_object_name: str | None = Field(
        None,
        description="Имя объекта работ из справочника. Если не задано — объект по умолчанию.",
    )
    context: CalculationContextInputSchema | None = None
    block: BlockCalculationInputSchema | None = Field(
        None,
        description="Геометрия блока для сценариев БВР/бурения.",
    )
    manual_input: ManualScenarioInputSchema | None = Field(
        None,
        description="Упрощённый ввод для ПВВ, ЭВВ, RC.",
    )
    materials_selection: MaterialsSelectionSchema | None = None
    production_volume_tons: float = Field(0, ge=0)


# --- Ответы ---


class MaterialLineSchema(BaseModel):
    section: str
    nomenclature: str
    unit: str
    quantity: float
    price: float
    amount: float
    source: str


class VariableMaterialsResultSchema(BaseModel):
    lines: list[MaterialLineSchema]
    total_amount: float


class DrillingCostLineSchema(BaseModel):
    section: str
    name: str
    quantity: float | None
    unit: str
    total_rub: float | None
    price_per_m: float
    note: str = ""


class DrillingUnitCostResultSchema(BaseModel):
    commercial_speed_m_per_shift: float
    fuel_l_per_m: float
    direct_cost_per_m: float
    cost_per_m: float
    price_per_m: float
    diesel_share: float
    lines: list[DrillingCostLineSchema] = Field(default_factory=list)


class DrillingCostResultSchema(BaseModel):
    total_holes: float
    hole_depth_m: float
    drilling_footage_m: float
    yield_per_meter_m3: float
    price_per_m: float
    amount: float


class LaborLineResultSchema(BaseModel):
    assignment_id: str
    position_id: str
    position_name: str
    headcount: float
    volume_m3: float
    employee_shifts: float
    fixed_part: float
    piece_part: float
    line_amount: float


class LaborFOTResultSchema(BaseModel):
    lines: list[LaborLineResultSchema]
    gross_salary: float
    accident_contribution: float
    social_contribution: float
    vacation_reserve: float
    contributions_total: float
    total_fot: float


class FixedCostLineSchema(BaseModel):
    section: str
    section_title: str
    name: str
    amount: float


class FixedCostsResultSchema(BaseModel):
    lines: list[FixedCostLineSchema]
    section_totals: dict[str, float]
    total_amount: float
    block_volume_m3: float
    total_per_m3: float


class AggregatedCostResultSchema(BaseModel):
    scenario_id: str
    work_object_name: str = ""
    block_geometry: BlockGeometrySchema | None = None
    drilling_unit_cost: DrillingUnitCostResultSchema | None = None
    drilling_total_cost: DrillingCostResultSchema | None = None
    materials_cost: VariableMaterialsResultSchema | None = None
    labor_fot: LaborFOTResultSchema | None = None
    fixed_costs: FixedCostsResultSchema | None = None
    total_amount_rub: float = 0.0
    cost_per_m3: float = 0.0
    cost_per_ton: float = 0.0
    variable_total_rub: float = 0.0
    fixed_total_rub: float = 0.0
    labor_total_rub: float = 0.0
    child_results: list["AggregatedCostResultSchema"] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# Forward ref для рекурсивной модели
AggregatedCostResultSchema.model_rebuild()
