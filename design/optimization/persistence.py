"""Write-once-friendly storage for optimization runs.

Files live in ``data/teams/{team_id}/optimizations/{design_id}/{run_id}.json``.
They are never written into ``designs/``. Saving a run does not call
``save_design``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cost.persistence import team_dir
from design.optimization.types import OptimizationResult

__all__ = [
    "OptimizationNotFoundError",
    "optimizations_dir",
    "list_runs",
    "load_run",
    "save_run",
]


class OptimizationNotFoundError(Exception):
    """Optimization run file is missing for this team / design."""


def optimizations_root(team_id: str) -> Path:
    return team_dir(team_id) / "optimizations"


def optimizations_dir(team_id: str, design_id: str) -> Path:
    _validate_id(design_id, "паспорт")
    return optimizations_root(team_id) / design_id


def _validate_id(value: str, label: str) -> None:
    if not value or value != Path(value).name or value in {".", ".."}:
        raise OptimizationNotFoundError(f"{label.capitalize()} «{value}» не найден.")


def run_path(team_id: str, design_id: str, run_id: str) -> Path:
    _validate_id(design_id, "паспорт")
    _validate_id(run_id, "прогон")
    base = optimizations_dir(team_id, design_id).resolve()
    path = (base / f"{run_id}.json").resolve()
    if not path.is_relative_to(base):
        raise OptimizationNotFoundError(f"Прогон «{run_id}» не найден.")
    return path


def list_runs(team_id: str, design_id: str) -> list[dict[str, Any]]:
    folder = optimizations_dir(team_id, design_id)
    if not folder.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "run_id": str(data.get("run_id", path.stem)),
                "design_id": str(data.get("design_id", design_id)),
                "created_at": str(data.get("created_at", "")),
                "evaluated": int(data.get("evaluated") or 0),
                "pareto_count": len(data.get("pareto_front") or []),
                "method": str(data.get("method") or ""),
                "modifies_design": False,
                "replaces_design": False,
            }
        )
    items.sort(key=lambda item: item["created_at"])
    return items


def load_run(team_id: str, design_id: str, run_id: str) -> OptimizationResult:
    path = run_path(team_id, design_id, run_id)
    if not path.exists():
        raise OptimizationNotFoundError(f"Прогон «{run_id}» не найден.")
    return OptimizationResult.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_run(team_id: str, result: OptimizationResult) -> OptimizationResult:
    if not result.run_id:
        from design.optimization.engine import new_run_id

        result.run_id = new_run_id()
    result.modifies_design = False
    result.replaces_design = False
    result.uses_rl = False
    path = run_path(team_id, result.design_id, result.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
