"""Хранение паспортов на бурение и их неизменяемых ревизий в PostgreSQL (TASK-015)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, create_engine, desc, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from cost.v2.db_repository import AuditLogRow, Base, JsonType, SCHEMA


class DrillingPassportRepositoryError(RuntimeError):
    pass


class DrillingPassportNotFoundError(DrillingPassportRepositoryError):
    pass


class DrillingPassportConflictError(DrillingPassportRepositoryError):
    pass


class DrillingPassportRow(Base):
    __tablename__ = "drilling_passports"
    __table_args__ = (
        Index("ix_drilling_passport_org_updated", "organization_id", "updated_at"),
        Index("ix_drilling_passport_design", "organization_id", "design_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    design_id: Mapped[str] = mapped_column(String(120), nullable=False)
    passport_no: Mapped[str] = mapped_column(String(120), nullable=False)
    passport_date: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class DrillingPassportRevisionRow(Base):
    __tablename__ = "drilling_passport_revisions"
    __table_args__ = (
        UniqueConstraint("passport_id", "revision_no", name="uq_drilling_passport_revision_no"),
        Index("ix_drilling_passport_revision_passport", "passport_id", "revision_no"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    passport_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.drilling_passports.id", ondelete="RESTRICT"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.drilling_passport_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    reference_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    formula_version: Mapped[str] = mapped_column(String(80), nullable=False)
    design_id: Mapped[str] = mapped_column(String(120), nullable=False)
    design_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    design_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _not_found(passport_id: str) -> DrillingPassportNotFoundError:
    return DrillingPassportNotFoundError(f"Паспорт на бурение {passport_id} не найден.")


class PostgresDrillingPassportRepository:
    """Черновики с оптимистичной блокировкой; ревизии только добавляются."""

    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True, future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    @staticmethod
    def _passport(row: DrillingPassportRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "design_id": row.design_id,
            "passport_no": row.passport_no,
            "passport_date": row.passport_date,
            "status": row.status,
            "version": row.version,
            "current_revision_id": row.current_revision_id,
            "payload": dict(row.payload or {}),
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
            "updated_at": row.updated_at.isoformat(),
            "updated_by": row.updated_by,
        }

    @staticmethod
    def _revision(row: DrillingPassportRevisionRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "passport_id": row.passport_id,
            "revision_no": row.revision_no,
            "previous_revision_id": row.previous_revision_id,
            "reference_revision_id": row.reference_revision_id,
            "formula_version": row.formula_version,
            "design_id": row.design_id,
            "design_revision": row.design_revision,
            "design_sha256": row.design_sha256,
            "content_sha256": row.content_sha256,
            "context": dict(row.context or {}),
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
        }

    def list_passports(self, organization_id: str, design_id: str | None = None) -> Sequence[dict[str, Any]]:
        with self.session_factory() as session:
            query = select(DrillingPassportRow).where(DrillingPassportRow.organization_id == organization_id)
            if design_id:
                query = query.where(DrillingPassportRow.design_id == design_id)
            rows = session.scalars(query.order_by(desc(DrillingPassportRow.updated_at))).all()
            return tuple(self._passport(row) for row in rows)

    def get_passport(self, organization_id: str, passport_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            return self._passport(self._passport_row(session, organization_id, passport_id))

    def create_passport(
        self, organization_id: str, actor: str, design_id: str, passport_no: str, passport_date: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = _now()
        passport_id = str(uuid4())
        with self.session_factory() as session, session.begin():
            session.add(
                DrillingPassportRow(
                    id=passport_id,
                    organization_id=organization_id,
                    design_id=design_id,
                    passport_no=passport_no,
                    passport_date=passport_date,
                    status="draft",
                    version=1,
                    payload=payload,
                    created_at=now,
                    created_by=actor,
                    updated_at=now,
                    updated_by=actor,
                )
            )
            self._audit(session, organization_id, actor, "CREATE_DRILLING_PASSPORT", passport_id, None, payload, now)
        return self.get_passport(organization_id, passport_id)

    def update_passport(
        self, organization_id: str, actor: str, passport_id: str, passport_no: str, passport_date: str,
        payload: dict[str, Any], expected_version: int,
    ) -> dict[str, Any]:
        now = _now()
        with self.session_factory() as session, session.begin():
            row = self._locked(session, organization_id, passport_id)
            if row.version != expected_version:
                raise DrillingPassportConflictError(
                    "Паспорт изменён другим пользователем. Обновите данные перед сохранением."
                )
            if row.status != "draft":
                raise DrillingPassportConflictError("Редактировать можно только черновик паспорта.")
            before = dict(row.payload or {})
            row.passport_no = passport_no
            row.passport_date = passport_date
            row.payload = payload
            row.version += 1
            row.updated_at = now
            row.updated_by = actor
            self._audit(session, organization_id, actor, "UPDATE_DRILLING_PASSPORT", passport_id, before, payload, now)
        return self.get_passport(organization_id, passport_id)

    def create_revision(
        self, organization_id: str, actor: str, passport_id: str, expected_version: int,
        reference_revision_id: str | None, context: dict[str, Any], content_sha256: str,
    ) -> dict[str, Any]:
        now = _now()
        revision_id = str(uuid4())
        with self.session_factory() as session, session.begin():
            passport = self._locked(session, organization_id, passport_id)
            if passport.version != expected_version:
                raise DrillingPassportConflictError(
                    "Паспорт изменён другим пользователем. Обновите данные перед выпуском ревизии."
                )
            if passport.status != "draft":
                raise DrillingPassportConflictError("Ревизию можно выпустить только из черновика.")
            previous = session.scalar(
                select(DrillingPassportRevisionRow)
                .where(DrillingPassportRevisionRow.passport_id == passport_id)
                .order_by(desc(DrillingPassportRevisionRow.revision_no))
                .limit(1)
            )
            session.add(
                DrillingPassportRevisionRow(
                    id=revision_id,
                    passport_id=passport_id,
                    revision_no=(previous.revision_no + 1) if previous else 1,
                    previous_revision_id=previous.id if previous else None,
                    reference_revision_id=reference_revision_id,
                    formula_version=str(context["formula_version"]),
                    design_id=str(context["design_id"]),
                    design_revision=int(context["design_revision"]),
                    design_sha256=str(context["design_sha256"]),
                    context=context,
                    content_sha256=content_sha256,
                    created_at=now,
                    created_by=actor,
                )
            )
            passport.current_revision_id = revision_id
            passport.version += 1
            passport.updated_at = now
            passport.updated_by = actor
            self._audit(
                session, organization_id, actor, "CREATE_DRILLING_PASSPORT_REVISION", revision_id, None,
                {"passport_id": passport_id, "content_sha256": content_sha256}, now,
            )
        return self.get_revision(organization_id, revision_id)

    def get_revision(self, organization_id: str, revision_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.get(DrillingPassportRevisionRow, revision_id)
            passport = session.get(DrillingPassportRow, row.passport_id) if row is not None else None
            if row is None or passport is None or passport.organization_id != organization_id:
                raise DrillingPassportNotFoundError(f"Ревизия паспорта на бурение {revision_id} не найдена.")
            return self._revision(row)

    @staticmethod
    def _passport_row(session: Session, organization_id: str, passport_id: str) -> DrillingPassportRow:
        row = session.get(DrillingPassportRow, passport_id)
        if row is None or row.organization_id != organization_id:
            raise _not_found(passport_id)
        return row

    @staticmethod
    def _locked(session: Session, organization_id: str, passport_id: str) -> DrillingPassportRow:
        row = session.scalar(
            select(DrillingPassportRow).where(DrillingPassportRow.id == passport_id).with_for_update()
        )
        if row is None or row.organization_id != organization_id:
            raise _not_found(passport_id)
        return row

    @staticmethod
    def _audit(
        session: Session, organization_id: str, actor: str, action: str, entity_id: str,
        before: dict[str, Any] | None, after: dict[str, Any] | None, now: datetime,
    ) -> None:
        session.add(AuditLogRow(
            id=str(uuid4()), organization_id=organization_id, actor=actor, action=action,
            entity_type="drilling_passport", entity_id=entity_id,
            before_payload=before, after_payload=after, created_at=now,
        ))
