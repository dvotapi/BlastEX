"""Hole- / neighborhood-level ML records (BDX-022).

Predictions stay on the PREDICTED layer. Designed charges and the approved
pattern are never overwritten. Residuals keep the unit of the named field
(x50_mm stays millimetres). There is no conversion step.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

ROLE_DESIGNED = "designed"
ROLE_EXECUTED = "executed"
ROLE_PREDICTED = "predicted"
ROLE_MEASURED = "measured"
DATA_ROLES = {
    "features_design": ROLE_DESIGNED,
    "features_execution": ROLE_EXECUTED,
    "predictions": ROLE_PREDICTED,
    "residuals": ROLE_PREDICTED,
    "targets": ROLE_MEASURED,
}

STATUS_CANDIDATE = "candidate"
STATUS_PRODUCTION = "production"
STATUS_RETIRED = "retired"
MODEL_STATUSES = (STATUS_CANDIDATE, STATUS_PRODUCTION, STATUS_RETIRED)

APPLIED_AS_OVERLAY = "predicted_overlay"
CLASS_SPATIAL = "SpatialHoleModel"
DEFAULT_ALGORITHM = "random_forest"
MIN_TRAINING_SAMPLES = 8
DEFAULT_NEIGHBOR_K = 4

METRIC_X50 = "x50_mm"
METRIC_OVERSIZE = "oversize_pct"
METRIC_TOE = "toe_probability"
RESIDUAL_X50 = "residual_x50_mm"
RESIDUAL_OVERSIZE = "residual_oversize_pct"
RESIDUAL_TOE = "residual_toe"
PRIMARY_METRICS = (METRIC_X50, METRIC_OVERSIZE, METRIC_TOE)
RESIDUAL_METRICS = (RESIDUAL_X50, RESIDUAL_OVERSIZE, RESIDUAL_TOE)

MAP_X50 = "x50"
MAP_OVERSIZE = "oversize"
MAP_TOE = "toe"
MAP_RESIDUAL_X50 = "residual_x50"
MAP_RESIDUAL_OVERSIZE = "residual_oversize"
MAP_RESIDUAL_TOE = "residual_toe"
SPATIAL_MAP_METRICS = (
    MAP_X50,
    MAP_OVERSIZE,
    MAP_TOE,
    MAP_RESIDUAL_X50,
    MAP_RESIDUAL_OVERSIZE,
    MAP_RESIDUAL_TOE,
)

UNITS = {
    METRIC_X50: "mm",
    METRIC_OVERSIZE: "%",
    METRIC_TOE: "",
    RESIDUAL_X50: "mm",
    RESIDUAL_OVERSIZE: "%",
    RESIDUAL_TOE: "",
    MAP_X50: "mm",
    MAP_OVERSIZE: "%",
    MAP_TOE: "",
    MAP_RESIDUAL_X50: "mm",
    MAP_RESIDUAL_OVERSIZE: "%",
    MAP_RESIDUAL_TOE: "",
}

METRIC_LABELS = {
    METRIC_X50: "X50",
    METRIC_OVERSIZE: "Негабарит",
    METRIC_TOE: "Риск забоя",
    RESIDUAL_X50: "Остаток X50",
    RESIDUAL_OVERSIZE: "Остаток негабарита",
    RESIDUAL_TOE: "Остаток риска забоя",
}

MAP_LABELS = {
    MAP_X50: "X50 (скважина, прогноз)",
    MAP_OVERSIZE: "Негабарит (скважина, прогноз)",
    MAP_TOE: "Риск забоя (скважина, прогноз)",
    MAP_RESIDUAL_X50: "Остаток X50 (скважина)",
    MAP_RESIDUAL_OVERSIZE: "Остаток негабарита (скважина)",
    MAP_RESIDUAL_TOE: "Остаток риска забоя (скважина)",
}

FEATURE_SCHEMA_VERSION = "spatial-1.0.0"

HOLE_FEATURE_NAMES = (
    "x_m",
    "y_m",
    "burden_m",
    "spacing_m",
    "diameter_mm",
    "length_m",
    "subdrill_m",
    "charge_kg",
    "stemming_m",
    "powder_factor_kg_m3",
    "delay_ms",
    "density_kg_m3",
    "ucs_mpa",
    "wet",
    "rel_charge_kg",
    "rel_burden_m",
    "rel_powder_factor_kg_m3",
    "rel_ucs_mpa",
    "nb_mean_charge_kg",
    "nb_mean_burden_m",
    "nb_mean_powder_factor_kg_m3",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


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
        f"Неизвестный статус пространственной модели: {value}. "
        f"Доступны: {', '.join(MODEL_STATUSES)}."
    )


def normalize_metric(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "x50": METRIC_X50,
        "x50_mm": METRIC_X50,
        "oversize": METRIC_OVERSIZE,
        "oversize_pct": METRIC_OVERSIZE,
        "negabarit": METRIC_OVERSIZE,
        "toe": METRIC_TOE,
        "toe_risk": METRIC_TOE,
        "toe_probability": METRIC_TOE,
        "residual": RESIDUAL_X50,
        "residual_x50": RESIDUAL_X50,
        "residual_x50_mm": RESIDUAL_X50,
        "residual_oversize": RESIDUAL_OVERSIZE,
        "residual_oversize_pct": RESIDUAL_OVERSIZE,
        "residual_toe": RESIDUAL_TOE,
    }
    if text in PRIMARY_METRICS or text in RESIDUAL_METRICS:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестная пространственная метрика: {value}. "
        f"Доступны: {', '.join(PRIMARY_METRICS + RESIDUAL_METRICS)}."
    )


def listed_metrics() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for name in PRIMARY_METRICS + RESIDUAL_METRICS:
        items.append(
            {
                "name": name,
                "unit": UNITS[name],
                "label": METRIC_LABELS[name],
                "role": ROLE_PREDICTED,
            }
        )
    return items


def listed_map_metrics() -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "unit": UNITS[name],
            "label": MAP_LABELS[name],
            "role": ROLE_PREDICTED,
        }
        for name in SPATIAL_MAP_METRICS
    ]


def clamp_metric(name: str, value: float) -> float:
    if name == METRIC_OVERSIZE:
        return float(min(100.0, max(0.0, value)))
    if name == METRIC_TOE:
        return float(min(1.0, max(0.0, value)))
    if name == METRIC_X50:
        return float(max(0.0, value))
    return float(value)


@dataclass
class HoleObservation:
    """One hole (or neighborhood centroid) frozen from a snapshot or a design."""

    hole_id: str
    x: float
    y: float
    kind: str = "production"
    features: dict[str, float] = field(default_factory=dict)
    feature_role: str = ROLE_DESIGNED
    predicted: dict[str, float | None] = field(default_factory=dict)
    measured: dict[str, float | None] = field(default_factory=dict)
    executed: dict[str, float | None] = field(default_factory=dict)
    neighbor_ids: list[str] = field(default_factory=list)
    source_blast_id: str = ""
    site_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_id": self.hole_id,
            "x": float(self.x),
            "y": float(self.y),
            "kind": self.kind,
            "features": _copy(self.features),
            "feature_role": self.feature_role or ROLE_DESIGNED,
            "predicted": _copy(self.predicted),
            "measured": _copy(self.measured),
            "executed": _copy(self.executed),
            "neighbor_ids": list(self.neighbor_ids),
            "source_blast_id": self.source_blast_id,
            "site_id": self.site_id,
            "predicted_role": ROLE_PREDICTED,
            "measured_role": ROLE_MEASURED,
            "executed_role": ROLE_EXECUTED,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HoleObservation:
        data = data or {}
        return cls(
            hole_id=str(data.get("hole_id", "") or ""),
            x=float(data.get("x", 0.0) or 0.0),
            y=float(data.get("y", 0.0) or 0.0),
            kind=str(data.get("kind", "production") or "production"),
            features={str(key): float(val) for key, val in (data.get("features") or {}).items() if val is not None and val != ""},
            feature_role=str(data.get("feature_role", ROLE_DESIGNED) or ROLE_DESIGNED),
            predicted=_optional_metric_map(data.get("predicted")),
            measured=_optional_metric_map(data.get("measured")),
            executed=_optional_metric_map(data.get("executed")),
            neighbor_ids=[str(item) for item in data.get("neighbor_ids", [])],
            source_blast_id=str(data.get("source_blast_id", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
        )


@dataclass
class HolePrediction:
    """Predicted values for one hole. Role is always predicted."""

    hole_id: str
    x: float
    y: float
    kind: str = "production"
    x50_mm: float | None = None
    oversize_pct: float | None = None
    toe_probability: float | None = None
    residual_x50_mm: float | None = None
    residual_oversize_pct: float | None = None
    residual_toe: float | None = None
    measured_x50_mm: float | None = None
    measured_oversize_pct: float | None = None
    measured_toe_probability: float | None = None
    residual_vs_measured_x50_mm: float | None = None
    residual_vs_measured_oversize_pct: float | None = None
    residual_vs_measured_toe: float | None = None
    neighbor_ids: list[str] = field(default_factory=list)
    role: str = ROLE_PREDICTED
    units: dict[str, str] = field(default_factory=lambda: dict(UNITS))

    def __post_init__(self) -> None:
        self.role = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_id": self.hole_id,
            "x": float(self.x),
            "y": float(self.y),
            "kind": self.kind,
            "x50_mm": self.x50_mm,
            "oversize_pct": self.oversize_pct,
            "toe_probability": self.toe_probability,
            "residual_x50_mm": self.residual_x50_mm,
            "residual_oversize_pct": self.residual_oversize_pct,
            "residual_toe": self.residual_toe,
            "measured_x50_mm": self.measured_x50_mm,
            "measured_oversize_pct": self.measured_oversize_pct,
            "measured_toe_probability": self.measured_toe_probability,
            "residual_vs_measured_x50_mm": self.residual_vs_measured_x50_mm,
            "residual_vs_measured_oversize_pct": self.residual_vs_measured_oversize_pct,
            "residual_vs_measured_toe": self.residual_vs_measured_toe,
            "neighbor_ids": list(self.neighbor_ids),
            "role": ROLE_PREDICTED,
            "units": {
                "x50_mm": "mm",
                "oversize_pct": "%",
                "toe_probability": "",
                "residual_x50_mm": "mm",
                "residual_oversize_pct": "%",
                "residual_toe": "",
            },
        }


@dataclass
class NeighborhoodPrediction:
    """Mean predicted values over a hole and its neighbors."""

    hole_id: str
    member_ids: list[str]
    x: float
    y: float
    x50_mm: float | None = None
    oversize_pct: float | None = None
    toe_probability: float | None = None
    residual_x50_mm: float | None = None
    residual_oversize_pct: float | None = None
    residual_toe: float | None = None
    role: str = ROLE_PREDICTED

    def __post_init__(self) -> None:
        self.role = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_id": self.hole_id,
            "member_ids": list(self.member_ids),
            "x": float(self.x),
            "y": float(self.y),
            "x50_mm": self.x50_mm,
            "oversize_pct": self.oversize_pct,
            "toe_probability": self.toe_probability,
            "residual_x50_mm": self.residual_x50_mm,
            "residual_oversize_pct": self.residual_oversize_pct,
            "residual_toe": self.residual_toe,
            "role": ROLE_PREDICTED,
            "units": {
                "x50_mm": "mm",
                "oversize_pct": "%",
                "toe_probability": "",
                "residual_x50_mm": "mm",
                "residual_oversize_pct": "%",
                "residual_toe": "",
            },
        }


@dataclass
class SpatialModel:
    """Trained local residual model. Candidate until a human promotes it."""

    model_id: str
    team_id: str
    site_id: str
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any]
    status: str = STATUS_CANDIDATE
    algorithm: str = DEFAULT_ALGORITHM
    feature_names: list[str] = field(default_factory=list)
    target_names: list[str] = field(default_factory=lambda: list(RESIDUAL_METRICS))
    class_name: str = CLASS_SPATIAL
    sample_count: int = 0
    hole_count: int = 0
    source_blast_ids: list[str] = field(default_factory=list)
    artifact_sha256: str = ""
    status_updated_at: str = ""
    neighbor_k: int = DEFAULT_NEIGHBOR_K
    data_roles: dict[str, str] = field(default_factory=lambda: dict(DATA_ROLES))
    estimators: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "team_id": self.team_id,
            "site_id": self.site_id,
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
            "class_name": self.class_name or CLASS_SPATIAL,
            "sample_count": int(self.sample_count),
            "hole_count": int(self.hole_count),
            "source_blast_ids": list(self.source_blast_ids),
            "artifact_sha256": self.artifact_sha256,
            "status_updated_at": self.status_updated_at,
            "neighbor_k": int(self.neighbor_k),
            "data_roles": _copy(self.data_roles or DATA_ROLES),
        }

    def summary(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("feature_names", None)
        payload.pop("source_blast_ids", None)
        payload["source_blast_count"] = len(self.source_blast_ids)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, *, estimators: dict[str, Any] | None = None) -> SpatialModel:
        data = data or {}
        stored = estimators if estimators is not None else data.get("estimators")
        if stored is None:
            stored = {}
        if not isinstance(stored, dict):
            stored = {"_single": stored}
        return cls(
            model_id=str(data.get("model_id", "") or ""),
            team_id=str(data.get("team_id", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
            model_version=int(data.get("model_version", 1) or 1),
            training_dataset_id=str(data.get("training_dataset_id", "") or ""),
            training_dataset_version=int(data.get("training_dataset_version", 0) or 0),
            feature_schema_version=str(data.get("feature_schema_version", FEATURE_SCHEMA_VERSION) or FEATURE_SCHEMA_VERSION),
            training_date=str(data.get("training_date", "") or ""),
            metrics=_copy(data.get("metrics") or {}),
            status=str(data.get("status", STATUS_CANDIDATE) or STATUS_CANDIDATE),
            algorithm=str(data.get("algorithm", DEFAULT_ALGORITHM) or DEFAULT_ALGORITHM),
            feature_names=[str(item) for item in data.get("feature_names", [])] or list(HOLE_FEATURE_NAMES),
            target_names=[str(item) for item in data.get("target_names", [])] or list(RESIDUAL_METRICS),
            class_name=str(data.get("class_name", "") or CLASS_SPATIAL),
            sample_count=int(data.get("sample_count", 0) or 0),
            hole_count=int(data.get("hole_count", 0) or 0),
            source_blast_ids=[str(item) for item in data.get("source_blast_ids", [])],
            artifact_sha256=str(data.get("artifact_sha256", "") or ""),
            status_updated_at=str(data.get("status_updated_at", "") or ""),
            neighbor_k=int(data.get("neighbor_k", DEFAULT_NEIGHBOR_K) or DEFAULT_NEIGHBOR_K),
            data_roles=dict(data.get("data_roles") or DATA_ROLES),
            estimators=dict(stored),
        )


@dataclass
class SpatialOverlay:
    """Predicted hole / neighborhood layer. Never mutates a design."""

    holes: list[HolePrediction]
    neighborhoods: list[NeighborhoodPrediction]
    maps: dict[str, Any]
    block: dict[str, float | None]
    model_id: str = ""
    team_id: str = ""
    site_id: str = ""
    model_version: int = 0
    training_dataset_version: int = 0
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    algorithm: str = ""
    status: str = ""
    hole_count: int = 0
    applied_as: str = APPLIED_AS_OVERLAY
    modifies_design: bool = False
    prediction_applied: bool = True
    warnings: list[str] = field(default_factory=list)
    role: str = ROLE_PREDICTED
    data_roles: dict[str, str] = field(default_factory=lambda: dict(DATA_ROLES))

    def __post_init__(self) -> None:
        self.role = ROLE_PREDICTED
        self.applied_as = APPLIED_AS_OVERLAY
        self.modifies_design = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "holes": [item.to_dict() for item in self.holes],
            "neighborhoods": [item.to_dict() for item in self.neighborhoods],
            "maps": _copy(self.maps),
            "block": _copy(self.block),
            "model_id": self.model_id,
            "team_id": self.team_id,
            "site_id": self.site_id,
            "model_version": int(self.model_version),
            "training_dataset_version": int(self.training_dataset_version),
            "feature_schema_version": self.feature_schema_version,
            "algorithm": self.algorithm,
            "status": self.status,
            "hole_count": int(self.hole_count or len(self.holes)),
            "applied_as": APPLIED_AS_OVERLAY,
            "modifies_design": False,
            "prediction_applied": bool(self.prediction_applied),
            "warnings": list(self.warnings),
            "role": ROLE_PREDICTED,
            "data_roles": _copy(self.data_roles or DATA_ROLES),
            "provenance": {
                "model_id": self.model_id,
                "team_id": self.team_id,
                "site_id": self.site_id,
                "model_version": int(self.model_version),
                "training_dataset_version": int(self.training_dataset_version),
                "feature_schema_version": self.feature_schema_version,
                "algorithm": self.algorithm,
                "status": self.status,
                "applied_as": APPLIED_AS_OVERLAY,
                "modifies_design": False,
                "role": ROLE_PREDICTED,
            },
        }


def _optional_metric_map(value: Any) -> dict[str, float | None]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float | None] = {}
    for key, raw in value.items():
        if raw is None or raw == "":
            out[str(key)] = None
            continue
        try:
            out[str(key)] = float(raw)
        except (TypeError, ValueError):
            continue
    return out
