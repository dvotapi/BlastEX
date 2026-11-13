"""PostgreSQL persistence for immutable mass-blast project revisions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, desc, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from cost.v2.db_repository import AuditLogRow, Base, JsonType, SCHEMA
from design.mass_blast import normalize_account_email, role_signers


class MassBlastRepositoryError(RuntimeError):
    pass


class MassBlastNotFoundError(MassBlastRepositoryError):
    pass


class MassBlastConflictError(MassBlastRepositoryError):
    pass


class MassBlastForbiddenError(MassBlastRepositoryError):
    pass


class MassBlastProjectRow(Base):
    __tablename__ = "mass_blast_projects"
    __table_args__ = (
        Index("ix_mass_blast_project_org_updated", "organization_id", "updated_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    site_code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    blast_date: Mapped[str] = mapped_column(String(10), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class MassBlastRevisionRow(Base):
    __tablename__ = "mass_blast_project_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision_no", name="uq_mass_blast_revision_no"),
        Index("ix_mass_blast_revision_project", "project_id", "revision_no"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_projects.id", ondelete="RESTRICT"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    reference_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    technical_formula_version: Mapped[str] = mapped_column(String(80), nullable=False)
    document_template_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    technical_snapshots: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    document_context: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)


class MassBlastBlockRow(Base):
    __tablename__ = "mass_blast_project_blocks"
    __table_args__ = (
        UniqueConstraint("revision_id", "sequence_no", name="uq_mass_blast_block_sequence"),
        Index("ix_mass_blast_block_design", "design_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    design_id: Mapped[str] = mapped_column(String(120), nullable=False)
    design_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    design_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    technical_passport_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.technical_passports.id", ondelete="RESTRICT"), nullable=True
    )
    block_code: Mapped[str] = mapped_column(String(120), nullable=False)
    horizon: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    object_name: Mapped[str] = mapped_column(String(300), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class MassBlastAttachmentRow(Base):
    __tablename__ = "mass_blast_attachments"
    __table_args__ = (Index("ix_mass_blast_attachment_project", "project_id", "created_at"), {"schema": SCHEMA})

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_projects.id", ondelete="RESTRICT"), nullable=False
    )
    revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)


class MassBlastDocumentRow(Base):
    __tablename__ = "mass_blast_documents"
    __table_args__ = (
        UniqueConstraint("revision_id", "kind", "format", name="uq_mass_blast_document_revision_kind"),
        Index("ix_mass_blast_document_revision", "revision_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    template_version: Mapped[str] = mapped_column(String(80), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)


class MassBlastApprovalRow(Base):
    __tablename__ = "mass_blast_approvals"
    __table_args__ = (
        UniqueConstraint("revision_id", "role_code", "actor", name="uq_mass_blast_approval_actor"),
        Index("ix_mass_blast_approval_revision", "revision_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    role_code: Mapped[str] = mapped_column(String(80), nullable=False)
    actor: Mapped[str] = mapped_column(String(320), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MassBlastLayerRow(Base):
    """Слой дня взрыва (TASK-018, PR 2): наряд-путёвка, уведомление, акты, талон."""

    __tablename__ = "mass_blast_layers"
    __table_args__ = (Index("ix_mass_blast_layer_project", "project_id", "kind"), {"schema": SCHEMA})

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_projects.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    project_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    seed: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)


class MassBlastLayerRevisionRow(Base):
    __tablename__ = "mass_blast_layer_revisions"
    __table_args__ = (
        UniqueConstraint("layer_id", "revision_no", name="uq_mass_blast_layer_revision_no"),
        Index("ix_mass_blast_layer_revision_layer", "layer_id", "revision_no"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    layer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_layers.id", ondelete="RESTRICT"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    project_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    context: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)


class MassBlastMagexVersionRow(Base):
    """Версия выписки наряда-путёвки в MagEX (TASK-018, PR 7)."""

    __tablename__ = "mass_blast_magex_versions"
    __table_args__ = (
        UniqueConstraint("layer_id", "ver", name="uq_mass_blast_magex_version"),
        Index("ix_mass_blast_magex_version_due", "status", "next_attempt_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    layer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_layers.id", ondelete="RESTRICT"), nullable=False
    )
    ver: Mapped[int] = mapped_column(Integer, nullable=False)
    layer_revision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_layer_revisions.id", ondelete="SET NULL"), nullable=True
    )
    jws: Mapped[str] = mapped_column(Text, nullable=False)
    kid: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MassBlastMagexNaryadRow(Base):
    """Последнее прочитанное исполнение наряда в MagEX (TASK-018, PR 7)."""

    __tablename__ = "mass_blast_magex_naryads"
    __table_args__ = {"schema": SCHEMA}

    layer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.mass_blast_layers.id", ondelete="RESTRICT"), primary_key=True
    )
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    execution: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _printable(context: dict[str, Any] | None, statuses: dict[int, str]) -> bool:
    """Ревизия слоя печатается: она без MagEX или её версия выписки принята MagEX."""

    magex = (context or {}).get("magex") or {}
    return magex.get("mode") != "ONLINE" or statuses.get(magex.get("ver")) == "ACCEPTED"


# Сколько «Разрешить» считается идущим (версия SENDING): дольше — процесс упал, версия заменима.
MAGEX_SENDING_GUARD_S = 120


class PostgresMassBlastRepository:
    """Storage with organization checks and optimistic locking for drafts."""

    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True, future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    @staticmethod
    def _summary(row: MassBlastProjectRow) -> dict[str, Any]:
        payload = dict(row.payload or {})
        return {
            "id": row.id,
            "name": row.name,
            "site_code": row.site_code,
            "object_name": str(payload.get("object_name", "")),
            "blast_date": row.blast_date,
            "lifecycle_status": row.lifecycle_status,
            "version": row.version,
            "current_revision_id": row.current_revision_id,
            "block_design_ids": [
                str(item.get("design_id", ""))
                for item in (payload.get("blocks") or [])
                if str(item.get("design_id", ""))
            ],
            "updated_at": row.updated_at.isoformat(),
        }

    @staticmethod
    def _project(row: MassBlastProjectRow) -> dict[str, Any]:
        payload = dict(row.payload or {})
        return {
            **PostgresMassBlastRepository._summary(row),
            **payload,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
            "updated_by": row.updated_by,
        }

    @staticmethod
    def _revision(row: MassBlastRevisionRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "revision_no": row.revision_no,
            "previous_revision_id": row.previous_revision_id,
            "reference_revision_id": row.reference_revision_id,
            "technical_formula_version": row.technical_formula_version,
            "document_template_version": row.document_template_version,
            "content_sha256": row.content_sha256,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
            "context": dict(row.document_context or {}),
        }

    def list_projects(self, organization_id: str) -> Sequence[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(MassBlastProjectRow)
                .where(MassBlastProjectRow.organization_id == organization_id)
                .order_by(desc(MassBlastProjectRow.updated_at))
            ).all()
            return tuple(self._summary(row) for row in rows)

    def get_project(self, organization_id: str, project_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.get(MassBlastProjectRow, project_id)
            if row is None or row.organization_id != organization_id:
                raise MassBlastNotFoundError(f"Проект массового взрыва {project_id} не найден.")
            return self._project(row)

    def create_project(self, organization_id: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        project_id = str(uuid4())
        with self.session_factory() as session, session.begin():
            row = MassBlastProjectRow(
                id=project_id,
                organization_id=organization_id,
                site_code=str(payload["site_code"]),
                name=str(payload["name"]),
                blast_date=str(payload["blast_date"]),
                lifecycle_status="draft",
                version=1,
                payload=payload,
                created_at=now,
                created_by=actor,
                updated_at=now,
                updated_by=actor,
            )
            session.add(row)
            self._audit(session, organization_id, actor, "CREATE_MASS_BLAST_PROJECT", project_id, None, payload, now)
        return self.get_project(organization_id, project_id)

    def update_project(
        self, organization_id: str, actor: str, project_id: str, payload: dict[str, Any], expected_version: int
    ) -> dict[str, Any]:
        now = _now()
        with self.session_factory() as session, session.begin():
            row = session.scalar(select(MassBlastProjectRow).where(MassBlastProjectRow.id == project_id).with_for_update())
            if row is None or row.organization_id != organization_id:
                raise MassBlastNotFoundError(f"Проект массового взрыва {project_id} не найден.")
            if row.version != expected_version:
                raise MassBlastConflictError("Проект изменён другим пользователем. Обновите данные перед сохранением.")
            if row.lifecycle_status != "draft":
                raise MassBlastConflictError("Редактировать состав можно только в статусе «черновик». Создайте новую ревизию после возврата в черновик.")
            before = dict(row.payload or {})
            row.site_code = str(payload["site_code"])
            row.name = str(payload["name"])
            row.blast_date = str(payload["blast_date"])
            row.payload = payload
            row.version += 1
            row.updated_at = now
            row.updated_by = actor
            self._audit(session, organization_id, actor, "UPDATE_MASS_BLAST_PROJECT", project_id, before, payload, now)
        return self.get_project(organization_id, project_id)

    def create_revision(
        self,
        organization_id: str,
        actor: str,
        project_id: str,
        expected_version: int,
        reference_revision_id: str,
        context: dict[str, Any],
        blocks: list[dict[str, Any]],
        technical_formula_version: str,
        document_template_version: str,
        content_sha256: str,
    ) -> dict[str, Any]:
        now = _now()
        revision_id = str(uuid4())
        with self.session_factory() as session, session.begin():
            project = session.scalar(select(MassBlastProjectRow).where(MassBlastProjectRow.id == project_id).with_for_update())
            if project is None or project.organization_id != organization_id:
                raise MassBlastNotFoundError(f"Проект массового взрыва {project_id} не найден.")
            if project.version != expected_version:
                raise MassBlastConflictError("Проект изменён другим пользователем. Обновите данные перед выпуском ревизии.")
            if project.lifecycle_status != "draft":
                raise MassBlastConflictError("Ревизию можно выпустить только из черновика.")
            previous = session.scalar(
                select(MassBlastRevisionRow)
                .where(MassBlastRevisionRow.project_id == project_id)
                .order_by(desc(MassBlastRevisionRow.revision_no))
                .limit(1)
            )
            revision = MassBlastRevisionRow(
                id=revision_id,
                project_id=project_id,
                revision_no=(previous.revision_no + 1) if previous else 1,
                previous_revision_id=previous.id if previous else None,
                reference_revision_id=reference_revision_id,
                technical_formula_version=technical_formula_version,
                document_template_version=document_template_version,
                input_snapshot=dict(project.payload or {}),
                technical_snapshots={"blocks": blocks},
                document_context=context,
                content_sha256=content_sha256,
                created_at=now,
                created_by=actor,
            )
            session.add(revision)
            session.flush()
            for sequence_no, block in enumerate(blocks, start=1):
                session.add(
                    MassBlastBlockRow(
                        id=str(uuid4()),
                        revision_id=revision_id,
                        sequence_no=sequence_no,
                        design_id=str(block["design_id"]),
                        design_revision=int(block["design_revision"]),
                        design_sha256=str(block["design_sha256"]),
                        technical_passport_id=block.get("technical_passport_id") or None,
                        block_code=str(block.get("code", "")),
                        horizon=str(block.get("horizon", "")),
                        object_name=str(block.get("object_name", "")),
                        snapshot=dict(block.get("snapshot") or {}),
                    )
                )
            for attachment in session.scalars(
                select(MassBlastAttachmentRow).where(
                    MassBlastAttachmentRow.project_id == project_id,
                    MassBlastAttachmentRow.revision_id.is_(None),
                )
            ).all():
                attachment.revision_id = revision_id
            project.current_revision_id = revision_id
            project.lifecycle_status = "in_review"
            project.version += 1
            project.updated_at = now
            project.updated_by = actor
            self._audit(session, organization_id, actor, "CREATE_MASS_BLAST_REVISION", revision_id, None, context, now)
        return self.get_revision(organization_id, revision_id)

    def get_revision(self, organization_id: str, revision_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.get(MassBlastRevisionRow, revision_id)
            if row is None or not self._revision_belongs_to_org(session, row, organization_id):
                raise MassBlastNotFoundError(f"Ревизия проекта массового взрыва {revision_id} не найдена.")
            return self._revision(row)

    def list_documents(self, organization_id: str, project_id: str) -> Sequence[dict[str, Any]]:
        with self.session_factory() as session:
            self._project_row(session, organization_id, project_id)
            rows = session.execute(
                select(MassBlastDocumentRow)
                .join(MassBlastRevisionRow, MassBlastDocumentRow.revision_id == MassBlastRevisionRow.id)
                .where(MassBlastRevisionRow.project_id == project_id)
                .order_by(desc(MassBlastDocumentRow.created_at))
            ).scalars().all()
            return tuple(self._document(row) for row in rows)

    def list_attachments(self, organization_id: str, project_id: str) -> Sequence[dict[str, Any]]:
        with self.session_factory() as session:
            self._project_row(session, organization_id, project_id)
            rows = session.scalars(
                select(MassBlastAttachmentRow)
                .where(MassBlastAttachmentRow.project_id == project_id)
                .order_by(desc(MassBlastAttachmentRow.created_at))
            ).all()
            return tuple(self._attachment(row) for row in rows)

    def list_draft_attachments(self, organization_id: str, project_id: str) -> Sequence[dict[str, Any]]:
        """Return only attachments that will be frozen into the next revision."""

        with self.session_factory() as session:
            self._project_row(session, organization_id, project_id)
            rows = session.scalars(
                select(MassBlastAttachmentRow)
                .where(
                    MassBlastAttachmentRow.project_id == project_id,
                    MassBlastAttachmentRow.revision_id.is_(None),
                )
                .order_by(desc(MassBlastAttachmentRow.created_at))
            ).all()
            return tuple(self._attachment(row) for row in rows)

    def save_attachment(
        self, organization_id: str, actor: str, project_id: str, *, kind: str, filename: str,
        mime_type: str, byte_size: int, storage_key: str, sha256: str,
    ) -> dict[str, Any]:
        now = _now()
        with self.session_factory() as session, session.begin():
            project = self._project_row(session, organization_id, project_id)
            if project.lifecycle_status != "draft":
                raise MassBlastConflictError("Вложения можно менять только в статусе «черновик».")
            row = MassBlastAttachmentRow(
                id=str(uuid4()), project_id=project_id, revision_id=None, kind=kind, filename=filename,
                mime_type=mime_type, byte_size=byte_size, storage_key=storage_key, sha256=sha256,
                metadata_payload={}, created_at=now, created_by=actor,
            )
            session.add(row)
            session.flush()
            result = self._attachment(row)
            self._audit(session, organization_id, actor, "UPLOAD_MASS_BLAST_ATTACHMENT", row.id, None, result, now)
            return result

    def delete_attachment(self, organization_id: str, actor: str, project_id: str, attachment_id: str) -> str:
        now = _now()
        with self.session_factory() as session, session.begin():
            project = self._project_row(session, organization_id, project_id)
            row = session.get(MassBlastAttachmentRow, attachment_id)
            if row is None or row.project_id != project_id:
                raise MassBlastNotFoundError(f"Вложение {attachment_id} не найдено.")
            if project.lifecycle_status != "draft" or row.revision_id is not None:
                raise MassBlastConflictError("Выпущенное вложение удалить нельзя.")
            storage_key = row.storage_key
            before = self._attachment(row)
            session.delete(row)
            self._audit(session, organization_id, actor, "DELETE_MASS_BLAST_ATTACHMENT", attachment_id, before, None, now)
            return storage_key

    def get_document(self, organization_id: str, document_id: str) -> tuple[dict[str, Any], str]:
        with self.session_factory() as session:
            row = session.get(MassBlastDocumentRow, document_id)
            if row is None:
                raise MassBlastNotFoundError(f"Документ {document_id} не найден.")
            revision = session.get(MassBlastRevisionRow, row.revision_id)
            if revision is None or not self._revision_belongs_to_org(session, revision, organization_id):
                raise MassBlastNotFoundError(f"Документ {document_id} не найден.")
            return self._document(row), revision.project_id

    def get_attachment(self, organization_id: str, project_id: str, attachment_id: str) -> tuple[dict[str, Any], str]:
        with self.session_factory() as session:
            self._project_row(session, organization_id, project_id)
            row = session.get(MassBlastAttachmentRow, attachment_id)
            if row is None or row.project_id != project_id:
                raise MassBlastNotFoundError(f"Вложение {attachment_id} не найдено.")
            return self._attachment(row), row.storage_key

    def save_document(
        self,
        organization_id: str,
        actor: str,
        revision_id: str,
        *,
        kind: str,
        format: str,
        template_version: str,
        filename: str,
        storage_key: str,
        sha256: str,
        byte_size: int,
    ) -> dict[str, Any]:
        now = _now()
        with self.session_factory() as session, session.begin():
            revision = session.get(MassBlastRevisionRow, revision_id)
            if revision is None or not self._revision_belongs_to_org(session, revision, organization_id):
                raise MassBlastNotFoundError(f"Ревизия проекта массового взрыва {revision_id} не найдена.")
            project = session.get(MassBlastProjectRow, revision.project_id)
            assert project is not None
            if project.lifecycle_status not in {"approved", "executed", "closed"}:
                raise MassBlastConflictError("Документы выпускаются только после утверждения ревизии.")
            row = session.scalar(
                select(MassBlastDocumentRow).where(
                    MassBlastDocumentRow.revision_id == revision_id,
                    MassBlastDocumentRow.kind == kind,
                    MassBlastDocumentRow.format == format,
                )
            )
            if row is not None:
                return self._document(row)
            row = MassBlastDocumentRow(
                id=str(uuid4()), revision_id=revision_id, kind=kind, format=format,
                template_version=template_version, filename=filename, storage_key=storage_key,
                sha256=sha256, byte_size=byte_size, created_at=now, created_by=actor,
            )
            session.add(row)
            self._audit(session, organization_id, actor, "GENERATE_MASS_BLAST_DOCUMENT", row.id, None, self._document(row), now)
            session.flush()
            return self._document(row)

    def approve_revision(
        self, organization_id: str, actor: str, revision_id: str, role_code: str, decision: str, comment: str
    ) -> dict[str, Any]:
        now = _now()
        with self.session_factory() as session, session.begin():
            revision = session.get(MassBlastRevisionRow, revision_id)
            if revision is None or not self._revision_belongs_to_org(session, revision, organization_id):
                raise MassBlastNotFoundError(f"Ревизия проекта массового взрыва {revision_id} не найдена.")
            signers = self._signers(revision)
            if role_code not in signers:
                raise MassBlastConflictError(f"Роль «{role_code}» не назначена в этой ревизии.")
            if normalize_account_email(actor) != signers[role_code]:
                raise MassBlastForbiddenError(
                    f"Согласовать роль «{role_code}» может только назначенная учётка {signers[role_code]}."
                )
            row = session.scalar(select(MassBlastApprovalRow).where(
                MassBlastApprovalRow.revision_id == revision_id,
                MassBlastApprovalRow.role_code == role_code,
                MassBlastApprovalRow.actor == actor,
            ))
            if row is None:
                row = MassBlastApprovalRow(
                    id=str(uuid4()), revision_id=revision_id, role_code=role_code, actor=actor,
                    decision=decision, comment=comment, content_sha256=revision.content_sha256, created_at=now,
                )
                session.add(row)
            else:
                row.decision = decision
                row.comment = comment
                row.content_sha256 = revision.content_sha256
                row.created_at = now
            session.flush()
            result = self._approval(row)
            self._audit(session, organization_id, actor, "APPROVE_MASS_BLAST_REVISION", row.id, None, result, now)
            return result

    def transition_project(
        self, organization_id: str, actor: str, project_id: str, to_status: str, expected_version: int, note: str
    ) -> dict[str, Any]:
        allowed = {
            "draft": {"in_review"}, "in_review": {"draft", "approved"}, "approved": {"executed"},
            "executed": {"closed"}, "closed": set(),
        }
        now = _now()
        with self.session_factory() as session, session.begin():
            row = session.scalar(select(MassBlastProjectRow).where(MassBlastProjectRow.id == project_id).with_for_update())
            if row is None or row.organization_id != organization_id:
                raise MassBlastNotFoundError(f"Проект массового взрыва {project_id} не найден.")
            if row.version != expected_version:
                raise MassBlastConflictError("Проект изменён другим пользователем. Обновите данные перед сменой статуса.")
            if to_status not in allowed.get(row.lifecycle_status, set()):
                raise MassBlastConflictError(f"Переход из «{row.lifecycle_status}» в «{to_status}» недопустим.")
            if to_status == "approved" and not row.current_revision_id:
                raise MassBlastConflictError("Нельзя утвердить проект без выпущенной ревизии.")
            if to_status == "approved":
                revision = session.get(MassBlastRevisionRow, row.current_revision_id)
                assert revision is not None
                signers = self._signers(revision)
                approved = {
                    (role_code, normalize_account_email(approver))
                    for role_code, approver in session.execute(
                        select(MassBlastApprovalRow.role_code, MassBlastApprovalRow.actor).where(
                            MassBlastApprovalRow.revision_id == revision.id,
                            MassBlastApprovalRow.decision == "approved",
                            MassBlastApprovalRow.content_sha256 == revision.content_sha256,
                        )
                    ).all()
                }
                missing_roles = {role_code for role_code, email in signers.items() if (role_code, email) not in approved}
                if missing_roles:
                    raise MassBlastConflictError(
                        "Для утверждения нужны согласования ролей: " + ", ".join(sorted(missing_roles)) + "."
                    )
            before = {"lifecycle_status": row.lifecycle_status, "version": row.version}
            row.lifecycle_status = to_status
            row.version += 1
            row.updated_at = now
            row.updated_by = actor
            self._audit(session, organization_id, actor, "TRANSITION_MASS_BLAST_PROJECT", project_id, before, {"to_status": to_status, "note": note}, now)
        return self.get_project(organization_id, project_id)

    @staticmethod
    def _document(row: MassBlastDocumentRow) -> dict[str, Any]:
        return {
            "id": row.id, "revision_id": row.revision_id, "kind": row.kind, "format": row.format,
            "filename": row.filename, "sha256": row.sha256, "created_at": row.created_at.isoformat(),
        }

    @staticmethod
    def _attachment(row: MassBlastAttachmentRow) -> dict[str, Any]:
        return {
            "id": row.id, "project_id": row.project_id, "revision_id": row.revision_id, "kind": row.kind,
            "filename": row.filename, "mime_type": row.mime_type, "byte_size": row.byte_size,
            "sha256": row.sha256, "created_at": row.created_at.isoformat(), "created_by": row.created_by,
        }

    @staticmethod
    def _approval(row: MassBlastApprovalRow) -> dict[str, Any]:
        return {
            "id": row.id, "revision_id": row.revision_id, "role_code": row.role_code, "actor": row.actor,
            "decision": row.decision, "comment": row.comment, "content_sha256": row.content_sha256,
            "created_at": row.created_at.isoformat(),
        }

    @staticmethod
    def _signers(revision: MassBlastRevisionRow) -> dict[str, str]:
        """Accounts frozen in the revision: the approver of a role is who the document names."""
        try:
            return role_signers(revision.document_context or {})
        except ValueError as exc:
            raise MassBlastConflictError(
                f"{exc} Верните проект в черновик, назначьте учётки и выпустите ревизию заново."
            ) from exc

    # --- слои дня взрыва (TASK-018, PR 2) ---------------------------------

    @staticmethod
    def _layer(row: MassBlastLayerRow, project_revision_id: str | None) -> dict[str, Any]:
        return {
            "id": row.id,
            "project_id": row.project_id,
            "kind": row.kind,
            "project_revision_id": row.project_revision_id,
            "status": row.status,
            "version": row.version,
            "current_revision_id": row.current_revision_id,
            "seed": dict(row.seed or {}),
            "payload": dict(row.payload or {}),
            # Слой основан не на текущей ревизии проекта — данные проекта могли измениться.
            "stale": project_revision_id is not None and row.project_revision_id != project_revision_id,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
            "updated_at": row.updated_at.isoformat(),
            "updated_by": row.updated_by,
        }

    @staticmethod
    def _layer_revision(row: MassBlastLayerRevisionRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "layer_id": row.layer_id,
            "revision_no": row.revision_no,
            "project_revision_id": row.project_revision_id,
            "content_sha256": row.content_sha256,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
            "context": dict(row.context or {}),
        }

    def _layer_row(self, session: Session, organization_id: str, layer_id: str, *, lock: bool = False) -> MassBlastLayerRow:
        query = select(MassBlastLayerRow).where(MassBlastLayerRow.id == layer_id)
        row = session.scalar(query.with_for_update() if lock else query)
        if row is None or row.organization_id != organization_id:
            raise MassBlastNotFoundError(f"Слой проекта массового взрыва {layer_id} не найден.")
        return row

    def list_layers(self, organization_id: str, project_id: str) -> Sequence[dict[str, Any]]:
        with self.session_factory() as session:
            project = self._project_row(session, organization_id, project_id)
            rows = session.scalars(
                select(MassBlastLayerRow)
                .where(MassBlastLayerRow.project_id == project_id)
                .order_by(MassBlastLayerRow.kind, MassBlastLayerRow.created_at)
            ).all()
            return tuple(self._layer(row, project.current_revision_id) for row in rows)

    def get_layer(self, organization_id: str, layer_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = self._layer_row(session, organization_id, layer_id)
            project = session.get(MassBlastProjectRow, row.project_id)
            return self._layer(row, project.current_revision_id if project else None)

    def create_layer(
        self, organization_id: str, actor: str, project_id: str, *, kind: str, project_revision_id: str,
        allowed_statuses: set[str], single: bool, seed: dict[str, Any], payload: dict[str, Any],
        unique_payload_key: str | None = None,
    ) -> dict[str, Any]:
        """Новый слой. `unique_payload_key` — поле payload, непустое значение которого у слоёв
        этого вида не повторяется (адресат уведомления); проверка — под блокировкой проекта."""

        now = _now()
        with self.session_factory() as session, session.begin():
            project = session.scalar(
                select(MassBlastProjectRow).where(MassBlastProjectRow.id == project_id).with_for_update()
            )
            if project is None or project.organization_id != organization_id:
                raise MassBlastNotFoundError(f"Проект массового взрыва {project_id} не найден.")
            if project.lifecycle_status not in allowed_statuses or project.current_revision_id != project_revision_id:
                raise MassBlastConflictError("Проект изменился: обновите его и откройте слой заново.")
            if single and session.scalar(
                select(MassBlastLayerRow.id).where(MassBlastLayerRow.project_id == project_id, MassBlastLayerRow.kind == kind)
            ):
                raise MassBlastConflictError("Такой слой у проекта уже есть.")
            value = str(payload.get(unique_payload_key) or "") if unique_payload_key else ""
            if value and any(
                str((other.payload or {}).get(unique_payload_key) or "") == value
                for other in session.scalars(
                    select(MassBlastLayerRow).where(MassBlastLayerRow.project_id == project_id, MassBlastLayerRow.kind == kind)
                )
            ):
                raise MassBlastConflictError("Такой слой этому адресату у проекта уже есть: на адресата — один.")
            row = MassBlastLayerRow(
                id=str(uuid4()), organization_id=organization_id, project_id=project_id, kind=kind,
                project_revision_id=project_revision_id, status="draft", version=1, current_revision_id=None,
                seed=seed, payload=payload, created_at=now, created_by=actor, updated_at=now, updated_by=actor,
            )
            session.add(row)
            self._audit(session, organization_id, actor, "CREATE_MASS_BLAST_LAYER", project_id, None, {"layer_id": row.id, "kind": kind}, now)
        return self.get_layer(organization_id, row.id)

    def update_layer(
        self, organization_id: str, actor: str, layer_id: str, *, expected_version: int,
        payload: dict[str, Any] | None = None, seed: dict[str, Any] | None = None, project_revision_id: str | None = None,
    ) -> dict[str, Any]:
        """Правка введённого вручную или повторный перенос данных проекта (`seed`)."""

        now = _now()
        with self.session_factory() as session, session.begin():
            row = self._layer_row(session, organization_id, layer_id, lock=True)
            if row.version != expected_version:
                raise MassBlastConflictError("Слой изменён другим пользователем. Обновите данные.")
            before = {"version": row.version, "project_revision_id": row.project_revision_id}
            if payload is not None:
                row.payload = payload
            if seed is not None:
                row.seed = seed
            if project_revision_id is not None:
                row.project_revision_id = project_revision_id
            row.version += 1
            row.updated_at = now
            row.updated_by = actor
            self._audit(session, organization_id, actor, "UPDATE_MASS_BLAST_LAYER", row.project_id, before, {"layer_id": layer_id, "refresh": seed is not None}, now)
        return self.get_layer(organization_id, layer_id)

    def get_layer_revision(self, organization_id: str, revision_id: str) -> dict[str, Any]:
        """Ревизия слоя (печать документа дня взрыва, PR 3) вместе с видом слоя."""

        with self.session_factory() as session:
            revision = session.get(MassBlastLayerRevisionRow, revision_id)
            if revision is None:
                raise MassBlastNotFoundError(f"Ревизия слоя {revision_id} не найдена.")
            row = self._layer_row(session, organization_id, revision.layer_id)
            return {**self._layer_revision(revision), "kind": row.kind, "project_id": row.project_id}

    def latest_layer_revision(self, organization_id: str, layer_id: str, project_revision_id: str) -> dict[str, Any] | None:
        """Последняя выпущенная ревизия слоя на заданной ревизии проекта (PACKAGE, PR 3)."""

        with self.session_factory() as session:
            row = self._layer_row(session, organization_id, layer_id)
            revision = session.scalar(
                select(MassBlastLayerRevisionRow)
                .where(
                    MassBlastLayerRevisionRow.layer_id == layer_id,
                    MassBlastLayerRevisionRow.project_revision_id == project_revision_id,
                )
                .order_by(desc(MassBlastLayerRevisionRow.revision_no))
                .limit(1)
            )
            if revision is None:
                return None
            return {**self._layer_revision(revision), "kind": row.kind, "project_id": row.project_id}

    def create_layer_revision(
        self, organization_id: str, actor: str, layer_id: str, *, expected_version: int,
        context: dict[str, Any], content_sha256: str,
        magex_activation: tuple[str, datetime] | None = None,
    ) -> dict[str, Any]:
        """Ревизия слоя. `magex_activation` — (версия выписки, срок попытки): версия встаёт в очередь
        с этой ревизией в той же транзакции (TASK-018 PR 7) — упавший процесс не оставит ревизию
        без версии в очереди."""

        now = _now()
        with self.session_factory() as session, session.begin():
            row = self._layer_row(session, organization_id, layer_id, lock=True)
            if row.version != expected_version:
                raise MassBlastConflictError("Слой изменён другим пользователем. Обновите данные перед выпуском.")
            latest = session.scalar(
                select(MassBlastLayerRevisionRow)
                .where(MassBlastLayerRevisionRow.layer_id == layer_id)
                .order_by(desc(MassBlastLayerRevisionRow.revision_no))
                .limit(1)
            )
            revision = MassBlastLayerRevisionRow(
                id=str(uuid4()), layer_id=layer_id, revision_no=(latest.revision_no + 1) if latest else 1,
                project_revision_id=row.project_revision_id, context=context, content_sha256=content_sha256,
                created_at=now, created_by=actor,
            )
            session.add(revision)
            row.status = "issued"
            row.current_revision_id = revision.id
            row.version += 1
            row.updated_at = now
            row.updated_by = actor
            self._audit(session, organization_id, actor, "ISSUE_MASS_BLAST_LAYER", row.project_id, None, {"layer_id": layer_id, "revision_id": revision.id}, now)
            if magex_activation is not None:
                session.flush()
                self._activate(session, magex_activation[0], revision.id, magex_activation[1], now)
            return self._layer_revision(revision)

    def discard_layer_revision(self, organization_id: str, actor: str, layer_id: str, revision_id: str) -> dict[str, Any]:
        """Убрать ревизию наряда, которую MagEX отклонил (TASK-018, PR 7, §5.2): как и в MagEX,
        отказ ничего не оставляет. Текущей становится прежняя ревизия слоя (или слой — черновик)."""

        now = _now()
        with self.session_factory() as session, session.begin():
            row = self._layer_row(session, organization_id, layer_id, lock=True)
            revision = session.get(MassBlastLayerRevisionRow, revision_id)
            if revision is None or revision.layer_id != layer_id:
                raise MassBlastNotFoundError(f"Ревизия слоя {revision_id} не найдена.")
            for version in session.scalars(
                select(MassBlastMagexVersionRow).where(MassBlastMagexVersionRow.layer_revision_id == revision_id)
            ):
                version.layer_revision_id = None
            session.flush()
            session.delete(revision)
            session.flush()
            if row.current_revision_id == revision_id:
                # Текущей — последняя ревизия, которую можно печатать: без MagEX или с принятой
                # версией (ревизия заменённой или ожидающей версии — нет, замечание Codex).
                statuses = {
                    item.ver: item.status
                    for item in session.scalars(select(MassBlastMagexVersionRow).where(MassBlastMagexVersionRow.layer_id == layer_id))
                }
                previous = next(
                    (
                        item for item in session.scalars(
                            select(MassBlastLayerRevisionRow)
                            .where(MassBlastLayerRevisionRow.layer_id == layer_id)
                            .order_by(desc(MassBlastLayerRevisionRow.revision_no))
                        )
                        if _printable(item.context, statuses)
                    ),
                    None,
                )
                row.current_revision_id = previous.id if previous else None
                row.status = "issued" if previous else "draft"
            row.version += 1
            row.updated_at = now
            row.updated_by = actor
            self._audit(
                session, organization_id, actor, "DISCARD_MASS_BLAST_LAYER_REVISION", row.project_id, None,
                {"layer_id": layer_id, "revision_id": revision_id}, now,
            )
        return self.get_layer(organization_id, layer_id)

    # --- MagEX: версии выписки и исполнение (TASK-018, PR 7) ----------------

    @staticmethod
    def _magex_version(row: MassBlastMagexVersionRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "layer_id": row.layer_id,
            "ver": row.ver,
            "layer_revision_id": row.layer_revision_id,
            "jws": row.jws,
            "kid": row.kid,
            "payload_sha256": row.payload_sha256,
            "status": row.status,
            "response_code": row.response_code,
            "response": dict(row.response or {}),
            "attempts": row.attempts,
            "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
            "updated_at": row.updated_at.isoformat(),
            "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
            "organization_id": row.organization_id,
        }

    def create_magex_version(
        self, organization_id: str, actor: str, layer_id: str, build: Any, *, expected_version: int | None = None,
    ) -> dict[str, Any]:
        """Новая версия выписки (`SENDING`): `ver` — наибольшая в слое + 1 под блокировкой слоя (два
        нажатия не получат один номер); `build(ver)` подписывает и возвращает `(jws, kid, payload_sha256)`.

        Прежние версии здесь не заменяются — только `activate_magex_version`, когда у новой есть
        ревизия слоя: сорвавшийся выпуск не снимает из очереди принятую к отправке версию. Слой
        изменён (`expected_version`) или другое «Разрешить» ещё отправляется — конфликт.
        """

        now = _now()
        with self.session_factory() as session, session.begin():
            layer = self._layer_row(session, organization_id, layer_id, lock=True)
            if expected_version is not None and layer.version != expected_version:
                raise MassBlastConflictError("Слой изменён другим пользователем. Обновите данные.")
            rows = session.scalars(
                select(MassBlastMagexVersionRow).where(MassBlastMagexVersionRow.layer_id == layer_id)
            ).all()
            if any(item.status == "SENDING" and item.updated_at > now - timedelta(seconds=MAGEX_SENDING_GUARD_S) for item in rows):
                raise MassBlastConflictError("Разрешение этой наряд-путёвки уже отправляется в MagEX: обновите окно.")
            ver = max((item.ver for item in rows), default=0) + 1
            jws, kid, payload_sha256 = build(ver)
            row = MassBlastMagexVersionRow(
                id=str(uuid4()), organization_id=organization_id, layer_id=layer_id, ver=ver, layer_revision_id=None,
                jws=jws, kid=kid, payload_sha256=payload_sha256, status="SENDING", response_code=None, response={},
                attempts=0, next_attempt_at=None, created_at=now, created_by=actor, updated_at=now, accepted_at=None,
            )
            session.add(row)
            session.flush()
            return self._magex_version(row)

    def _activate(self, session: Session, version_id: str, layer_revision_id: str, next_attempt_at: datetime, now: datetime) -> MassBlastMagexVersionRow:
        row = session.get(MassBlastMagexVersionRow, version_id, with_for_update=True)
        if row is None:
            raise MassBlastNotFoundError(f"Версия выписки {version_id} не найдена.")
        for item in session.scalars(
            select(MassBlastMagexVersionRow)
            .where(MassBlastMagexVersionRow.layer_id == row.layer_id, MassBlastMagexVersionRow.id != version_id)
            .with_for_update()
        ):
            if item.status in ("PENDING", "SENDING"):
                item.status = "SUPERSEDED"
                item.next_attempt_at = None
                item.updated_at = now
        row.layer_revision_id = layer_revision_id
        row.status = "PENDING"
        row.next_attempt_at = next_attempt_at
        row.updated_at = now
        return row

    def activate_magex_version(self, version_id: str, layer_revision_id: str, next_attempt_at: datetime) -> dict[str, Any]:
        """Версия с ревизией слоя — в очередь (`PENDING`, срок аренды); прежние ожидающие той же
        наряд-путёвки заменяются ею (`SUPERSEDED`) в той же транзакции."""

        with self.session_factory() as session, session.begin():
            return self._magex_version(self._activate(session, version_id, layer_revision_id, next_attempt_at, _now()))

    def update_magex_version(self, version_id: str, *, only_from: tuple[str, ...] | None = None, **changes: Any) -> dict[str, Any]:
        """Результат отправки: состояние, ответ, ревизия слоя, попытки, срок следующей.

        `only_from` — обновить, только если версия ещё в одном из этих состояний (замену,
        пришедшую во время отправки, ответ отправки не отменяет); иначе — версия как есть."""

        allowed = {"status", "response_code", "response", "layer_revision_id", "attempts", "next_attempt_at", "accepted_at"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Поля версии MagEX не меняются: {sorted(unknown)}")
        with self.session_factory() as session, session.begin():
            row = session.get(MassBlastMagexVersionRow, version_id, with_for_update=True)
            if row is None:
                raise MassBlastNotFoundError(f"Версия выписки {version_id} не найдена.")
            if only_from is not None and row.status not in only_from:
                return self._magex_version(row)
            for key, value in changes.items():
                setattr(row, key, value)
            row.updated_at = _now()
            return self._magex_version(row)

    def list_magex_versions(self, organization_id: str, layer_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            self._layer_row(session, organization_id, layer_id)
            rows = session.scalars(
                select(MassBlastMagexVersionRow)
                .where(MassBlastMagexVersionRow.layer_id == layer_id)
                .order_by(MassBlastMagexVersionRow.ver)
            ).all()
            return [self._magex_version(row) for row in rows]

    def claim_due_magex_versions(self, now: datetime, lease_s: int, limit: int = 20) -> list[dict[str, Any]]:
        """Версии в очереди повтора со сроком попытки: срок сдвигается на `lease_s`
        (`FOR UPDATE SKIP LOCKED` — несколько процессов API не возьмут одну версию)."""

        with self.session_factory() as session, session.begin():
            rows = session.scalars(
                select(MassBlastMagexVersionRow)
                .where(MassBlastMagexVersionRow.status == "PENDING", MassBlastMagexVersionRow.next_attempt_at <= now)
                .order_by(MassBlastMagexVersionRow.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for row in rows:
                row.next_attempt_at = now + timedelta(seconds=lease_s)
            return [self._magex_version(row) for row in rows]

    def save_magex_execution(self, organization_id: str, layer_id: str, execution: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        with self.session_factory() as session, session.begin():
            self._layer_row(session, organization_id, layer_id)
            row = session.get(MassBlastMagexNaryadRow, layer_id, with_for_update=True)
            if row is None:
                row = MassBlastMagexNaryadRow(layer_id=layer_id, organization_id=organization_id, status="", execution={}, fetched_at=now)
                session.add(row)
            row.status = str(execution.get("status") or "")
            row.execution = execution
            row.fetched_at = now
            return {"status": row.status, "execution": dict(row.execution), "fetched_at": now.isoformat()}

    def magex_execution(self, organization_id: str, layer_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.get(MassBlastMagexNaryadRow, layer_id)
            if row is None or row.organization_id != organization_id:
                return None
            return {"status": row.status, "execution": dict(row.execution or {}), "fetched_at": row.fetched_at.isoformat()}

    def magex_keys_in_use(self, organization_id: str) -> list[dict[str, Any]]:
        """`kid`, без которых пока нельзя: принятые версии незакрытых (по последнему известному
        статусу) нарядов и версии в очереди или в отправке — их строки ещё уйдут в MagEX."""

        with self.session_factory() as session:
            rows = session.execute(
                select(
                    MassBlastMagexVersionRow.kid, MassBlastMagexVersionRow.layer_id, MassBlastMagexVersionRow.status,
                    MassBlastMagexNaryadRow.status,
                )
                .join(MassBlastMagexNaryadRow, MassBlastMagexNaryadRow.layer_id == MassBlastMagexVersionRow.layer_id, isouter=True)
                .where(
                    MassBlastMagexVersionRow.organization_id == organization_id,
                    MassBlastMagexVersionRow.status.in_(("ACCEPTED", "PENDING", "SENDING")),
                )
            ).all()
        open_layers: dict[str, set[str]] = {}
        queued: dict[str, int] = {}
        for kid, layer_id, version_status, naryad_status in rows:
            if version_status in ("PENDING", "SENDING"):
                queued[kid] = queued.get(kid, 0) + 1
                continue
            if naryad_status in ("closed", "cancelled"):
                continue
            open_layers.setdefault(kid, set()).add(layer_id)
        return [
            {"kid": kid, "open_naryads": len(open_layers.get(kid, ())), "queued_versions": queued.get(kid, 0)}
            for kid in sorted(set(open_layers) | set(queued))
        ]

    @staticmethod
    def _project_row(session: Session, organization_id: str, project_id: str) -> MassBlastProjectRow:
        row = session.get(MassBlastProjectRow, project_id)
        if row is None or row.organization_id != organization_id:
            raise MassBlastNotFoundError(f"Проект массового взрыва {project_id} не найден.")
        return row

    @staticmethod
    def _revision_belongs_to_org(session: Session, revision: MassBlastRevisionRow, organization_id: str) -> bool:
        project = session.get(MassBlastProjectRow, revision.project_id)
        return project is not None and project.organization_id == organization_id

    @staticmethod
    def _audit(
        session: Session, organization_id: str, actor: str, action: str, entity_id: str,
        before: dict[str, Any] | None, after: dict[str, Any] | None, now: datetime,
    ) -> None:
        session.add(AuditLogRow(
            id=str(uuid4()), organization_id=organization_id, actor=actor, action=action,
            entity_type="mass_blast_project", entity_id=entity_id,
            before_payload=before, after_payload=after, created_at=now,
        ))
