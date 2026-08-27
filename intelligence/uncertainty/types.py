"""Uncertainty, similarity and applicability attached to every ML prediction.

BDX-014: a point estimate without an interval is treated as false precision.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)

CONFIDENCE_LABELS_RU = {
    CONFIDENCE_HIGH: "Высокая",
    CONFIDENCE_MEDIUM: "Средняя",
    CONFIDENCE_LOW: "Низкая",
}

METHOD_ENSEMBLE = "ensemble_trees"
METHOD_RMSE = "residual_rmse"
METHOD_NONE = "none"

COMPARABLE_DISTANCE = 0.35
SIMILARITY_DECAY = 2.0
INTERVAL_PERCENTILES = (10.0, 90.0)
RMSE_Z = 1.28155156554  # ~80 % coverage, matching the 10–90 ensemble band


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


def confidence_label_ru(level: str) -> str:
    return CONFIDENCE_LABELS_RU.get(level, level)


@dataclass
class FeatureRange:
    name: str
    min: float
    max: float
    mean: float = 0.0
    std: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "min": float(self.min),
            "max": float(self.max),
            "mean": float(self.mean),
            "std": float(self.std),
        }

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any] | None) -> FeatureRange:
        data = data or {}
        return cls(
            name=name,
            min=float(data.get("min", 0.0) or 0.0),
            max=float(data.get("max", 0.0) or 0.0),
            mean=float(data.get("mean", 0.0) or 0.0),
            std=float(data.get("std", 0.0) or 0.0),
        )


@dataclass
class DomainViolation:
    feature: str
    value: float
    min: float
    max: float
    label: str = ""
    unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "value": float(self.value),
            "min": float(self.min),
            "max": float(self.max),
            "label": self.label,
            "unit": self.unit,
        }


@dataclass
class DomainCheck:
    in_domain: bool
    violations: list[DomainViolation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "in_domain": self.in_domain,
            "violations": [item.to_dict() for item in self.violations],
        }


@dataclass
class SimilarityResult:
    score: float
    comparable_count: int
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": float(self.score),
            "comparable_count": int(self.comparable_count),
            "sample_count": int(self.sample_count),
        }


@dataclass
class UncertaintyInterval:
    std: float | None
    lower: float | None
    upper: float | None
    method: str = METHOD_NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "std": None if self.std is None else float(self.std),
            "lower": None if self.lower is None else float(self.lower),
            "upper": None if self.upper is None else float(self.upper),
            "method": self.method,
        }

    @classmethod
    def none(cls) -> UncertaintyInterval:
        return cls(std=None, lower=None, upper=None, method=METHOD_NONE)


@dataclass
class PredictionAssessment:
    """The five fields required by BDX-014 plus UI helpers."""

    prediction: float | None
    uncertainty: UncertaintyInterval
    confidence: str
    similarity_score: float
    applicability_warning: str
    comparable_count: int = 0
    in_domain: bool = True
    sample_count: int = 0
    extrapolated_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction": None if self.prediction is None else float(self.prediction),
            "uncertainty": self.uncertainty.to_dict(),
            "confidence": self.confidence,
            "confidence_label": confidence_label_ru(self.confidence),
            "similarity_score": float(self.similarity_score),
            "applicability_warning": self.applicability_warning,
            "comparable_count": int(self.comparable_count),
            "in_domain": self.in_domain,
            "sample_count": int(self.sample_count),
            "extrapolated_features": list(self.extrapolated_features),
        }


def empty_assessment(*, prediction: float | None = None, reason: str = "") -> PredictionAssessment:
    warning = reason or "Модель не применена — интервал и сходство недоступны."
    return PredictionAssessment(
        prediction=None if prediction is None else float(prediction),
        uncertainty=UncertaintyInterval.none(),
        confidence=CONFIDENCE_LOW,
        similarity_score=0.0,
        applicability_warning=warning,
        comparable_count=0,
        in_domain=False,
        sample_count=0,
        extrapolated_features=[],
    )


def ranges_to_dict(ranges: dict[str, FeatureRange] | dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    payload: dict[str, dict[str, float]] = {}
    for name, item in (ranges or {}).items():
        if isinstance(item, FeatureRange):
            payload[str(name)] = item.to_dict()
        else:
            payload[str(name)] = {
                "min": float(item.get("min", 0.0) or 0.0),
                "max": float(item.get("max", 0.0) or 0.0),
                "mean": float(item.get("mean", 0.0) or 0.0),
                "std": float(item.get("std", 0.0) or 0.0),
            }
    return payload


def ranges_from_dict(data: dict[str, Any] | None) -> dict[str, FeatureRange]:
    result: dict[str, FeatureRange] = {}
    for name, item in (data or {}).items():
        if isinstance(item, FeatureRange):
            result[str(name)] = item
        else:
            result[str(name)] = FeatureRange.from_dict(str(name), item or {})
    return result


def matrix_from_payload(data: Any) -> list[list[float]]:
    matrix: list[list[float]] = []
    for row in data or []:
        matrix.append([float(item) for item in row])
    return matrix
