"""Delta-style design levers — not a full scenario engine (BDX-016).

Each hint answers: if this controllable feature moves a small engineering
step, what happens to the overlay prediction? Physics baselines are held
fixed; only the ML overlay is re-evaluated.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from intelligence.explainability.labels import (
    feature_label_en,
    format_expected_delta,
)
from intelligence.explainability.types import (
    ACTION_INCREASE,
    ACTION_REDUCE,
    RecommendationHint,
)
from intelligence.uncertainty.labels import feature_label

# Controllable blast-design knobs. Geology / environment / baseline are not levers.
CONTROLLABLE_FEATURES: dict[str, dict[str, float | str]] = {
    "GEOMETRY.mean_burden_m": {
        "step": 0.2,
        "frac": 0.1,
        "min_value": 0.5,
        "preferred_action": ACTION_REDUCE,
    },
    "GEOMETRY.mean_spacing_m": {
        "step": 0.2,
        "frac": 0.1,
        "min_value": 0.5,
        "preferred_action": ACTION_REDUCE,
    },
    "GEOMETRY.mean_diameter_mm": {
        "step": 10.0,
        "frac": 0.05,
        "min_value": 50.0,
        "preferred_action": ACTION_REDUCE,
    },
    "GEOMETRY.mean_subdrill_m": {
        "step": 0.15,
        "frac": 0.15,
        "min_value": 0.0,
        "preferred_action": ACTION_INCREASE,
    },
    "CHARGING.mean_powder_factor_kg_m3": {
        "step": 0.05,
        "frac": 0.1,
        "min_value": 0.1,
        "preferred_action": ACTION_INCREASE,
    },
    "CHARGING.mean_stemming_m": {
        "step": 0.2,
        "frac": 0.1,
        "min_value": 0.3,
        "preferred_action": ACTION_REDUCE,
    },
    "CHARGING.mean_charge_kg": {
        "step": 5.0,
        "frac": 0.08,
        "min_value": 1.0,
        "preferred_action": ACTION_INCREASE,
    },
    "TIMING.mean_delay_ms": {
        "step": 5.0,
        "frac": 0.1,
        "min_value": 0.0,
        "preferred_action": ACTION_INCREASE,
    },
}

ACTION_LABELS_RU = {
    ACTION_REDUCE: "Снижение",
    ACTION_INCREASE: "Увеличение",
}

TOP_RECOMMENDATIONS = 4


def _step_size(current: float, spec: dict[str, float | str]) -> float:
    step = abs(float(spec.get("step") or 0.0))
    frac = abs(float(spec.get("frac") or 0.0))
    sized = max(step, frac * abs(float(current)))
    return sized if sized > 0 else step


def _threshold(current_prediction: float, unit: str) -> float:
    magnitude = abs(float(current_prediction))
    text = str(unit or "").strip().lower()
    if text in {"", "0-1", "0–1"}:
        return 0.005
    if text in {"mm", "мм"}:
        return max(0.5, 0.004 * magnitude)
    if text in {"%", "mm/s", "мм/с"}:
        return max(0.02, 0.004 * magnitude)
    return max(0.01, 0.003 * magnitude)


def _action_label(action: str, label: str) -> str:
    prefix = ACTION_LABELS_RU.get(action, action)
    return f"{prefix} {label}"


def _hint(
    *,
    feature: str,
    action: str,
    delta: float,
    step: float,
    unit: str,
    target_name: str,
    target_label: str,
) -> RecommendationHint:
    label = feature_label(feature)
    label_en = feature_label_en(feature)
    action_label = _action_label(action, label)
    summary = (
        f"{action_label}: ожидаемый {target_label or target_name} "
        f"{format_expected_delta(delta, unit)}"
    )
    return RecommendationHint(
        feature=feature,
        label=label,
        label_en=label_en,
        action=action,
        action_label=action_label,
        delta=float(delta),
        unit=unit,
        target_name=target_name,
        target_label=target_label,
        step=float(step),
        summary=summary,
    )


def recommendation_deltas(
    *,
    vector: np.ndarray,
    feature_names: list[str],
    predict_scalar: Callable[[np.ndarray], float],
    target_name: str,
    target_label: str,
    unit: str,
    top_n: int = TOP_RECOMMENDATIONS,
) -> list[RecommendationHint]:
    """Perturb each controllable column and keep the strongest overlay deltas."""
    x = np.asarray(vector, dtype=float).reshape(-1)
    if x.size != len(feature_names):
        return []
    current = float(predict_scalar(x))
    threshold = _threshold(current, unit)
    index_by_name = {name: index for index, name in enumerate(feature_names)}
    hints: list[RecommendationHint] = []

    for feature, spec in CONTROLLABLE_FEATURES.items():
        index = index_by_name.get(feature)
        if index is None:
            continue
        current_value = float(x[index])
        step = _step_size(current_value, spec)
        if step <= 0:
            continue
        min_value = float(spec.get("min_value") or 0.0)
        preferred = str(spec.get("preferred_action") or ACTION_REDUCE)
        candidates: list[tuple[str, float, float]] = []

        reduced = max(min_value, current_value - step)
        if abs(reduced - current_value) > 1e-9:
            probe = np.array(x, copy=True)
            probe[index] = reduced
            delta = float(predict_scalar(probe)) - current
            candidates.append((ACTION_REDUCE, delta, reduced - current_value))

        increased = current_value + step
        probe = np.array(x, copy=True)
        probe[index] = increased
        delta = float(predict_scalar(probe)) - current
        candidates.append((ACTION_INCREASE, delta, step))

        meaningful = [item for item in candidates if abs(item[1]) >= threshold]
        if not meaningful:
            continue
        preferred_hit = next((item for item in meaningful if item[0] == preferred), None)
        chosen = preferred_hit or max(meaningful, key=lambda item: abs(item[1]))
        hints.append(
            _hint(
                feature=feature,
                action=chosen[0],
                delta=chosen[1],
                step=chosen[2],
                unit=unit,
                target_name=target_name,
                target_label=target_label,
            )
        )

    hints.sort(key=lambda item: abs(item.delta), reverse=True)
    return hints[: max(1, int(top_n))]
