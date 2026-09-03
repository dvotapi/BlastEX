"""Каталог данных команды и снапшот сценария сметы Cost V1.

Справочники, настройки и сценарии живут в PostgreSQL (`cost/v2/repository.py`).
Здесь остались пути `data/teams/<team>/`, которыми пользуются паспорта
проектирования и ML-слой, и структура снапшота сценария.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cost.catalog import DEFAULT_CATALOG, catalog_to_records
from cost.drilling import DrillingUnitCostInput
from cost.fixed_costs import DEFAULT_FIXED_COSTS, fixed_costs_to_records
from cost.labor import (
    DEFAULT_LABOR_ASSIGNMENTS,
    DEFAULT_LABOR_CATALOG,
    labor_assignments_to_records,
    labor_catalog_to_records,
)
from cost.scenarios import DEFAULT_SCENARIO_ID, get_scenario_template, normalize_scenario_id

WORKSPACE_VERSION = 1
DEFAULT_TEAM_ID = "default"


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
