"""Side-by-side comparison of design overlays (BDX-016).

This is a table, not a multi-objective optimiser (BDX-017) and not an ML
recommendation engine (BDX-018).
"""
from __future__ import annotations

from typing import Any

from design.scenarios.types import (
    COMPARE_METRICS,
    LOWER_IS_BETTER,
    DesignScenario,
)


def compare_scenarios(scenarios: list[DesignScenario]) -> dict[str, Any]:
    """Build a metric×scenario table with optional 'better' highlights."""
    columns = [
        {
            "scenario_id": item.scenario_id,
            "name": item.name,
            "kind": item.kind,
            "design_id": item.design_id,
        }
        for item in scenarios
    ]
    rows: list[dict[str, Any]] = []
    cells: dict[str, dict[str, float | None]] = {}
    for item in scenarios:
        cells[item.scenario_id] = {
            metric["key"]: item.outcomes.metric_value(metric["key"]) for metric in COMPARE_METRICS
        }

    for metric in COMPARE_METRICS:
        key = metric["key"]
        values = [cells[item.scenario_id][key] for item in scenarios]
        best_id = _best_scenario_id(scenarios, key, values) if key in LOWER_IS_BETTER else None
        rows.append(
            {
                "key": key,
                "label": metric["label"],
                "unit": metric["unit"],
                "values": {
                    item.scenario_id: _round_metric(key, cells[item.scenario_id][key])
                    for item in scenarios
                },
                "best_scenario_id": best_id,
            }
        )

    return {
        "metrics": [dict(item) for item in COMPARE_METRICS],
        "scenarios": columns,
        "rows": rows,
        "cells": {
            scenario_id: {key: _round_metric(key, value) for key, value in row.items()}
            for scenario_id, row in cells.items()
        },
        "applied_as": "scenario_overlay",
        "modifies_design": False,
        "is_optimiser": False,
    }


def _round_metric(key: str, value: float | None) -> float | None:
    if value is None:
        return None
    if key in {"hole_count"}:
        return float(int(round(value)))
    if key in {"diameter_mm", "direct_cost_rub", "total_predicted_cost_rub", "x50_mm", "x80_mm"}:
        return round(float(value), 1)
    if key in {"mic_kg", "explosive_mass_kg", "drilling_metres"}:
        return round(float(value), 2)
    return round(float(value), 3)


def _best_scenario_id(
    scenarios: list[DesignScenario],
    key: str,
    values: list[float | None],
) -> str | None:
    ranked = [
        (item.scenario_id, value)
        for item, value in zip(scenarios, values)
        if value is not None
    ]
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[1])
    return ranked[0][0]
