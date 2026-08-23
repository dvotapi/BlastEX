"""Build the BDX-015 explanation attached to a single overlay prediction."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from intelligence.explainability.importance import global_feature_importance
from intelligence.explainability.labels import feature_label_en, format_share_pct
from intelligence.explainability.recommendations import recommendation_deltas
from intelligence.explainability.shap_values import local_shap_values
from intelligence.explainability.types import (
    METHOD_NONE,
    FeatureDriver,
    PredictionExplanation,
    empty_explanation,
)
from intelligence.uncertainty.labels import feature_label

TOP_DRIVERS = 5
MIN_SHARE_PCT = 1.0


def _direction(shap_value: float) -> str:
    if shap_value > 1e-9:
        return "increases"
    if shap_value < -1e-9:
        return "decreases"
    return "neutral"


def _shares(values: np.ndarray) -> np.ndarray:
    total = float(np.sum(np.abs(values)))
    if total <= 1e-12:
        return np.zeros(values.size, dtype=float)
    return 100.0 * np.abs(values) / total


def _driver_rows(
    *,
    feature_names: list[str],
    shap_values: np.ndarray,
    importance: np.ndarray,
    top_n: int,
) -> list[FeatureDriver]:
    local_share = _shares(shap_values)
    global_share = _shares(importance) if importance.size == shap_values.size else np.zeros_like(local_share)
    if float(np.sum(local_share)) <= 1e-9 and float(np.sum(global_share)) > 1e-9:
        local_share = global_share
        shap_values = np.zeros_like(shap_values)
    order = np.argsort(-local_share)
    rows: list[FeatureDriver] = []
    for index in order:
        share = float(local_share[index])
        if rows and share < MIN_SHARE_PCT and len(rows) >= min(3, top_n):
            continue
        name = feature_names[int(index)]
        rows.append(
            FeatureDriver(
                feature=name,
                label=feature_label(name),
                label_en=feature_label_en(name),
                share_pct=round(share, 1),
                importance_pct=round(float(global_share[index]) if index < global_share.size else 0.0, 1),
                shap_value=round(float(shap_values[index]), 6),
                direction=_direction(float(shap_values[index])),
            )
        )
        if len(rows) >= top_n:
            break
    return rows


def driver_summary(target_label: str, drivers: list[FeatureDriver], *, limit: int = 3) -> str:
    if not drivers:
        return ""
    title = target_label or "прогноза"
    parts = [f"{item.label} {format_share_pct(item.share_pct)}" for item in drivers[:limit]]
    return f"Основные драйверы {title}: " + ", ".join(parts)


def explain_estimator(
    *,
    estimator: Any,
    vector: list[float] | np.ndarray,
    feature_names: list[str],
    training_matrix: list[list[float]] | np.ndarray | None = None,
    predict_fn: Callable[[np.ndarray], np.ndarray] | None = None,
    clamp: Callable[[float], float] | None = None,
    residual_offset: float = 0.0,
    target_name: str = "",
    target_label: str = "",
    unit: str = "",
    top_n: int = TOP_DRIVERS,
) -> PredictionExplanation:
    """Local SHAP-style drivers + delta-style levers for one estimator."""
    if estimator is None or not feature_names:
        return empty_explanation(target_name=target_name, target_label=target_label, unit=unit)

    x = np.asarray(vector, dtype=float).reshape(-1)
    if x.size != len(feature_names):
        return empty_explanation(target_name=target_name, target_label=target_label, unit=unit)

    def raw_predict(X: np.ndarray) -> np.ndarray:
        if predict_fn is not None:
            return np.asarray(predict_fn(X), dtype=float)
        return np.asarray(estimator.predict(X), dtype=float)

    def reported(value: float) -> float:
        point = float(value) + float(residual_offset)
        if clamp is not None:
            return float(clamp(point))
        return point

    try:
        contrib, expected_raw, method = local_shap_values(
            estimator,
            x,
            training_matrix=training_matrix,
            predict_fn=raw_predict,
            feature_names=feature_names,
        )
        importance = global_feature_importance(
            estimator,
            feature_names,
            training_matrix=training_matrix,
            predict_fn=raw_predict,
        )
    except Exception:
        return empty_explanation(target_name=target_name, target_label=target_label, unit=unit)

    expected = reported(expected_raw)
    drivers = _driver_rows(
        feature_names=feature_names,
        shap_values=np.asarray(contrib, dtype=float).reshape(-1),
        importance=np.asarray(importance, dtype=float).reshape(-1),
        top_n=top_n,
    )
    recommendations = recommendation_deltas(
        vector=x,
        feature_names=feature_names,
        predict_scalar=lambda row: reported(float(raw_predict(np.asarray(row, dtype=float).reshape(1, -1))[0])),
        target_name=target_name,
        target_label=target_label,
        unit=unit,
    )
    rec_summary = recommendations[0].summary if recommendations else ""
    return PredictionExplanation(
        method=method or METHOD_NONE,
        expected_value=round(float(expected), 6),
        drivers=drivers,
        recommendations=recommendations,
        target_name=target_name,
        target_label=target_label,
        unit=unit,
        summary=driver_summary(target_label or target_name, drivers),
        recommendation_summary=rec_summary,
    )
