"""Write-once storage for specialised outcome-model artifacts.

Artifacts live in ``data/teams/{team_id}/outcomes/`` — never inside
``designs/`` or mutable production records. The estimator file is immutable;
only the status field may change after training.
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
from intelligence.outcomes.types import (
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    STATUS_RETIRED,
    OutcomeModel,
    normalize_status,
    utc_now_iso,
)


class OutcomeNotFoundError(Exception):
    """Outcome model with the given id is not in the team store."""


class ImmutableOutcomeError(Exception):
    """A trained artifact cannot be overwritten."""


@dataclass
class OutcomeSummary:
    model_id: str
    site_id: str
    model_type: str
    class_name: str
    model_version: int
    training_dataset_id: str
    training_dataset_version: int
    feature_schema_version: str
    training_date: str
    metrics: dict[str, Any]
    status: str
    algorithm: str
    primary_target: str
    target_names: list[str]
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


def outcomes_dir(team_id: str) -> Path:
    return team_dir(team_id) / "outcomes"


def _validate_model_id(model_id: str) -> None:
    if not model_id or model_id != Path(model_id).name or model_id in {".", ".."}:
        raise OutcomeNotFoundError(f"Модель исхода «{model_id}» не найдена.")


def metadata_path(team_id: str, model_id: str) -> Path:
    _validate_model_id(model_id)
    base = outcomes_dir(team_id).resolve()
    path = (base / f"{model_id}.json").resolve()
    if not path.is_relative_to(base):
        raise OutcomeNotFoundError(f"Модель исхода «{model_id}» не найдена.")
    return path


def artifact_path(team_id: str, model_id: str) -> Path:
    _validate_model_id(model_id)
    base = outcomes_dir(team_id).resolve()
    path = (base / f"{model_id}.joblib").resolve()
    if not path.is_relative_to(base):
        raise OutcomeNotFoundError(f"Модель исхода «{model_id}» не найдена.")
    return path


def new_model_id() -> str:
    return uuid.uuid4().hex[:12]


def existing_versions(team_id: str, site_id: str, model_type: str) -> list[int]:
    return [
        item.model_version
        for item in list_models(team_id)
        if item.site_id == site_id and item.model_type == model_type
    ]


def list_models(team_id: str, *, model_type: str = "") -> list[OutcomeSummary]:
    folder = outcomes_dir(team_id)
    folder.mkdir(parents=True, exist_ok=True)
    summaries: list[OutcomeSummary] = []
    wanted = model_type.strip()
    for path in sorted(folder.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        item_type = str(data.get("model_type", ""))
        if wanted and item_type != wanted:
            continue
        summaries.append(
            OutcomeSummary(
                model_id=str(data.get("model_id", path.stem)),
                site_id=str(data.get("site_id", "")),
                model_type=item_type,
                class_name=str(data.get("class_name", "")),
                model_version=int(data.get("model_version", 0) or 0),
                training_dataset_id=str(data.get("training_dataset_id", "")),
                training_dataset_version=int(data.get("training_dataset_version", 0) or 0),
                feature_schema_version=str(data.get("feature_schema_version", "")),
                training_date=str(data.get("training_date", "")),
                metrics=dict(data.get("metrics") or {}),
                status=str(data.get("status", STATUS_CANDIDATE) or STATUS_CANDIDATE),
                algorithm=str(data.get("algorithm", "")),
                primary_target=str(data.get("primary_target", "")),
                target_names=[str(item) for item in data.get("target_names", [])],
                sample_count=int(data.get("sample_count", 0) or 0),
            )
        )
    summaries.sort(key=lambda item: (item.training_date, item.model_version), reverse=True)
    return summaries


def load_model(team_id: str, model_id: str) -> OutcomeModel:
    meta = metadata_path(team_id, model_id)
    artifact = artifact_path(team_id, model_id)
    if not meta.exists() or not artifact.exists():
        raise OutcomeNotFoundError(f"Модель исхода «{model_id}» не найдена.")
    data = _read_json(meta)
    stored_hash = str(data.get("integrity_sha256", "") or "")
    if stored_hash and stored_hash != integrity_hash(data):
        raise ImmutableOutcomeError(
            f"Метаданные модели «{model_id}» повреждены и больше не являются неизменяемыми."
        )
    stored_artifact = str(data.get("artifact_sha256", "") or "")
    if stored_artifact and stored_artifact != artifact_hash(artifact):
        raise ImmutableOutcomeError(f"Артефакт модели «{model_id}» повреждён.")
    loaded = joblib.load(artifact)
    estimators = loaded if isinstance(loaded, dict) else {"_single": loaded}
    return OutcomeModel.from_dict(data, estimators=estimators)


def save_model(team_id: str, model: OutcomeModel) -> OutcomeModel:
    """Persist a new candidate. Existing artifacts are never overwritten."""
    if not model.model_id:
        model.model_id = new_model_id()
    if not model.estimators:
        raise ValueError("Нельзя сохранить модель без обученного артефакта.")
    meta = metadata_path(team_id, model.model_id)
    artifact = artifact_path(team_id, model.model_id)
    if meta.exists() or artifact.exists():
        raise ImmutableOutcomeError(
            f"Модель «{model.model_id}» уже сохранена и не может быть перезаписана."
        )
    model.status = STATUS_CANDIDATE
    artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model.estimators, artifact)
    model.artifact_sha256 = artifact_hash(artifact)
    payload = model.to_dict()
    payload["integrity_sha256"] = integrity_hash(payload)
    _write_json(meta, payload)
    return load_model(team_id, model.model_id)


def production_model(team_id: str, site_id: str, model_type: str) -> OutcomeModel | None:
    matches = [
        item
        for item in list_models(team_id)
        if item.site_id == site_id and item.model_type == model_type and item.status == STATUS_PRODUCTION
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: (item.training_date, item.model_version), reverse=True)
    return load_model(team_id, matches[0].model_id)


def set_status(team_id: str, model_id: str, status: str) -> OutcomeModel:
    """Explicit status change. Never auto-promotes a freshly trained model."""
    status = normalize_status(status)
    model = load_model(team_id, model_id)
    if status == STATUS_PRODUCTION:
        for item in list_models(team_id):
            if (
                item.model_id != model_id
                and item.site_id == model.site_id
                and item.model_type == model.model_type
                and item.status == STATUS_PRODUCTION
            ):
                _write_status(team_id, item.model_id, STATUS_RETIRED)
    _write_status(team_id, model_id, status)
    return load_model(team_id, model_id)


def _write_status(team_id: str, model_id: str, status: str) -> None:
    path = metadata_path(team_id, model_id)
    data = _read_json(path)
    data["status"] = status
    data["status_updated_at"] = utc_now_iso()
    data["integrity_sha256"] = integrity_hash(data)
    _write_json(path, data)
