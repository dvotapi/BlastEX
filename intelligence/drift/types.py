"""Drift-monitoring records (BDX-021).

Compare a live observation window with the immutable snapshot a production
model was trained on. The output is alerts only: nothing here trains, promotes
or silently swaps the live model.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

KIND_FEATURE = "feature"
KIND_TARGET = "target"
KIND_PREDICTION = "prediction"
DRIFT_KINDS = (KIND_FEATURE, KIND_TARGET, KIND_PREDICTION)

SEVERITY_OK = "ok"
SEVERITY_WATCH = "watch"
SEVERITY_ALERT = "alert"
DRIFT_SEVERITIES = (SEVERITY_OK, SEVERITY_WATCH, SEVERITY_ALERT)

ROLE_DESIGNED = "designed"
ROLE_EXECUTED = "executed"
ROLE_PREDICTED = "predicted"
ROLE_MEASURED = "measured"
DATA_ROLES = {
    "features_design": ROLE_DESIGNED,
    "features_execution": ROLE_EXECUTED,
    "targets": ROLE_MEASURED,
    "predictions": ROLE_PREDICTED,
}

ACTION_ALERT_ONLY = "alert_only"
ACTION_HUMAN_PROMOTE = "human_promote_via_registry"

AUTO_ACTORS = frozenset({"", "auto", "system", "scheduler", "cron", "pipeline", "ci"})

KIND_LABELS = {
    KIND_FEATURE: "Признаки",
    KIND_TARGET: "Цели (измеренные)",
    KIND_PREDICTION: "Прогнозы модели",
}

SEVERITY_LABELS = {
    SEVERITY_OK: "норма",
    SEVERITY_WATCH: "наблюдение",
    SEVERITY_ALERT: "сигнал",
}

ROLE_LABELS = {
    ROLE_DESIGNED: "проект",
    ROLE_EXECUTED: "исполнение",
    ROLE_PREDICTED: "прогноз",
    ROLE_MEASURED: "факт",
}

# Industry-standard PSI / KS / relative-mean bands. Values stay in the unit
# of the named field (x50_mm stays millimetres). There is no conversion step.
PSI_WATCH = 0.10
PSI_ALERT = 0.25
KS_WATCH = 0.35
KS_ALERT = 0.50
MEAN_SHIFT_WATCH = 0.20
MEAN_SHIFT_ALERT = 0.40
MIN_SERIES_LENGTH = 3


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


def normalize_kind(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "features": KIND_FEATURE,
        "input": KIND_FEATURE,
        "inputs": KIND_FEATURE,
        "covariate": KIND_FEATURE,
        "label": KIND_TARGET,
        "labels": KIND_TARGET,
        "measured": KIND_TARGET,
        "outcome": KIND_TARGET,
        "outcomes": KIND_TARGET,
        "output": KIND_PREDICTION,
        "outputs": KIND_PREDICTION,
        "pred": KIND_PREDICTION,
        "preds": KIND_PREDICTION,
        "score": KIND_PREDICTION,
        "scores": KIND_PREDICTION,
    }
    if text in DRIFT_KINDS:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестный канал дрифта: {value}. Доступны: {', '.join(DRIFT_KINDS)}."
    )


def normalize_severity(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "none": SEVERITY_OK,
        "normal": SEVERITY_OK,
        "green": SEVERITY_OK,
        "warn": SEVERITY_WATCH,
        "warning": SEVERITY_WATCH,
        "yellow": SEVERITY_WATCH,
        "red": SEVERITY_ALERT,
        "critical": SEVERITY_ALERT,
        "drift": SEVERITY_ALERT,
    }
    if text in DRIFT_SEVERITIES:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестная серьёзность дрифта: {value}. Доступны: {', '.join(DRIFT_SEVERITIES)}."
    )


def worse_severity(left: str, right: str) -> str:
    order = {SEVERITY_OK: 0, SEVERITY_WATCH: 1, SEVERITY_ALERT: 2}
    a = normalize_severity(left) if left else SEVERITY_OK
    b = normalize_severity(right) if right else SEVERITY_OK
    return a if order[a] >= order[b] else b


def listed_kinds() -> list[dict[str, str]]:
    return [{"name": name, "label": KIND_LABELS[name]} for name in DRIFT_KINDS]


def listed_severities() -> list[dict[str, str]]:
    return [{"name": name, "label": SEVERITY_LABELS[name]} for name in DRIFT_SEVERITIES]


@dataclass
class DriftMetric:
    """One named series compared against the training snapshot."""

    name: str
    kind: str
    role: str
    unit: str = ""
    baseline_count: int = 0
    current_count: int = 0
    baseline_mean: float | None = None
    current_mean: float | None = None
    baseline_std: float | None = None
    current_std: float | None = None
    psi: float | None = None
    ks: float | None = None
    mean_shift: float | None = None
    severity: str = SEVERITY_OK
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "role": self.role,
            "unit": self.unit,
            "baseline_count": int(self.baseline_count),
            "current_count": int(self.current_count),
            "baseline_mean": self.baseline_mean,
            "current_mean": self.current_mean,
            "baseline_std": self.baseline_std,
            "current_std": self.current_std,
            "psi": self.psi,
            "ks": self.ks,
            "mean_shift": self.mean_shift,
            "severity": self.severity,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DriftMetric:
        data = data or {}
        return cls(
            name=str(data.get("name", "") or ""),
            kind=str(data.get("kind", KIND_FEATURE) or KIND_FEATURE),
            role=str(data.get("role", ROLE_DESIGNED) or ROLE_DESIGNED),
            unit=str(data.get("unit", "") or ""),
            baseline_count=int(data.get("baseline_count", 0) or 0),
            current_count=int(data.get("current_count", 0) or 0),
            baseline_mean=_optional_float(data.get("baseline_mean")),
            current_mean=_optional_float(data.get("current_mean")),
            baseline_std=_optional_float(data.get("baseline_std")),
            current_std=_optional_float(data.get("current_std")),
            psi=_optional_float(data.get("psi")),
            ks=_optional_float(data.get("ks")),
            mean_shift=_optional_float(data.get("mean_shift")),
            severity=str(data.get("severity", SEVERITY_OK) or SEVERITY_OK),
            reasons=[str(item) for item in data.get("reasons", [])],
        )


@dataclass
class DriftAlert:
    """A human-facing signal. Never deploys or retrains."""

    alert_id: str
    team_id: str
    family: str
    model_id: str
    kind: str
    role: str
    metric_name: str
    severity: str
    message: str
    report_id: str = ""
    site_id: str = ""
    created_at: str = ""
    acknowledged: bool = False
    acknowledged_by: str = ""
    acknowledged_at: str = ""
    auto_deployed: bool = False
    auto_retrained: bool = False
    live_model_unchanged: bool = True
    action: str = ACTION_ALERT_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "team_id": self.team_id,
            "family": self.family,
            "model_id": self.model_id,
            "kind": self.kind,
            "role": self.role,
            "metric_name": self.metric_name,
            "severity": self.severity,
            "message": self.message,
            "report_id": self.report_id,
            "site_id": self.site_id,
            "created_at": self.created_at,
            "acknowledged": bool(self.acknowledged),
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at,
            "auto_deployed": False,
            "auto_retrained": False,
            "live_model_unchanged": True,
            "action": ACTION_ALERT_ONLY,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DriftAlert:
        data = data or {}
        return cls(
            alert_id=str(data.get("alert_id", "") or ""),
            team_id=str(data.get("team_id", "") or ""),
            family=str(data.get("family", "") or ""),
            model_id=str(data.get("model_id", "") or ""),
            kind=str(data.get("kind", "") or ""),
            role=str(data.get("role", "") or ""),
            metric_name=str(data.get("metric_name", "") or ""),
            severity=str(data.get("severity", SEVERITY_ALERT) or SEVERITY_ALERT),
            message=str(data.get("message", "") or ""),
            report_id=str(data.get("report_id", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
            created_at=str(data.get("created_at", "") or ""),
            acknowledged=bool(data.get("acknowledged", False)),
            acknowledged_by=str(data.get("acknowledged_by", "") or ""),
            acknowledged_at=str(data.get("acknowledged_at", "") or ""),
            auto_deployed=False,
            auto_retrained=False,
            live_model_unchanged=True,
            action=ACTION_ALERT_ONLY,
        )


@dataclass
class DriftReport:
    """Window comparison vs the training snapshot of a production model."""

    report_id: str
    team_id: str
    family: str
    model_id: str
    model_checksum: str
    model_status: str
    training_dataset_ids: list[str] = field(default_factory=list)
    training_dataset_version: int = 0
    current_dataset_id: str = ""
    current_dataset_version: int = 0
    feature_schema_version: str = ""
    site_id: str = ""
    created_at: str = ""
    overall_severity: str = SEVERITY_OK
    metrics: list[DriftMetric] = field(default_factory=list)
    alerts: list[DriftAlert] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data_roles: dict[str, str] = field(default_factory=lambda: dict(DATA_ROLES))
    auto_deployed: bool = False
    auto_retrained: bool = False
    live_model_unchanged: bool = True
    action: str = ACTION_ALERT_ONLY
    next_step: str = ACTION_HUMAN_PROMOTE

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "team_id": self.team_id,
            "family": self.family,
            "model_id": self.model_id,
            "model_checksum": self.model_checksum,
            "model_status": self.model_status,
            "training_dataset_ids": list(self.training_dataset_ids),
            "training_dataset_version": int(self.training_dataset_version),
            "current_dataset_id": self.current_dataset_id,
            "current_dataset_version": int(self.current_dataset_version),
            "feature_schema_version": self.feature_schema_version,
            "site_id": self.site_id,
            "created_at": self.created_at,
            "overall_severity": self.overall_severity,
            "metrics": [item.to_dict() for item in self.metrics],
            "alerts": [item.to_dict() for item in self.alerts],
            "warnings": list(self.warnings),
            "data_roles": _copy(self.data_roles or DATA_ROLES),
            "auto_deployed": False,
            "auto_retrained": False,
            "live_model_unchanged": True,
            "action": ACTION_ALERT_ONLY,
            "next_step": ACTION_HUMAN_PROMOTE,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DriftReport:
        data = data or {}
        return cls(
            report_id=str(data.get("report_id", "") or ""),
            team_id=str(data.get("team_id", "") or ""),
            family=str(data.get("family", "") or ""),
            model_id=str(data.get("model_id", "") or ""),
            model_checksum=str(data.get("model_checksum", "") or ""),
            model_status=str(data.get("model_status", "") or ""),
            training_dataset_ids=[str(item) for item in data.get("training_dataset_ids", []) if str(item or "").strip()],
            training_dataset_version=int(data.get("training_dataset_version", 0) or 0),
            current_dataset_id=str(data.get("current_dataset_id", "") or ""),
            current_dataset_version=int(data.get("current_dataset_version", 0) or 0),
            feature_schema_version=str(data.get("feature_schema_version", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
            created_at=str(data.get("created_at", "") or ""),
            overall_severity=str(data.get("overall_severity", SEVERITY_OK) or SEVERITY_OK),
            metrics=[DriftMetric.from_dict(item) for item in data.get("metrics", [])],
            alerts=[DriftAlert.from_dict(item) for item in data.get("alerts", [])],
            warnings=[str(item) for item in data.get("warnings", [])],
            data_roles=dict(data.get("data_roles") or DATA_ROLES),
            auto_deployed=False,
            auto_retrained=False,
            live_model_unchanged=True,
            action=ACTION_ALERT_ONLY,
            next_step=ACTION_HUMAN_PROMOTE,
        )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
