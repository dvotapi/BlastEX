"""Сохранение и загрузка паспортов БВР по командам.

Зеркалит устройство `cost/persistence.py`: файлы лежат в
`data/teams/{team_id}/designs/{design_id}.json`, тот же `data/teams/` уже
исключён из git (`.gitignore`), сериализация — обычный JSON без сжатия.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cost.persistence import team_dir
from design.models import DESIGN_VERSION, BlastDesign

__all__ = [
    "DesignNotFoundError",
    "DesignSummary",
    "designs_dir",
    "design_path",
    "ensure_designs_layout",
    "new_design_id",
    "list_designs",
    "load_design",
    "save_design",
    "delete_design",
    "rename_design",
]


class DesignNotFoundError(Exception):
    """Паспорт БВР с указанным id не найден в хранилище команды."""


@dataclass
class DesignSummary:
    design_id: str
    name: str
    updated_at: str
    hole_count: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def designs_dir(team_id: str) -> Path:
    return team_dir(team_id) / "designs"


def _validate_design_id(design_id: str) -> None:
    if not design_id or design_id != Path(design_id).name or design_id in {".", ".."}:
        raise DesignNotFoundError(f"Паспорт БВР «{design_id}» не найден.")


def design_path(team_id: str, design_id: str) -> Path:
    _validate_design_id(design_id)
    base = designs_dir(team_id).resolve()
    path = (base / f"{design_id}.json").resolve()
    if not path.is_relative_to(base):
        raise DesignNotFoundError(f"Паспорт БВР «{design_id}» не найден.")
    return path


def ensure_designs_layout(team_id: str) -> None:
    designs_dir(team_id).mkdir(parents=True, exist_ok=True)


def new_design_id() -> str:
    return uuid.uuid4().hex[:12]


def list_designs(team_id: str) -> list[DesignSummary]:
    ensure_designs_layout(team_id)
    summaries: list[DesignSummary] = []
    for path in sorted(designs_dir(team_id).glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        summaries.append(
            DesignSummary(
                design_id=str(data.get("design_id", path.stem)),
                name=str(data.get("name", path.stem)),
                updated_at=str(data.get("updated_at", "")),
                hole_count=len(data.get("holes", [])),
            )
        )
    summaries.sort(key=lambda s: s.updated_at, reverse=True)
    return summaries


def load_design(team_id: str, design_id: str) -> BlastDesign:
    path = design_path(team_id, design_id)
    if not path.exists():
        raise DesignNotFoundError(f"Паспорт БВР «{design_id}» не найден.")
    return BlastDesign.from_dict(_read_json(path))


def save_design(team_id: str, design: BlastDesign) -> BlastDesign:
    ensure_designs_layout(team_id)
    if not design.design_id:
        design.design_id = new_design_id()
    design.version = DESIGN_VERSION
    design.updated_at = _utc_now_iso()
    _write_json(design_path(team_id, design.design_id), design.to_dict())
    return design


def delete_design(team_id: str, design_id: str) -> None:
    path = design_path(team_id, design_id)
    if not path.exists():
        raise DesignNotFoundError(f"Паспорт БВР «{design_id}» не найден.")
    path.unlink()


def rename_design(team_id: str, design_id: str, new_name: str) -> BlastDesign:
    design = load_design(team_id, design_id)
    design.name = new_name
    return save_design(team_id, design)
