"""Стратегия: взрывные работы без бурения."""
from __future__ import annotations

from typing import Any

from cost.models import AggregatedCostResult, BlockCalculationInput, CalculationContext
from cost.strategies.base import BaseScenarioStrategy
from cost.strategies.common import finalize_aggregate, run_fixed_module, run_labor_module, run_materials_module


class BlastingOnlyScenarioStrategy(BaseScenarioStrategy):
    scenario_id = "blasting"

    def calculate(
        self,
        block_data: BlockCalculationInput | None,
        ctx: CalculationContext,
        **kwargs: Any,
    ) -> AggregatedCostResult:
        if block_data is None:
            result = self._empty_result(ctx)
            result.notes.append("Нет данных блока для расчёта взрывных работ.")
            return result

        include_labor = kwargs.get("include_labor", True)
        include_fixed = kwargs.get("include_fixed", True)

        result = AggregatedCostResult(
            scenario_id=kwargs.get("scenario_id", self.scenario_id),
            work_object_name=ctx.work_object.name,
            block_geometry=block_data.block,
        )
        run_materials_module(result, block_data, ctx, selection=kwargs.get("materials_selection"))

        if include_labor:
            run_labor_module(result, ctx)
        if include_fixed:
            run_fixed_module(result, block_data, ctx)

        return finalize_aggregate(result, block_data)
