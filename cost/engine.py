"""Фасад расчёта сметы — единая точка входа для UI."""
from __future__ import annotations

from typing import Any

from cost.catalog import catalog_from_records
from cost.drilling import DrillingUnitCostInput
from cost.drilling_data import DEFAULT_OBJECT_NAME, DEFAULT_WORK_OBJECTS, find_object
from cost.fixed_costs import fixed_costs_from_records
from cost.labor import (
    LaborFOTSettings,
    labor_assignments_from_records,
    labor_catalog_from_records,
)
from cost.models import AggregatedCostResult, BlockCalculationInput, CalculationContext
from cost.scenarios import get_scenario_template, normalize_scenario_id
from cost.strategies.factory import ScenarioStrategyFactory


class CostEngine:
    """Собирает CalculationContext из session_state и делегирует расчёт стратегии."""

    def build_context(self, session_state: Any) -> CalculationContext:
        work_object_name = str(
            session_state.get("active_work_object_name", DEFAULT_OBJECT_NAME)
        )
        work_object = find_object(work_object_name)
        if work_object is None:
            work_object = next(
                (obj for obj in DEFAULT_WORK_OBJECTS if obj.name == DEFAULT_OBJECT_NAME),
                DEFAULT_WORK_OBJECTS[0],
            )

        drilling_dict = dict(session_state.get("drilling_calculator_input", {}))
        if not drilling_dict:
            drilling_dict = DrillingUnitCostInput().__dict__
        drilling_input = DrillingUnitCostInput(**drilling_dict)

        labor_settings = LaborFOTSettings(
            shifts_per_month=float(session_state.get("labor_shifts_per_month", 5.0)),
        )

        return CalculationContext(
            work_object=work_object,
            catalog=catalog_from_records(session_state.get("cost_catalog_records", [])),
            labor_catalog=labor_catalog_from_records(
                session_state.get("labor_catalog_records", [])
            ),
            labor_assignments=labor_assignments_from_records(
                session_state.get("labor_assignment_records", [])
            ),
            fixed_costs_items=fixed_costs_from_records(
                session_state.get("fixed_cost_records", [])
            ),
            drilling_input_base=drilling_input,
            labor_settings=labor_settings,
            scenario_phase_overrides=dict(session_state.get("scenario_phase_overrides", {})),
        )

    def calculate(
        self,
        *,
        session_state: Any,
        block_data: BlockCalculationInput | None = None,
        scenario_id: str | None = None,
        **kwargs: Any,
    ) -> AggregatedCostResult:
        scenario_id = normalize_scenario_id(
            scenario_id or str(session_state.get("active_scenario_id", "drill_blast"))
        )
        ctx = self.build_context(session_state)
        strategy = ScenarioStrategyFactory.create(scenario_id)
        return strategy.calculate(block_data, ctx, **kwargs)

    def scenario_supports_module(
        self,
        session_state: Any,
        module: str,
        scenario_id: str | None = None,
    ) -> bool:
        scenario_id = normalize_scenario_id(
            scenario_id or str(session_state.get("active_scenario_id", "drill_blast"))
        )
        template = get_scenario_template(scenario_id)
        if template is None:
            return True
        overrides = dict(session_state.get("scenario_phase_overrides", {}))
        return template.is_module_enabled(module, overrides)

    def get_drilling_price_per_m(self, session_state: Any) -> float:
        ctx = self.build_context(session_state)
        from cost.strategies.common import apply_work_object_to_drilling_input
        from cost.drilling import calculate_drilling_unit_cost

        params = apply_work_object_to_drilling_input(
            ctx.drilling_input_base,
            ctx.work_object.name,
        )
        return calculate_drilling_unit_cost(params).price_per_m
