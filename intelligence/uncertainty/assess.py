"""Build the BDX-014 assessment attached to every prediction."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from intelligence.uncertainty.domain import (
    check_domain,
    extrapolation_scale,
    format_applicability_warning,
    resolve_ranges,
    similarity_to_training,
)
from intelligence.uncertainty.interval import (
    apply_offset,
    clamp_interval,
    ensemble_interval,
    grade_confidence,
    inflate_interval,
)
from intelligence.uncertainty.types import (
    PredictionAssessment,
    empty_assessment,
)


def assess_vector(
    *,
    prediction: float,
    vector: list[float],
    feature_names: list[str],
    feature_ranges: dict[str, Any] | None,
    training_matrix: list[list[float]] | None,
    estimator: Any = None,
    rmse: float | None = None,
    residual_offset: float = 0.0,
    clamp: Callable[[float], float] | None = None,
    X: np.ndarray | None = None,
) -> PredictionAssessment:
    """Attach interval, confidence, similarity and an applicability warning."""
    ranges = resolve_ranges(feature_names, feature_ranges, training_matrix)
    missing = not ranges
    domain = check_domain(vector, feature_names, ranges) if ranges else check_domain([], [], {})
    if missing:
        domain.in_domain = False
    warning = format_applicability_warning(domain, missing_domain=missing)
    similarity = similarity_to_training(vector, training_matrix or [], ranges, feature_names)

    query = X if X is not None else np.asarray([vector], dtype=float)
    point = float(prediction)
    if estimator is not None:
        _raw, interval = ensemble_interval(estimator, query, rmse=rmse)
        interval = apply_offset(interval, float(residual_offset))
    else:
        from intelligence.uncertainty.interval import interval_from_rmse

        interval = interval_from_rmse(point, rmse)

    if not domain.in_domain and not missing:
        interval = inflate_interval(interval, extrapolation_scale(domain))
    if clamp is not None:
        point = float(clamp(point))
    interval = clamp_interval(interval, point, clamp)
    if interval.lower is not None and interval.upper is not None:
        half = 0.5 * (float(interval.upper) - float(interval.lower))
        interval.lower = point - half
        interval.upper = point + half
        interval = clamp_interval(interval, point, clamp)
    confidence = grade_confidence(
        in_domain=domain.in_domain and not missing,
        similarity=similarity,
    )
    return PredictionAssessment(
        prediction=point,
        uncertainty=interval,
        confidence=confidence,
        similarity_score=float(similarity.score),
        applicability_warning=warning,
        comparable_count=int(similarity.comparable_count),
        in_domain=bool(domain.in_domain and not missing),
        sample_count=int(similarity.sample_count),
        extrapolated_features=[item.feature for item in domain.violations],
    )


def unavailable(*, prediction: float | None = None, reason: str = "") -> PredictionAssessment:
    return empty_assessment(prediction=prediction, reason=reason)
