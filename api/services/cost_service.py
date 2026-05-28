"""Сервис сметного расчёта."""
from __future__ import annotations

from api.schemas.cost import AggregatedCostResultSchema, CostCalculateRequest
from api.services.converters import (
    aggregated_result_to_schema,
    build_calculation_context,
    materials_selection_from_schema,
    resolve_block_data,
    validate_scenario_exists,
)
from cost.engine import CostEngine
from cost.scenarios import get_scenario_calc_profile


def calculate_cost(request: CostCalculateRequest) -> AggregatedCostResultSchema:
    validate_scenario_exists(request.scenario_id)
    context = build_calculation_context(request)
    block_data = resolve_block_data(request)
    profile = get_scenario_calc_profile(request.scenario_id)

    if block_data is None and not profile.is_manual_input:
        from api.exceptions import InvalidGeometryError

        raise InvalidGeometryError(
            "Для выбранного сценария требуется блок `block` или `manual_input`."
        )

    materials_selection = materials_selection_from_schema(request.materials_selection)
    if block_data is not None and materials_selection is not None:
        block_data = type(block_data)(
            hole=block_data.hole,
            block=block_data.block,
            initiation=block_data.initiation,
            explosive_key=block_data.explosive_key,
            hole_depth_m=block_data.hole_depth_m,
            materials_selection=materials_selection,
            production_volume_tons=(
                request.production_volume_tons or block_data.production_volume_tons
            ),
            rock_density_t_m3=block_data.rock_density_t_m3,
        )

    production_tons = request.production_volume_tons
    if block_data is not None and production_tons <= 0:
        production_tons = block_data.production_volume_tons

    engine = CostEngine()
    result = engine.calculate_with_context(
        context=context,
        block_data=block_data,
        scenario_id=request.scenario_id,
        materials_selection=materials_selection,
        production_volume_tons=production_tons,
        explosive_id=materials_selection.explosive_id if materials_selection else None,
    )
    return aggregated_result_to_schema(result)
