"""Фасад расчёта сметы Cost V1: готовый контекст → стратегия сценария."""
from __future__ import annotations

from typing import Any

from cost.models import AggregatedCostResult, BlockCalculationInput, CalculationContext
from cost.scenarios import normalize_scenario_id
from cost.strategies.factory import ScenarioStrategyFactory


class CostEngine:
    """Делегирует расчёт стратегии сценария. Контекст собирает
    `api.services.converters.build_calculation_context`."""

    def calculate_with_context(
        self,
        *,
        context: CalculationContext,
        block_data: BlockCalculationInput | None = None,
        scenario_id: str,
        **kwargs: Any,
    ) -> AggregatedCostResult:
        scenario_id = normalize_scenario_id(scenario_id)
        strategy = ScenarioStrategyFactory.create(scenario_id)
        return strategy.calculate(block_data, context, **kwargs)
