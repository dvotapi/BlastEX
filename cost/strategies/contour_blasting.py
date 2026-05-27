"""Стратегия: контурное взрывание (бурение + заряжание)."""
from __future__ import annotations

from typing import Any

from cost.models import BlockCalculationInput, CalculationContext
from cost.strategies.blasting_only import BlastingOnlyScenarioStrategy
from cost.strategies.common import merge_partial_results
from cost.strategies.drilling_only import DrillingOnlyScenarioStrategy


class ContourBlastingScenarioStrategy(DrillingOnlyScenarioStrategy):
    scenario_id = "contour_blasting"

    def __init__(self) -> None:
        self._blasting_strategy = BlastingOnlyScenarioStrategy()

    def calculate(
        self,
        block_data: BlockCalculationInput | None,
        ctx: CalculationContext,
        **kwargs: Any,
    ):
        if block_data is None:
            result = self._empty_result(ctx)
            result.notes.append("Нет данных для контурного взрывания.")
            return result

        child_kwargs = {
            "include_labor": False,
            "include_fixed": False,
            "scenario_id": self.scenario_id,
            "materials_selection": kwargs.get("materials_selection"),
        }
        drilling_part = super().calculate(block_data, ctx, **child_kwargs)
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
