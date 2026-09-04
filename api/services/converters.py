"""Преобразование dataclass ↔ Pydantic для API."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from Blast import ExplosiveProperties, RockProperties, TargetParams
from api.schemas.blast import (
    BlastOptimizeRequest,
    ExplosivePropertiesSchema,
    RockPropertiesSchema,
    TargetParamsSchema,
)
from api.schemas.cost import (
    AggregatedCostResultSchema,
    BlockCalculationInputSchema,
    CalculationContextInputSchema,
    CostCalculateRequest,
    ManualScenarioInputSchema,
    MaterialsSelectionSchema,
)
from cost.catalog import catalog_from_records
from cost.drilling import DrillingUnitCostInput
from cost.drilling_data import DEFAULT_OBJECT_NAME, find_object
from cost.fixed_costs import fixed_costs_from_records
from cost.geometry import build_manual_block_input
from cost.labor import (
    DEFAULT_LABOR_ASSIGNMENTS,
    LaborFOTSettings,
    labor_assignments_from_records,
    labor_catalog_from_records,
)
from cost.materials import MaterialsSelection
from cost.models import (
    AggregatedCostResult,
    BlockCalculationInput,
    BlockGeometry,
    CalculationContext,
    HoleGeometry,
    InitiationConfig,
)
from cost.scenarios import get_scenario_calc_profile, get_scenario_template
from cost.v2.legacy_adapter import (
    LegacyReferences,
    resolve_work_object_name as resolve_existing_work_object_name,
)


def rock_from_schema(schema: RockPropertiesSchema) -> RockProperties:
    return RockProperties(**schema.model_dump())


def explosive_from_schema(schema: ExplosivePropertiesSchema) -> ExplosiveProperties:
    return ExplosiveProperties(**schema.model_dump())


def target_from_schema(schema: TargetParamsSchema) -> TargetParams:
    return TargetParams(**schema.model_dump())


def blast_request_to_engine_inputs(
    request: BlastOptimizeRequest,
) -> tuple[RockProperties, ExplosiveProperties, TargetParams]:
    return (
        rock_from_schema(request.rock),
        explosive_from_schema(request.explosive),
        target_from_schema(request.target),
    )


def materials_selection_from_schema(
    schema: MaterialsSelectionSchema | None,
) -> MaterialsSelection | None:
    if schema is None:
        return None
    return MaterialsSelection(**schema.model_dump())


def block_input_from_schema(schema: BlockCalculationInputSchema) -> BlockCalculationInput:
    return BlockCalculationInput(
        hole=HoleGeometry(**schema.hole.model_dump()),
        block=BlockGeometry(**schema.block.model_dump()),
        initiation=InitiationConfig(**schema.initiation.model_dump()),
        explosive_key=schema.explosive_key,
        hole_depth_m=schema.hole_depth_m,
        materials_selection=materials_selection_from_schema(schema.materials_selection),
        production_volume_tons=schema.production_volume_tons,
        rock_density_t_m3=schema.rock_density_t_m3,
    )


def manual_input_to_block(schema: ManualScenarioInputSchema) -> BlockCalculationInput:
    return build_manual_block_input(
        block_volume_m3=schema.block_volume_m3,
        total_holes=schema.total_holes,
        drilling_footage_m=schema.drilling_footage_m,
        total_charge_mass_kg=schema.total_charge_mass_kg,
        production_volume_tons=schema.production_volume_tons,
        explosive_key=schema.explosive_key,
    )


def resolve_work_object_name(name: str | None, legacy: LegacyReferences) -> str:
    """Имя объекта для сметы.

    Расчёт из «Проектирования» имени не присылает, а объекта Cost V1 по
    умолчанию в справочнике организации может не быть — тогда берём объект из
    самой ревизии. Явно названный объект не подменяем: если его нет, об этом
    нужно сказать, а не считать чужую смету.
    """

    if name:
        return name
    return resolve_existing_work_object_name(legacy, DEFAULT_OBJECT_NAME)


def build_calculation_context(
    request: CostCalculateRequest,
    legacy: LegacyReferences,
) -> CalculationContext:
    """Контекст сметы: справочники — из опубликованной ревизии, переопределения — из запроса."""

    from api.exceptions import WorkObjectNotFoundError

    ctx_input = request.context or CalculationContextInputSchema()
    work_object_name = resolve_work_object_name(request.work_object_name, legacy)
    work_objects = list(legacy.work_objects)
    drill_rigs = list(legacy.drill_rigs)
    work_object = find_object(work_object_name, work_objects)
    if work_object is None:
        raise WorkObjectNotFoundError(work_object_name)

    catalog = (
        list(legacy.catalog)
        if ctx_input.catalog is None
        else catalog_from_records([item.model_dump() for item in ctx_input.catalog])
    )
    labor_catalog = (
        list(legacy.labor_catalog)
        if ctx_input.labor_catalog is None
        else labor_catalog_from_records([item.model_dump() for item in ctx_input.labor_catalog])
    )
    labor_assignments = (
        list(DEFAULT_LABOR_ASSIGNMENTS)
        if ctx_input.labor_assignments is None
        else labor_assignments_from_records([item.model_dump() for item in ctx_input.labor_assignments])
    )
    fixed_costs = (
        list(legacy.fixed_costs)
        if ctx_input.fixed_costs_items is None
        else fixed_costs_from_records([item.model_dump() for item in ctx_input.fixed_costs_items])
    )

    drilling_defaults = DrillingUnitCostInput(object_name=work_object_name)
    if ctx_input.drilling_input is not None:
        drilling_dict = drilling_defaults.__dict__ | ctx_input.drilling_input.model_dump(exclude_unset=True)
        drilling_dict["object_name"] = work_object_name
        drilling_input = DrillingUnitCostInput(**drilling_dict)
    else:
        drilling_input = DrillingUnitCostInput(**(drilling_defaults.__dict__ | {"object_name": work_object_name}))

    labor_settings = (
        LaborFOTSettings()
        if ctx_input.labor_settings is None
        else LaborFOTSettings(**ctx_input.labor_settings.model_dump())
    )

    return CalculationContext(
        work_object=work_object,
        work_objects=work_objects,
        drill_rigs=drill_rigs,
        catalog=catalog,
        labor_catalog=labor_catalog,
        labor_assignments=labor_assignments,
        fixed_costs_items=fixed_costs,
        drilling_input_base=drilling_input,
        labor_settings=labor_settings,
        scenario_phase_overrides=dict(ctx_input.scenario_phase_overrides),
    )


def resolve_block_data(request: CostCalculateRequest) -> BlockCalculationInput | None:
    if request.block is not None:
        return block_input_from_schema(request.block)
    if request.manual_input is not None:
        return manual_input_to_block(request.manual_input)
    profile = get_scenario_calc_profile(request.scenario_id)
    if not profile.is_manual_input:
        return None

    manual_type = profile.manual_type
    if manual_type == "evv":
        # Объём производства — в production_volume_tons, не в total_charge_mass_kg.
        return build_manual_block_input(
            production_volume_tons=request.production_volume_tons,
        )
    if manual_type == "pvv":
        # Масса ВВ задаётся явно в manual_input.total_charge_mass_kg (кг).
        return build_manual_block_input()
    if manual_type == "rc":
        return build_manual_block_input()

    return build_manual_block_input(production_volume_tons=request.production_volume_tons)


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return {key: _serialize_value(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


def aggregated_result_to_schema(result: AggregatedCostResult) -> AggregatedCostResultSchema:
    payload = _serialize_value(result)
    payload["variable_total_rub"] = result.variable_total_rub
    payload["fixed_total_rub"] = result.fixed_total_rub
    payload["labor_total_rub"] = result.labor_total_rub
    if result.fixed_costs is not None:
        payload["fixed_costs"]["total_per_m3"] = result.fixed_costs.total_per_m3
    if result.drilling_unit_cost is not None:
        unit = result.drilling_unit_cost
        payload["drilling_unit_cost"] = {
            "commercial_speed_m_per_shift": unit.commercial_speed_m_per_shift,
            "fuel_l_per_m": unit.fuel_l_per_m,
            "direct_cost_per_m": unit.direct_cost_per_m,
            "cost_per_m": unit.cost_per_m,
            "price_per_m": unit.price_per_m,
            "diesel_share": unit.diesel_share,
            "lines": _serialize_value(unit.lines),
        }
    payload["child_results"] = [
        aggregated_result_to_schema(child).model_dump()
        for child in result.child_results
    ]
    return AggregatedCostResultSchema.model_validate(payload)


def validate_scenario_exists(scenario_id: str) -> None:
    from api.exceptions import ScenarioNotFoundError

    if get_scenario_template(scenario_id) is None:
        raise ScenarioNotFoundError(scenario_id)
