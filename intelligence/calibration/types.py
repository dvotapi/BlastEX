"""Site-specific residual-correction model records (BDX-012).

A calibration model stores metadata and a tree estimator. Status starts as
``candidate`` and is never treated as production until explicitly marked.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

STATUS_CANDIDATE = "candidate"
STATUS_PRODUCTION = "production"
STATUS_RETIRED = "retired"
MODEL_STATUSES = (STATUS_CANDIDATE, STATUS_PRODUCTION, STATUS_RETIRED)

MODEL_KUZRAM_RESIDUAL = "kuzram_residual"
MODEL_OVERSIZE_RESIDUAL = "oversize_residual"
MODEL_PPV_RESIDUAL = "ppv_residual"
MODEL_TYPES = (MODEL_KUZRAM_RESIDUAL, MODEL_OVERSIZE_RESIDUAL, MODEL_PPV_RESIDUAL)

APPLIED_AS_OVERLAY = "recommendation_overlay"
ROLE_RECOMMENDATION = "recommendation_overlay"

DEFAULT_ALGORITHM = "random_forest"
MIN_TRAINING_SAMPLES = 4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


MODEL_SPECS: dict[str, dict[str, str]] = {
    MODEL_KUZRAM_RESIDUAL: {
        "target_group": "FRAGMENTATION",
        "measured_field": "x50_mm",
        "baseline_field": "predicted_x50_mm",
        "unit": "mm",
        "baseline_source": "kuzram",
        "label": "Kuz-Ram residual (x50)",
    },
    MODEL_OVERSIZE_RESIDUAL: {
        "target_group": "FRAGMENTATION",
        "measured_field": "oversize_pct",
        "baseline_field": "predicted_oversize_pct",
        "unit": "%",
        "baseline_source": "kuzram",
        "label": "Oversize residual",
    },
    MODEL_PPV_RESIDUAL: {
        "target_group": "VIBRATION",
        "measured_field": "max_ppv_mm_s",
        "measured_field_fallback": "ppv_mm_s",
        "baseline_field": "predicted_max_ppv_mm_s",
        "unit": "mm/s",
        "baseline_source": "ppv_empirical",
        "label": "PPV residual",
    },
}


def normalize_model_type(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "kuzram": MODEL_KUZRAM_RESIDUAL,
        "kuz_ram": MODEL_KUZRAM_RESIDUAL,
        "kuzram_x50": MODEL_KUZRAM_RESIDUAL,
        "x50": MODEL_KUZRAM_RESIDUAL,
        "oversize": MODEL_OVERSIZE_RESIDUAL,
        "negabarit": MODEL_OVERSIZE_RESIDUAL,
        "ppv": MODEL_PPV_RESIDUAL,
        "vibration": MODEL_PPV_RESIDUAL,
    }
    if text in MODEL_TYPES:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестный тип модели калибровки: {value}. "
        f"Доступны: {', '.join(MODEL_TYPES)}."
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


@dataclass
class CalibrationModel:
    """Trained residual model plus the metadata required by BDX-012."""

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
    target_name: str = ""
    baseline_field: str = ""
    measured_field: str = ""
    sample_count: int = 0
    source_blast_ids: list[str] = field(default_factory=list)
    artifact_sha256: str = ""
    status_updated_at: str = ""
    estimator: Any = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "site_id": self.site_id,
            "model_type": self.model_type,
            "model_version": int(self.model_version),
            "training_dataset_id": self.training_dataset_id,
            "training_dataset_version": int(self.training_dataset_version),
            "feature_schema_version": self.feature_schema_version,
            "training_date": self.training_date,
            "metrics": _copy(self.metrics),
            "status": self.status,
            "algorithm": self.algorithm,
            "feature_names": list(self.feature_names),
            "target_name": self.target_name,
            "baseline_field": self.baseline_field,
            "measured_field": self.measured_field,
            "sample_count": int(self.sample_count),
            "source_blast_ids": list(self.source_blast_ids),
            "artifact_sha256": self.artifact_sha256,
            "status_updated_at": self.status_updated_at,
        }

    def summary(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("feature_names", None)
        payload.pop("source_blast_ids", None)
        payload["source_blast_count"] = len(self.source_blast_ids)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, estimator: Any = None) -> CalibrationModel:
        data = data or {}
        return cls(
            model_id=str(data.get("model_id", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
            model_type=str(data.get("model_type", "") or ""),
            model_version=int(data.get("model_version", 1) or 1),
            training_dataset_id=str(data.get("training_dataset_id", "") or ""),
            training_dataset_version=int(data.get("training_dataset_version", 0) or 0),
            feature_schema_version=str(data.get("feature_schema_version", "") or ""),
            training_date=str(data.get("training_date", "") or ""),
            metrics=_copy(data.get("metrics") or {}),
            status=str(data.get("status", STATUS_CANDIDATE) or STATUS_CANDIDATE),
            algorithm=str(data.get("algorithm", DEFAULT_ALGORITHM) or DEFAULT_ALGORITHM),
            feature_names=[str(item) for item in data.get("feature_names", [])],
            target_name=str(data.get("target_name", "") or ""),
            baseline_field=str(data.get("baseline_field", "") or ""),
            measured_field=str(data.get("measured_field", "") or ""),
            sample_count=int(data.get("sample_count", 0) or 0),
            source_blast_ids=[str(item) for item in data.get("source_blast_ids", [])],
            artifact_sha256=str(data.get("artifact_sha256", "") or ""),
            status_updated_at=str(data.get("status_updated_at", "") or ""),
            estimator=estimator,
        )


@dataclass
class ResidualRow:
    source_blast_id: str
    features: dict[str, float]
    baseline: float
    measured: float
    residual: float


@dataclass
class ResidualTable:
    feature_names: list[str]
    rows: list[ResidualRow]
    X: list[list[float]]
    y: list[float]
    baselines: list[float]
    measured: list[float]
    source_blast_ids: list[str]


@dataclass
class CalibrationPrediction:
    """Hybrid prediction: empirical baseline + ML residual. Overlay only."""

    baseline: float
    residual: float
    calibrated: float
    model_id: str
    site_id: str
    model_type: str
    model_version: int
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    algorithm: str
    status: str
    metrics: dict[str, Any]
    applied_as: str = APPLIED_AS_OVERLAY
    modifies_design: bool = False
    calibration_applied: bool = True
    baseline_source: str = ""
    unit: str = ""
    warnings: list[str] = field(default_factory=list)
    role: str = ROLE_RECOMMENDATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline,
            "residual": self.residual,
            "calibrated": self.calibrated,
            "model_id": self.model_id,
            "site_id": self.site_id,
            "model_type": self.model_type,
            "model_version": int(self.model_version),
            "training_dataset_version": int(self.training_dataset_version),
            "feature_schema_version": self.feature_schema_version,
            "training_date": self.training_date,
            "algorithm": self.algorithm,
            "status": self.status,
            "metrics": _copy(self.metrics),
            "applied_as": APPLIED_AS_OVERLAY,
            "modifies_design": False,
            "calibration_applied": self.calibration_applied,
            "baseline_source": self.baseline_source,
            "unit": self.unit,
            "warnings": list(self.warnings),
            "role": ROLE_RECOMMENDATION,
            "provenance": {
                "site_id": self.site_id,
                "model_id": self.model_id,
                "model_type": self.model_type,
                "model_version": int(self.model_version),
                "training_dataset_version": int(self.training_dataset_version),
                "feature_schema_version": self.feature_schema_version,
                "training_date": self.training_date,
                "algorithm": self.algorithm,
                "status": self.status,
                "applied_as": APPLIED_AS_OVERLAY,
                "modifies_design": False,
                "baseline_source": self.baseline_source,
                "role": ROLE_RECOMMENDATION,
            },
        }
