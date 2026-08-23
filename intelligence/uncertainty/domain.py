"""Training-domain ranges, extrapolation checks and nearest-blast similarity."""
from __future__ import annotations

from typing import Any

import numpy as np

from intelligence.uncertainty.labels import feature_label, feature_unit, format_number
from intelligence.uncertainty.types import (
    COMPARABLE_DISTANCE,
    SIMILARITY_DECAY,
    DomainCheck,
    DomainViolation,
    FeatureRange,
    SimilarityResult,
    ranges_from_dict,
)

_CONSTANT_REL_TOL = 0.01
_CONSTANT_ABS_FLOOR = 1e-6


def compute_feature_ranges(
    X: list[list[float]] | np.ndarray,
    feature_names: list[str],
) -> dict[str, FeatureRange]:
    matrix = np.asarray(X, dtype=float)
    ranges: dict[str, FeatureRange] = {}
    if matrix.size == 0:
        for name in feature_names:
            ranges[name] = FeatureRange(name=name, min=0.0, max=0.0, mean=0.0, std=0.0)
        return ranges
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    for index, name in enumerate(feature_names):
        column = matrix[:, index]
        ranges[name] = FeatureRange(
            name=name,
            min=float(np.min(column)),
            max=float(np.max(column)),
            mean=float(np.mean(column)),
            std=float(np.std(column)),
        )
    return ranges


def resolve_ranges(
    feature_names: list[str],
    feature_ranges: dict[str, Any] | None,
    training_matrix: list[list[float]] | None,
) -> dict[str, FeatureRange]:
    ranges = ranges_from_dict(feature_ranges)
    if ranges:
        return ranges
    if training_matrix:
        return compute_feature_ranges(training_matrix, feature_names)
    return {}


def _constant_tolerance(lo: float, hi: float) -> float:
    span = abs(hi - lo)
    if span > 1e-12:
        return 0.0
    return max(abs(lo) * _CONSTANT_REL_TOL, _CONSTANT_ABS_FLOOR)


def check_domain(
    vector: list[float],
    feature_names: list[str],
    feature_ranges: dict[str, FeatureRange] | dict[str, dict[str, Any]],
) -> DomainCheck:
    ranges = ranges_from_dict(feature_ranges) if not _is_range_map(feature_ranges) else feature_ranges
    violations: list[DomainViolation] = []
    for name, value in zip(feature_names, vector):
        bounds = ranges.get(name)
        if bounds is None:
            continue
        lo = float(bounds.min)
        hi = float(bounds.max)
        extra = _constant_tolerance(lo, hi)
        if value < lo - extra or value > hi + extra:
            violations.append(
                DomainViolation(
                    feature=name,
                    value=float(value),
                    min=lo,
                    max=hi,
                    label=feature_label(name),
                    unit=feature_unit(name),
                )
            )
    return DomainCheck(in_domain=not violations, violations=violations)


def _is_range_map(value: Any) -> bool:
    if not value:
        return True
    first = next(iter(value.values()))
    return isinstance(first, FeatureRange)


def extrapolation_scale(check: DomainCheck) -> float:
    """Widen intervals when the query sits far outside the training box."""
    scale = 1.0
    for item in check.violations:
        span = max(item.max - item.min, abs(item.max), abs(item.min), 1.0)
        if item.value > item.max:
            scale = max(scale, 1.0 + (item.value - item.max) / span)
        elif item.value < item.min:
            scale = max(scale, 1.0 + (item.min - item.value) / span)
    return float(scale)


def format_applicability_warning(check: DomainCheck, *, missing_domain: bool = False) -> str:
    if missing_domain:
        return "Нет сохранённого диапазона обучения — применимость не проверена."
    if check.in_domain:
        return ""
    parts: list[str] = []
    for item in check.violations:
        unit = f" {item.unit}" if item.unit else ""
        lo = format_number(item.min)
        hi = format_number(item.max)
        value = format_number(item.value)
        if abs(item.max - item.min) < 1e-12:
            parts.append(f"{item.label} {value}{unit} при обучении {lo}{unit}")
        else:
            parts.append(
                f"{item.label} {value}{unit} при диапазоне обучения {lo}–{hi}{unit}"
            )
    joined = "; ".join(parts)
    return f"Прогноз вне области применимости: {joined}."


def similarity_to_training(
    vector: list[float],
    training_matrix: list[list[float]] | np.ndarray,
    feature_ranges: dict[str, FeatureRange] | dict[str, dict[str, Any]],
    feature_names: list[str],
    *,
    comparable_distance: float = COMPARABLE_DISTANCE,
) -> SimilarityResult:
    matrix = np.asarray(training_matrix, dtype=float)
    if matrix.size == 0:
        return SimilarityResult(score=0.0, comparable_count=0, sample_count=0)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    ranges = ranges_from_dict(feature_ranges) if not _is_range_map(feature_ranges) else feature_ranges
    scales: list[float] = []
    for name in feature_names:
        bounds = ranges.get(name)
        if bounds is None:
            scales.append(1.0)
            continue
        span = float(bounds.max - bounds.min)
        std = float(bounds.std)
        scales.append(max(span, 2.0 * std, 1e-6))
    scale = np.asarray(scales, dtype=float)
    query = np.asarray(vector, dtype=float)
    diff = (matrix - query) / scale
    distances = np.sqrt(np.mean(diff**2, axis=1))
    scores = np.exp(-SIMILARITY_DECAY * distances)
    comparable = int(np.sum(distances <= comparable_distance))
    return SimilarityResult(
        score=float(np.max(scores)),
        comparable_count=comparable,
        sample_count=int(matrix.shape[0]),
    )


def flatten_query(
    features: dict[str, Any],
    feature_names: list[str],
    vectorize,
    *extra: Any,
    **kwargs: Any,
) -> list[float]:
    return vectorize(features, feature_names, *extra, **kwargs)
