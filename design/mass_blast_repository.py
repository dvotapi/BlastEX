"""PostgreSQL persistence for immutable mass-blast project revisions."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, desc, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from cost.v2.db_repository import AuditLogRow, Base, JsonType, SCHEMA


class MassBlastRepositoryError(RuntimeError):
    pass


class MassBlastNotFoundError(MassBlastRepositoryError):
    pass


class MassBlastConflictError(MassBlastRepositoryError):
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


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


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
                required_roles = {
                    str(item.get("role_code", "")).strip()
                    for item in (row.payload or {}).get("responsibilities", [])
                    if str(item.get("role_code", "")).strip()
                }
                approved_roles = set(session.scalars(
                    select(MassBlastApprovalRow.role_code).where(
                        MassBlastApprovalRow.revision_id == revision.id,
                        MassBlastApprovalRow.decision == "approved",
                        MassBlastApprovalRow.content_sha256 == revision.content_sha256,
                    )
                ).all())
                missing_roles = required_roles - approved_roles
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
