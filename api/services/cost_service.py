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
from cost.v2.legacy_adapter import LegacyReferences


def calculate_cost(request: CostCalculateRequest, legacy: LegacyReferences) -> AggregatedCostResultSchema:
    validate_scenario_exists(request.scenario_id)
    context = build_calculation_context(request, legacy)
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


def calculate_drilling_unit(
    request: "DrillingUnitCalculateRequest", legacy: LegacyReferences
) -> "DrillingUnitCalculateResponse":
    from dataclasses import asdict

    from api.schemas.cost import (
        DrillingCostLineSchema,
        DrillingUnitCalculateResponse,
        DrillingUnitCostResultSchema,
    )
    from cost.drilling import DrillingUnitCostInput, calculate_drilling_unit_cost, unit_cost_summary_rows

    params = DrillingUnitCostInput(**request.input.model_dump())
    result = calculate_drilling_unit_cost(
        params, work_objects=list(legacy.work_objects), drill_rigs=list(legacy.drill_rigs)
    )

    result_schema = DrillingUnitCostResultSchema(
        commercial_speed_m_per_shift=result.commercial_speed_m_per_shift,
        fuel_l_per_m=result.fuel_l_per_m,
        direct_cost_per_m=result.direct_cost_per_m,
        cost_per_m=result.cost_per_m,
        price_per_m=result.price_per_m,
        diesel_share=result.diesel_share,
        lines=[DrillingCostLineSchema(**asdict(line)) for line in result.lines],
    )
    return DrillingUnitCalculateResponse(
        result=result_schema,
        summary_rows=unit_cost_summary_rows(result),
    )


def calculate_labor(request: "LaborCalculateRequest") -> "LaborCalculateResponse":
    from dataclasses import asdict

    from api.schemas.cost import LaborCalculateResponse, LaborFOTResultSchema, LaborLineResultSchema
    from cost.labor import (
        LaborFOTSettings,
        calculate_labor_fot,
        labor_assignments_from_records,
        labor_catalog_from_records,
        labor_summary_rows,
        labor_table_rows,
    )

    catalog = labor_catalog_from_records([item.model_dump() for item in request.labor_catalog])
    assignments = labor_assignments_from_records(
        [item.model_dump() for item in request.labor_assignments]
    )
    settings = LaborFOTSettings(**request.settings.model_dump())
    result = calculate_labor_fot(catalog=catalog, assignments=assignments, settings=settings)

    result_schema = LaborFOTResultSchema(
        lines=[LaborLineResultSchema(**asdict(line)) for line in result.lines],
        gross_salary=result.gross_salary,
        accident_contribution=result.accident_contribution,
        social_contribution=result.social_contribution,
        vacation_reserve=result.vacation_reserve,
        contributions_total=result.contributions_total,
        total_fot=result.total_fot,
    )
    return LaborCalculateResponse(
        result=result_schema,
        table_rows=labor_table_rows(result),
        summary_rows=labor_summary_rows(result),
    )


def resolve_materials_auto(request: "MaterialsAutoRequest", legacy: LegacyReferences) -> "MaterialsAutoResponse":
    from api.schemas.cost import MaterialsAutoResponse, MaterialsSelectionSchema
    from cost.materials import auto_materials_selection
    from cost.models import InitiationConfig

    catalog = list(legacy.catalog)

    selection = auto_materials_selection(
        catalog=catalog,
        explosive_key=request.explosive_key,
        initiation=InitiationConfig(**request.initiation.model_dump()),
    )
    return MaterialsAutoResponse(selection=MaterialsSelectionSchema(**selection.__dict__))
