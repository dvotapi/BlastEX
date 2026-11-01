"""Сервис сметного расчёта."""
from __future__ import annotations

import logging
from typing import Any

from api.schemas.cost import AggregatedCostResultSchema, CostCalculateRequest
from api.services.converters import (
    aggregated_result_to_schema,
    build_calculation_context,
    materials_selection_from_schema,
    resolve_block_data,
    validate_scenario_exists,
)
from cost.engine import CostEngine
from cost.model.drilling_price import DrillingPriceSource
from cost.model.inputs import ModelParameters
from cost.scenarios import get_scenario_calc_profile
from cost.v2.legacy_adapter import LegacyReferences
from cost.v2.repository import EconomicsRepository


def resolve_drilling_price_source(
    request: CostCalculateRequest,
    repository: EconomicsRepository,
    organization_id: str,
) -> DrillingPriceSource | None:
    """Параметры черновика сметы блока + справочники его ревизии; нет черновика — None.

    Ревизия берётся та же, что у вкладки «Экономика»: пустая — актуальная, иначе
    цена метра на листе расходилась бы с ценой в смете блока.
    """

    model = request.context.drilling_model if request.context else None
    if model is None:
        return None
    parameters = ModelParameters.from_dict(model.parameters.model_dump(mode="json"))
    references = repository.get_reference_snapshot(
        organization_id, parameters.reference_revision_id or None
    )
    return DrillingPriceSource(params=parameters, references=references)


def design_drilling_price_source(
    request: CostCalculateRequest,
    repository: EconomicsRepository,
    organization_id: str,
) -> DrillingPriceSource | None:
    """Источник цены метра для расчётов «Проектирования», у которых нет вкладки «Экономика».

    Явный `drilling_model` главнее; иначе — параметры по умолчанию из актуальной
    ревизии организации (`drilling_price.default_source`).
    """

    explicit = resolve_drilling_price_source(request, repository, organization_id)
    if explicit is not None:
        return explicit
    from cost.model import drilling_price

    return drilling_price.default_source(
        repository.get_reference_snapshot(organization_id, None),
        site_name=request.work_object_name,
    )


def default_design_price_source(
    organization_id: str, *, work_object_name: str | None = None, context: Any = None
) -> DrillingPriceSource | None:
    """Источник цены метра для сервисов без репозитория в аргументах (сценарии, рекомендации, оптимизация).

    Зовётся один раз на прогон: оптимизация считает смету по каждому кандидату,
    снимок справочников для всех один.

    Справочники читаются ревизией организации вызывающего (не чужой «default»);
    сбой чтения не должен ронять сравнение — тогда цены бурения нет, и это в warnings.
    """

    from api.services.economics_service import get_economics_repository

    try:
        cost_request = CostCalculateRequest(
            scenario_id="drill_blast", work_object_name=work_object_name, context=context
        )
        return design_drilling_price_source(cost_request, get_economics_repository(), organization_id)
    except Exception:
        logging.getLogger(__name__).warning("Источник цены бурения не собран", exc_info=True)
        return None


def apply_estimate_to_outcomes(result: AggregatedCostResultSchema, outcomes: Any) -> bool:
    """Смета «Проектирования» → итоги сценария; без цены бурения итог не публикуется.

    Нулевая цена метра при ненулевом погонаже означает, что бурение в смете
    пропущено: такой итог занизил бы стоимость и сделал кандидата оптимизации
    «дешёвым». Причина уходит в предупреждения сценария.
    """

    drilling = result.drilling_total_cost
    if drilling is not None and drilling.drilling_footage_m > 0 and drilling.price_per_m <= 0:
        reason = "; ".join(result.notes) or "нет параметров бурения"
        outcomes.warnings.append(f"Смета не посчитана: цена бурения не определена ({reason}).")
        return False
    for note in result.notes:
        if note not in outcomes.warnings:
            outcomes.warnings.append(note)
    outcomes.total_predicted_cost_rub = float(result.total_amount_rub)
    outcomes.direct_cost_rub = float(result.variable_total_rub)
    outcomes.cost_per_m3 = float(result.cost_per_m3)
    outcomes.cost_source = "engineering"
    return True


def calculate_cost(
    request: CostCalculateRequest,
    legacy: LegacyReferences,
    drilling_price_source: DrillingPriceSource | None = None,
) -> AggregatedCostResultSchema:
    validate_scenario_exists(request.scenario_id)
    context = build_calculation_context(request, legacy, drilling_price_source)
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
