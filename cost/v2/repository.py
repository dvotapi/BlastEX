"""Контракт хранилища Cost V2 и in-memory реализация для тестов."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Protocol, Sequence
from uuid import uuid4

from cost.v2.models import EconomicScenario, ReferenceSnapshot
from cost.v2.references import default_reference_snapshot, normalize_sections


class EconomicsRepositoryError(RuntimeError):
    pass


class ReferenceRevisionConflict(EconomicsRepositoryError):
    def __init__(self, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Справочники уже изменены: ожидалась ревизия {expected}, актуальна {actual}."
        )


class EconomicsRecordNotFound(EconomicsRepositoryError):
    pass


@dataclass(frozen=True)
class ReferenceRevisionInfo:
    id: str
    organization_id: str
    sequence_no: int
    published_at: datetime
    published_by: str
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "sequence_no": self.sequence_no,
            "published_at": self.published_at.isoformat(),
            "published_by": self.published_by,
            "comment": self.comment,
        }


@dataclass(frozen=True)
class StoredScenario:
    scenario: EconomicScenario
    organization_id: str
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.scenario.to_dict(),
            "organization_id": self.organization_id,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "updated_at": self.updated_at.isoformat(),
            "updated_by": self.updated_by,
        }


@dataclass(frozen=True)
class StoredCalculationRun:
    id: str
    organization_id: str
    scenario_id: str
    reference_revision_id: str
    formula_version: str
    input_snapshot: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime
    created_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "scenario_id": self.scenario_id,
            "reference_revision_id": self.reference_revision_id,
            "formula_version": self.formula_version,
            "input_snapshot": self.input_snapshot,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }


class EconomicsRepository(Protocol):
    def get_reference_snapshot(
        self, organization_id: str, revision_id: str | None = None
    ) -> ReferenceSnapshot: ...

    def list_reference_revisions(
        self, organization_id: str
    ) -> Sequence[ReferenceRevisionInfo]: ...

    def publish_references(
        self,
        organization_id: str,
        user_id: str,
        base_revision: str,
        sections: dict[str, Any],
        comment: str = "",
    ) -> ReferenceSnapshot: ...

    def list_scenarios(self, organization_id: str) -> Sequence[StoredScenario]: ...

    def get_scenario(self, organization_id: str, scenario_id: str) -> StoredScenario: ...

    def save_scenario(
        self, organization_id: str, user_id: str, scenario: EconomicScenario
    ) -> StoredScenario: ...

    def clone_scenario(
        self, organization_id: str, user_id: str, scenario_id: str
    ) -> StoredScenario: ...

    def save_calculation_run(
        self,
        organization_id: str,
        user_id: str,
        scenario: EconomicScenario,
        reference_revision_id: str,
        formula_version: str,
        result: dict[str, Any],
    ) -> StoredCalculationRun: ...

    def get_calculation_run(
        self, organization_id: str, run_id: str
    ) -> StoredCalculationRun: ...


class InMemoryEconomicsRepository:
    """Потокобезопасное хранилище для unit/API-тестов."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshots: dict[tuple[str, str], ReferenceSnapshot] = {}
        self._revisions: dict[str, list[ReferenceRevisionInfo]] = {}
        self._scenarios: dict[tuple[str, str], StoredScenario] = {}
        self._runs: dict[tuple[str, str], StoredCalculationRun] = {}

    def _ensure_org(self, organization_id: str) -> None:
        if organization_id in self._revisions:
            return
        now = datetime.now(timezone.utc).replace(microsecond=0)
        revision_id = f"SYSTEM-{organization_id}-1"
        default = default_reference_snapshot()
        snapshot = ReferenceSnapshot(
            revision_id=revision_id,
            sections=deepcopy(default.sections),
            published_at=now,
            published_by="system",
        )
        self._snapshots[(organization_id, revision_id)] = snapshot
        self._revisions[organization_id] = [
            ReferenceRevisionInfo(
                id=revision_id,
                organization_id=organization_id,
                sequence_no=1,
                published_at=now,
                published_by="system",
                comment="Начальные справочники Cost V2",
            )
        ]

    def get_reference_snapshot(
        self, organization_id: str, revision_id: str | None = None
    ) -> ReferenceSnapshot:
        with self._lock:
            self._ensure_org(organization_id)
            actual_id = revision_id or self._revisions[organization_id][-1].id
            try:
                return deepcopy(self._snapshots[(organization_id, actual_id)])
            except KeyError as exc:
                raise EconomicsRecordNotFound(
                    f"Ревизия справочников {actual_id} не найдена."
                ) from exc

    def list_reference_revisions(
        self, organization_id: str
    ) -> Sequence[ReferenceRevisionInfo]:
        with self._lock:
            self._ensure_org(organization_id)
            return tuple(reversed(self._revisions[organization_id]))

    def publish_references(
        self,
        organization_id: str,
        user_id: str,
        base_revision: str,
        sections: dict[str, Any],
        comment: str = "",
    ) -> ReferenceSnapshot:
        with self._lock:
            self._ensure_org(organization_id)
            current = self._revisions[organization_id][-1]
            if current.id != base_revision:
                raise ReferenceRevisionConflict(base_revision, current.id)
            now = datetime.now(timezone.utc).replace(microsecond=0)
            revision_id = str(uuid4())
            snapshot = ReferenceSnapshot(
                revision_id=revision_id,
                sections=normalize_sections(sections),
                published_at=now,
                published_by=user_id,
            )
            self._snapshots[(organization_id, revision_id)] = deepcopy(snapshot)
            self._revisions[organization_id].append(
                ReferenceRevisionInfo(
                    id=revision_id,
                    organization_id=organization_id,
                    sequence_no=current.sequence_no + 1,
                    published_at=now,
                    published_by=user_id,
                    comment=comment,
                )
            )
            return deepcopy(snapshot)

    def list_scenarios(self, organization_id: str) -> Sequence[StoredScenario]:
        with self._lock:
            rows = [
                deepcopy(value)
                for (org, _), value in self._scenarios.items()
                if org == organization_id
            ]
            return tuple(sorted(rows, key=lambda row: row.updated_at, reverse=True))

    def get_scenario(self, organization_id: str, scenario_id: str) -> StoredScenario:
        with self._lock:
            try:
                return deepcopy(self._scenarios[(organization_id, scenario_id)])
            except KeyError as exc:
                raise EconomicsRecordNotFound(f"Сценарий {scenario_id} не найден.") from exc

    def save_scenario(
        self, organization_id: str, user_id: str, scenario: EconomicScenario
    ) -> StoredScenario:
        with self._lock:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            scenario_id = scenario.id or str(uuid4())
            normalized = EconomicScenario.from_dict({**scenario.to_dict(), "id": scenario_id})
            existing = self._scenarios.get((organization_id, scenario_id))
            stored = StoredScenario(
                scenario=normalized,
                organization_id=organization_id,
                created_at=existing.created_at if existing else now,
                created_by=existing.created_by if existing else user_id,
                updated_at=now,
                updated_by=user_id,
            )
            self._scenarios[(organization_id, scenario_id)] = stored
            return deepcopy(stored)

    def clone_scenario(
        self, organization_id: str, user_id: str, scenario_id: str
    ) -> StoredScenario:
        source = self.get_scenario(organization_id, scenario_id)
        clone = EconomicScenario.from_dict(
            {
                **source.scenario.to_dict(),
                "id": str(uuid4()),
                "name": f"{source.scenario.name} — копия",
            }
        )
        return self.save_scenario(organization_id, user_id, clone)

    def save_calculation_run(
        self,
        organization_id: str,
        user_id: str,
        scenario: EconomicScenario,
        reference_revision_id: str,
        formula_version: str,
        result: dict[str, Any],
    ) -> StoredCalculationRun:
        with self._lock:
            run_id = str(uuid4())
            run = StoredCalculationRun(
                id=run_id,
                organization_id=organization_id,
                scenario_id=scenario.id,
                reference_revision_id=reference_revision_id,
                formula_version=formula_version,
                input_snapshot=deepcopy(scenario.to_dict()),
                result=deepcopy(result),
                created_at=datetime.now(timezone.utc).replace(microsecond=0),
                created_by=user_id,
            )
            self._runs[(organization_id, run_id)] = run
            return deepcopy(run)

    def get_calculation_run(
        self, organization_id: str, run_id: str
    ) -> StoredCalculationRun:
        with self._lock:
            try:
                return deepcopy(self._runs[(organization_id, run_id)])
            except KeyError as exc:
                raise EconomicsRecordNotFound(f"Расчёт {run_id} не найден.") from exc
