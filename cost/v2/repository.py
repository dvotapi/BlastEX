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
    scenario_id: str | None
    reference_revision_id: str
    formula_version: str
    input_snapshot: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime
    created_by: str
    calculation_scope: str = "UNIT"
    technical_passport_id: str | None = None
    site_code: str = ""
    period: str = ""
    technical_formula_version: str = ""

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
            "calculation_scope": self.calculation_scope,
            "technical_passport_id": self.technical_passport_id,
            "site_code": self.site_code,
            "period": self.period,
            "technical_formula_version": self.technical_formula_version,
        }


@dataclass(frozen=True)
class StoredTechnicalPassport:
    id: str
    organization_id: str
    site_code: str
    object_name: str
    version_no: int
    previous_passport_id: str | None
    reference_revision_id: str
    formula_version: str
    input_snapshot: dict[str, Any]
    selected_variant: dict[str, Any]
    block_snapshot: dict[str, Any]
    physical: dict[str, Any]
    lineage: dict[str, str]
    created_at: datetime
    created_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "site_code": self.site_code,
            "object_name": self.object_name,
            "version_no": self.version_no,
            "previous_passport_id": self.previous_passport_id,
            "reference_revision_id": self.reference_revision_id,
            "formula_version": self.formula_version,
            "input_snapshot": self.input_snapshot,
            "selected_variant": self.selected_variant,
            "block_snapshot": self.block_snapshot,
            "physical": self.physical,
            "lineage": self.lineage,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
        }


@dataclass(frozen=True)
class StoredEconomicsRun:
    """Снимок прогона модели себестоимости блока.

    Хранится целиком: паспорт, пакет, ревизия справочников, параметры модели
    и результат. Сравнение сценариев идёт между снимками, поэтому пересчёт
    старого прогона на новых справочниках невозможен по построению.
    """

    id: str
    organization_id: str
    name: str
    technical_passport_id: str
    package_code: str
    reference_revision_id: str
    parameters: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime
    created_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "technical_passport_id": self.technical_passport_id,
            "package_code": self.package_code,
            "reference_revision_id": self.reference_revision_id,
            "parameters": self.parameters,
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

    def list_technical_passports(
        self, organization_id: str, site_code: str | None = None
    ) -> Sequence[StoredTechnicalPassport]: ...

    def get_technical_passport(
        self, organization_id: str, passport_id: str
    ) -> StoredTechnicalPassport: ...

    def save_technical_passport(
        self,
        organization_id: str,
        user_id: str,
        *,
        site_code: str,
        object_name: str,
        previous_passport_id: str | None,
        reference_revision_id: str,
        formula_version: str,
        input_snapshot: dict[str, Any],
        selected_variant: dict[str, Any],
        block_snapshot: dict[str, Any],
        physical: dict[str, Any],
        lineage: dict[str, str],
    ) -> StoredTechnicalPassport: ...

    def save_event_calculation_run(
        self,
        organization_id: str,
        user_id: str,
        *,
        reference_revision_id: str,
        formula_version: str,
        technical_formula_version: str,
        technical_passport_id: str,
        site_code: str,
        period: str,
        input_snapshot: dict[str, Any],
        result: dict[str, Any],
    ) -> StoredCalculationRun: ...

    def save_economics_run(
        self,
        organization_id: str,
        user_id: str,
        *,
        name: str,
        technical_passport_id: str,
        package_code: str,
        reference_revision_id: str,
        parameters: dict[str, Any],
        result: dict[str, Any],
    ) -> StoredEconomicsRun: ...

    def list_economics_runs(
        self, organization_id: str, technical_passport_id: str | None = None
    ) -> Sequence[StoredEconomicsRun]: ...

    def get_economics_run(self, organization_id: str, run_id: str) -> StoredEconomicsRun: ...


