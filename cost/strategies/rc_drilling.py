"""Стратегия: RC-бурение."""
from __future__ import annotations

from cost.strategies.drilling_only import DrillingOnlyScenarioStrategy


class RcDrillingScenarioStrategy(DrillingOnlyScenarioStrategy):
    scenario_id = "rc_drilling"
