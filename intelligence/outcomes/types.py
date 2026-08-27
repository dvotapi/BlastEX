"""Specialised blast-outcome models (BDX-013).

Direct predictors, not a single universal net and not residual calibration:

* FragmentationModel — X50 / X80
* VibrationModel — PPV / frequency
* OversizeModel — oversize share
* ToeRiskModel — toe leftover probability

Status starts as ``candidate``. Predictions are overlays with model version;
they never write back onto a design.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from intelligence.explainability.types import (
    PredictionExplanation,
    copy_explanation,
    empty_explanation,
    explanation_from_payload,
)
from intelligence.uncertainty.types import (
    PredictionAssessment,
    UncertaintyInterval,
    matrix_from_payload,
    ranges_from_dict,
    ranges_to_dict,
)

STATUS_CANDIDATE = "candidate"
STATUS_PRODUCTION = "production"
STATUS_RETIRED = "retired"
MODEL_STATUSES = (STATUS_CANDIDATE, STATUS_PRODUCTION, STATUS_RETIRED)

MODEL_FRAGMENTATION = "fragmentation"
MODEL_VIBRATION = "vibration"
MODEL_OVERSIZE = "oversize"
MODEL_TOE_RISK = "toe_risk"
MODEL_TYPES = (MODEL_FRAGMENTATION, MODEL_VIBRATION, MODEL_OVERSIZE, MODEL_TOE_RISK)

CLASS_FRAGMENTATION = "FragmentationModel"
CLASS_VIBRATION = "VibrationModel"
CLASS_OVERSIZE = "OversizeModel"
CLASS_TOE_RISK = "ToeRiskModel"

APPLIED_AS_OVERLAY = "recommendation_overlay"
ROLE_RECOMMENDATION = "recommendation_overlay"

DEFAULT_ALGORITHM = "random_forest"
MIN_TRAINING_SAMPLES = 4

TARGET_X50 = "x50_mm"
TARGET_X80 = "x80_mm"
TARGET_OVERSIZE = "oversize_pct"
TARGET_PPV = "max_ppv_mm_s"
TARGET_FREQUENCY = "frequency_hz"
TARGET_TOE_RISK = "toe_probability"

PANEL_TARGETS = (TARGET_X50, TARGET_X80, TARGET_OVERSIZE, TARGET_PPV, TARGET_TOE_RISK)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


MODEL_SPECS: dict[str, dict[str, Any]] = {
    MODEL_FRAGMENTATION: {
        "class_name": CLASS_FRAGMENTATION,
        "label": "Кусковатость (X50 / X80)",
        "label_en": "Fragmentation (X50 / X80)",
        "primary_target": TARGET_X50,
        "targets": (
            {
                "name": TARGET_X50,
                "group": "FRAGMENTATION",
                "field": "x50_mm",
                "unit": "mm",
                "label": "X50",
            },
            {
                "name": TARGET_X80,
                "group": "FRAGMENTATION",
                "field": "x80_mm",
                "unit": "mm",
                "label": "X80",
            },
        ),
    },
    MODEL_VIBRATION: {
        "class_name": CLASS_VIBRATION,
        "label": "Сейсмика (PPV / частота)",
        "label_en": "Vibration (PPV / frequency)",
        "primary_target": TARGET_PPV,
        "targets": (
            {
                "name": TARGET_PPV,
                "group": "VIBRATION",
                "field": "max_ppv_mm_s",
                "field_fallback": "ppv_mm_s",
                "unit": "mm/s",
                "label": "PPV",
            },
            {
                "name": TARGET_FREQUENCY,
                "group": "VIBRATION",
                "field": "frequency_hz",
                "field_fallback": "max_frequency_hz",
                "unit": "Hz",
                "label": "Частота",
            },
        ),
    },
    MODEL_OVERSIZE: {
        "class_name": CLASS_OVERSIZE,
        "label": "Негабарит",
        "label_en": "Oversize",
        "primary_target": TARGET_OVERSIZE,
        "targets": (
            {
                "name": TARGET_OVERSIZE,
                "group": "FRAGMENTATION",
                "field": "oversize_pct",
                "unit": "%",
                "label": "Негабарит",
            },
        ),
    },
    MODEL_TOE_RISK: {
        "class_name": CLASS_TOE_RISK,
        "label": "Риск забоя",
        "label_en": "Toe risk",
        "primary_target": TARGET_TOE_RISK,
        "targets": (
            {
                "name": TARGET_TOE_RISK,
                "group": "BLAST",
                "field": "toe_probability",
                "derived": True,
                "unit": "",
                "label": "Риск забоя",
            },
        ),
    },
}


def normalize_model_type(value: str) -> str:
    text = str(value or "").strip()
    compact = text.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "fragmentation": MODEL_FRAGMENTATION,
        "fragmentationmodel": MODEL_FRAGMENTATION,
        "fragmentation_model": MODEL_FRAGMENTATION,
        "x50": MODEL_FRAGMENTATION,
        "x80": MODEL_FRAGMENTATION,
        "vibration": MODEL_VIBRATION,
        "vibrationmodel": MODEL_VIBRATION,
        "vibration_model": MODEL_VIBRATION,
        "ppv": MODEL_VIBRATION,
        "frequency": MODEL_VIBRATION,
        "oversize": MODEL_OVERSIZE,
        "oversizemodel": MODEL_OVERSIZE,
        "oversize_model": MODEL_OVERSIZE,
        "negabarit": MODEL_OVERSIZE,
        "toe": MODEL_TOE_RISK,
        "toe_risk": MODEL_TOE_RISK,
        "toerisk": MODEL_TOE_RISK,
        "toeriskmodel": MODEL_TOE_RISK,
        "toe_risk_model": MODEL_TOE_RISK,
    }
    class_aliases = {
        CLASS_FRAGMENTATION.lower(): MODEL_FRAGMENTATION,
        CLASS_VIBRATION.lower(): MODEL_VIBRATION,
        CLASS_OVERSIZE.lower(): MODEL_OVERSIZE,
        CLASS_TOE_RISK.lower(): MODEL_TOE_RISK,
    }
    if compact in MODEL_TYPES:
        return compact
    if compact in aliases:
        return aliases[compact]
    if compact in class_aliases:
        return class_aliases[compact]
    raise ValueError(
        f"Неизвестный тип модели исхода: {value}. "
        f"Доступны: {', '.join(MODEL_TYPES)} "
        f"({CLASS_FRAGMENTATION}, {CLASS_VIBRATION}, {CLASS_OVERSIZE}, {CLASS_TOE_RISK})."
    )


def normalize_status(value: str) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "prod": STATUS_PRODUCTION,
        "approved": STATUS_PRODUCTION,
        "active": STATUS_PRODUCTION,
        "draft": STATUS_CANDIDATE,
        "archived": STATUS_RETIRED,
    }
    if text in MODEL_STATUSES:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестный статус модели: {value}. Доступны: {', '.join(MODEL_STATUSES)}."
    )


def spec_for(model_type: str) -> dict[str, Any]:
    return MODEL_SPECS[normalize_model_type(model_type)]


def target_spec(model_type: str, target_name: str) -> dict[str, Any]:
    spec = spec_for(model_type)
    for item in spec["targets"]:
        if item["name"] == target_name:
            return item
    raise ValueError(f"Цель «{target_name}» не входит в модель «{model_type}».")


def listed_model_types() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name, spec in MODEL_SPECS.items():
        items.append(
            {
                "name": name,
                "class_name": spec["class_name"],
                "label": spec["label"],
                "label_en": spec["label_en"],
                "primary_target": spec["primary_target"],
                "targets": [
                    {
                        "name": item["name"],
                        "unit": item["unit"],
                        "label": item["label"],
                    }
                    for item in spec["targets"]
                ],
            }
        )
    return items


@dataclass
class OutcomeModel:
    """Trained specialised outcome model plus BDX-013 provenance metadata."""

    model_id: str
    site_id: str
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
    artifact_sha256: str = ""
    status_updated_at: str = ""
    feature_ranges: dict[str, dict[str, float]] = field(default_factory=dict)
    training_matrix: list[list[float]] = field(default_factory=list)
    estimators: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        spec = MODEL_SPECS.get(self.model_type) or {}
        return {
            "model_id": self.model_id,
            "site_id": self.site_id,
            "model_type": self.model_type,
            "class_name": self.class_name or spec.get("class_name", ""),
            "model_version": int(self.model_version),
            "training_dataset_id": self.training_dataset_id,
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
            "artifact_sha256": self.artifact_sha256,
            "status_updated_at": self.status_updated_at,
            "feature_ranges": ranges_to_dict(self.feature_ranges),
            "training_matrix": [list(row) for row in self.training_matrix],
        }

    def summary(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("feature_names", None)
        payload.pop("source_blast_ids", None)
        payload.pop("training_matrix", None)
        payload["source_blast_count"] = len(self.source_blast_ids)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, estimators: dict[str, Any] | None = None) -> OutcomeModel:
        data = data or {}
        model_type = str(data.get("model_type", "") or "")
        spec = MODEL_SPECS.get(model_type) or {}
        stored = estimators if estimators is not None else data.get("estimators")
        if stored is None:
            stored = {}
        if not isinstance(stored, dict):
            stored = {"_single": stored}
        return cls(
            model_id=str(data.get("model_id", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
            model_type=model_type,
            model_version=int(data.get("model_version", 1) or 1),
            training_dataset_id=str(data.get("training_dataset_id", "") or ""),
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
            artifact_sha256=str(data.get("artifact_sha256", "") or ""),
            status_updated_at=str(data.get("status_updated_at", "") or ""),
            feature_ranges=ranges_to_dict(ranges_from_dict(data.get("feature_ranges") or {})),
            training_matrix=matrix_from_payload(data.get("training_matrix")),
            estimators=dict(stored),
        )


@dataclass
class TargetRow:
    source_blast_id: str
    features: dict[str, float]
    y: float


@dataclass
class TargetTable:
    target_name: str
    feature_names: list[str]
    rows: list[TargetRow]
    X: list[list[float]]
    y: list[float]
    source_blast_ids: list[str]


@dataclass
class TargetPrediction:
    target_name: str
    value: float
    unit: str
    label: str
    model_type: str
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
            "unit": self.unit,
            "label": self.label,
            "model_type": self.model_type,
            "prediction_applied": self.prediction_applied,
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
class OutcomePrediction:
    """Point prediction overlay. Never mutates a design."""

    predicted: float | None
    predictions: dict[str, TargetPrediction]
    model_id: str
    site_id: str
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
    warnings: list[str] = field(default_factory=list)
    role: str = ROLE_RECOMMENDATION
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
        uncertainty = self.uncertainty or (primary.uncertainty if primary and primary.uncertainty else UncertaintyInterval.none().to_dict())
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
            "similarity_score": float(self.similarity_score if self.similarity_score or not primary else primary.similarity_score),
            "applicability_warning": self.applicability_warning or (primary.applicability_warning if primary else ""),
            "comparable_count": int(self.comparable_count or (primary.comparable_count if primary else 0)),
            "in_domain": bool(self.in_domain if self.confidence else (primary.in_domain if primary else False)),
            "sample_count": int(self.sample_count or (primary.sample_count if primary else 0)),
            "extrapolated_features": list(self.extrapolated_features or (primary.extrapolated_features if primary else [])),
            "model_id": self.model_id,
            "site_id": self.site_id,
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
            "warnings": list(self.warnings),
            "role": ROLE_RECOMMENDATION,
            "provenance": {
                "site_id": self.site_id,
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
                "role": ROLE_RECOMMENDATION,
                "primary_target": self.primary_target,
            },
        }
