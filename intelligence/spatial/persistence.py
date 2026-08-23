"""Tenant-isolated storage for spatial hole-level models.

Artifacts live in ``data/teams/{team_id}/spatial/``. Existing artifacts are
never overwritten. Status may change after a human action.
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
from intelligence.learning.isolation import CrossTenantError, IsolationError, require_team_id
from intelligence.spatial.types import (
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    STATUS_RETIRED,
    SpatialModel,
    normalize_status,
    utc_now_iso,
)


class SpatialNotFoundError(Exception):
    """Spatial model with the given id is not in the team store."""


class ImmutableSpatialError(Exception):
    """A trained spatial artifact cannot be overwritten."""


class InvalidSpatialError(ValueError):
    """Train / predict / status broke a product rule."""


@dataclass
class SpatialSummary:
    model_id: str
    team_id: str
    site_id: str
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any]
    status: str
    algorithm: str
    class_name: str
    hole_count: int
    sample_count: int


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


def spatial_dir(team_id: str) -> Path:
    return team_dir(require_team_id(team_id)) / "spatial"


def _validate_model_id(model_id: str) -> str:
    text = str(model_id or "").strip()
    if not text or text != Path(text).name or text in {".", ".."}:
        raise SpatialNotFoundError(f"Пространственная модель «{model_id}» не найдена.")
    return text


def metadata_path(team_id: str, model_id: str) -> Path:
    model_id = _validate_model_id(model_id)
    base = spatial_dir(team_id).resolve()
    path = (base / f"{model_id}.json").resolve()
    if not path.is_relative_to(base):
        raise SpatialNotFoundError(f"Пространственная модель «{model_id}» не найдена.")
    return path


def artifact_path(team_id: str, model_id: str) -> Path:
    model_id = _validate_model_id(model_id)
    base = spatial_dir(team_id).resolve()
    path = (base / f"{model_id}.joblib").resolve()
    if not path.is_relative_to(base):
        raise SpatialNotFoundError(f"Пространственная модель «{model_id}» не найдена.")
    return path


def new_model_id() -> str:
    return uuid.uuid4().hex[:12]


def existing_versions(team_id: str, site_id: str) -> list[int]:
    return [item.model_version for item in list_models(team_id) if item.site_id == site_id]


def _assert_team(payload: dict[str, Any], team_id: str, *, resource: str) -> None:
    stored = str(payload.get("team_id", "") or "")
    if stored and stored != team_id:
        raise CrossTenantError(
            f"{resource} принадлежит команде «{stored}», доступ команды «{team_id}» запрещён."
        )


def list_models(team_id: str, *, site_id: str = "") -> list[SpatialSummary]:
    team = require_team_id(team_id)
    folder = spatial_dir(team)
    folder.mkdir(parents=True, exist_ok=True)
    summaries: list[SpatialSummary] = []
    wanted = site_id.strip()
    for path in sorted(folder.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        try:
            _assert_team(data, team, resource=f"модель «{path.stem}»")
        except CrossTenantError:
            continue
        if wanted and str(data.get("site_id", "") or "") != wanted:
            continue
        summaries.append(
            SpatialSummary(
                model_id=str(data.get("model_id", path.stem)),
                team_id=str(data.get("team_id", team)),
                site_id=str(data.get("site_id", "")),
                model_version=int(data.get("model_version", 0) or 0),
                training_dataset_id=str(data.get("training_dataset_id", "")),
                training_dataset_version=int(data.get("training_dataset_version", 0) or 0),
                feature_schema_version=str(data.get("feature_schema_version", "")),
                training_date=str(data.get("training_date", "")),
                metrics=dict(data.get("metrics") or {}),
                status=str(data.get("status", STATUS_CANDIDATE) or STATUS_CANDIDATE),
                algorithm=str(data.get("algorithm", "")),
                class_name=str(data.get("class_name", "")),
                hole_count=int(data.get("hole_count", 0) or 0),
                sample_count=int(data.get("sample_count", 0) or 0),
            )
        )
    summaries.sort(key=lambda item: (item.training_date, item.model_version), reverse=True)
    return summaries


def load_model(team_id: str, model_id: str) -> SpatialModel:
    team = require_team_id(team_id)
    meta = metadata_path(team, model_id)
    artifact = artifact_path(team, model_id)
    if not meta.exists() or not artifact.exists():
        raise SpatialNotFoundError(f"Пространственная модель «{model_id}» не найдена.")
    data = _read_json(meta)
    _assert_team(data, team, resource=f"модель «{model_id}»")
    stored_hash = str(data.get("integrity_sha256", "") or "")
    if stored_hash and stored_hash != integrity_hash(data):
        raise ImmutableSpatialError(
            f"Метаданные модели «{model_id}» повреждены и больше не являются неизменяемыми."
        )
    stored_artifact = str(data.get("artifact_sha256", "") or "")
    if stored_artifact and stored_artifact != artifact_hash(artifact):
        raise ImmutableSpatialError(f"Артефакт модели «{model_id}» повреждён.")
    loaded = joblib.load(artifact)
    estimators = loaded if isinstance(loaded, dict) else {"_single": loaded}
    return SpatialModel.from_dict(data, estimators=estimators)


def save_model(team_id: str, model: SpatialModel) -> SpatialModel:
    team = require_team_id(team_id)
    if model.team_id and model.team_id != team:
        raise CrossTenantError(
            f"Модель принадлежит команде «{model.team_id}», запись от команды «{team}» запрещена."
        )
    if not model.model_id:
        model.model_id = new_model_id()
    if not model.estimators:
        raise ValueError("Нельзя сохранить модель без обученного артефакта.")
    model.team_id = team
    meta = metadata_path(team, model.model_id)
    artifact = artifact_path(team, model.model_id)
    if meta.exists() or artifact.exists():
        raise ImmutableSpatialError(
            f"Модель «{model.model_id}» уже сохранена и не может быть перезаписана."
        )
    model.status = STATUS_CANDIDATE
    artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model.estimators, artifact)
    model.artifact_sha256 = artifact_hash(artifact)
    payload = model.to_dict()
    payload["integrity_sha256"] = integrity_hash(payload)
    _write_json(meta, payload)
    return load_model(team, model.model_id)


def production_model(team_id: str, site_id: str) -> SpatialModel | None:
    matches = [
        item
        for item in list_models(team_id)
        if item.site_id == site_id and item.status == STATUS_PRODUCTION
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: (item.training_date, item.model_version), reverse=True)
    return load_model(team_id, matches[0].model_id)


def set_status(team_id: str, model_id: str, status: str) -> SpatialModel:
    status = normalize_status(status)
    model = load_model(team_id, model_id)
    if status == STATUS_PRODUCTION:
        for item in list_models(team_id):
            if item.model_id != model_id and item.site_id == model.site_id and item.status == STATUS_PRODUCTION:
                _write_status(team_id, item.model_id, STATUS_RETIRED)
    _write_status(team_id, model_id, status)
    return load_model(team_id, model_id)


def _write_status(team_id: str, model_id: str, status: str) -> None:
    path = metadata_path(team_id, model_id)
    data = _read_json(path)
    _assert_team(data, team_id, resource=f"модель «{model_id}»")
    data["status"] = status
    data["status_updated_at"] = utc_now_iso()
    data["integrity_sha256"] = integrity_hash(data)
    _write_json(path, data)


def require_team(team_id: str) -> str:
    try:
        return require_team_id(team_id)
    except IsolationError:
        raise
