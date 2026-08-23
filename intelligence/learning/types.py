"""Two-level learning records (BDX-019).

A global/prior model is trained inside one tenant. A site model may start
from that prior and store ``team_id`` / ``site_id`` isolation keys. Status
starts as ``candidate``. Formal promotion lives in ``intelligence.registry``
(BDX-020).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from intelligence.explainability.types import (
    PredictionExplanation,
    copy_explanation,
    empty_explanation,
    explanation_from_payload,
)
from intelligence.outcomes.types import (
    APPLIED_AS_OVERLAY,
    DEFAULT_ALGORITHM,
    MODEL_TYPES,
    ROLE_RECOMMENDATION,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    STATUS_RETIRED,
    MODEL_STATUSES,
    listed_model_types,
    normalize_model_type,
    normalize_status,
    spec_for,
    utc_now_iso,
)
from intelligence.uncertainty.types import (
    PredictionAssessment,
    UncertaintyInterval,
    matrix_from_payload,
    ranges_from_dict,
    ranges_to_dict,
)

SCOPE_GLOBAL = "global"
SCOPE_SITE = "site"
MODEL_SCOPES = (SCOPE_GLOBAL, SCOPE_SITE)

GLOBAL_SITE_ID = "*"
ADAPTATION_DIRECT = "direct"
ADAPTATION_RESIDUAL = "residual"

ROLE_DESIGNED = "designed"
ROLE_EXECUTED = "executed"
ROLE_PREDICTED = "predicted"
ROLE_MEASURED = "measured"

MIN_TRAINING_SAMPLES = 4

DATA_ROLES = {
    "training_targets": ROLE_MEASURED,
    "prediction": ROLE_PREDICTED,
    "design": ROLE_DESIGNED,
    "execution": ROLE_EXECUTED,
}


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


def normalize_scope(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "prior": SCOPE_GLOBAL,
        "pooled": SCOPE_GLOBAL,
        "global_prior": SCOPE_GLOBAL,
        "local": SCOPE_SITE,
        "adapted": SCOPE_SITE,
        "site_adapted": SCOPE_SITE,
    }
    if text in MODEL_SCOPES:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестный уровень обучения: {value}. Доступны: {', '.join(MODEL_SCOPES)}."
    )


def normalize_site_id(value: str, *, scope: str = SCOPE_SITE) -> str:
    text = str(value or "").strip()
    if normalize_scope(scope) == SCOPE_GLOBAL:
        return GLOBAL_SITE_ID if text in {"", GLOBAL_SITE_ID, "global", "all"} else text or GLOBAL_SITE_ID
    return text


@dataclass(frozen=True)
class IsolationKeys:
    """Tenant / site keys that must travel with every learned artifact."""

    team_id: str
    site_id: str
    scope: str

    def to_dict(self) -> dict[str, str]:
        return {
            "team_id": self.team_id,
            "site_id": self.site_id,
            "scope": self.scope,
        }


@dataclass
class LearnedModel:
    """Global prior or site-adapted model. Never trained from a live passport."""

    model_id: str
    team_id: str
    site_id: str
    scope: str
    model_type: str
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any]
    status: str = STATUS_CANDIDATE
    algorithm: str = DEFAULT_ALGORITHM
    feature_names: list[str] = field(default_factory=list)
    target_names: list[str] = field(default_factory=list)
    primary_target: str = ""
    class_name: str = ""
    sample_count: int = 0
    source_blast_ids: list[str] = field(default_factory=list)
    source_site_ids: list[str] = field(default_factory=list)
    training_dataset_ids: list[str] = field(default_factory=list)
    artifact_sha256: str = ""
    status_updated_at: str = ""
    feature_ranges: dict[str, dict[str, float]] = field(default_factory=dict)
    training_matrix: list[list[float]] = field(default_factory=list)
    prior_model_id: str = ""
    prior_team_id: str = ""
    prior_scope: str = ""
    adaptation: str = ADAPTATION_DIRECT
    estimators: dict[str, Any] = field(default_factory=dict, repr=False)
    prior_estimators: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def isolation(self) -> IsolationKeys:
        return IsolationKeys(team_id=self.team_id, site_id=self.site_id, scope=self.scope)

    def to_dict(self) -> dict[str, Any]:
        spec = spec_for(self.model_type) if self.model_type else {}
        return {
            "model_id": self.model_id,
            "team_id": self.team_id,
            "site_id": self.site_id,
            "scope": self.scope,
            "isolation": self.isolation.to_dict(),
            "model_type": self.model_type,
            "class_name": self.class_name or spec.get("class_name", ""),
            "model_version": int(self.model_version),
            "training_dataset_id": self.training_dataset_id,
            "training_dataset_ids": list(self.training_dataset_ids or [self.training_dataset_id]),
            "training_dataset_version": int(self.training_dataset_version),
            "feature_schema_version": self.feature_schema_version,
            "training_date": self.training_date,
            "metrics": _copy(self.metrics),
            "status": self.status,
            "algorithm": self.algorithm,
            "feature_names": list(self.feature_names),
            "target_names": list(self.target_names),
            "primary_target": self.primary_target,
            "sample_count": int(self.sample_count),
            "source_blast_ids": list(self.source_blast_ids),
            "source_site_ids": list(self.source_site_ids),
            "artifact_sha256": self.artifact_sha256,
            "status_updated_at": self.status_updated_at,
            "feature_ranges": ranges_to_dict(self.feature_ranges),
            "training_matrix": [list(row) for row in self.training_matrix],
            "prior_model_id": self.prior_model_id,
            "prior_team_id": self.prior_team_id,
            "prior_scope": self.prior_scope,
            "adaptation": self.adaptation,
            "data_roles": dict(DATA_ROLES),
            "auto_approved": False,
        }

    def summary(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("feature_names", None)
        payload.pop("source_blast_ids", None)
        payload.pop("training_matrix", None)
        payload["source_blast_count"] = len(self.source_blast_ids)
        return payload

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any] | None,
        *,
        estimators: dict[str, Any] | None = None,
        prior_estimators: dict[str, Any] | None = None,
    ) -> LearnedModel:
        data = data or {}
        model_type = str(data.get("model_type", "") or "")
        spec = spec_for(model_type) if model_type else {}
        stored = estimators if estimators is not None else data.get("estimators")
        if stored is None:
            stored = {}
        if not isinstance(stored, dict):
            stored = {"_single": stored}
        prior_stored = prior_estimators if prior_estimators is not None else data.get("prior_estimators")
        if prior_stored is None:
            prior_stored = {}
        if not isinstance(prior_stored, dict):
            prior_stored = {"_single": prior_stored}
        isolation = data.get("isolation") or {}
        team_id = str(data.get("team_id") or isolation.get("team_id") or "")
        scope = str(data.get("scope") or isolation.get("scope") or SCOPE_SITE)
        site_id = str(data.get("site_id") or isolation.get("site_id") or "")
        dataset_ids = [str(item) for item in data.get("training_dataset_ids", []) if str(item)]
        primary_id = str(data.get("training_dataset_id", "") or "")
        if primary_id and primary_id not in dataset_ids:
            dataset_ids.insert(0, primary_id)
        return cls(
            model_id=str(data.get("model_id", "") or ""),
            team_id=team_id,
            site_id=site_id,
            scope=scope,
            model_type=model_type,
            model_version=int(data.get("model_version", 1) or 1),
            training_dataset_id=primary_id or (dataset_ids[0] if dataset_ids else ""),
            training_dataset_version=int(data.get("training_dataset_version", 0) or 0),
            feature_schema_version=str(data.get("feature_schema_version", "") or ""),
            training_date=str(data.get("training_date", "") or ""),
            metrics=_copy(data.get("metrics") or {}),
            status=str(data.get("status", STATUS_CANDIDATE) or STATUS_CANDIDATE),
            algorithm=str(data.get("algorithm", DEFAULT_ALGORITHM) or DEFAULT_ALGORITHM),
            feature_names=[str(item) for item in data.get("feature_names", [])],
            target_names=[str(item) for item in data.get("target_names", [])],
            primary_target=str(data.get("primary_target", "") or spec.get("primary_target", "")),
            class_name=str(data.get("class_name", "") or spec.get("class_name", "")),
            sample_count=int(data.get("sample_count", 0) or 0),
            source_blast_ids=[str(item) for item in data.get("source_blast_ids", [])],
            source_site_ids=[str(item) for item in data.get("source_site_ids", [])],
            training_dataset_ids=dataset_ids,
            artifact_sha256=str(data.get("artifact_sha256", "") or ""),
            status_updated_at=str(data.get("status_updated_at", "") or ""),
            feature_ranges=ranges_to_dict(ranges_from_dict(data.get("feature_ranges") or {})),
            training_matrix=matrix_from_payload(data.get("training_matrix")),
            prior_model_id=str(data.get("prior_model_id", "") or ""),
            prior_team_id=str(data.get("prior_team_id", "") or ""),
            prior_scope=str(data.get("prior_scope", "") or ""),
            adaptation=str(data.get("adaptation", ADAPTATION_DIRECT) or ADAPTATION_DIRECT),
            estimators=dict(stored),
            prior_estimators=dict(prior_stored),
        )


@dataclass
class TargetContribution:
    target_name: str
    value: float
    unit: str
    label: str
    model_type: str
    global_value: float | None = None
    residual_value: float | None = None
    prediction_applied: bool = True
    prediction: float | None = None
    uncertainty: dict[str, Any] = field(default_factory=dict)
    confidence: str = ""
    confidence_label: str = ""
    similarity_score: float = 0.0
    applicability_warning: str = ""
    comparable_count: int = 0
    in_domain: bool = True
    sample_count: int = 0
    extrapolated_features: list[str] = field(default_factory=list)
    explanation: PredictionExplanation = field(default_factory=empty_explanation)

    def apply_assessment(self, assessment: PredictionAssessment) -> None:
        payload = assessment.to_dict()
        self.prediction = payload["prediction"]
        if payload["prediction"] is not None:
            self.value = float(payload["prediction"])
        self.uncertainty = payload["uncertainty"]
        self.confidence = payload["confidence"]
        self.confidence_label = payload["confidence_label"]
        self.similarity_score = float(payload["similarity_score"])
        self.applicability_warning = str(payload["applicability_warning"] or "")
        self.comparable_count = int(payload["comparable_count"])
        self.in_domain = bool(payload["in_domain"])
        self.sample_count = int(payload["sample_count"])
        self.extrapolated_features = list(payload["extrapolated_features"])

    def apply_explanation(self, explanation: PredictionExplanation | dict[str, Any] | None) -> None:
        self.explanation = explanation_from_payload(explanation)

    def to_dict(self) -> dict[str, Any]:
        prediction = self.prediction if self.prediction is not None else self.value
        uncertainty = self.uncertainty or UncertaintyInterval.none().to_dict()
        return {
            "target_name": self.target_name,
            "value": self.value,
            "prediction": prediction,
            "global_value": self.global_value,
            "residual_value": self.residual_value,
            "unit": self.unit,
            "label": self.label,
            "model_type": self.model_type,
            "prediction_applied": self.prediction_applied,
            "role": ROLE_PREDICTED,
            "uncertainty": _copy(uncertainty),
            "confidence": self.confidence,
            "confidence_label": self.confidence_label,
            "similarity_score": float(self.similarity_score),
            "applicability_warning": self.applicability_warning,
            "comparable_count": int(self.comparable_count),
            "in_domain": bool(self.in_domain),
            "sample_count": int(self.sample_count),
            "extrapolated_features": list(self.extrapolated_features),
            "explanation": copy_explanation(self.explanation),
        }


@dataclass
class LearningPrediction:
    """Two-level overlay. Never mutates or approves a design."""

    predicted: float | None
    predictions: dict[str, TargetContribution]
    model_id: str
    team_id: str
    site_id: str
    scope: str
    model_type: str
    class_name: str
    model_version: int
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    algorithm: str
    status: str
    metrics: dict[str, Any]
    primary_target: str
    unit: str = ""
    applied_as: str = APPLIED_AS_OVERLAY
    modifies_design: bool = False
    prediction_applied: bool = True
    auto_approved: bool = False
    warnings: list[str] = field(default_factory=list)
    role: str = ROLE_RECOMMENDATION
    prior_model_id: str = ""
    adaptation: str = ADAPTATION_DIRECT
    prediction: float | None = None
    uncertainty: dict[str, Any] = field(default_factory=dict)
    confidence: str = ""
    confidence_label: str = ""
    similarity_score: float = 0.0
    applicability_warning: str = ""
    comparable_count: int = 0
    in_domain: bool = True
    sample_count: int = 0
    extrapolated_features: list[str] = field(default_factory=list)
    explanation: PredictionExplanation = field(default_factory=empty_explanation)

    def apply_assessment(self, assessment: PredictionAssessment) -> None:
        payload = assessment.to_dict()
        self.prediction = payload["prediction"]
        if payload["prediction"] is not None:
            self.predicted = float(payload["prediction"])
        self.uncertainty = payload["uncertainty"]
        self.confidence = payload["confidence"]
        self.confidence_label = payload["confidence_label"]
        self.similarity_score = float(payload["similarity_score"])
        self.applicability_warning = str(payload["applicability_warning"] or "")
        self.comparable_count = int(payload["comparable_count"])
        self.in_domain = bool(payload["in_domain"])
        self.sample_count = int(payload["sample_count"])
        self.extrapolated_features = list(payload["extrapolated_features"])
        if self.applicability_warning and self.applicability_warning not in self.warnings:
            self.warnings.insert(0, self.applicability_warning)

    def apply_explanation(self, explanation: PredictionExplanation | dict[str, Any] | None) -> None:
        self.explanation = explanation_from_payload(explanation)

    def to_dict(self) -> dict[str, Any]:
        primary = self.predictions.get(self.primary_target)
        unit = self.unit or (primary.unit if primary else "")
        predicted = self.predicted if self.predicted is not None else (primary.value if primary else None)
        prediction = self.prediction if self.prediction is not None else predicted
        uncertainty = self.uncertainty or (
            primary.uncertainty if primary and primary.uncertainty else UncertaintyInterval.none().to_dict()
        )
        explanation = copy_explanation(self.explanation)
        if explanation.get("method") == "none" and primary is not None:
            explanation = copy_explanation(primary.explanation)
        return {
            "predicted": predicted,
            "prediction": prediction,
            "predictions": {name: item.to_dict() for name, item in self.predictions.items()},
            "uncertainty": _copy(uncertainty),
            "explanation": explanation,
            "confidence": self.confidence or (primary.confidence if primary else ""),
            "confidence_label": self.confidence_label or (primary.confidence_label if primary else ""),
            "similarity_score": float(
                self.similarity_score if self.similarity_score or not primary else primary.similarity_score
            ),
            "applicability_warning": self.applicability_warning
            or (primary.applicability_warning if primary else ""),
            "comparable_count": int(self.comparable_count or (primary.comparable_count if primary else 0)),
            "in_domain": bool(self.in_domain if self.confidence else (primary.in_domain if primary else False)),
            "sample_count": int(self.sample_count or (primary.sample_count if primary else 0)),
            "extrapolated_features": list(
                self.extrapolated_features or (primary.extrapolated_features if primary else [])
            ),
            "model_id": self.model_id,
            "team_id": self.team_id,
            "site_id": self.site_id,
            "scope": self.scope,
            "isolation": {"team_id": self.team_id, "site_id": self.site_id, "scope": self.scope},
            "model_type": self.model_type,
            "class_name": self.class_name,
            "model_version": int(self.model_version),
            "training_dataset_version": int(self.training_dataset_version),
            "feature_schema_version": self.feature_schema_version,
            "training_date": self.training_date,
            "algorithm": self.algorithm,
            "status": self.status,
            "metrics": _copy(self.metrics),
            "primary_target": self.primary_target,
            "unit": unit,
            "applied_as": APPLIED_AS_OVERLAY,
            "modifies_design": False,
            "prediction_applied": self.prediction_applied,
            "auto_approved": False,
            "warnings": list(self.warnings),
            "role": ROLE_RECOMMENDATION,
            "prior_model_id": self.prior_model_id,
            "adaptation": self.adaptation,
            "data_roles": dict(DATA_ROLES),
            "provenance": {
                "team_id": self.team_id,
                "site_id": self.site_id,
                "scope": self.scope,
                "model_id": self.model_id,
                "model_type": self.model_type,
                "class_name": self.class_name,
                "model_version": int(self.model_version),
                "training_dataset_version": int(self.training_dataset_version),
                "feature_schema_version": self.feature_schema_version,
                "training_date": self.training_date,
                "algorithm": self.algorithm,
                "status": self.status,
                "applied_as": APPLIED_AS_OVERLAY,
                "modifies_design": False,
                "auto_approved": False,
                "role": ROLE_RECOMMENDATION,
                "prediction_role": ROLE_PREDICTED,
                "primary_target": self.primary_target,
                "prior_model_id": self.prior_model_id,
                "adaptation": self.adaptation,
                "data_roles": dict(DATA_ROLES),
            },
        }


__all__ = [
    "ADAPTATION_DIRECT",
    "ADAPTATION_RESIDUAL",
    "APPLIED_AS_OVERLAY",
    "DATA_ROLES",
    "DEFAULT_ALGORITHM",
    "GLOBAL_SITE_ID",
    "IsolationKeys",
    "LearnedModel",
    "LearningPrediction",
    "MIN_TRAINING_SAMPLES",
    "MODEL_SCOPES",
    "MODEL_STATUSES",
    "MODEL_TYPES",
    "ROLE_DESIGNED",
    "ROLE_EXECUTED",
    "ROLE_MEASURED",
    "ROLE_PREDICTED",
    "ROLE_RECOMMENDATION",
    "SCOPE_GLOBAL",
    "SCOPE_SITE",
    "STATUS_CANDIDATE",
    "STATUS_PRODUCTION",
    "STATUS_RETIRED",
    "TargetContribution",
    "listed_model_types",
    "normalize_model_type",
    "normalize_scope",
    "normalize_site_id",
    "normalize_status",
    "spec_for",
    "utc_now_iso",
]