class InMemoryEconomicsRepository:
    """Потокобезопасное хранилище для unit/API-тестов."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshots: dict[tuple[str, str], ReferenceSnapshot] = {}
        self._revisions: dict[str, list[ReferenceRevisionInfo]] = {}
        self._scenarios: dict[tuple[str, str], StoredScenario] = {}
        self._runs: dict[tuple[str, str], StoredCalculationRun] = {}
        self._passports: dict[tuple[str, str], StoredTechnicalPassport] = {}
        self._economics_runs: dict[tuple[str, str], StoredEconomicsRun] = {}

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

    def list_technical_passports(
        self, organization_id: str, site_code: str | None = None
    ) -> Sequence[StoredTechnicalPassport]:
        with self._lock:
            rows = [
                deepcopy(value)
                for (org, _), value in self._passports.items()
                if org == organization_id and (not site_code or value.site_code == site_code)
            ]
            return tuple(sorted(rows, key=lambda row: row.created_at, reverse=True))

    def get_technical_passport(
        self, organization_id: str, passport_id: str
    ) -> StoredTechnicalPassport:
        with self._lock:
            try:
                return deepcopy(self._passports[(organization_id, passport_id)])
            except KeyError as exc:
                raise EconomicsRecordNotFound(
                    f"Технический паспорт {passport_id} не найден."
                ) from exc

    def save_technical_passport(
        self,
        organization_id: str,
        user_id: str,
        *,
        site_code: str,
        object_name: str,
        previous_passport_id: str | None,
        reference_revision_id: str,
        formula_version: str,
        input_snapshot: dict[str, Any],
        selected_variant: dict[str, Any],
        block_snapshot: dict[str, Any],
        physical: dict[str, Any],
        lineage: dict[str, str],
    ) -> StoredTechnicalPassport:
        with self._lock:
            self.get_reference_snapshot(organization_id, reference_revision_id)
            previous = (
                self.get_technical_passport(organization_id, previous_passport_id)
                if previous_passport_id
                else None
            )
            if previous and previous.site_code != site_code:
                raise EconomicsRepositoryError(
                    "Новая версия паспорта должна относиться к тому же объекту."
                )
            passport_id = str(uuid4())
            stored = StoredTechnicalPassport(
                id=passport_id,
                organization_id=organization_id,
                site_code=site_code,
                object_name=object_name,
                version_no=(previous.version_no + 1 if previous else 1),
                previous_passport_id=previous_passport_id,
                reference_revision_id=reference_revision_id,
                formula_version=formula_version,
                input_snapshot=deepcopy(input_snapshot),
                selected_variant=deepcopy(selected_variant),
                block_snapshot=deepcopy(block_snapshot),
                physical=deepcopy(physical),
                lineage=deepcopy(lineage),
                created_at=datetime.now(timezone.utc).replace(microsecond=0),
                created_by=user_id,
            )
            self._passports[(organization_id, passport_id)] = stored
            return deepcopy(stored)

    def save_event_calculation_run(
        self,
        organization_id: str,
        user_id: str,
        *,
        reference_revision_id: str,
        formula_version: str,
        technical_formula_version: str,
        technical_passport_id: str,
        site_code: str,
        period: str,
        input_snapshot: dict[str, Any],
        result: dict[str, Any],
    ) -> StoredCalculationRun:
        with self._lock:
            self.get_technical_passport(organization_id, technical_passport_id)
            run_id = str(uuid4())
            run = StoredCalculationRun(
                id=run_id,
                organization_id=organization_id,
                scenario_id=None,
                reference_revision_id=reference_revision_id,
                formula_version=formula_version,
                input_snapshot=deepcopy(input_snapshot),
                result=deepcopy(result),
                created_at=datetime.now(timezone.utc).replace(microsecond=0),
                created_by=user_id,
                calculation_scope="EVENT",
                technical_passport_id=technical_passport_id,
                site_code=site_code,
                period=period,
                technical_formula_version=technical_formula_version,
            )
            self._runs[(organization_id, run_id)] = run
            return deepcopy(run)

    def save_economics_run(
        self,
        organization_id: str,
        user_id: str,
        *,
        name: str,
        technical_passport_id: str,
        package_code: str,
        reference_revision_id: str,
        parameters: dict[str, Any],
        result: dict[str, Any],
    ) -> StoredEconomicsRun:
        with self._lock:
            self.get_technical_passport(organization_id, technical_passport_id)
            run_id = str(uuid4())
            run = StoredEconomicsRun(
                id=run_id,
                organization_id=organization_id,
                name=name,
                technical_passport_id=technical_passport_id,
                package_code=package_code,
                reference_revision_id=reference_revision_id,
                parameters=deepcopy(parameters),
                result=deepcopy(result),
                created_at=datetime.now(timezone.utc).replace(microsecond=0),
                created_by=user_id,
            )
            self._economics_runs[(organization_id, run_id)] = run
            return deepcopy(run)

    def list_economics_runs(
        self, organization_id: str, technical_passport_id: str | None = None
    ) -> Sequence[StoredEconomicsRun]:
        with self._lock:
            rows = [
                deepcopy(value)
                for (org, _), value in self._economics_runs.items()
                if org == organization_id
                and (
                    not technical_passport_id
                    or value.technical_passport_id == technical_passport_id
                )
            ]
            return tuple(sorted(rows, key=lambda row: row.created_at, reverse=True))

    def get_economics_run(self, organization_id: str, run_id: str) -> StoredEconomicsRun:
        with self._lock:
            try:
                return deepcopy(self._economics_runs[(organization_id, run_id)])
            except KeyError as exc:
                raise EconomicsRecordNotFound(f"Прогон экономики {run_id} не найден.") from exc
