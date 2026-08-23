"""ML design recommendation entities (BDX-018).

A recommendation is a suggested overlay. It never approves, replaces or
rewrites the DESIGNED passport. The engineer remains the decision maker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from design.optimization.types import OptimizationCandidate
from intelligence.explainability.types import (
    PredictionExplanation,
    empty_explanation,
    explanation_from_payload,
)
from intelligence.uncertainty.types import (
    UncertaintyInterval,
    empty_assessment,
)

APPLIED_AS = "recommendation_overlay"
METHOD_PROFILE_PARETO = "profile_weighted_pareto"
ROLE_PREDICTED = "predicted"
ROLE_DESIGNED = "designed"
ROLE_EXECUTED = "executed"
ROLE_MEASURED = "measured"

PROFILE_BALANCED = "BALANCED"
PROFILE_LOW_COST = "LOW_COST"
PROFILE_FINE_FRAGMENTATION = "FINE_FRAGMENTATION"
PROFILE_LOW_VIBRATION = "LOW_VIBRATION"

PROFILE_KEYS = (
    PROFILE_BALANCED,
    PROFILE_LOW_COST,
    PROFILE_FINE_FRAGMENTATION,
    PROFILE_LOW_VIBRATION,
)

REASON_PROFILE = "profile"
REASON_DELTA = "delta"
REASON_PARAM = "param"
REASON_UNCERTAINTY = "uncertainty"
REASON_EXPLANATION = "explanation"
REASON_DECISION = "decision"

DEFAULT_TARGET_X50_MM = 200.0
DEFAULT_MAX_CANDIDATES = 24


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


@dataclass(frozen=True)
class RecommendationProfile:
    """Named preference over PREDICTED objectives. Weights are dimensionless."""

    key: str
    label: str
    label_en: str
    description: str
    weights: dict[str, float]
    primary_objectives: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "label_en": self.label_en,
            "description": self.description,
            "weights": dict(self.weights),
            "primary_objectives": list(self.primary_objectives),
        }


PROFILES: dict[str, RecommendationProfile] = {
    PROFILE_BALANCED: RecommendationProfile(
        key=PROFILE_BALANCED,
        label="Сбалансированный",
        label_en="Balanced",
        description="Компромисс утопии Парето: равные веса затрат, негабарита, погонажа, PPV и отклонения от целевого X50.",
        weights={
            "cost": 1.0,
            "oversize": 1.0,
            "drilling_metres": 1.0,
            "ppv": 1.0,
            "target_x50": 1.0,
        },
        primary_objectives=("cost", "oversize", "drilling_metres", "ppv", "target_x50"),
    ),
    PROFILE_LOW_COST: RecommendationProfile(
        key=PROFILE_LOW_COST,
        label="Низкая стоимость",
        label_en="Low cost",
        description="Сильнее штрафует прогнозные затраты и погонаж бурения. Не утверждает паспорт.",
        weights={
            "cost": 4.0,
            "oversize": 1.0,
            "drilling_metres": 2.0,
            "ppv": 1.0,
            "target_x50": 1.0,
        },
        primary_objectives=("cost", "drilling_metres"),
    ),
    PROFILE_FINE_FRAGMENTATION: RecommendationProfile(
        key=PROFILE_FINE_FRAGMENTATION,
        label="Мелкое дробление",
        label_en="Fine fragmentation",
        description="Сильнее штрафует негабарит и отклонение от целевого X50 (мм). Не утверждает паспорт.",
        weights={
            "cost": 1.0,
            "oversize": 3.0,
            "drilling_metres": 1.0,
            "ppv": 1.0,
            "target_x50": 3.0,
        },
        primary_objectives=("oversize", "target_x50"),
    ),
    PROFILE_LOW_VIBRATION: RecommendationProfile(
        key=PROFILE_LOW_VIBRATION,
        label="Низкая сейсмика",
        label_en="Low vibration",
        description="Сильнее штрафует прогнозный PPV (мм/с). Не утверждает паспорт.",
        weights={
            "cost": 1.0,
            "oversize": 1.0,
            "drilling_metres": 1.0,
            "ppv": 4.0,
            "target_x50": 1.0,
        },
        primary_objectives=("ppv",),
    ),
}


@dataclass
class RecommendationReason:
    """One human-readable 'why' line. Values stay in the declared unit."""

    kind: str
    title: str
    detail: str
    metric: str = ""
    unit: str = ""
    baseline: float | None = None
    recommended: float | None = None
    delta: float | None = None
    role: str = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "detail": self.detail,
            "metric": self.metric,
            "unit": self.unit,
            "baseline": self.baseline,
            "recommended": self.recommended,
            "delta": self.delta,
            "role": ROLE_PREDICTED if self.role not in {ROLE_DESIGNED, ROLE_EXECUTED, ROLE_MEASURED, ROLE_PREDICTED} else self.role,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RecommendationReason:
        data = data or {}
        role = str(data.get("role") or ROLE_PREDICTED)
        if role not in {ROLE_DESIGNED, ROLE_EXECUTED, ROLE_MEASURED, ROLE_PREDICTED}:
            role = ROLE_PREDICTED
        return cls(
            kind=str(data.get("kind") or REASON_DELTA),
            title=str(data.get("title") or ""),
            detail=str(data.get("detail") or ""),
            metric=str(data.get("metric") or ""),
            unit=str(data.get("unit") or ""),
            baseline=_opt_float(data, "baseline"),
            recommended=_opt_float(data, "recommended"),
            delta=_opt_float(data, "delta"),
            role=role,
        )


@dataclass
class RecommendationAssessment:
    """BDX-014 interval / confidence / similarity plus BDX-015 drivers."""

    target_name: str
    target_label: str
    unit: str
    prediction: float | None
    uncertainty: dict[str, Any] = field(default_factory=dict)
    confidence: str = "low"
    confidence_label: str = ""
    similarity_score: float = 0.0
    applicability_warning: str = ""
    comparable_count: int = 0
    in_domain: bool = False
    sample_count: int = 0
    extrapolated_features: list[str] = field(default_factory=list)
    explanation: dict[str, Any] = field(default_factory=dict)
    model_id: str = ""
    model_available: bool = False
    role: str = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        uncertainty = self.uncertainty or UncertaintyInterval.none().to_dict()
        explanation = self.explanation or empty_explanation(
            target_name=self.target_name,
            target_label=self.target_label,
            unit=self.unit,
        ).to_dict()
        return {
            "target_name": self.target_name,
            "target_label": self.target_label,
            "unit": self.unit,
            "prediction": None if self.prediction is None else float(self.prediction),
            "uncertainty": dict(uncertainty),
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "similarity_score": float(self.similarity_score),
            "applicability_warning": self.applicability_warning,
            "comparable_count": int(self.comparable_count),
            "in_domain": bool(self.in_domain),
            "sample_count": int(self.sample_count),
            "extrapolated_features": list(self.extrapolated_features),
            "explanation": dict(explanation),
            "model_id": self.model_id,
            "model_available": bool(self.model_available),
            "role": ROLE_PREDICTED,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RecommendationAssessment:
        data = data or {}
        explanation = explanation_from_payload(data.get("explanation")).to_dict()
        uncertainty = data.get("uncertainty") or UncertaintyInterval.none().to_dict()
        return cls(
            target_name=str(data.get("target_name") or ""),
            target_label=str(data.get("target_label") or ""),
            unit=str(data.get("unit") or ""),
            prediction=_opt_float(data, "prediction"),
            uncertainty=dict(uncertainty),
            confidence=str(data.get("confidence") or "low"),
            confidence_label=str(data.get("confidence_label") or ""),
            similarity_score=float(data.get("similarity_score") or 0.0),
            applicability_warning=str(data.get("applicability_warning") or ""),
            comparable_count=int(data.get("comparable_count") or 0),
            in_domain=bool(data.get("in_domain", False)),
            sample_count=int(data.get("sample_count") or 0),
            extrapolated_features=[str(item) for item in data.get("extrapolated_features") or []],
            explanation=explanation,
            model_id=str(data.get("model_id") or ""),
            model_available=bool(data.get("model_available", False)),
            role=ROLE_PREDICTED,
        )

    @classmethod
    def unavailable(cls, target_name: str, target_label: str, unit: str, reason: str = "") -> RecommendationAssessment:
        assessment = empty_assessment(reason=reason)
        payload = assessment.to_dict()
        return cls(
            target_name=target_name,
            target_label=target_label,
            unit=unit,
            prediction=None,
            uncertainty=payload["uncertainty"],
            confidence=payload["confidence"],
            confidence_label=payload["confidence_label"],
            similarity_score=payload["similarity_score"],
            applicability_warning=payload["applicability_warning"],
            comparable_count=payload["comparable_count"],
            in_domain=False,
            sample_count=payload["sample_count"],
            extrapolated_features=[],
            explanation=empty_explanation(target_name=target_name, target_label=target_label, unit=unit).to_dict(),
            model_available=False,
            role=ROLE_PREDICTED,
        )


@dataclass
class DesignRecommendation:
    """Suggested overlay report. The approved design stays DESIGNED and unchanged."""

    recommendation_id: str
    design_id: str
    profile: str
    suggested: OptimizationCandidate | None = None
    baseline: OptimizationCandidate | None = None
    alternatives: list[OptimizationCandidate] = field(default_factory=list)
    profile_picks: dict[str, str] = field(default_factory=dict)
    reasons: list[RecommendationReason] = field(default_factory=list)
    assessments: list[RecommendationAssessment] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)
    target_x50_mm: float = DEFAULT_TARGET_X50_MM
    search_run_id: str = ""
    evaluated: int = 0
    pareto_count: int = 0
    method: str = METHOD_PROFILE_PARETO
    auto_applied: bool = False
    approved: bool = False
    replaces_design: bool = False
    modifies_design: bool = False
    applied_as: str = APPLIED_AS
    source_design_role: str = ROLE_DESIGNED
    suggested_role: str = ROLE_PREDICTED
    engineer_decides: bool = True
    source_revision_sha256: str = ""
    approved_unchanged: bool = True
    created_at: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "design_id": self.design_id,
            "profile": self.profile,
            "suggested": None if self.suggested is None else self.suggested.to_dict(),
            "baseline": None if self.baseline is None else self.baseline.to_dict(),
            "alternatives": [item.to_dict() for item in self.alternatives],
            "profile_picks": dict(self.profile_picks),
            "reasons": [item.to_dict() for item in self.reasons],
            "assessments": [item.to_dict() for item in self.assessments],
            "objectives": list(self.objectives),
            "target_x50_mm": float(self.target_x50_mm),
            "search_run_id": self.search_run_id,
            "evaluated": int(self.evaluated),
            "pareto_count": int(self.pareto_count),
            "method": METHOD_PROFILE_PARETO,
            "auto_applied": False,
            "approved": False,
            "replaces_design": False,
            "modifies_design": False,
            "applied_as": APPLIED_AS,
            "source_design_role": ROLE_DESIGNED,
            "suggested_role": ROLE_PREDICTED,
            "engineer_decides": True,
            "source_revision_sha256": self.source_revision_sha256,
            "approved_unchanged": True,
            "created_at": self.created_at,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DesignRecommendation:
        data = data or {}
        suggested = data.get("suggested")
        baseline = data.get("baseline")
        profile = str(data.get("profile") or PROFILE_BALANCED)
        if profile not in PROFILE_KEYS:
            profile = PROFILE_BALANCED
        return cls(
            recommendation_id=str(data.get("recommendation_id") or ""),
            design_id=str(data.get("design_id") or ""),
            profile=profile,
            suggested=OptimizationCandidate.from_dict(suggested) if suggested else None,
            baseline=OptimizationCandidate.from_dict(baseline) if baseline else None,
            alternatives=[OptimizationCandidate.from_dict(item) for item in data.get("alternatives") or []],
            profile_picks={str(key): str(value) for key, value in dict(data.get("profile_picks") or {}).items()},
            reasons=[RecommendationReason.from_dict(item) for item in data.get("reasons") or []],
            assessments=[RecommendationAssessment.from_dict(item) for item in data.get("assessments") or []],
            objectives=[str(item) for item in data.get("objectives") or []],
            target_x50_mm=float(data.get("target_x50_mm") or DEFAULT_TARGET_X50_MM),
            search_run_id=str(data.get("search_run_id") or ""),
            evaluated=int(data.get("evaluated") or 0),
            pareto_count=int(data.get("pareto_count") or 0),
            method=METHOD_PROFILE_PARETO,
            auto_applied=False,
            approved=False,
            replaces_design=False,
            modifies_design=False,
            applied_as=APPLIED_AS,
            source_design_role=ROLE_DESIGNED,
            suggested_role=ROLE_PREDICTED,
            engineer_decides=True,
            source_revision_sha256=str(data.get("source_revision_sha256") or ""),
            approved_unchanged=True,
            created_at=str(data.get("created_at") or ""),
            warnings=[str(item) for item in data.get("warnings", [])],
        )
