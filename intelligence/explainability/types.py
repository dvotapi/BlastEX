"""Explanation payloads attached to every ML prediction (BDX-015).

A point forecast without drivers is treated as unexplained: the engineer
must see *why* the model moved X50 / PPV / oversize, and what a small
design change would do. Full scenario replay is BDX-016; this module only
attributes the current overlay.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

METHOD_TREE_PATH = "tree_path"
METHOD_PERMUTATION = "permutation"
METHOD_IMPORTANCE = "feature_importance"
METHOD_NONE = "none"

ACTION_REDUCE = "reduce"
ACTION_INCREASE = "increase"


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


@dataclass
class FeatureDriver:
    """One feature's share of a local (and global) explanation."""

    feature: str
    label: str
    label_en: str
    share_pct: float
    importance_pct: float
    shap_value: float
    direction: str = "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "label": self.label,
            "label_en": self.label_en,
            "share_pct": float(self.share_pct),
            "importance_pct": float(self.importance_pct),
            "shap_value": float(self.shap_value),
            "direction": self.direction,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FeatureDriver:
        data = data or {}
        return cls(
            feature=str(data.get("feature", "") or ""),
            label=str(data.get("label", "") or ""),
            label_en=str(data.get("label_en", "") or ""),
            share_pct=float(data.get("share_pct", 0.0) or 0.0),
            importance_pct=float(data.get("importance_pct", 0.0) or 0.0),
            shap_value=float(data.get("shap_value", 0.0) or 0.0),
            direction=str(data.get("direction", "neutral") or "neutral"),
        )


@dataclass
class RecommendationHint:
    """Qualitative / delta-style lever: reducing burden → expected X50 −34 mm."""

    feature: str
    label: str
    label_en: str
    action: str
    action_label: str
    delta: float
    unit: str
    target_name: str
    target_label: str
    step: float
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "label": self.label,
            "label_en": self.label_en,
            "action": self.action,
            "action_label": self.action_label,
            "delta": float(self.delta),
            "unit": self.unit,
            "target_name": self.target_name,
            "target_label": self.target_label,
            "step": float(self.step),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RecommendationHint:
        data = data or {}
        return cls(
            feature=str(data.get("feature", "") or ""),
            label=str(data.get("label", "") or ""),
            label_en=str(data.get("label_en", "") or ""),
            action=str(data.get("action", "") or ""),
            action_label=str(data.get("action_label", "") or ""),
            delta=float(data.get("delta", 0.0) or 0.0),
            unit=str(data.get("unit", "") or ""),
            target_name=str(data.get("target_name", "") or ""),
            target_label=str(data.get("target_label", "") or ""),
            step=float(data.get("step", 0.0) or 0.0),
            summary=str(data.get("summary", "") or ""),
        )


@dataclass
class PredictionExplanation:
    """Local SHAP-style drivers plus delta-style recommendation hints."""

    method: str = METHOD_NONE
    expected_value: float | None = None
    drivers: list[FeatureDriver] = field(default_factory=list)
    recommendations: list[RecommendationHint] = field(default_factory=list)
    target_name: str = ""
    target_label: str = ""
    unit: str = ""
    summary: str = ""
    recommendation_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "expected_value": None if self.expected_value is None else float(self.expected_value),
            "drivers": [item.to_dict() for item in self.drivers],
            "recommendations": [item.to_dict() for item in self.recommendations],
            "target_name": self.target_name,
            "target_label": self.target_label,
            "unit": self.unit,
            "summary": self.summary,
            "recommendation_summary": self.recommendation_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PredictionExplanation:
        data = data or {}
        expected = data.get("expected_value")
        return cls(
            method=str(data.get("method", METHOD_NONE) or METHOD_NONE),
            expected_value=None if expected is None else float(expected),
            drivers=[FeatureDriver.from_dict(item) for item in data.get("drivers") or []],
            recommendations=[
                RecommendationHint.from_dict(item) for item in data.get("recommendations") or []
            ],
            target_name=str(data.get("target_name", "") or ""),
            target_label=str(data.get("target_label", "") or ""),
            unit=str(data.get("unit", "") or ""),
            summary=str(data.get("summary", "") or ""),
            recommendation_summary=str(data.get("recommendation_summary", "") or ""),
        )


def empty_explanation(
    *,
    target_name: str = "",
    target_label: str = "",
    unit: str = "",
) -> PredictionExplanation:
    return PredictionExplanation(
        method=METHOD_NONE,
        expected_value=None,
        drivers=[],
        recommendations=[],
        target_name=target_name,
        target_label=target_label,
        unit=unit,
        summary="",
        recommendation_summary="",
    )


def explanation_from_payload(data: Any) -> PredictionExplanation:
    if isinstance(data, PredictionExplanation):
        return data
    if isinstance(data, dict):
        return PredictionExplanation.from_dict(data)
    return empty_explanation()


def copy_explanation(value: PredictionExplanation | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return empty_explanation().to_dict()
    if isinstance(value, PredictionExplanation):
        return value.to_dict()
    return _copy(PredictionExplanation.from_dict(value).to_dict())
