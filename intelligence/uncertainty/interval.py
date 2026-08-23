"""Point-estimate intervals from tree ensembles, with an RMSE floor."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from intelligence.uncertainty.types import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    INTERVAL_PERCENTILES,
    METHOD_ENSEMBLE,
    METHOD_RMSE,
    RMSE_Z,
    DomainCheck,
    SimilarityResult,
    UncertaintyInterval,
)

MIN_HALF_WIDTH = 1e-9


def _tree_estimators(estimator: Any) -> list[Any]:
    trees = getattr(estimator, "estimators_", None)
    if trees is None:
        return []
    return list(trees)


def ensemble_interval(
    estimator: Any,
    X: np.ndarray,
    *,
    rmse: float | None = None,
) -> tuple[np.ndarray, UncertaintyInterval]:
    """Return mean prediction and a single-row interval for X[0]."""
    X = np.asarray(X, dtype=float)
    trees = _tree_estimators(estimator)
    method = METHOD_RMSE
    std = float(rmse) if rmse is not None else 0.0
    if trees:
        stacked = np.vstack([np.asarray(tree.predict(X), dtype=float) for tree in trees])
        mean = stacked.mean(axis=0)
        lo_q, hi_q = INTERVAL_PERCENTILES
        lower = np.percentile(stacked, lo_q, axis=0)
        upper = np.percentile(stacked, hi_q, axis=0)
        tree_std = float(stacked.std(axis=0, ddof=1)[0]) if stacked.shape[0] > 1 else 0.0
        std = max(std, tree_std)
        method = METHOD_ENSEMBLE
    else:
        mean = np.asarray(estimator.predict(X), dtype=float)
        lower = mean.copy()
        upper = mean.copy()

    half_floor = RMSE_Z * float(rmse) if rmse is not None else 0.0
    half = max(float(upper[0] - lower[0]) / 2.0, half_floor, MIN_HALF_WIDTH)
    if method == METHOD_ENSEMBLE and half_floor >= float(upper[0] - lower[0]) / 2.0 - 1e-12:
        if rmse is not None:
            method = METHOD_ENSEMBLE
    centre = float(mean[0])
    interval = UncertaintyInterval(
        std=std if std > 0 else (float(rmse) if rmse is not None else 0.0),
        lower=centre - half,
        upper=centre + half,
        method=method,
    )
    return mean, interval


def apply_offset(interval: UncertaintyInterval, offset: float) -> UncertaintyInterval:
    lower = None if interval.lower is None else float(interval.lower) + float(offset)
    upper = None if interval.upper is None else float(interval.upper) + float(offset)
    return UncertaintyInterval(std=interval.std, lower=lower, upper=upper, method=interval.method)


def clamp_interval(
    interval: UncertaintyInterval,
    prediction: float,
    clamp: Callable[[float], float] | None,
) -> UncertaintyInterval:
    lower = interval.lower
    upper = interval.upper
    if clamp is not None:
        if lower is not None:
            lower = float(clamp(lower))
        if upper is not None:
            upper = float(clamp(upper))
        prediction = float(clamp(prediction))
    if lower is not None:
        lower = min(lower, prediction)
    if upper is not None:
        upper = max(upper, prediction)
    return UncertaintyInterval(std=interval.std, lower=lower, upper=upper, method=interval.method)


def inflate_interval(interval: UncertaintyInterval, scale: float) -> UncertaintyInterval:
    if interval.lower is None or interval.upper is None:
        return interval
    centre = 0.5 * (float(interval.lower) + float(interval.upper))
    half = 0.5 * (float(interval.upper) - float(interval.lower)) * max(float(scale), 1.0)
    std = None if interval.std is None else float(interval.std) * max(float(scale), 1.0)
    return UncertaintyInterval(
        std=std,
        lower=centre - half,
        upper=centre + half,
        method=interval.method,
    )


def grade_confidence(
    *,
    in_domain: bool,
    similarity: SimilarityResult,
    comparable_count: int | None = None,
) -> str:
    comparable = similarity.comparable_count if comparable_count is None else int(comparable_count)
    if not in_domain or comparable <= 0:
        return CONFIDENCE_LOW
    if similarity.score >= 0.75 and comparable >= 4:
        return CONFIDENCE_HIGH
    return CONFIDENCE_MEDIUM


def interval_from_rmse(prediction: float, rmse: float | None) -> UncertaintyInterval:
    sigma = float(rmse) if rmse is not None else 0.0
    half = max(RMSE_Z * sigma, MIN_HALF_WIDTH)
    return UncertaintyInterval(
        std=sigma,
        lower=float(prediction) - half,
        upper=float(prediction) + half,
        method=METHOD_RMSE,
    )
