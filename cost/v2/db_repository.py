"""PostgreSQL-репозиторий Cost V2.

Импортируется лениво зависимостью FastAPI, поэтому отсутствие настроенной БД
не ломает Cost V1 и остальные маршруты приложения.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    desc,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from cost.v2.models import EconomicScenario, ReferenceItem, ReferenceSnapshot
from cost.v2.references import default_reference_snapshot, normalize_sections
from cost.v2.repository import (
    EconomicsRecordNotFound,
    LegacyWorkspaceSettings,
    PublicLink,
    PublicLinkConflict,
    ReferenceRevisionConflict,
    ReferenceRevisionInfo,
    StoredCalculationRun,
    StoredEconomicsRun,
    StoredScenario,
    StoredTechnicalPassport,
    links_for_sections,
)
from cost.v2.public_sync.settings import PublicSyncSettings, flags_from_settings, settings_from_flags


SCHEMA = "blastex"
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class ReferenceRevisionRow(Base):
    __tablename__ = "reference_revisions"
    __table_args__ = (
        UniqueConstraint("organization_id", "sequence_no", name="uq_reference_revision_sequence"),
        Index("ix_reference_revision_latest", "organization_id", "sequence_no"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_by: Mapped[str] = mapped_column(String(320), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ReferenceItemRow(Base):
    __tablename__ = "reference_items"
    __table_args__ = (
        UniqueConstraint("revision_id", "section", "code", name="uq_reference_item_code"),
        Index("ix_reference_item_lookup", "organization_id", "revision_id", "section"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    valid_from: Mapped[Any | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Any | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    item_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class EconomicScenarioRow(Base):
    __tablename__ = "economic_scenarios"
    __table_args__ = (
        Index("ix_economic_scenario_org_updated", "organization_id", "updated_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    production_unit_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class CalculationRunRow(Base):
    __tablename__ = "calculation_runs"
    __table_args__ = (
        Index("ix_calculation_run_scenario", "organization_id", "scenario_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    scenario_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.economic_scenarios.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reference_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    formula_version: Mapped[str] = mapped_column(String(80), nullable=False)
    calculation_scope: Mapped[str] = mapped_column(String(20), nullable=False, default="UNIT")
    technical_passport_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.technical_passports.id", ondelete="RESTRICT"),
        nullable=True,
    )
    site_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    period: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    technical_formula_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default=""
    )
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)


class TechnicalPassportRow(Base):
    __tablename__ = "technical_passports"
    __table_args__ = (
        Index("ix_technical_passport_org_site", "organization_id", "site_code", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    site_code: Mapped[str] = mapped_column(String(80), nullable=False)
    object_name: Mapped[str] = mapped_column(String(300), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_passport_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.technical_passports.id", ondelete="RESTRICT"),
        nullable=True,
    )
    reference_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    formula_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    selected_variant: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    block_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    physical: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    lineage: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)


class EconomicsRunRow(Base):
    """Снимок прогона модели себестоимости блока (TASK-007)."""

    __tablename__ = "economics_runs"
    __table_args__ = (
        Index("ix_economics_run_passport", "organization_id", "technical_passport_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    technical_passport_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.technical_passports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    package_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)


class LegacyWorkspaceSettingsRow(Base):
    __tablename__ = "legacy_workspace_settings"
    __table_args__ = ({"schema": SCHEMA},)

    organization_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    team_name: Mapped[str] = mapped_column(String(300), nullable=False)
    active_scenario_id: Mapped[str] = mapped_column(String(120), nullable=False)
    active_work_object_name: Mapped[str] = mapped_column(String(300), nullable=False)
    reference_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class LegacyCostScenarioRow(Base):
    __tablename__ = "legacy_cost_scenarios"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scenario_key", name="uq_legacy_cost_scenario_key"
        ),
        Index("ix_legacy_cost_scenario_org", "organization_id", "updated_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    scenario_key: Mapped[str] = mapped_column(String(120), nullable=False)
    reference_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    labor_assignment_records: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    drilling_calculator_input: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    scenario_phase_overrides: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_org_created", "organization_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    actor: Mapped[str] = mapped_column(String(320), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    before_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    after_payload: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublicLinkRow(Base):
    __tablename__ = "public_links"
    __table_args__ = (
        UniqueConstraint("public_table", "public_id", name="uq_public_links_public_row"),
        {"schema": SCHEMA},
    )

    organization_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    section: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(120), primary_key=True)
    public_table: Mapped[str] = mapped_column(String(64), nullable=False)
    public_id: Mapped[int] = mapped_column(Integer, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class PublicMirrorSectionRow(Base):
    __tablename__ = "public_mirror_sections"
    __table_args__ = ({"schema": SCHEMA},)

    organization_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    section: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class PostgresEconomicsRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True, future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def _latest_revision(self, session: Session, organization_id: str) -> ReferenceRevisionRow | None:
        return session.scalar(
            select(ReferenceRevisionRow)
            .where(ReferenceRevisionRow.organization_id == organization_id)
            .order_by(desc(ReferenceRevisionRow.sequence_no))
            .limit(1)
        )

    def _ensure_defaults(self, organization_id: str) -> None:
        with self.session_factory() as session, session.begin():
            # Two first requests for the same organization must not both try to
            # create revision No. 1. PostgreSQL releases this lock on commit.
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"blastex-cost-v2:{organization_id}"},
            )
            if self._latest_revision(session, organization_id) is not None:
                return
            default = default_reference_snapshot()
            revision_id = str(uuid4())
            now = datetime.now(timezone.utc).replace(microsecond=0)
            session.add(
                ReferenceRevisionRow(
                    id=revision_id,
                    organization_id=organization_id,
                    sequence_no=1,
                    published_at=now,
                    published_by="system",
                    comment="Начальные справочники Cost V2",
                )
            )
            # The reference rows have an FK to the newly created revision and
            # are inserted in bulk below. Flush the parent explicitly so the
            # database enforces the FK in the intended order.
            session.flush()
            self._insert_reference_items(session, organization_id, revision_id, default.sections)

    def get_reference_snapshot(
        self, organization_id: str, revision_id: str | None = None
    ) -> ReferenceSnapshot:
        self._ensure_defaults(organization_id)
        with self.session_factory() as session:
            if revision_id:
                revision = session.get(ReferenceRevisionRow, revision_id)
                if revision is None or revision.organization_id != organization_id:
                    raise EconomicsRecordNotFound(f"Ревизия {revision_id} не найдена.")
            else:
                revision = self._latest_revision(session, organization_id)
            assert revision is not None
            rows = session.scalars(
                select(ReferenceItemRow)
                .where(
                    ReferenceItemRow.organization_id == organization_id,
                    ReferenceItemRow.revision_id == revision.id,
                )
                .order_by(ReferenceItemRow.section, ReferenceItemRow.code)
            ).all()
            sections: dict[str, list[ReferenceItem]] = {}
            for row in rows:
                sections.setdefault(row.section, []).append(
                    ReferenceItem(
                        code=row.code,
                        name=row.name,
                        payload=dict(row.payload or {}),
                        is_active=row.is_active,
                        valid_from=row.valid_from,
                        valid_to=row.valid_to,
                        source=row.source,
                        comment=row.comment,
                        revision=row.item_revision,
                    )
                )
            return ReferenceSnapshot(
                revision_id=revision.id,
                sections={key: tuple(values) for key, values in sections.items()},
                published_at=revision.published_at,
                published_by=revision.published_by,
            )

    def list_reference_revisions(
        self, organization_id: str
    ) -> Sequence[ReferenceRevisionInfo]:
        self._ensure_defaults(organization_id)
        with self.session_factory() as session:
            rows = session.scalars(
                select(ReferenceRevisionRow)
                .where(ReferenceRevisionRow.organization_id == organization_id)
                .order_by(desc(ReferenceRevisionRow.sequence_no))
            ).all()
            return tuple(self._revision_info(row) for row in rows)

    def publish_references(
        self,
        organization_id: str,
        user_id: str,
        base_revision: str,
        sections: dict[str, Any],
        comment: str = "",
        public_links: Sequence[PublicLink] = (),
    ) -> ReferenceSnapshot:
        self._ensure_defaults(organization_id)
        normalized = normalize_sections(sections)
        # Связи черновика записываются той же транзакцией и под той же
        # блокировкой, что и ревизия: иначе между записью ревизии и записью
        # связи есть окно, в котором строка журнала снова выглядит несвязанной.
        saved_links = links_for_sections(public_links, normalized)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        revision_id = str(uuid4())
        with self.session_factory() as session, session.begin():
            # Serialize publications per organization. Locking only the current
            # revision row is not enough: a waiter could hold a statement
            # snapshot taken before the winner inserted the next revision.
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"blastex-cost-v2:{organization_id}"},
            )
            current = session.scalar(
                select(ReferenceRevisionRow)
                .where(ReferenceRevisionRow.organization_id == organization_id)
                .order_by(desc(ReferenceRevisionRow.sequence_no))
                .limit(1)
                .with_for_update()
            )
            assert current is not None
            if current.id != base_revision:
                raise ReferenceRevisionConflict(base_revision, current.id)
            before = self._snapshot_dict(session, organization_id, current.id)
            session.add(
                ReferenceRevisionRow(
                    id=revision_id,
                    organization_id=organization_id,
                    sequence_no=current.sequence_no + 1,
                    published_at=now,
                    published_by=user_id,
                    comment=comment,
                )
            )
            # Записи ссылаются на новую ревизию внешним ключом; порядок вставки
            # задаём явно, как и при создании начальной ревизии.
            session.flush()
            self._insert_reference_items(session, organization_id, revision_id, normalized)
            after = {
                key: [item.to_dict() for item in values]
                for key, values in normalized.items()
            }
            session.add(
                AuditLogRow(
                    id=str(uuid4()),
                    organization_id=organization_id,
                    actor=user_id,
                    action="PUBLISH_REFERENCES",
                    entity_type="reference_revision",
                    entity_id=revision_id,
                    before_payload=before,
                    after_payload=after,
                    created_at=now,
                )
            )
            for link in saved_links:
                self._upsert_public_link(session, organization_id, user_id, link, now)
        return self.get_reference_snapshot(organization_id, revision_id)

    def list_scenarios(self, organization_id: str) -> Sequence[StoredScenario]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(EconomicScenarioRow)
                .where(EconomicScenarioRow.organization_id == organization_id)
                .order_by(desc(EconomicScenarioRow.updated_at))
            ).all()
            return tuple(self._stored_scenario(row) for row in rows)

    def get_scenario(self, organization_id: str, scenario_id: str) -> StoredScenario:
        with self.session_factory() as session:
            row = session.get(EconomicScenarioRow, scenario_id)
            if row is None or row.organization_id != organization_id:
                raise EconomicsRecordNotFound(f"Сценарий {scenario_id} не найден.")
            return self._stored_scenario(row)

    def save_scenario(
        self, organization_id: str, user_id: str, scenario: EconomicScenario
    ) -> StoredScenario:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        scenario_id = scenario.id or str(uuid4())
        normalized = EconomicScenario.from_dict({**scenario.to_dict(), "id": scenario_id})
        with self.session_factory() as session, session.begin():
            row = session.get(EconomicScenarioRow, scenario_id)
            if row is not None and row.organization_id != organization_id:
                raise EconomicsRecordNotFound(f"Сценарий {scenario_id} не найден.")
            before = dict(row.payload) if row else None
            if row is None:
                row = EconomicScenarioRow(
                    id=scenario_id,
                    organization_id=organization_id,
                    production_unit_code=normalized.production_unit_code,
                    name=normalized.name,
                    payload=normalized.to_dict(),
                    created_at=now,
                    created_by=user_id,
                    updated_at=now,
                    updated_by=user_id,
                )
                session.add(row)
            else:
                row.production_unit_code = normalized.production_unit_code
                row.name = normalized.name
                row.payload = normalized.to_dict()
                row.updated_at = now
                row.updated_by = user_id
            session.add(
                AuditLogRow(
                    id=str(uuid4()),
                    organization_id=organization_id,
                    actor=user_id,
                    action="CREATE_SCENARIO" if before is None else "UPDATE_SCENARIO",
                    entity_type="economic_scenario",
                    entity_id=scenario_id,
                    before_payload=before,
                    after_payload=normalized.to_dict(),
                    created_at=now,
                )
            )
        return self.get_scenario(organization_id, scenario_id)

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
        run_id = str(uuid4())
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with self.session_factory() as session, session.begin():
            session.add(
                CalculationRunRow(
                    id=run_id,
                    organization_id=organization_id,
                    scenario_id=scenario.id,
                    reference_revision_id=reference_revision_id,
                    formula_version=formula_version,
                    calculation_scope="UNIT",
                    input_snapshot=scenario.to_dict(),
                    result=result,
                    created_at=now,
                    created_by=user_id,
                )
            )
        return self.get_calculation_run(organization_id, run_id)

    def get_calculation_run(
        self, organization_id: str, run_id: str
    ) -> StoredCalculationRun:
        with self.session_factory() as session:
            row = session.get(CalculationRunRow, run_id)
            if row is None or row.organization_id != organization_id:
                raise EconomicsRecordNotFound(f"Расчёт {run_id} не найден.")
            return StoredCalculationRun(
                id=row.id,
                organization_id=row.organization_id,
                scenario_id=row.scenario_id,
                reference_revision_id=row.reference_revision_id,
                formula_version=row.formula_version,
                input_snapshot=dict(row.input_snapshot),
                result=dict(row.result),
                created_at=row.created_at,
                created_by=row.created_by,
                calculation_scope=row.calculation_scope,
                technical_passport_id=row.technical_passport_id,
                site_code=row.site_code,
                period=row.period,
                technical_formula_version=row.technical_formula_version,
            )

    def list_technical_passports(
        self, organization_id: str, site_code: str | None = None
    ) -> Sequence[StoredTechnicalPassport]:
        with self.session_factory() as session:
            statement = select(TechnicalPassportRow).where(
                TechnicalPassportRow.organization_id == organization_id
            )
            if site_code:
                statement = statement.where(TechnicalPassportRow.site_code == site_code)
            rows = session.scalars(statement.order_by(desc(TechnicalPassportRow.created_at))).all()
            return tuple(self._stored_technical_passport(row) for row in rows)

    def get_technical_passport(
        self, organization_id: str, passport_id: str
    ) -> StoredTechnicalPassport:
        with self.session_factory() as session:
            row = session.get(TechnicalPassportRow, passport_id)
            if row is None or row.organization_id != organization_id:
                raise EconomicsRecordNotFound(
                    f"Технический паспорт {passport_id} не найден."
                )
            return self._stored_technical_passport(row)

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
        passport_id = str(uuid4())
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with self.session_factory() as session, session.begin():
            revision = session.get(ReferenceRevisionRow, reference_revision_id)
            if revision is None or revision.organization_id != organization_id:
                raise EconomicsRecordNotFound(
                    f"Ревизия {reference_revision_id} не найдена."
                )
            previous = None
            if previous_passport_id:
                previous = session.get(TechnicalPassportRow, previous_passport_id)
                if previous is None or previous.organization_id != organization_id:
                    raise EconomicsRecordNotFound(
                        f"Технический паспорт {previous_passport_id} не найден."
                    )
                if previous.site_code != site_code:
                    raise ValueError(
                        "Новая версия паспорта должна относиться к тому же объекту."
                    )
            row = TechnicalPassportRow(
                id=passport_id,
                organization_id=organization_id,
                site_code=site_code,
                object_name=object_name,
                version_no=(previous.version_no + 1 if previous else 1),
                previous_passport_id=previous_passport_id,
                reference_revision_id=reference_revision_id,
                formula_version=formula_version,
                input_snapshot=input_snapshot,
                selected_variant=selected_variant,
                block_snapshot=block_snapshot,
                physical=physical,
                lineage=lineage,
                created_at=now,
                created_by=user_id,
            )
            session.add(row)
            session.add(
                AuditLogRow(
                    id=str(uuid4()),
                    organization_id=organization_id,
                    actor=user_id,
                    action="CREATE_TECHNICAL_PASSPORT",
                    entity_type="technical_passport",
                    entity_id=passport_id,
                    before_payload=None,
                    after_payload={
                        "site_code": site_code,
                        "object_name": object_name,
                        "version_no": row.version_no,
                        "reference_revision_id": reference_revision_id,
                    },
                    created_at=now,
                )
            )
        return self.get_technical_passport(organization_id, passport_id)

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
        run_id = str(uuid4())
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with self.session_factory() as session, session.begin():
            passport = session.get(TechnicalPassportRow, technical_passport_id)
            if passport is None or passport.organization_id != organization_id:
                raise EconomicsRecordNotFound(
                    f"Технический паспорт {technical_passport_id} не найден."
                )
            session.add(
                CalculationRunRow(
                    id=run_id,
                    organization_id=organization_id,
                    scenario_id=None,
                    reference_revision_id=reference_revision_id,
                    formula_version=formula_version,
                    calculation_scope="EVENT",
                    technical_passport_id=technical_passport_id,
                    site_code=site_code,
                    period=period,
                    technical_formula_version=technical_formula_version,
                    input_snapshot=input_snapshot,
                    result=result,
                    created_at=now,
                    created_by=user_id,
                )
            )
        return self.get_calculation_run(organization_id, run_id)

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
        run_id = str(uuid4())
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with self.session_factory() as session, session.begin():
            passport = session.get(TechnicalPassportRow, technical_passport_id)
            if passport is None or passport.organization_id != organization_id:
                raise EconomicsRecordNotFound(
                    f"Технический паспорт {technical_passport_id} не найден."
                )
            session.add(
                EconomicsRunRow(
                    id=run_id,
                    organization_id=organization_id,
                    name=name,
                    technical_passport_id=technical_passport_id,
                    package_code=package_code,
                    reference_revision_id=reference_revision_id,
                    parameters=parameters,
                    result=result,
                    created_at=now,
                    created_by=user_id,
                )
            )
        return self.get_economics_run(organization_id, run_id)

    def list_economics_runs(
        self, organization_id: str, technical_passport_id: str | None = None
    ) -> Sequence[StoredEconomicsRun]:
        with self.session_factory() as session:
            statement = select(EconomicsRunRow).where(
                EconomicsRunRow.organization_id == organization_id
            )
            if technical_passport_id:
                statement = statement.where(
                    EconomicsRunRow.technical_passport_id == technical_passport_id
                )
            rows = session.scalars(statement.order_by(desc(EconomicsRunRow.created_at))).all()
            return tuple(self._stored_economics_run(row) for row in rows)

    def get_economics_run(self, organization_id: str, run_id: str) -> StoredEconomicsRun:
        with self.session_factory() as session:
            row = session.get(EconomicsRunRow, run_id)
            if row is None or row.organization_id != organization_id:
                raise EconomicsRecordNotFound(f"Прогон экономики {run_id} не найден.")
            return self._stored_economics_run(row)

    @staticmethod
    def _stored_economics_run(row: EconomicsRunRow) -> StoredEconomicsRun:
        return StoredEconomicsRun(
            id=row.id,
            organization_id=row.organization_id,
            name=row.name,
            technical_passport_id=row.technical_passport_id,
            package_code=row.package_code,
            reference_revision_id=row.reference_revision_id,
            parameters=dict(row.parameters or {}),
            result=dict(row.result or {}),
            created_at=row.created_at,
            created_by=row.created_by,
        )

    def get_legacy_workspace(self, organization_id: str) -> LegacyWorkspaceSettings | None:
        with self.session_factory() as session:
            row = session.get(LegacyWorkspaceSettingsRow, organization_id)
            if row is None:
                return None
            return LegacyWorkspaceSettings(
                team_name=row.team_name,
                active_scenario_id=row.active_scenario_id,
                active_work_object_name=row.active_work_object_name,
                reference_revision_id=row.reference_revision_id,
            )

    def get_legacy_scenario(self, organization_id: str, scenario_key: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(LegacyCostScenarioRow).where(
                    LegacyCostScenarioRow.organization_id == organization_id,
                    LegacyCostScenarioRow.scenario_key == scenario_key,
                )
            )
            if row is None:
                return None
            # Отдельные колонки — источник правды для того, что фронт правит;
            # payload хранит остальное (смены в месяц и т.п.).
            return {
                **dict(row.payload or {}),
                "labor_assignment_records": list(row.labor_assignment_records or []),
                "drilling_calculator_input": dict(row.drilling_calculator_input or {}),
                "scenario_phase_overrides": dict(row.scenario_phase_overrides or {}),
                "reference_revision_id": row.reference_revision_id,
            }

    def import_legacy_workspace(
        self,
        organization_id: str,
        user_id: str,
        *,
        team_name: str,
        active_scenario_id: str,
        active_work_object_name: str,
        reference_revision_id: str | None = None,
    ) -> None:
        """Настройки рабочего пространства Cost V1 → PostgreSQL.

        Данные переносятся один раз при развёртывании: после этого каталог
        `data/teams/` из тома больше не нужен.
        """

        now = datetime.now(timezone.utc).replace(microsecond=0)
        with self.session_factory() as session, session.begin():
            row = session.get(LegacyWorkspaceSettingsRow, organization_id)
            if row is None:
                session.add(
                    LegacyWorkspaceSettingsRow(
                        organization_id=organization_id,
                        team_name=team_name,
                        active_scenario_id=active_scenario_id,
                        active_work_object_name=active_work_object_name,
                        reference_revision_id=reference_revision_id,
                        created_at=now,
                        created_by=user_id,
                        updated_at=now,
                        updated_by=user_id,
                    )
                )
                return
            row.team_name = team_name
            row.active_scenario_id = active_scenario_id
            row.active_work_object_name = active_work_object_name
            row.reference_revision_id = reference_revision_id
            row.updated_at = now
            row.updated_by = user_id

    def import_legacy_scenarios(
        self,
        organization_id: str,
        user_id: str,
        scenarios: Mapping[str, dict[str, Any]],
        *,
        reference_revision_id: str | None = None,
    ) -> list[str]:
        """Сценарии сметы Cost V1 → PostgreSQL; ключ сценария остаётся прежним."""

        now = datetime.now(timezone.utc).replace(microsecond=0)
        imported: list[str] = []
        with self.session_factory() as session, session.begin():
            existing = {
                row.scenario_key: row
                for row in session.scalars(
                    select(LegacyCostScenarioRow).where(
                        LegacyCostScenarioRow.organization_id == organization_id
                    )
                ).all()
            }
            for scenario_key, payload in scenarios.items():
                row = existing.get(scenario_key)
                values = {
                    "labor_assignment_records": list(payload.get("labor_assignment_records") or []),
                    "drilling_calculator_input": dict(payload.get("drilling_calculator_input") or {}),
                    "scenario_phase_overrides": dict(payload.get("scenario_phase_overrides") or {}),
                    "payload": dict(payload),
                    "reference_revision_id": reference_revision_id,
                }
                if row is None:
                    session.add(
                        LegacyCostScenarioRow(
                            id=str(uuid4()),
                            organization_id=organization_id,
                            scenario_key=scenario_key,
                            created_at=now,
                            created_by=user_id,
                            updated_at=now,
                            updated_by=user_id,
                            **values,
                        )
                    )
                else:
                    for field, value in values.items():
                        setattr(row, field, value)
                    row.updated_at = now
                    row.updated_by = user_id
                imported.append(scenario_key)
        return imported

    def list_public_links(self, organization_id: str) -> Sequence[PublicLink]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(PublicLinkRow)
                .where(PublicLinkRow.organization_id == organization_id)
                .order_by(PublicLinkRow.section, PublicLinkRow.code)
            ).all()
            return tuple(self._public_link(row) for row in rows)

    @staticmethod
    def _upsert_public_link(
        session: Session,
        organization_id: str,
        user_id: str,
        link: PublicLink,
        now: datetime,
    ) -> None:
        """Upsert связи по (organization_id, section, code) внутри транзакции.

        Уникальность (public_table, public_id) проверяется и записывается в
        одной транзакции; `uq_public_links_public_row` в БД — подстраховка на
        случай гонки, поэтому её нарушение тоже превращается в понятную
        доменную ошибку, а не в необработанный IntegrityError. Ради этого
        строка сбрасывается в базу сразу: при публикации откатить нужно и
        ревизию, а не только связь.
        """

        conflict = session.scalar(
            select(PublicLinkRow).where(
                PublicLinkRow.public_table == link.public_table,
                PublicLinkRow.public_id == link.public_id,
            )
        )
        if conflict is not None and (
            conflict.organization_id != organization_id
            or conflict.section != link.section
            or conflict.code != link.code
        ):
            raise PublicLinkConflict(link.public_table, link.public_id)
        row = session.scalar(
            select(PublicLinkRow).where(
                PublicLinkRow.organization_id == organization_id,
                PublicLinkRow.section == link.section,
                PublicLinkRow.code == link.code,
            )
        )
        if row is None:
            session.add(
                PublicLinkRow(
                    organization_id=organization_id,
                    section=link.section,
                    code=link.code,
                    public_table=link.public_table,
                    public_id=link.public_id,
                    synced_at=now,
                    updated_by=user_id,
                )
            )
        else:
            row.public_table = link.public_table
            row.public_id = link.public_id
            row.synced_at = now
            row.updated_by = user_id
        try:
            session.flush()
        except IntegrityError as exc:
            if "uq_public_links_public_row" in str(getattr(exc, "orig", exc)):
                raise PublicLinkConflict(link.public_table, link.public_id) from exc
            raise

    def save_public_link(self, organization_id: str, user_id: str, link: PublicLink) -> PublicLink:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with self.session_factory() as session, session.begin():
            self._upsert_public_link(session, organization_id, user_id, link, now)
        return PublicLink(
            section=link.section,
            code=link.code,
            public_table=link.public_table,
            public_id=link.public_id,
            synced_at=now,
        )

    def list_mirror_sections(self, organization_id: str) -> dict[str, bool]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(PublicMirrorSectionRow).where(
                    PublicMirrorSectionRow.organization_id == organization_id
                )
            ).all()
            return {row.section: row.enabled for row in rows}

    def set_mirror_section(
        self, organization_id: str, user_id: str, section: str, enabled: bool
    ) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with self.session_factory() as session, session.begin():
            row = session.scalar(
                select(PublicMirrorSectionRow).where(
                    PublicMirrorSectionRow.organization_id == organization_id,
                    PublicMirrorSectionRow.section == section,
                )
            )
            if row is None:
                session.add(
                    PublicMirrorSectionRow(
                        organization_id=organization_id,
                        section=section,
                        enabled=enabled,
                        updated_at=now,
                        updated_by=user_id,
                    )
                )
            else:
                row.enabled = enabled
                row.updated_at = now
                row.updated_by = user_id

    def get_public_sync_settings(self, organization_id: str) -> PublicSyncSettings:
        return settings_from_flags(self.list_mirror_sections(organization_id))

    def set_public_sync_settings(
        self, organization_id: str, user_id: str, settings: PublicSyncSettings
    ) -> PublicSyncSettings:
        # Пока просто делегирует `set_mirror_section` построчно; создание
        # самого зеркала (выгрузка раздела) — уровнем выше, в следующей
        # задаче.
        for section, enabled in flags_from_settings(settings).items():
            self.set_mirror_section(organization_id, user_id, section, enabled)
        return self.get_public_sync_settings(organization_id)

    @staticmethod
    def _public_link(row: PublicLinkRow) -> PublicLink:
        return PublicLink(
            section=row.section,
            code=row.code,
            public_table=row.public_table,
            public_id=row.public_id,
            synced_at=row.synced_at,
        )

    def _insert_reference_items(
        self,
        session: Session,
        organization_id: str,
        revision_id: str,
        sections: dict[str, Any],
    ) -> None:
        for section, items in sections.items():
            for item in items:
                session.add(
                    ReferenceItemRow(
                        id=str(uuid4()),
                        organization_id=organization_id,
                        revision_id=revision_id,
                        section=section,
                        code=item.code,
                        name=item.name,
                        payload=item.payload,
                        is_active=item.is_active,
                        valid_from=item.valid_from,
                        valid_to=item.valid_to,
                        source=item.source,
                        comment=item.comment,
                        item_revision=item.revision,
                    )
                )

    def _snapshot_dict(
        self, session: Session, organization_id: str, revision_id: str
    ) -> dict[str, Any]:
        rows = session.scalars(
            select(ReferenceItemRow).where(
                ReferenceItemRow.organization_id == organization_id,
                ReferenceItemRow.revision_id == revision_id,
            )
        ).all()
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(row.section, []).append(
                {
                    "code": row.code,
                    "name": row.name,
                    "payload": row.payload,
                    "is_active": row.is_active,
                    "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                    "valid_to": row.valid_to.isoformat() if row.valid_to else None,
                    "source": row.source,
                    "comment": row.comment,
                    "revision": row.item_revision,
                }
            )
        return result

    @staticmethod
    def _revision_info(row: ReferenceRevisionRow) -> ReferenceRevisionInfo:
        return ReferenceRevisionInfo(
            id=row.id,
            organization_id=row.organization_id,
            sequence_no=row.sequence_no,
            published_at=row.published_at,
            published_by=row.published_by,
            comment=row.comment,
        )

    @staticmethod
    def _stored_scenario(row: EconomicScenarioRow) -> StoredScenario:
        return StoredScenario(
            scenario=EconomicScenario.from_dict(row.payload),
            organization_id=row.organization_id,
            created_at=row.created_at,
            created_by=row.created_by,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )

    @staticmethod
    def _stored_technical_passport(row: TechnicalPassportRow) -> StoredTechnicalPassport:
        return StoredTechnicalPassport(
            id=row.id,
            organization_id=row.organization_id,
            site_code=row.site_code,
            object_name=row.object_name,
            version_no=row.version_no,
            previous_passport_id=row.previous_passport_id,
            reference_revision_id=row.reference_revision_id,
            formula_version=row.formula_version,
            input_snapshot=dict(row.input_snapshot),
            selected_variant=dict(row.selected_variant),
            block_snapshot=dict(row.block_snapshot),
            physical=dict(row.physical),
            lineage={key: str(value) for key, value in dict(row.lineage).items()},
            created_at=row.created_at,
            created_by=row.created_by,
        )
