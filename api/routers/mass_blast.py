"""REST API of the mass-blast project lifecycle."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from api.schemas.mass_blast import (
    MassBlastApprovalCreateSchema,
    MassBlastApprovalSchema,
    MassBlastAttachmentSchema,
    MassBlastDocumentCreateSchema,
    MassBlastDocumentSchema,
    MassBlastLifecycleSchema,
    MassBlastProjectInputSchema,
    MassBlastProjectSchema,
    MassBlastProjectSummarySchema,
    MassBlastRevisionSchema,
    MassBlastValidationResponse,
    RevisionCreateSchema,
)
from api.security import require_internal_access
from api.services.economics_service import get_economics_repository
from api.services.mass_blast_service import (
    approve_revision,
    attachment_path,
    create_project,
    create_revision,
    delete_attachment,
    document_path,
    generate_document,
    get_mass_blast_repository,
    repository_error,
    transition_project,
    upload_attachment,
    update_project,
    validate_project,
)
from cost.v2.repository import EconomicsRepository
from design.mass_blast_repository import PostgresMassBlastRepository


router = APIRouter(prefix="/design/mass-blast-projects", tags=["mass-blast"])


def _identity(session: dict[str, object]) -> tuple[str, str]:
    return str(session.get("org") or "default"), str(session.get("sub") or "unknown")


@router.get("", response_model=list[MassBlastProjectSummarySchema])
def list_projects(
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> list[MassBlastProjectSummarySchema]:
    organization_id, _ = _identity(session)
    try:
        return [MassBlastProjectSummarySchema.model_validate(item) for item in repository.list_projects(organization_id)]
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("", response_model=MassBlastProjectSchema, status_code=status.HTTP_201_CREATED)
def post_project(
    payload: MassBlastProjectInputSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastProjectSchema:
    organization_id, actor = _identity(session)
    try:
        return MassBlastProjectSchema.model_validate(create_project(repository, economics_repository, organization_id, actor, payload))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/{project_id}", response_model=MassBlastProjectSchema)
def get_project(
    project_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> MassBlastProjectSchema:
    organization_id, _ = _identity(session)
    try:
        return MassBlastProjectSchema.model_validate(repository.get_project(organization_id, project_id))
    except Exception as exc:
        raise repository_error(exc) from exc


@router.put("/{project_id}", response_model=MassBlastProjectSchema)
def put_project(
    project_id: str,
    payload: MassBlastProjectInputSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastProjectSchema:
    organization_id, actor = _identity(session)
    try:
        return MassBlastProjectSchema.model_validate(update_project(repository, economics_repository, organization_id, actor, project_id, payload))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/{project_id}/validate", response_model=MassBlastValidationResponse)
def post_validate(
    project_id: str,
    require_attachments: bool = False,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> MassBlastValidationResponse:
    organization_id, _ = _identity(session)
    try:
        return MassBlastValidationResponse.model_validate(validate_project(repository, organization_id, project_id, require_attachments=require_attachments))
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/{project_id}/revisions", response_model=MassBlastRevisionSchema, status_code=status.HTTP_201_CREATED)
def post_revision(
    project_id: str,
    payload: RevisionCreateSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastRevisionSchema:
    organization_id, actor = _identity(session)
    try:
        return MassBlastRevisionSchema.model_validate(create_revision(
            repository, economics_repository, organization_id, actor, project_id, payload.expected_version,
            require_attachments=payload.require_attachments,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/revisions/{revision_id}", response_model=MassBlastRevisionSchema)
def get_revision(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> MassBlastRevisionSchema:
    organization_id, _ = _identity(session)
    try:
        return MassBlastRevisionSchema.model_validate(repository.get_revision(organization_id, revision_id))
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/revisions/{revision_id}/approvals", response_model=MassBlastApprovalSchema)
def post_approval(
    revision_id: str,
    payload: MassBlastApprovalCreateSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> MassBlastApprovalSchema:
    organization_id, actor = _identity(session)
    try:
        return MassBlastApprovalSchema.model_validate(approve_revision(
            repository, organization_id, actor, revision_id, payload.role_code, payload.decision, payload.comment
        ))
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/{project_id}/lifecycle", response_model=MassBlastProjectSchema)
def post_lifecycle(
    project_id: str,
    payload: MassBlastLifecycleSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> MassBlastProjectSchema:
    organization_id, actor = _identity(session)
    try:
        return MassBlastProjectSchema.model_validate(transition_project(
            repository, organization_id, actor, project_id, payload.to_status,
            payload.expected_version, payload.confirm, payload.note,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/{project_id}/documents", response_model=list[MassBlastDocumentSchema])
def list_documents(
    project_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> list[MassBlastDocumentSchema]:
    organization_id, _ = _identity(session)
    try:
        return [MassBlastDocumentSchema.model_validate(item) for item in repository.list_documents(organization_id, project_id)]
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/{project_id}/attachments", response_model=list[MassBlastAttachmentSchema])
def list_attachments(
    project_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> list[MassBlastAttachmentSchema]:
    organization_id, _ = _identity(session)
    try:
        return [MassBlastAttachmentSchema.model_validate(item) for item in repository.list_attachments(organization_id, project_id)]
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/{project_id}/attachments", response_model=MassBlastAttachmentSchema, status_code=status.HTTP_201_CREATED)
async def post_attachment(
    project_id: str,
    kind: str = Form(...),
    file: UploadFile = File(...),
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> MassBlastAttachmentSchema:
    organization_id, actor = _identity(session)
    try:
        content = await file.read()
        return MassBlastAttachmentSchema.model_validate(upload_attachment(
            repository, organization_id, actor, project_id, kind=kind,
            filename=file.filename or "attachment", content_type=file.content_type, content=content,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc
    finally:
        await file.close()


@router.delete("/{project_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_attachment(
    project_id: str,
    attachment_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> None:
    organization_id, actor = _identity(session)
    try:
        delete_attachment(repository, organization_id, actor, project_id, attachment_id)
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/{project_id}/attachments/{attachment_id}/download")
def download_attachment(
    project_id: str,
    attachment_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> FileResponse:
    organization_id, _ = _identity(session)
    try:
        attachment, path = attachment_path(repository, organization_id, project_id, attachment_id)
        return FileResponse(path, media_type=attachment["mime_type"], filename=attachment["filename"])
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/{project_id}/documents", response_model=MassBlastDocumentSchema, status_code=status.HTTP_201_CREATED)
def post_document(
    project_id: str,
    payload: MassBlastDocumentCreateSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> MassBlastDocumentSchema:
    organization_id, actor = _identity(session)
    try:
        revision = repository.get_revision(organization_id, payload.revision_id)
        if revision["project_id"] != project_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ревизия относится к другому проекту.")
        return MassBlastDocumentSchema.model_validate(generate_document(
            repository, organization_id, actor, payload.revision_id, payload.kind, payload.format
        ))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        raise repository_error(exc) from exc


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> FileResponse:
    organization_id, _ = _identity(session)
    try:
        document, path = document_path(repository, organization_id, document_id)
        media_type = {"PDF": "application/pdf", "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "ZIP": "application/zip"}.get(document["format"], "application/octet-stream")
        return FileResponse(path, media_type=media_type, filename=document["filename"])
    except Exception as exc:
        raise repository_error(exc) from exc
