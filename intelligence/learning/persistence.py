"""Write-once storage for two-level learning artifacts.

Artifacts live in ``data/teams/{team_id}/learning/``. Isolation keys
``team_id`` / ``site_id`` are stored on every record. Cross-tenant access
fails. The estimator file is immutable; only status may change after training.
Formal staging / production / archive promotion is ``intelligence.registry``.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

from cost.persistence import team_dir
from intelligence.learning.isolation import (
    CrossTenantError,
    assert_model_tenant,
    require_team_id,
)
from intelligence.learning.types import (
    SCOPE_GLOBAL,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    STATUS_RETIRED,
    LearnedModel,
    normalize_scope,
    normalize_status,
    utc_now_iso,
)


class LearningNotFoundError(Exception):
    """Learned model with the given id is not in the team store."""


class ImmutableLearningError(Exception):
    """A trained artifact cannot be overwritten."""


@dataclass
class LearningSummary:
    model_id: str
    team_id: str
    site_id: str
    scope: str
    model_type: str
    class_name: str
    model_version: int
    training_dataset_id: str
    training_dataset_ids: list[str]
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any]
    status: str
    algorithm: str
    primary_target: str
    target_names: list[str]
    sample_count: int
    prior_model_id: str
    adaptation: str
    source_site_ids: list[str]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def integrity_hash(payload: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in payload.items()
        if key not in {"integrity_sha256", "status", "status_updated_at"}
    }
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def artifact_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def learning_dir(team_id: str) -> Path:
    return team_dir(require_team_id(team_id)) / "learning"


def _validate_model_id(model_id: str) -> None:
    if not model_id or model_id != Path(model_id).name or model_id in {".", ".."}:
        raise LearningNotFoundError(f"Модель обучения «{model_id}» не найдена.")


def metadata_path(team_id: str, model_id: str) -> Path:
    _validate_model_id(model_id)
    base = learning_dir(team_id).resolve()
    path = (base / f"{model_id}.json").resolve()
    if not path.is_relative_to(base):
        raise LearningNotFoundError(f"Модель обучения «{model_id}» не найдена.")
    return path


def artifact_path(team_id: str, model_id: str) -> Path:
    _validate_model_id(model_id)
    base = learning_dir(team_id).resolve()
    path = (base / f"{model_id}.joblib").resolve()
    if not path.is_relative_to(base):
        raise LearningNotFoundError(f"Модель обучения «{model_id}» не найдена.")
    return path


def new_model_id() -> str:
    return uuid.uuid4().hex[:12]


def existing_versions(
    team_id: str,
    *,
    scope: str,
    site_id: str,
    model_type: str,
) -> list[int]:
    return [
        item.model_version
        for item in list_models(team_id, scope=scope, site_id=site_id, model_type=model_type)
    ]


def list_models(
    team_id: str,
    *,
    model_type: str = "",
    scope: str = "",
    site_id: str = "",
) -> list[LearningSummary]:
    folder = learning_dir(team_id)
    folder.mkdir(parents=True, exist_ok=True)
    summaries: list[LearningSummary] = []
    wanted_type = model_type.strip()
    wanted_scope = normalize_scope(scope) if scope.strip() else ""
    wanted_site = site_id.strip()
    for path in sorted(folder.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        stored_team = str(data.get("team_id", "") or "")
        if stored_team and stored_team != team_id:
            continue
        item_type = str(data.get("model_type", ""))
        item_scope = str(data.get("scope", ""))
        item_site = str(data.get("site_id", ""))
        if wanted_type and item_type != wanted_type:
            continue
        if wanted_scope and item_scope != wanted_scope:
            continue
        if wanted_site and item_site != wanted_site:
            continue
        summaries.append(
            LearningSummary(
                model_id=str(data.get("model_id", path.stem)),
                team_id=str(data.get("team_id", team_id)),
                site_id=item_site,
                scope=item_scope,
                model_type=item_type,
                class_name=str(data.get("class_name", "")),
                model_version=int(data.get("model_version", 0) or 0),
                training_dataset_id=str(data.get("training_dataset_id", "")),
                training_dataset_ids=[str(item) for item in data.get("training_dataset_ids", [])],
                training_dataset_version=int(data.get("training_dataset_version", 0) or 0),
                feature_schema_version=str(data.get("feature_schema_version", "")),
                training_date=str(data.get("training_date", "")),
                metrics=dict(data.get("metrics") or {}),
                status=str(data.get("status", STATUS_CANDIDATE) or STATUS_CANDIDATE),
                algorithm=str(data.get("algorithm", "")),
                primary_target=str(data.get("primary_target", "")),
                target_names=[str(item) for item in data.get("target_names", [])],
                sample_count=int(data.get("sample_count", 0) or 0),
                prior_model_id=str(data.get("prior_model_id", "") or ""),
                adaptation=str(data.get("adaptation", "") or ""),
                source_site_ids=[str(item) for item in data.get("source_site_ids", [])],
            )
        )
    summaries.sort(key=lambda item: (item.training_date, item.model_version), reverse=True)
    return summaries


def _unpack_artifact(loaded: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(loaded, dict) and ("estimators" in loaded or "prior_estimators" in loaded):
        estimators = loaded.get("estimators") or {}
        prior = loaded.get("prior_estimators") or {}
        if not isinstance(estimators, dict):
            estimators = {"_single": estimators}
        if not isinstance(prior, dict):
            prior = {"_single": prior}
        return dict(estimators), dict(prior)
    if isinstance(loaded, dict):
        return dict(loaded), {}
    return {"_single": loaded}, {}


def load_model(team_id: str, model_id: str) -> LearnedModel:
    team = require_team_id(team_id)
    meta = metadata_path(team, model_id)
    artifact = artifact_path(team, model_id)
    if not meta.exists() or not artifact.exists():
        raise LearningNotFoundError(f"Модель обучения «{model_id}» не найдена.")
    data = _read_json(meta)
    stored_team = str(data.get("team_id", "") or "")
    if stored_team and stored_team != team:
        raise CrossTenantError(
            f"Модель «{model_id}» принадлежит команде «{stored_team}», доступ команды «{team}» запрещён."
        )
    stored_hash = str(data.get("integrity_sha256", "") or "")
    if stored_hash and stored_hash != integrity_hash(data):
        raise ImmutableLearningError(
            f"Метаданные модели «{model_id}» повреждены и больше не являются неизменяемыми."
        )
    stored_artifact = str(data.get("artifact_sha256", "") or "")
    if stored_artifact and stored_artifact != artifact_hash(artifact):
        raise ImmutableLearningError(f"Артефакт модели «{model_id}» повреждён.")
    estimators, prior_estimators = _unpack_artifact(joblib.load(artifact))
    model = LearnedModel.from_dict(data, estimators=estimators, prior_estimators=prior_estimators)
    assert_model_tenant(model, team)
    return model


def save_model(team_id: str, model: LearnedModel) -> LearnedModel:
    """Persist a new candidate. Existing artifacts are never overwritten."""
    team = require_team_id(team_id)
    if not str(model.team_id or "").strip():
        model.team_id = team
    assert_model_tenant(model, team)
    if not model.model_id:
        model.model_id = new_model_id()
    if not model.estimators:
        raise ValueError("Нельзя сохранить модель без обученного артефакта.")
    meta = metadata_path(team, model.model_id)
    artifact = artifact_path(team, model.model_id)
    if meta.exists() or artifact.exists():
        raise ImmutableLearningError(
            f"Модель «{model.model_id}» уже сохранена и не может быть перезаписана."
        )
    model.status = STATUS_CANDIDATE
    artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "estimators": model.estimators,
            "prior_estimators": model.prior_estimators,
            "adaptation": model.adaptation,
        },
        artifact,
    )
    model.artifact_sha256 = artifact_hash(artifact)
    payload = model.to_dict()
    payload["integrity_sha256"] = integrity_hash(payload)
    _write_json(meta, payload)
    return load_model(team, model.model_id)


def production_model(
    team_id: str,
    *,
    model_type: str,
    scope: str,
    site_id: str = "",
) -> LearnedModel | None:
    matches = [
        item
        for item in list_models(team_id, model_type=model_type, scope=scope, site_id=site_id)
        if item.status == STATUS_PRODUCTION
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: (item.training_date, item.model_version), reverse=True)
    return load_model(team_id, matches[0].model_id)


def latest_global(team_id: str, model_type: str) -> LearnedModel | None:
    items = [
        item
        for item in list_models(team_id, model_type=model_type, scope=SCOPE_GLOBAL)
    ]
    if not items:
        return None
    items.sort(key=lambda item: (item.status == STATUS_PRODUCTION, item.training_date, item.model_version), reverse=True)
    return load_model(team_id, items[0].model_id)


def set_status(team_id: str, model_id: str, status: str) -> LearnedModel:
    """Explicit status change. Never auto-promotes a freshly trained model."""
    status = normalize_status(status)
    model = load_model(team_id, model_id)
    if status == STATUS_PRODUCTION:
        for item in list_models(team_id, model_type=model.model_type, scope=model.scope, site_id=model.site_id):
            if item.model_id != model_id and item.status == STATUS_PRODUCTION:
                _write_status(team_id, item.model_id, STATUS_RETIRED)
    _write_status(team_id, model_id, status)
    return load_model(team_id, model_id)


def _write_status(team_id: str, model_id: str, status: str) -> None:
    path = metadata_path(team_id, model_id)
    data = _read_json(path)
    stored_team = str(data.get("team_id", "") or "")
    if stored_team and stored_team != team_id:
        raise CrossTenantError(
            f"Нельзя менять статус модели команды «{stored_team}» из команды «{team_id}»."
        )
    data["status"] = status
    data["status_updated_at"] = utc_now_iso()
    data["integrity_sha256"] = integrity_hash(data)
    _write_json(path, data)
