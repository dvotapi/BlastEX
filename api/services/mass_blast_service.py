"""Application service for mass-blast projects.

Only PostgreSQL persists project state.  Existing file-backed BlastDesigns are
read as technical inputs and frozen into revision snapshots.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from api import config
from api.schemas.mass_blast import MassBlastProjectInputSchema
from api.services.economics_service import get_economics_repository
from cost.v2.repository import EconomicsRepository
from design import persistence as design_persistence
from design.mass_blast import (
    MASS_BLAST_FORMULA_VERSION,
    ProjectBlock,
    ValidationIssue,
    block_from_design,
    build_document_context,
    content_sha256,
    has_blocking_issues,
    validate_project_context,
)
from design.mass_blast_rendering import render_pdf, render_xlsx, render_zip
from design.mass_blast_repository import (
    MassBlastConflictError,
    MassBlastNotFoundError,
    PostgresMassBlastRepository,
)


DOCUMENT_TEMPLATE_VERSION = "mass-blast-standard-v1"


@lru_cache(maxsize=4)
def _postgres_repository(database_url: str) -> PostgresMassBlastRepository:
    return PostgresMassBlastRepository(database_url)


def get_mass_blast_repository() -> PostgresMassBlastRepository:
    return _postgres_repository(config.database_url())


def _blocks_from_payload(organization_id: str, payload: dict[str, Any]) -> list[ProjectBlock]:
    blocks: list[ProjectBlock] = []
    for item in payload.get("blocks") or []:
        design_id = str(item.get("design_id", ""))
        try:
            design = design_persistence.load_design(organization_id, design_id)
        except design_persistence.DesignNotFoundError as exc:
            raise ValueError(f"Технический паспорт БВР {design_id} не найден в организации.") from exc
        blocks.append(
            block_from_design(
                design,
                code=str(item.get("code", "")),
                horizon=str(item.get("horizon", "")),
                technical_passport_id=item.get("technical_passport_id") or None,
            )
        )
    return blocks


def _payload_with_snapshots(organization_id: str, payload: MassBlastProjectInputSchema) -> dict[str, Any]:
    data = payload.model_dump(exclude={"expected_version"})
    blocks = _blocks_from_payload(organization_id, data)
    data["blocks"] = [block.to_dict() for block in blocks]
    return data


def _context_from_stored(payload: dict[str, Any]) -> tuple[dict[str, Any], list[ProjectBlock]]:
    blocks = [
        ProjectBlock(
            design_id=str(item["design_id"]),
            design_revision=int(item["design_revision"]),
            design_sha256=str(item["design_sha256"]),
            technical_passport_id=item.get("technical_passport_id") or None,
            code=str(item.get("code", "")),
            horizon=str(item.get("horizon", "")),
            object_name=str(item.get("object_name", "")),
            snapshot=dict(item.get("snapshot") or {}),
        )
        for item in payload.get("blocks") or []
    ]
    return build_document_context(payload, blocks), blocks


def _assert_sources_current(organization_id: str, blocks: list[ProjectBlock]) -> None:
    for block in blocks:
        try:
            current = design_persistence.load_design(organization_id, block.design_id)
        except design_persistence.DesignNotFoundError as exc:
            raise ValueError(f"Источник блока {block.design_id} больше недоступен. Обновите черновик.") from exc
        current_hash = current.designed_sha256
        if current_hash != block.design_sha256:
            raise ValueError(
                f"Источник блока «{block.code or block.design_id}» изменился после добавления в проект. "
                "Вернитесь в черновик, обновите технический снимок и создайте новую ревизию."
            )


def _resolve_reference_revision(
    economics_repository: EconomicsRepository, organization_id: str, requested: str | None
) -> str:
    return economics_repository.get_reference_snapshot(organization_id, requested).revision_id


def create_project(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository,
    organization_id: str,
    actor: str,
    payload: MassBlastProjectInputSchema,
) -> dict[str, Any]:
    stored = _payload_with_snapshots(organization_id, payload)
    stored["reference_revision_id"] = _resolve_reference_revision(
        economics_repository, organization_id, payload.reference_revision_id
    )
    return repository.create_project(organization_id, actor, stored)


def update_project(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository,
    organization_id: str,
    actor: str,
    project_id: str,
    payload: MassBlastProjectInputSchema,
) -> dict[str, Any]:
    if payload.expected_version is None:
        raise ValueError("Для сохранения требуется версия черновика.")
    stored = _payload_with_snapshots(organization_id, payload)
    stored["reference_revision_id"] = _resolve_reference_revision(
        economics_repository, organization_id, payload.reference_revision_id
    )
    return repository.update_project(organization_id, actor, project_id, stored, payload.expected_version)


def validate_project(repository: PostgresMassBlastRepository, organization_id: str, project_id: str, *, require_attachments: bool = False) -> dict[str, Any]:
    project = repository.get_project(organization_id, project_id)
    context, blocks = _context_from_stored(project)
    context["attachments"] = list(repository.list_draft_attachments(organization_id, project_id))
    issues = validate_project_context(context, require_attachments=require_attachments)
    try:
        _assert_sources_current(organization_id, blocks)
    except ValueError as exc:
        issues.append(ValidationIssue("error", "stale_source", str(exc), "blocks"))
    return {"valid": not has_blocking_issues(issues), "issues": [issue.to_dict() for issue in issues], "context": context}


def create_revision(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository,
    organization_id: str,
    actor: str,
    project_id: str,
    expected_version: int,
    *,
    require_attachments: bool = False,
) -> dict[str, Any]:
    project = repository.get_project(organization_id, project_id)
    if project["version"] != expected_version:
        raise MassBlastConflictError("Проект изменён другим пользователем. Обновите данные перед выпуском ревизии.")
    context, blocks = _context_from_stored(project)
    context["attachments"] = list(repository.list_draft_attachments(organization_id, project_id))
    _assert_sources_current(organization_id, blocks)
    issues = validate_project_context(context, require_attachments=require_attachments)
    if has_blocking_issues(issues):
        messages = "; ".join(issue.message for issue in issues if issue.level == "error")
        raise ValueError(f"Ревизию нельзя выпустить: {messages}")
    reference_revision_id = _resolve_reference_revision(
        economics_repository, organization_id, project.get("reference_revision_id")
    )
    context["project"]["reference_revision_id"] = reference_revision_id
    return repository.create_revision(
        organization_id, actor, project_id, expected_version, reference_revision_id, context,
        [block.to_dict() for block in blocks], MASS_BLAST_FORMULA_VERSION,
        DOCUMENT_TEMPLATE_VERSION, content_sha256(context),
    )


def approve_revision(
    repository: PostgresMassBlastRepository, organization_id: str, actor: str, revision_id: str,
    role_code: str, decision: str, comment: str,
) -> dict[str, Any]:
    return repository.approve_revision(organization_id, actor, revision_id, role_code, decision, comment)


def transition_project(
    repository: PostgresMassBlastRepository, organization_id: str, actor: str, project_id: str,
    to_status: str, expected_version: int, confirm: bool, note: str,
) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Подтвердите осознанный перевод статуса.")
    return repository.transition_project(organization_id, actor, project_id, to_status, expected_version, note)


def _document_dir() -> Path:
    root = Path(os.getenv("BLASTEX_MASS_BLAST_DOCUMENT_ROOT", "/app/data/mass_blast_documents")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _attachment_dir() -> Path:
    root = Path(os.getenv("BLASTEX_MASS_BLAST_ATTACHMENT_ROOT", "/app/data/mass_blast_attachments")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


ATTACHMENT_KINDS = {"PLAN", "CHARGING_SCHEME", "DANGER_ZONE", "GUARD_POSTS", "SHOTPLUS_XLSX", "OTHER"}
ALLOWED_ATTACHMENT_SUFFIXES = {".pdf", ".xlsx", ".dxf", ".dwg", ".png", ".jpg", ".jpeg"}
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def upload_attachment(
    repository: PostgresMassBlastRepository, organization_id: str, actor: str, project_id: str,
    *, kind: str, filename: str, content_type: str | None, content: bytes,
) -> dict[str, Any]:
    if kind not in ATTACHMENT_KINDS:
        raise ValueError("Недопустимый вид приложения.")
    original = Path(filename or "attachment").name
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_ATTACHMENT_SUFFIXES:
        raise ValueError("Разрешены PDF, XLSX, DXF, DWG, PNG и JPG приложения.")
    if not content or len(content) > MAX_ATTACHMENT_BYTES:
        raise ValueError("Размер приложения должен быть от 1 байта до 25 МБ.")
    digest = hashlib.sha256(content).hexdigest()
    safe_name = _safe_filename(Path(original).stem) + suffix
    target = _attachment_dir() / project_id / f"{digest[:12]}_{safe_name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if not target.exists():
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        created = True
    try:
        return repository.save_attachment(
            organization_id, actor, project_id, kind=kind, filename=original,
            mime_type=content_type or mimetypes.guess_type(original)[0] or "application/octet-stream",
            byte_size=len(content), storage_key=str(target), sha256=digest,
        )
    except Exception:
        if created and target.exists():
            target.unlink()
        raise


def delete_attachment(
    repository: PostgresMassBlastRepository, organization_id: str, actor: str, project_id: str, attachment_id: str,
) -> None:
    storage_key = repository.delete_attachment(organization_id, actor, project_id, attachment_id)
    path = Path(storage_key).resolve()
    root = _attachment_dir()
    if path.is_relative_to(root) and path.exists():
        path.unlink()


def _safe_filename(value: str) -> str:
    clean = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return clean.strip("_") or "mass_blast"


def generate_document(
    repository: PostgresMassBlastRepository, organization_id: str, actor: str, revision_id: str, kind: str, format: str
) -> dict[str, Any]:
    revision = repository.get_revision(organization_id, revision_id)
    project = repository.get_project(organization_id, revision["project_id"])
    if project["lifecycle_status"] not in {"approved", "executed", "closed"}:
        raise MassBlastConflictError("Документы выпускаются только после утверждения ревизии.")
    context = revision["context"]
    base = _safe_filename(f"{context.get('project', {}).get('site_code', 'site')}_{context.get('project', {}).get('blast_date', '')}_r{revision['revision_no']}_{kind.lower()}")
    if format == "PDF":
        content, suffix = render_pdf(context, kind), ".pdf"
    elif format == "XLSX":
        content, suffix = render_xlsx(context, kind), ".xlsx"
    elif format == "ZIP":
        pdf = render_pdf(context, "PROJECT")
        xlsx = render_xlsx(context, "PROJECT")
        content, suffix = render_zip(context, pdf, xlsx, base), ".zip"
    else:
        raise ValueError(f"Неподдерживаемый формат документа: {format}.")
    digest = hashlib.sha256(content).hexdigest()
    filename = f"{base}{suffix}"
    target = _document_dir() / revision_id / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if not target.exists():
        temporary = target.with_suffix(f"{target.suffix}.tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        created = True
    try:
        return repository.save_document(
            organization_id, actor, revision_id, kind=kind, format=format,
            template_version=revision["document_template_version"], filename=filename,
            storage_key=str(target), sha256=digest, byte_size=len(content),
        )
    except Exception:
        if created and target.exists():
            target.unlink()
        raise


def document_path(repository: PostgresMassBlastRepository, organization_id: str, document_id: str) -> tuple[dict[str, Any], Path]:
    document, _project_id = repository.get_document(organization_id, document_id)
    # Storage key is intentionally not in the public schema. Read it internally
    # from the repository's database record only after organization verification.
    with repository.session_factory() as session:
        from design.mass_blast_repository import MassBlastDocumentRow

        row = session.get(MassBlastDocumentRow, document_id)
        assert row is not None
        path = Path(row.storage_key).resolve()
    root = _document_dir()
    if not path.is_relative_to(root) or not path.is_file():
        raise MassBlastNotFoundError(f"Файл документа {document_id} не найден.")
    return document, path


def attachment_path(
    repository: PostgresMassBlastRepository, organization_id: str, project_id: str, attachment_id: str,
) -> tuple[dict[str, Any], Path]:
    attachment, storage_key = repository.get_attachment(organization_id, project_id, attachment_id)
    path = Path(storage_key).resolve()
    root = _attachment_dir()
    if not path.is_relative_to(root) or not path.is_file():
        raise MassBlastNotFoundError(f"Файл приложения {attachment_id} не найден.")
    return attachment, path


def repository_error(exc: Exception) -> HTTPException:
    if isinstance(exc, MassBlastNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, MassBlastConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Модуль массовых взрывов временно недоступен: {exc}")
