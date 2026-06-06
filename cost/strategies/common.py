"""Общие функции оркестрации модулей расчёта для стратегий сценариев."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from cost.drilling import (
    DrillingUnitCostInput,
    calculate_drilling_cost,
    calculate_drilling_unit_cost,
)
from cost.fixed_costs import FixedCostItem, calculate_fixed_costs
from cost.labor import LaborFOTSettings, calculate_labor_fot
from cost.materials import MaterialsSelection, calculate_variable_materials
from cost.models import AggregatedCostResult, BlockCalculationInput, CalculationContext

if TYPE_CHECKING:
    from cost.catalog import CatalogItem


def apply_work_object_to_drilling_input(
    base: DrillingUnitCostInput,
    work_object_name: str,
    *,
    volume_m: float | None = None,
) -> DrillingUnitCostInput:
    """Подставляет объект работ: мобилизация и цена ДТ из справочника WorkObject."""
    params = replace(base, object_name=work_object_name)
    if volume_m is not None:
        params = replace(params, volume_m=volume_m)
    return params


def run_drilling_module(
    result: AggregatedCostResult,
    block_data: BlockCalculationInput,
    ctx: CalculationContext,
) -> None:
    drilling_input = apply_work_object_to_drilling_input(
        ctx.drilling_input_base,
        ctx.work_object.name,
        volume_m=block_data.block.drilling_footage_m,
    )
    unit_cost = calculate_drilling_unit_cost(
        drilling_input,
        work_objects=ctx.work_objects or [ctx.work_object],
        drill_rigs=ctx.drill_rigs or None,
    )
    total_cost = calculate_drilling_cost(
        block=block_data.block,
        hole_depth_m=block_data.hole_depth_m,
        price_per_m=unit_cost.price_per_m,
    )
    result.drilling_unit_cost = unit_cost
    result.drilling_total_cost = total_cost
    result.block_geometry = block_data.block


def run_materials_module(
    result: AggregatedCostResult,
    block_data: BlockCalculationInput,
    ctx: CalculationContext,
    *,
    selection: MaterialsSelection | None = None,
) -> None:
    if selection is None:
        selection = block_data.materials_selection
    if selection is None:
        return

    materials = calculate_variable_materials(
        block=block_data.block,
        initiation=block_data.initiation,
        catalog=ctx.catalog,
        selection=selection,
    )
    result.materials_cost = materials
    result.block_geometry = block_data.block


def run_manufacturing_materials_module(
    result: AggregatedCostResult,
    ctx: CalculationContext,
    *,
    production_volume_tons: float,
    explosive_id: str | None = None,
) -> None:
    """Упрощённый расчёт материалов производства ЭВВ: объём в тоннах × цена из каталога."""
    from cost.catalog import get_catalog_item, items_by_category
    from cost.materials import MaterialLine, VariableMaterialsResult

    if production_volume_tons <= 0:
        return

    explosive = None
    if explosive_id:
        explosive = get_catalog_item(ctx.catalog, explosive_id)
    if explosive is None:
        explosives = items_by_category(ctx.catalog, "explosive")
        explosive = explosives[0] if explosives else None
    if explosive is None:
        return

    mass_kg = production_volume_tons * 1000.0
    amount = mass_kg * explosive.price
    result.materials_cost = VariableMaterialsResult(
        lines=[
            MaterialLine(
                section="Производство ЭВВ",
                nomenclature=explosive.name,
                unit=explosive.unit,
                quantity=mass_kg,
                price=explosive.price,
                amount=amount,
                source=f"объём производства {production_volume_tons:.1f} т",
            )
        ],
        total_amount=amount,
    )


def run_labor_module(
    result: AggregatedCostResult,
    ctx: CalculationContext,
) -> None:
    result.labor_fot = calculate_labor_fot(
        catalog=ctx.labor_catalog,
        assignments=ctx.labor_assignments,
        settings=ctx.labor_settings,
    )


def run_fixed_module(
    result: AggregatedCostResult,
    block_data: BlockCalculationInput | None,
    ctx: CalculationContext,
) -> None:
    volume_m3 = block_data.block.block_volume_m3 if block_data is not None else 30_000.0
    result.fixed_costs = calculate_fixed_costs(
        block_volume_m3=volume_m3,
        items=ctx.fixed_costs_items,
    )


def merge_partial_results(
    *,
    scenario_id: str,
    work_object_name: str,
    parts: list[AggregatedCostResult],
    block_data: BlockCalculationInput | None,
    include_labor: bool = True,
    include_fixed: bool = True,
    ctx: CalculationContext | None = None,
) -> AggregatedCostResult:
    merged = AggregatedCostResult(
        scenario_id=scenario_id,
        work_object_name=work_object_name,
        child_results=parts,
    )
    for part in parts:
        if part.block_geometry is not None:
            merged.block_geometry = part.block_geometry
        if part.drilling_unit_cost is not None:
            merged.drilling_unit_cost = part.drilling_unit_cost
        if part.drilling_total_cost is not None:
            merged.drilling_total_cost = part.drilling_total_cost
        if part.materials_cost is not None:
            merged.materials_cost = part.materials_cost
        merged.notes.extend(part.notes)

    if include_labor and ctx is not None:
        run_labor_module(merged, ctx)
    if include_fixed and ctx is not None:
        run_fixed_module(merged, block_data, ctx)

    finalize_aggregate(merged, block_data)
    return merged


def finalize_aggregate(
    result: AggregatedCostResult,
    block_data: BlockCalculationInput | None,
) -> AggregatedCostResult:
    total = result.variable_total_rub + result.labor_total_rub + result.fixed_total_rub
    result.total_amount_rub = total

    block_volume_m3 = 0.0
    production_tons = 0.0
    rock_density = 2.65
    if block_data is not None:
        block_volume_m3 = block_data.block.block_volume_m3
        production_tons = block_data.production_volume_tons
        rock_density = block_data.rock_density_t_m3

    if block_volume_m3 > 0:
        result.cost_per_m3 = total / block_volume_m3

    if production_tons > 0:
        result.cost_per_ton = total / production_tons
    elif block_volume_m3 > 0 and rock_density > 0:
        mass_tons = block_volume_m3 * rock_density
        if mass_tons > 0:
            result.cost_per_ton = total / mass_tons

    return result
