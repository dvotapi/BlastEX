"""Стратегия: буровзрывные работы (композиция бурение + взрывные)."""
from __future__ import annotations

from typing import Any

from cost.models import BlockCalculationInput, CalculationContext
from cost.strategies.base import BaseScenarioStrategy
from cost.strategies.blasting_only import BlastingOnlyScenarioStrategy
from cost.strategies.common import merge_partial_results
from cost.strategies.drilling_only import DrillingOnlyScenarioStrategy


class DrillBlastScenarioStrategy(BaseScenarioStrategy):
    scenario_id = "drill_blast"

    def __init__(self) -> None:
        self._drilling_strategy = DrillingOnlyScenarioStrategy()
        self._blasting_strategy = BlastingOnlyScenarioStrategy()

    def calculate(
        self,
        block_data: BlockCalculationInput | None,
        ctx: CalculationContext,
        **kwargs: Any,
    ) -> AggregatedCostResult:
        if block_data is None:
            result = self._empty_result(ctx)
            result.notes.append("Нет данных блока для буровзрывных работ.")
            return result

        child_kwargs = {
            "include_labor": False,
            "include_fixed": False,
            "scenario_id": self.scenario_id,
            "materials_selection": kwargs.get("materials_selection"),
        }

        drilling_part = self._drilling_strategy.calculate(block_data, ctx, **child_kwargs)
        blasting_part = self._blasting_strategy.calculate(block_data, ctx, **child_kwargs)

        return merge_partial_results(
            scenario_id=self.scenario_id,
            work_object_name=ctx.work_object.name,
            parts=[drilling_part, blasting_part],
            block_data=block_data,
            include_labor=True,
            include_fixed=True,
            ctx=ctx,
        )
