"""Базовый интерфейс стратегий расчёта сценариев."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from cost.models import AggregatedCostResult, BlockCalculationInput, CalculationContext


class BaseScenarioStrategy(ABC):
    scenario_id: str = ""

    @abstractmethod
    def calculate(
        self,
        block_data: BlockCalculationInput | None,
        ctx: CalculationContext,
        **kwargs: Any,
    ) -> AggregatedCostResult:
        """Выполнить расчёт сметы для сценария."""

    def _empty_result(self, ctx: CalculationContext) -> AggregatedCostResult:
        return AggregatedCostResult(
            scenario_id=self.scenario_id,
            work_object_name=ctx.work_object.name,
        )
