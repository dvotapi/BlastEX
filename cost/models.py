"""Dataclass'ы для сметных расчётов (этап 0) и DDD-контракты движка сметы."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cost.catalog import CatalogItem
    from cost.drilling import (
        DrillingCostResult,
        DrillingUnitCostInput,
        DrillingUnitCostResult,
    )
    from cost.drilling_data import WorkObject
    from cost.fixed_costs import FixedCostItem, FixedCostsResult
    from cost.labor import JobPosition, LaborAssignment, LaborFOTResult, LaborFOTSettings
    from cost.materials import MaterialsSelection, VariableMaterialsResult


@dataclass
class HoleGeometry:
    """Геометрия и заряд одной скважины (левый блок Excel)."""

    grid_a_m: float
    grid_b_m: float
    depth_m: float
    overdrill_m: float
    undercharge_m: float
    charge_length_m: float
    charge_diameter_m: float
    capacity_kg_per_m: float
    charge_mass_kg: float
    yield_m3: float
    specific_q_kg_m3: float
    explosive_name: str
    explosive_label: str

    @property
    def charge_diameter_mm(self) -> float:
        return self.charge_diameter_m * 1000


@dataclass
class InitiationConfig:
    """Схема инициирования одной скважины."""

    intermediate_detonators_per_hole: int
    nsi_per_hole: int
    nsi_length_1_m: float
    nsi_length_2_m: float
    detonator_delay_ms: int

    @property
    def downhole_nsi_per_hole(self) -> int:
        return self.nsi_per_hole

    @property
    def surface_nsi_per_hole(self) -> int:
        return 1


@dataclass
class BlockGeometry:
    """Показатели блока по одному варианту заряжания."""

    block_volume_m3: float
    yield_per_hole_m3: float
    hole_count: int
    additional_holes_pct: float
    additional_holes: int
    total_holes: int
    drilling_footage_m: float
    total_charge_mass_kg: float
    specific_q_kg_m3: float
    intermediate_detonators_per_hole: int
    nsi_per_hole: int
    nsi_length_1_m: float
    nsi_length_2_m: float
    detonator_delay_ms: int
    total_intermediate_detonators: int
    total_downhole_nsi: int
    total_nsi_length_m: float
    total_boosters: int
    total_surface_nsi: int
    total_start_nsi: int


@dataclass
class BlockCalculationInput:
    """Входные данные технического расчёта блока для стратегии сценария."""

    hole: HoleGeometry
    block: BlockGeometry
    initiation: InitiationConfig
    explosive_key: str
    hole_depth_m: float
    materials_selection: MaterialsSelection | None = None
    production_volume_tons: float = 0.0
    rock_density_t_m3: float = 2.65


@dataclass
class CalculationContext:
    """Сквозной контекст расчёта сметы для любой стратегии."""

    work_object: WorkObject
    catalog: list[CatalogItem]
    labor_catalog: list[JobPosition]
    labor_assignments: list[LaborAssignment]
    fixed_costs_items: list[FixedCostItem]
    drilling_input_base: DrillingUnitCostInput
    labor_settings: LaborFOTSettings = field(default_factory=lambda: _default_labor_settings())
    scenario_phase_overrides: dict[str, bool] = field(default_factory=dict)


def _default_labor_settings() -> LaborFOTSettings:
    from cost.labor import LaborFOTSettings

    return LaborFOTSettings()


@dataclass
class AggregatedCostResult:
    """Унифицированный результат расчёта сценария для UI."""

    scenario_id: str
    work_object_name: str = ""
    block_geometry: BlockGeometry | None = None
    drilling_unit_cost: DrillingUnitCostResult | None = None
    drilling_total_cost: DrillingCostResult | None = None
    materials_cost: VariableMaterialsResult | None = None
    labor_fot: LaborFOTResult | None = None
    fixed_costs: FixedCostsResult | None = None
    total_amount_rub: float = 0.0
    cost_per_m3: float = 0.0
    cost_per_ton: float = 0.0
    child_results: list[AggregatedCostResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def variable_total_rub(self) -> float:
        total = 0.0
        if self.materials_cost is not None:
            total += self.materials_cost.total_amount
        if self.drilling_total_cost is not None:
            total += self.drilling_total_cost.amount
        return total

    @property
    def fixed_total_rub(self) -> float:
        if self.fixed_costs is None:
            return 0.0
        return self.fixed_costs.total_amount

    @property
    def labor_total_rub(self) -> float:
        if self.labor_fot is None:
            return 0.0
        return self.labor_fot.total_fot
