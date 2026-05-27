"""Стратегия: поставка ПВВ в скважину."""
from __future__ import annotations

from typing import Any

from cost.models import BlockCalculationInput, CalculationContext
from cost.strategies.blasting_only import BlastingOnlyScenarioStrategy


class PvvDeliveryScenarioStrategy(BlastingOnlyScenarioStrategy):
    scenario_id = "pvv_delivery"

    def calculate(
        self,
        block_data: BlockCalculationInput | None,
        ctx: CalculationContext,
        **kwargs: Any,
    ):
        kwargs.setdefault("scenario_id", self.scenario_id)
        return super().calculate(block_data, ctx, **kwargs)
