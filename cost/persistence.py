"""
Сохранение и загрузка рабочих данных команды (справочники, сценарии).

Файлы хранятся в data/teams/{team_id}/ и не коммитятся в git.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cost.catalog import DEFAULT_CATALOG, catalog_to_records
from cost.drilling import DrillingUnitCostInput, calculate_drilling_unit_cost
from cost.fixed_costs import DEFAULT_FIXED_COSTS, fixed_costs_to_records
from cost.labor import (
    DEFAULT_LABOR_ASSIGNMENTS,
    DEFAULT_LABOR_CATALOG,
    labor_assignments_to_records,
    labor_catalog_to_records,
)
from cost.drilling_data import DEFAULT_OBJECT_NAME
from cost.scenarios import (
    DEFAULT_SCENARIO_ID,
    list_scenario_templates,
    normalize_scenario_id,
)

WORKSPACE_VERSION = 1
DEFAULT_TEAM_ID = "default"


@dataclass
class TeamSettings:
    version: int = WORKSPACE_VERSION
    team_id: str = DEFAULT_TEAM_ID
    team_name: str = "Команда по умолчанию"
    active_scenario_id: str = DEFAULT_SCENARIO_ID
    active_work_object_name: str = DEFAULT_OBJECT_NAME


@dataclass
class WorkspaceSnapshot:
    version: int = WORKSPACE_VERSION
    scenario_id: str = DEFAULT_SCENARIO_ID
    updated_at: str = ""
    cost_catalog_records: list[dict] = field(default_factory=list)
    fixed_cost_records: list[dict] = field(default_factory=list)
    labor_catalog_records: list[dict] = field(default_factory=list)
    labor_assignment_records: list[dict] = field(default_factory=list)
    labor_shifts_per_month: float = 5.0
    drilling_calculator_input: dict[str, Any] = field(default_factory=dict)
    scenario_phase_overrides: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceSnapshot:
        return cls(
            version=int(data.get("version", WORKSPACE_VERSION)),
            scenario_id=normalize_scenario_id(str(data.get("scenario_id", DEFAULT_SCENARIO_ID))),
            updated_at=str(data.get("updated_at", "")),
            cost_catalog_records=list(data.get("cost_catalog_records", [])),
            fixed_cost_records=list(data.get("fixed_cost_records", [])),
            labor_catalog_records=list(data.get("labor_catalog_records", [])),
            labor_assignment_records=list(data.get("labor_assignment_records", [])),
            labor_shifts_per_month=float(data.get("labor_shifts_per_month", 5.0)),
            drilling_calculator_input=dict(data.get("drilling_calculator_input", {})),
            scenario_phase_overrides={
                str(k): bool(v) for k, v in dict(data.get("scenario_phase_overrides", {})).items()
            },
        )


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    return project_root() / "data"


def team_dir(team_id: str = DEFAULT_TEAM_ID) -> Path:
    return data_root() / "teams" / team_id


def team_settings_path(team_id: str = DEFAULT_TEAM_ID) -> Path:
    return team_dir(team_id) / "settings.json"


def scenario_path(team_id: str, scenario_id: str) -> Path:
    return team_dir(team_id) / "scenarios" / f"{scenario_id}.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_default_snapshot(scenario_id: str) -> WorkspaceSnapshot:
    template = get_scenario_template(scenario_id)
    phase_overrides = {}
    if template:
        phase_overrides = {phase.id: phase.enabled for phase in template.phases}

    return WorkspaceSnapshot(
        scenario_id=scenario_id,
        updated_at=_utc_now_iso(),
        cost_catalog_records=catalog_to_records(DEFAULT_CATALOG),
        fixed_cost_records=fixed_costs_to_records(DEFAULT_FIXED_COSTS),
        labor_catalog_records=labor_catalog_to_records(DEFAULT_LABOR_CATALOG),
        labor_assignment_records=labor_assignments_to_records(DEFAULT_LABOR_ASSIGNMENTS),
        labor_shifts_per_month=5.0,
        drilling_calculator_input=DrillingUnitCostInput().__dict__,
        scenario_phase_overrides=phase_overrides,
    )


def ensure_team_layout(team_id: str = DEFAULT_TEAM_ID) -> None:
    team_dir(team_id).mkdir(parents=True, exist_ok=True)
    (team_dir(team_id) / "scenarios").mkdir(parents=True, exist_ok=True)


def load_team_settings(team_id: str = DEFAULT_TEAM_ID) -> TeamSettings:
    ensure_team_layout(team_id)
    path = team_settings_path(team_id)
    if not path.exists():
        settings = TeamSettings(team_id=team_id)
        save_team_settings(settings)
        return settings
    data = _read_json(path)
    raw_active = str(data.get("active_scenario_id", DEFAULT_SCENARIO_ID))
    active = normalize_scenario_id(raw_active)
    settings = TeamSettings(
        version=int(data.get("version", WORKSPACE_VERSION)),
        team_id=str(data.get("team_id", team_id)),
        team_name=str(data.get("team_name", team_id)),
        active_scenario_id=active,
        active_work_object_name=str(
            data.get("active_work_object_name", DEFAULT_OBJECT_NAME)
        ),
    )
    if raw_active != active:
        save_team_settings(settings)
    return settings


def save_team_settings(settings: TeamSettings) -> None:
    ensure_team_layout(settings.team_id)
    _write_json(team_settings_path(settings.team_id), asdict(settings))


def load_scenario_snapshot(team_id: str, scenario_id: str) -> WorkspaceSnapshot:
    ensure_team_layout(team_id)
    path = scenario_path(team_id, scenario_id)
    if not path.exists():
        snapshot = build_default_snapshot(scenario_id)
        save_scenario_snapshot(team_id, snapshot)
        return snapshot
    return WorkspaceSnapshot.from_dict(_read_json(path))


def save_scenario_snapshot(team_id: str, snapshot: WorkspaceSnapshot) -> None:
    ensure_team_layout(team_id)
    snapshot.updated_at = _utc_now_iso()
    _write_json(scenario_path(team_id, snapshot.scenario_id), snapshot.to_dict())


def bootstrap_team_scenarios(team_id: str = DEFAULT_TEAM_ID) -> None:
    """Создать файлы всех шаблонных сценариев, если их ещё нет."""
    for template in list_scenario_templates():
        path = scenario_path(team_id, template.id)
        if not path.exists():
            save_scenario_snapshot(team_id, build_default_snapshot(template.id))


def collect_snapshot_from_session(session_state: Any, *, scenario_id: str) -> WorkspaceSnapshot:
    drilling_input = dict(session_state.get("drilling_calculator_input", DrillingUnitCostInput().__dict__))
    return WorkspaceSnapshot(
        scenario_id=scenario_id,
        cost_catalog_records=list(session_state.get("cost_catalog_records", [])),
        fixed_cost_records=list(session_state.get("fixed_cost_records", [])),
        labor_catalog_records=list(session_state.get("labor_catalog_records", [])),
        labor_assignment_records=list(session_state.get("labor_assignment_records", [])),
        labor_shifts_per_month=float(session_state.get("labor_shifts_per_month", 5.0)),
        drilling_calculator_input=drilling_input,
        scenario_phase_overrides=dict(session_state.get("scenario_phase_overrides", {})),
    )


def apply_snapshot_to_session(session_state: Any, snapshot: WorkspaceSnapshot) -> None:
    session_state["cost_catalog_records"] = list(snapshot.cost_catalog_records)
    session_state["fixed_cost_records"] = list(snapshot.fixed_cost_records)
    session_state["labor_catalog_records"] = list(snapshot.labor_catalog_records)
    session_state["labor_assignment_records"] = list(snapshot.labor_assignment_records)
    session_state["labor_shifts_per_month"] = float(snapshot.labor_shifts_per_month)
    session_state["drilling_calculator_input"] = dict(snapshot.drilling_calculator_input)
    session_state["scenario_phase_overrides"] = dict(snapshot.scenario_phase_overrides)
    session_state["active_scenario_id"] = snapshot.scenario_id

    from cost.engine import CostEngine
    from cost.strategies.common import apply_work_object_to_drilling_input

    engine = CostEngine()
    ctx = engine.build_context(session_state)
    drilling_input = apply_work_object_to_drilling_input(
        ctx.drilling_input_base,
        ctx.work_object.name,
    )
    drilling_result = calculate_drilling_unit_cost(drilling_input)
    session_state["drilling_price_per_m"] = drilling_result.price_per_m
    session_state["drilling_unit_cost_result"] = drilling_result


def snapshot_fingerprint(snapshot: WorkspaceSnapshot) -> str:
    payload = json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_snapshot_dirty(session_state: Any) -> bool:
    if "workspace_saved_fingerprint" not in session_state:
        return False
    scenario_id = normalize_scenario_id(str(session_state.get("active_scenario_id", DEFAULT_SCENARIO_ID)))
    current = collect_snapshot_from_session(session_state, scenario_id=scenario_id)
    return snapshot_fingerprint(current) != session_state["workspace_saved_fingerprint"]


def save_current_workspace(session_state: Any) -> Path:
    team_id = str(session_state.get("workspace_team_id", DEFAULT_TEAM_ID))
    scenario_id = normalize_scenario_id(str(session_state.get("active_scenario_id", DEFAULT_SCENARIO_ID)))
    snapshot = collect_snapshot_from_session(session_state, scenario_id=scenario_id)
    save_scenario_snapshot(team_id, snapshot)
    settings = load_team_settings(team_id)
    settings.active_work_object_name = str(
        session_state.get("active_work_object_name", DEFAULT_OBJECT_NAME)
    )
    save_team_settings(settings)
    session_state["workspace_saved_fingerprint"] = snapshot_fingerprint(snapshot)
    return scenario_path(team_id, scenario_id)


def load_workspace_scenario(
    session_state: Any,
    *,
    team_id: str,
    scenario_id: str,
) -> WorkspaceSnapshot:
    scenario_id = normalize_scenario_id(scenario_id)
    snapshot = load_scenario_snapshot(team_id, scenario_id)
    apply_snapshot_to_session(session_state, snapshot)
    session_state["workspace_team_id"] = team_id
    session_state["active_scenario_id"] = scenario_id
    session_state["workspace_saved_fingerprint"] = snapshot_fingerprint(snapshot)
    return snapshot
