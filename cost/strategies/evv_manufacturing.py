"""Стратегия: производство компонентов ЭВВ."""
from __future__ import annotations

from typing import Any

from cost.models import AggregatedCostResult, BlockCalculationInput, CalculationContext
from cost.strategies.base import BaseScenarioStrategy
from cost.strategies.common import (
    finalize_aggregate,
    run_fixed_module,
    run_labor_module,
    run_manufacturing_materials_module,
)


class ExplosiveManufacturingStrategy(BaseScenarioStrategy):
    scenario_id = "evv_manufacturing"

    def calculate(
        self,
        block_data: BlockCalculationInput | None,
        ctx: CalculationContext,
        **kwargs: Any,
    ) -> AggregatedCostResult:
        production_tons = kwargs.get("production_volume_tons", 0.0)
        if block_data is not None and block_data.production_volume_tons > 0:
            production_tons = block_data.production_volume_tons

        result = AggregatedCostResult(
            scenario_id=self.scenario_id,
            work_object_name=ctx.work_object.name,
        )

        if production_tons <= 0:
            result.notes.append("Укажите объём производства ЭВВ, т.")
            return result

        run_manufacturing_materials_module(
            result,
            ctx,
            production_volume_tons=production_tons,
            explosive_id=kwargs.get("explosive_id"),
        )
        run_labor_module(result, ctx)
        run_fixed_module(result, block_data, ctx)

        synthetic_block = block_data
        if synthetic_block is None:
            from cost.models import BlockGeometry, HoleGeometry, InitiationConfig

            synthetic_block = BlockCalculationInput(
                hole=HoleGeometry(
                    grid_a_m=0,
                    grid_b_m=0,
                    depth_m=0,
                    overdrill_m=0,
                    undercharge_m=0,
                    charge_length_m=0,
                    charge_diameter_m=0,
                    capacity_kg_per_m=0,
                    charge_mass_kg=0,
                    yield_m3=0,
                    specific_q_kg_m3=0,
                    explosive_name="",
                    explosive_label="",
                ),
                block=BlockGeometry(
                    block_volume_m3=0,
                    yield_per_hole_m3=0,
                    hole_count=0,
                    additional_holes_pct=0,
                    additional_holes=0,
                    total_holes=0,
                    drilling_footage_m=0,
                    total_charge_mass_kg=production_tons * 1000,
                    specific_q_kg_m3=0,
                    intermediate_detonators_per_hole=0,
                    nsi_per_hole=0,
                    nsi_length_1_m=0,
                    nsi_length_2_m=0,
                    detonator_delay_ms=0,
                    total_intermediate_detonators=0,
                    total_downhole_nsi=0,
                    total_nsi_length_m=0,
                    total_boosters=0,
                    total_surface_nsi=0,
                    total_start_nsi=0,
                ),
                initiation=InitiationConfig(0, 0, 0, 0, 0),
                explosive_key="",
                hole_depth_m=0,
                production_volume_tons=production_tons,
            )
        else:
            synthetic_block = BlockCalculationInput(
                hole=block_data.hole,
                block=block_data.block,
                initiation=block_data.initiation,
                explosive_key=block_data.explosive_key,
                hole_depth_m=block_data.hole_depth_m,
                materials_selection=block_data.materials_selection,
                production_volume_tons=production_tons,
                rock_density_t_m3=block_data.rock_density_t_m3,
            )

        return finalize_aggregate(result, synthetic_block)
