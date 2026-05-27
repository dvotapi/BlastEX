"""Фабрика стратегий расчёта сценариев."""
from __future__ import annotations

from cost.scenarios import normalize_scenario_id
from cost.strategies.base import BaseScenarioStrategy
from cost.strategies.blasting_only import BlastingOnlyScenarioStrategy
from cost.strategies.contour_blasting import ContourBlastingScenarioStrategy
from cost.strategies.drill_blast import DrillBlastScenarioStrategy
from cost.strategies.drilling_only import DrillingOnlyScenarioStrategy
from cost.strategies.evv_manufacturing import ExplosiveManufacturingStrategy
from cost.strategies.pvv_delivery import PvvDeliveryScenarioStrategy
from cost.strategies.rc_drilling import RcDrillingScenarioStrategy


class ScenarioStrategyFactory:
    _registry: dict[str, type[BaseScenarioStrategy]] = {
        "evv_manufacturing": ExplosiveManufacturingStrategy,
        "pvv_delivery": PvvDeliveryScenarioStrategy,
        "blasting": BlastingOnlyScenarioStrategy,
        "drilling": DrillingOnlyScenarioStrategy,
        "drill_blast": DrillBlastScenarioStrategy,
        "contour_blasting": ContourBlastingScenarioStrategy,
        "rc_drilling": RcDrillingScenarioStrategy,
    }

    @classmethod
    def create(cls, scenario_id: str) -> BaseScenarioStrategy:
        normalized = normalize_scenario_id(scenario_id)
        strategy_cls = cls._registry.get(normalized, DrillBlastScenarioStrategy)
        strategy = strategy_cls()
        strategy.scenario_id = normalized
        return strategy

    @classmethod
    def registered_ids(cls) -> list[str]:
        return list(cls._registry.keys())
