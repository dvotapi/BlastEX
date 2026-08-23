"""Write-once storage for training snapshots.

Snapshots live in ``data/teams/{team_id}/datasets/`` — never inside
``designs/``. Production BlastDesign files stay mutable; snapshots do not.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cost.persistence import team_dir

from intelligence.datasets.builder import DatasetSnapshot

__all__ = [
    "DatasetNotFoundError",
    "ImmutableDatasetError",
    "DatasetSummary",
    "datasets_dir",
    "dataset_path",
    "new_dataset_id",
    "list_snapshots",
    "load_snapshot",
    "save_snapshot",
    "integrity_hash",
]


class DatasetNotFoundError(Exception):
    """Training snapshot with the given id is not in the team store."""


class ImmutableDatasetError(Exception):
    """A write-once snapshot cannot be overwritten or mutated."""


@dataclass
class DatasetSummary:
    dataset_id: str
    name: str
    dataset_version: int
    feature_schema_version: str
    site_id: str
    created_at: str
    source_blast_ids: list[str]
    sample_count: int
    rejected_count: int
    immutable: bool = True


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def integrity_hash(payload: dict[str, Any]) -> str:
    canonical = {key: value for key, value in payload.items() if key != "integrity_sha256"}
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def datasets_dir(team_id: str) -> Path:
    return team_dir(team_id) / "datasets"


def _validate_dataset_id(dataset_id: str) -> None:
    if not dataset_id or dataset_id != Path(dataset_id).name or dataset_id in {".", ".."}:
        raise DatasetNotFoundError(f"Снимок датасета «{dataset_id}» не найден.")


def dataset_path(team_id: str, dataset_id: str) -> Path:
    _validate_dataset_id(dataset_id)
    base = datasets_dir(team_id).resolve()
    path = (base / f"{dataset_id}.json").resolve()
    if not path.is_relative_to(base):
        raise DatasetNotFoundError(f"Снимок датасета «{dataset_id}» не найден.")
    return path


def new_dataset_id() -> str:
    return uuid.uuid4().hex[:12]


def list_snapshots(team_id: str) -> list[DatasetSummary]:
    folder = datasets_dir(team_id)
    folder.mkdir(parents=True, exist_ok=True)
    summaries: list[DatasetSummary] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        summaries.append(
            DatasetSummary(
                dataset_id=str(data.get("dataset_id", path.stem)),
                name=str(data.get("name", "")),
                dataset_version=int(data.get("dataset_version", 0) or 0),
                feature_schema_version=str(data.get("feature_schema_version", "")),
                site_id=str(data.get("site_id", "")),
                created_at=str(data.get("created_at", "")),
                source_blast_ids=[str(item) for item in data.get("source_blast_ids", [])],
                sample_count=int(data.get("sample_count", len(data.get("samples", []))) or 0),
                rejected_count=int(data.get("rejected_count", len(data.get("rejected", []))) or 0),
                immutable=True,
            )
        )
    summaries.sort(key=lambda item: (item.created_at, item.dataset_version), reverse=True)
    return summaries


def load_snapshot(team_id: str, dataset_id: str) -> DatasetSnapshot:
    path = dataset_path(team_id, dataset_id)
    if not path.exists():
        raise DatasetNotFoundError(f"Снимок датасета «{dataset_id}» не найден.")
    data = _read_json(path)
    stored_hash = str(data.get("integrity_sha256", "") or "")
    if stored_hash and stored_hash != integrity_hash(data):
        raise ImmutableDatasetError(f"Снимок датасета «{dataset_id}» повреждён и больше не является неизменяемым.")
    return DatasetSnapshot.from_dict(data)


def save_snapshot(team_id: str, snapshot: DatasetSnapshot) -> DatasetSnapshot:
    """Persist a new snapshot. Existing files are never overwritten."""
    if not snapshot.dataset_id:
        snapshot.dataset_id = new_dataset_id()
    path = dataset_path(team_id, snapshot.dataset_id)
    if path.exists():
        raise ImmutableDatasetError(
            f"Снимок датасета «{snapshot.dataset_id}» уже сохранён и не может быть перезаписан."
        )
    frozen = DatasetSnapshot.from_dict(snapshot.to_dict())
    payload = frozen.to_dict()
    payload["integrity_sha256"] = integrity_hash(payload)
    _write_json(path, payload)
    return frozen


def existing_versions(team_id: str, site_id: str) -> list[int]:
    return [item.dataset_version for item in list_snapshots(team_id) if item.site_id == site_id]
