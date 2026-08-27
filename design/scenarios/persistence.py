"""Write-once-friendly storage for design scenarios.

Files live in ``data/teams/{team_id}/scenarios/{design_id}/{scenario_id}.json``.
They are never written into ``designs/``. Creating a scenario does not call
``save_design``.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cost.persistence import team_dir
from design.scenarios.types import DesignScenario, ScenarioSummary

__all__ = [
    "DesignScenarioNotFoundError",
    "scenarios_dir",
    "scenario_path",
    "new_scenario_id",
    "list_scenarios",
    "load_scenario",
    "save_scenario",
    "delete_scenario",
]


class DesignScenarioNotFoundError(Exception):
    """Scenario file is missing for this team / design."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scenarios_root(team_id: str) -> Path:
    return team_dir(team_id) / "scenarios"


def scenarios_dir(team_id: str, design_id: str) -> Path:
    _validate_id(design_id, "паспорт")
    return scenarios_root(team_id) / design_id


def _validate_id(value: str, label: str) -> None:
    if not value or value != Path(value).name or value in {".", ".."}:
        raise DesignScenarioNotFoundError(f"{label.capitalize()} «{value}» не найден.")


def scenario_path(team_id: str, design_id: str, scenario_id: str) -> Path:
    _validate_id(design_id, "паспорт")
    _validate_id(scenario_id, "сценарий")
    base = scenarios_dir(team_id, design_id).resolve()
    path = (base / f"{scenario_id}.json").resolve()
    if not path.is_relative_to(base):
        raise DesignScenarioNotFoundError(f"Сценарий «{scenario_id}» не найден.")
    return path


def new_scenario_id() -> str:
    return "scn-" + uuid.uuid4().hex[:10]


def list_scenarios(team_id: str, design_id: str) -> list[ScenarioSummary]:
    folder = scenarios_dir(team_id, design_id)
    if not folder.exists():
        return []
    items: list[ScenarioSummary] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        outcomes = data.get("outcomes") or {}
        params = data.get("params") or {}
        items.append(
            ScenarioSummary(
                scenario_id=str(data.get("scenario_id", path.stem)),
                design_id=str(data.get("design_id", design_id)),
                name=str(data.get("name", path.stem)),
                kind=str(data.get("kind") or "overlay"),
                created_at=str(data.get("created_at", "")),
                diameter_mm=_as_float(outcomes.get("diameter_mm", params.get("diameter_mm"))),
                spacing_a_m=_as_float(outcomes.get("spacing_a_m", params.get("spacing_a_m"))),
                burden_b_m=_as_float(outcomes.get("burden_b_m", params.get("burden_b_m"))),
                powder_factor_kg_m3=_as_float(
                    outcomes.get("powder_factor_kg_m3", params.get("powder_factor_kg_m3"))
                ),
                hole_count=int(outcomes.get("hole_count") or 0),
            )
        )
    items.sort(key=lambda item: item.created_at)
    return items


def _as_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    return float(raw)


def load_scenario(team_id: str, design_id: str, scenario_id: str) -> DesignScenario:
    path = scenario_path(team_id, design_id, scenario_id)
    if not path.exists():
        raise DesignScenarioNotFoundError(f"Сценарий «{scenario_id}» не найден.")
    return DesignScenario.from_dict(_read_json(path))


def save_scenario(team_id: str, scenario: DesignScenario) -> DesignScenario:
    if not scenario.scenario_id:
        scenario.scenario_id = new_scenario_id()
    if not scenario.created_at:
        scenario.created_at = _utc_now_iso()
    scenario.modifies_design = False
    _write_json(scenario_path(team_id, scenario.design_id, scenario.scenario_id), scenario.to_dict())
    return scenario


def delete_scenario(team_id: str, design_id: str, scenario_id: str) -> None:
    path = scenario_path(team_id, design_id, scenario_id)
    if not path.exists():
        raise DesignScenarioNotFoundError(f"Сценарий «{scenario_id}» не найден.")
    path.unlink()
