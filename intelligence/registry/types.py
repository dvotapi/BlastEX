"""Formal model-registry records (BDX-020).

Wraps candidate artifacts from calibration (BDX-012), outcomes (BDX-013)
and two-level learning (BDX-019). Status moves only through an explicit
human-gated promotion. Nothing here trains a model or deploys one.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

FAMILY_CALIBRATION = "calibration"
FAMILY_OUTCOMES = "outcomes"
FAMILY_LEARNING = "learning"
MODEL_FAMILIES = (FAMILY_CALIBRATION, FAMILY_OUTCOMES, FAMILY_LEARNING)

STATUS_CANDIDATE = "candidate"
STATUS_STAGING = "staging"
STATUS_PRODUCTION = "production"
STATUS_RETIRED = "retired"
STATUS_ARCHIVED = "archived"
REGISTRY_STATUSES = (
    STATUS_CANDIDATE,
    STATUS_STAGING,
    STATUS_PRODUCTION,
    STATUS_RETIRED,
    STATUS_ARCHIVED,
)

SOURCE_STATUSES = (STATUS_CANDIDATE, STATUS_PRODUCTION, STATUS_RETIRED)

# candidate → staging/production → retired/archived. Archived is terminal.
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATUS_CANDIDATE: (STATUS_STAGING, STATUS_PRODUCTION, STATUS_RETIRED, STATUS_ARCHIVED),
    STATUS_STAGING: (STATUS_PRODUCTION, STATUS_RETIRED, STATUS_ARCHIVED),
    STATUS_PRODUCTION: (STATUS_RETIRED, STATUS_ARCHIVED),
    STATUS_RETIRED: (STATUS_ARCHIVED,),
    STATUS_ARCHIVED: (),
}

# Staging is never production in the underlying store. Archived maps to retired
# so prediction paths that only know candidate/production/retired stay closed.
SOURCE_STATUS_FOR_REGISTRY = {
    STATUS_CANDIDATE: STATUS_CANDIDATE,
    STATUS_STAGING: STATUS_CANDIDATE,
    STATUS_PRODUCTION: STATUS_PRODUCTION,
    STATUS_RETIRED: STATUS_RETIRED,
    STATUS_ARCHIVED: STATUS_RETIRED,
}

ROLE_DESIGNED = "designed"
ROLE_EXECUTED = "executed"
ROLE_PREDICTED = "predicted"
ROLE_MEASURED = "measured"

DATA_ROLES = {
    "training_targets": ROLE_MEASURED,
    "prediction": ROLE_PREDICTED,
    "design": ROLE_DESIGNED,
    "execution": ROLE_EXECUTED,
}

AUTO_ACTORS = frozenset({"", "auto", "system", "scheduler", "cron", "pipeline", "ci"})

FAMILY_LABELS = {
    FAMILY_CALIBRATION: "Калибровка площадки",
    FAMILY_OUTCOMES: "Прогноз исходов",
    FAMILY_LEARNING: "Глобальное / площадочное обучение",
}

STATUS_LABELS = {
    STATUS_CANDIDATE: "кандидат",
    STATUS_STAGING: "стейджинг",
    STATUS_PRODUCTION: "производство",
    STATUS_RETIRED: "снята",
    STATUS_ARCHIVED: "архив",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


def normalize_family(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "cal": FAMILY_CALIBRATION,
        "calib": FAMILY_CALIBRATION,
        "residual": FAMILY_CALIBRATION,
        "outcome": FAMILY_OUTCOMES,
        "outcomes": FAMILY_OUTCOMES,
        "learn": FAMILY_LEARNING,
        "learned": FAMILY_LEARNING,
        "global_site": FAMILY_LEARNING,
    }
    if text in MODEL_FAMILIES:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестное семейство реестра: {value}. Доступны: {', '.join(MODEL_FAMILIES)}."
    )


def normalize_status(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "prod": STATUS_PRODUCTION,
        "approved": STATUS_PRODUCTION,
        "active": STATUS_PRODUCTION,
        "draft": STATUS_CANDIDATE,
        "stage": STATUS_STAGING,
        "staged": STATUS_STAGING,
        "archive": STATUS_ARCHIVED,
        "arch": STATUS_ARCHIVED,
    }
    if text in REGISTRY_STATUSES:
        return text
    if text in aliases:
        return aliases[text]
    raise ValueError(
        f"Неизвестный статус реестра: {value}. Доступны: {', '.join(REGISTRY_STATUSES)}."
    )


def normalize_source_status(value: str) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "prod": STATUS_PRODUCTION,
        "approved": STATUS_PRODUCTION,
        "active": STATUS_PRODUCTION,
        "draft": STATUS_CANDIDATE,
        "archived": STATUS_RETIRED,
        "staging": STATUS_CANDIDATE,
        "stage": STATUS_CANDIDATE,
    }
    if text in SOURCE_STATUSES:
        return text
    if text in aliases:
        return aliases[text]
    if text in REGISTRY_STATUSES:
        return SOURCE_STATUS_FOR_REGISTRY[text]
    raise ValueError(
        f"Неизвестный статус исходной модели: {value}. Доступны: {', '.join(SOURCE_STATUSES)}."
    )


def allowed_transitions(status: str) -> list[str]:
    return list(ALLOWED_TRANSITIONS.get(normalize_status(status), ()))


def source_status_for(registry_status: str) -> str:
    return SOURCE_STATUS_FOR_REGISTRY[normalize_status(registry_status)]


def effective_status(source_status: str, overlay_status: str = "") -> str:
    """Reconcile the live store with optional registry overlay.

    The existing artifact remains the source of truth for candidate /
    production / retired. Overlay only adds staging (while the source is
    still a candidate) and archived (once the source is retired).
    """
    source = normalize_source_status(source_status)
    overlay = normalize_status(overlay_status) if str(overlay_status or "").strip() else ""
    if overlay == STATUS_ARCHIVED and source == STATUS_RETIRED:
        return STATUS_ARCHIVED
    if overlay == STATUS_STAGING and source == STATUS_CANDIDATE:
        return STATUS_STAGING
    if source == STATUS_PRODUCTION:
        return STATUS_PRODUCTION
    if source == STATUS_RETIRED:
        return STATUS_RETIRED
    if overlay:
        return overlay
    return source


def listed_families() -> list[dict[str, str]]:
    return [
        {"name": name, "label": FAMILY_LABELS[name]}
        for name in MODEL_FAMILIES
    ]


def listed_statuses() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "label": STATUS_LABELS[name],
            "allowed_transitions": allowed_transitions(name),
        }
        for name in REGISTRY_STATUSES
    ]


@dataclass
class DatasetLineage:
    """Pointer to the immutable snapshot that trained the artifact."""

    training_dataset_id: str = ""
    training_dataset_ids: list[str] = field(default_factory=list)
    training_dataset_version: int = 0
    feature_schema_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        ids = list(self.training_dataset_ids)
        if self.training_dataset_id and self.training_dataset_id not in ids:
            ids.insert(0, self.training_dataset_id)
        return {
            "training_dataset_id": self.training_dataset_id,
            "training_dataset_ids": ids,
            "training_dataset_version": int(self.training_dataset_version),
            "feature_schema_version": self.feature_schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DatasetLineage:
        data = data or {}
        dataset_id = str(data.get("training_dataset_id", "") or "")
        ids = [str(item) for item in data.get("training_dataset_ids", []) if str(item or "").strip()]
        if dataset_id and dataset_id not in ids:
            ids.insert(0, dataset_id)
        return cls(
            training_dataset_id=dataset_id or (ids[0] if ids else ""),
            training_dataset_ids=ids,
            training_dataset_version=int(data.get("training_dataset_version", 0) or 0),
            feature_schema_version=str(data.get("feature_schema_version", "") or ""),
        )


@dataclass
class PromotionEvent:
    """One explicit, human-gated status change. Never auto-deployed."""

    from_status: str
    to_status: str
    actor: str
    at: str
    note: str = ""
    confirm: bool = True
    auto_deployed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_status": self.from_status,
            "to_status": self.to_status,
            "actor": self.actor,
            "at": self.at,
            "note": self.note,
            "confirm": True,
            "auto_deployed": False,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PromotionEvent:
        data = data or {}
        return cls(
            from_status=str(data.get("from_status", "") or ""),
            to_status=str(data.get("to_status", "") or ""),
            actor=str(data.get("actor", "") or ""),
            at=str(data.get("at", "") or ""),
            note=str(data.get("note", "") or ""),
            confirm=True,
            auto_deployed=False,
        )


@dataclass
class RegistryRecord:
    """Catalog card over an existing trained artifact. No second estimator tree."""

    family: str
    model_id: str
    team_id: str
    site_id: str
    scope: str
    model_type: str
    model_version: int
    status: str
    source_status: str
    checksum: str
    lineage: DatasetLineage
    class_name: str = ""
    training_date: str = ""
    algorithm: str = ""
    sample_count: int = 0
    promoted_by: str = ""
    promoted_at: str = ""
    transitions: list[PromotionEvent] = field(default_factory=list)
    allowed_transitions: list[str] = field(default_factory=list)
    auto_deployed: bool = False
    data_roles: dict[str, str] = field(default_factory=lambda: dict(DATA_ROLES))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "model_id": self.model_id,
            "team_id": self.team_id,
            "site_id": self.site_id,
            "scope": self.scope,
            "model_type": self.model_type,
            "class_name": self.class_name,
            "model_version": int(self.model_version),
            "status": self.status,
            "source_status": self.source_status,
            "checksum": self.checksum,
            "lineage": self.lineage.to_dict(),
            "training_date": self.training_date,
            "algorithm": self.algorithm,
            "sample_count": int(self.sample_count),
            "promoted_by": self.promoted_by,
            "promoted_at": self.promoted_at,
            "transitions": [item.to_dict() for item in self.transitions],
            "allowed_transitions": list(self.allowed_transitions or allowed_transitions(self.status)),
            "auto_deployed": False,
            "data_roles": _copy(self.data_roles or DATA_ROLES),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RegistryRecord:
        data = data or {}
        status = str(data.get("status", STATUS_CANDIDATE) or STATUS_CANDIDATE)
        return cls(
            family=str(data.get("family", "") or ""),
            model_id=str(data.get("model_id", "") or ""),
            team_id=str(data.get("team_id", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
            scope=str(data.get("scope", "") or ""),
            model_type=str(data.get("model_type", "") or ""),
            class_name=str(data.get("class_name", "") or ""),
            model_version=int(data.get("model_version", 0) or 0),
            status=status,
            source_status=str(data.get("source_status", "") or ""),
            checksum=str(data.get("checksum", "") or data.get("artifact_sha256", "") or ""),
            lineage=DatasetLineage.from_dict(data.get("lineage") or data),
            training_date=str(data.get("training_date", "") or ""),
            algorithm=str(data.get("algorithm", "") or ""),
            sample_count=int(data.get("sample_count", 0) or 0),
            promoted_by=str(data.get("promoted_by", "") or ""),
            promoted_at=str(data.get("promoted_at", "") or ""),
            transitions=[PromotionEvent.from_dict(item) for item in data.get("transitions", [])],
            allowed_transitions=list(data.get("allowed_transitions") or allowed_transitions(status)),
            auto_deployed=False,
            data_roles=dict(data.get("data_roles") or DATA_ROLES),
        )
