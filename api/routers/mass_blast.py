"""REST API of the mass-blast project lifecycle."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response

from api.schemas.mass_blast import (
    MassBlastAccountSchema,
    MassBlastApprovalCreateSchema,
    MassBlastApprovalSchema,
    MassBlastAttachmentSchema,
    MassBlastDocumentCreateSchema,
    MassBlastDocumentSchema,
    MassBlastHintsSchema,
    MassBlastLayerAvailabilitySchema,
    MassBlastLayerCreateSchema,
    MassBlastLayerIssueSchema,
    MassBlastLayerRefreshResponse,
    MassBlastLayerRefreshSchema,
    MassBlastLayerRevisionSchema,
    MassBlastLayerSchema,
    MassBlastLayerUpdateSchema,
    MassBlastLifecycleSchema,
    MassBlastNewProjectSchema,
    MassBlastRememberResponse,
    MassBlastRememberSchema,
    MassBlastProjectInputSchema,
    MassBlastProjectSchema,
    MassBlastProjectSummarySchema,
    MassBlastRevisionSchema,
    MassBlastValidationResponse,
    NotificationAddresseesSchema,
    RevisionCreateSchema,
)
from api import config
from api.security import require_human, require_internal_access, require_reference_editor
from api.services import mass_blast_documents_v2 as documents_v2
from api.services import mass_blast_layers_service as layers_service
from api.services.economics_service import get_economics_repository
from api.services.mass_blast_service import (
    approve_revision,
    attachment_path,
    create_new_project_v2,
    create_project,
    create_revision,
    delete_attachment,
    document_path,
    generate_document,
    get_mass_blast_repository,
    organization_accounts,
    project_hints,
    repository_error,
    transition_project,
    upload_attachment,
    update_project,
    validate_project,
)
from api.services.public_sync_service import get_public_reader, reference_issues
from cost.v2.public_sync import PublicReader
from cost.v2.repository import EconomicsRepository, ReferenceRevisionConflict
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


@router.get("/accounts", response_model=list[MassBlastAccountSchema])
def list_accounts(session: dict[str, object] = Depends(require_internal_access)) -> list[MassBlastAccountSchema]:
    """Учётки организации, которые можно назначить подписывать роль (до `/{project_id}`)."""
    organization_id, _ = _identity(session)
    return [MassBlastAccountSchema.model_validate(item) for item in organization_accounts(organization_id)]


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
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastValidationResponse:
    organization_id, _ = _identity(session)
    try:
        return MassBlastValidationResponse.model_validate(validate_project(
            repository, organization_id, project_id, require_attachments=require_attachments,
            economics_repository=economics_repository,
        ))
    except Exception as exc:
        raise repository_error(exc) from exc


@router.post("/{project_id}/revisions", response_model=MassBlastRevisionSchema, status_code=status.HTTP_201_CREATED)
def post_revision(
    project_id: str,
    payload: RevisionCreateSchema,
    session: dict[str, object] = Depends(require_human),
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
    session: dict[str, object] = Depends(require_human),
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
    session: dict[str, object] = Depends(require_human),
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


# --- Слои дня взрыва (TASK-018, PR 2): за флагом `mass_blast_v2` -------------


def _require_layers() -> None:
    if not config.mass_blast_v2_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Слои проекта массового взрыва недоступны.")


def _layer_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return repository_error(exc)


# --- Печать проекта v2 и слоёв (TASK-018, PR 3): на лету из ревизий ----------


def _download(content: bytes, filename: str, media_type: str) -> Response:
    from urllib.parse import quote

    return Response(
        content, media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def _print_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return repository_error(exc)


@router.get("/revisions/{revision_id}/package.zip", response_class=Response, dependencies=[Depends(_require_layers)])
def get_revision_package(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> Response:
    organization_id, _ = _identity(session)
    try:
        content, filename = documents_v2.project_package(repository, organization_id, revision_id)
    except Exception as exc:
        raise _print_errors(exc) from exc
    return _download(content, filename, "application/zip")


@router.get(
    "/revisions/{revision_id}/documents/{document}.pdf", response_class=Response, dependencies=[Depends(_require_layers)]
)
def get_revision_document(
    revision_id: str,
    document: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> Response:
    organization_id, _ = _identity(session)
    try:
        content, filename = documents_v2.project_document(repository, organization_id, revision_id, document)
    except Exception as exc:
        raise _print_errors(exc) from exc
    return _download(content, filename, "application/pdf")


@router.get(
    "/layers/revisions/{layer_revision_id}/document.pdf", response_class=Response, dependencies=[Depends(_require_layers)]
)
def get_layer_revision_document(
    layer_revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> Response:
    organization_id, _ = _identity(session)
    try:
        content, filename = documents_v2.layer_document(repository, organization_id, layer_revision_id)
    except Exception as exc:
        raise _print_errors(exc) from exc
    return _download(content, filename, "application/pdf")


@router.get("/layers/{layer_id}/preview.pdf", response_class=Response, dependencies=[Depends(_require_layers)])
def get_layer_preview(
    layer_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> Response:
    organization_id, _ = _identity(session)
    try:
        content = documents_v2.layer_preview(repository, economics_repository, organization_id, layer_id)
    except Exception as exc:
        raise _print_errors(exc) from exc
    return Response(content, media_type="application/pdf")


@router.get("/{project_id}/preview/{document}.pdf", response_class=Response, dependencies=[Depends(_require_layers)])
def get_project_preview(
    project_id: str,
    document: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> Response:
    organization_id, _ = _identity(session)
    try:
        content = documents_v2.project_preview(repository, economics_repository, organization_id, project_id, document)
    except Exception as exc:
        raise _print_errors(exc) from exc
    return Response(content, media_type="application/pdf")


@router.get("/{project_id}/layers", response_model=list[MassBlastLayerSchema], dependencies=[Depends(_require_layers)])
def get_layers(
    project_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> list[MassBlastLayerSchema]:
    organization_id, _ = _identity(session)
    try:
        return [MassBlastLayerSchema.model_validate(item) for item in layers_service.list_layers(repository, economics_repository, organization_id, project_id)]
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.post(
    "/{project_id}/layers", response_model=MassBlastLayerSchema, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_layers)],
)
def post_layer(
    project_id: str,
    payload: MassBlastLayerCreateSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastLayerSchema:
    organization_id, actor = _identity(session)
    try:
        return MassBlastLayerSchema.model_validate(layers_service.create_layer(
            repository, economics_repository, organization_id, actor, project_id, payload.kind, payload.payload,
        ))
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.get("/layers/{layer_id}", response_model=MassBlastLayerSchema, dependencies=[Depends(_require_layers)])
def get_layer(
    layer_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastLayerSchema:
    organization_id, _ = _identity(session)
    try:
        return MassBlastLayerSchema.model_validate(layers_service.get_layer(repository, economics_repository, organization_id, layer_id))
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.put("/layers/{layer_id}", response_model=MassBlastLayerSchema, dependencies=[Depends(_require_layers)])
def put_layer(
    layer_id: str,
    payload: MassBlastLayerUpdateSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastLayerSchema:
    organization_id, actor = _identity(session)
    try:
        return MassBlastLayerSchema.model_validate(layers_service.update_layer(
            repository, economics_repository, organization_id, actor, layer_id, payload.payload, payload.expected_version,
        ))
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.post("/layers/{layer_id}/refresh", response_model=MassBlastLayerRefreshResponse, dependencies=[Depends(_require_layers)])
def post_layer_refresh(
    layer_id: str,
    payload: MassBlastLayerRefreshSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastLayerRefreshResponse:
    organization_id, actor = _identity(session)
    try:
        return MassBlastLayerRefreshResponse.model_validate(layers_service.refresh_layer(
            repository, economics_repository, organization_id, actor, layer_id, payload.expected_version, payload.confirm,
        ))
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.post(
    "/layers/{layer_id}/revisions", response_model=MassBlastLayerRevisionSchema, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_layers)],
)
def post_layer_revision(
    layer_id: str,
    payload: MassBlastLayerIssueSchema,
    session: dict[str, object] = Depends(require_human),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastLayerRevisionSchema:
    organization_id, actor = _identity(session)
    try:
        return MassBlastLayerRevisionSchema.model_validate(layers_service.issue_layer(
            repository, economics_repository, organization_id, actor, layer_id, payload.expected_version,
        ))
    except Exception as exc:
        raise _layer_errors(exc) from exc



# --- Окно проекта МВ (TASK-018, PR 6) ----------------------------------------


@router.post(
    "/new", response_model=MassBlastProjectSchema, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_layers)],
)
def post_new_project(
    payload: MassBlastNewProjectSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> MassBlastProjectSchema:
    """Новый проект по форме ВМ.09.03: дата, время и блоки — остальное заполняется само."""

    organization_id, actor = _identity(session)
    try:
        return MassBlastProjectSchema.model_validate(create_new_project_v2(
            repository, economics_repository, organization_id, actor,
            design_ids=payload.design_ids, blast_date=payload.blast_date,
            blast_time=payload.blast_time, site_code=payload.site_code,
        ))
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.get("/{project_id}/hints", response_model=MassBlastHintsSchema, dependencies=[Depends(_require_layers)])
def get_hints(
    project_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> MassBlastHintsSchema:
    organization_id, _ = _identity(session)
    try:
        return MassBlastHintsSchema.model_validate(project_hints(repository, organization_id, project_id))
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.get(
    "/{project_id}/layers/available", response_model=list[MassBlastLayerAvailabilitySchema],
    dependencies=[Depends(_require_layers)],
)
def get_available_layers(
    project_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
) -> list[MassBlastLayerAvailabilitySchema]:
    organization_id, _ = _identity(session)
    try:
        return [MassBlastLayerAvailabilitySchema.model_validate(item)
                for item in layers_service.available_layers(repository, organization_id, project_id)]
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.get(
    "/{project_id}/notification-addressees", response_model=NotificationAddresseesSchema,
    dependencies=[Depends(_require_layers)],
)
def get_notification_addressees(
    project_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> NotificationAddresseesSchema:
    organization_id, _ = _identity(session)
    try:
        return NotificationAddresseesSchema.model_validate(layers_service.notification_addressees(
            repository, economics_repository, organization_id, project_id,
        ))
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.post(
    "/{project_id}/remember", response_model=MassBlastRememberResponse, dependencies=[Depends(_require_layers)],
)
def post_remember(
    project_id: str,
    payload: MassBlastRememberSchema,
    session: dict[str, object] = Depends(require_reference_editor),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
    reader: PublicReader = Depends(get_public_reader),
) -> MassBlastRememberResponse:
    """«Запомнить для объекта» (В8): поля объекта из проекта или слоя — в справочник новой ревизией."""

    from api.services.mass_blast_remember import remember_for_site

    organization_id, actor = _identity(session)
    try:
        project = repository.get_project(organization_id, project_id)
        layer = None
        if payload.layer_id:
            layer = repository.get_layer(organization_id, payload.layer_id)
            if layer["project_id"] != project_id:
                raise ValueError("Слой относится к другому проекту.")
        return MassBlastRememberResponse.model_validate(remember_for_site(
            economics_repository, organization_id, actor, project, payload.paths, layer=layer,
            issues_of=lambda sections: reference_issues(reader, economics_repository, organization_id, sections),
        ))
    except ReferenceRevisionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Справочник только что изменили: проект сохранён, сохраните его ещё раз, чтобы запомнить значения.",
        ) from exc
    except Exception as exc:
        raise _layer_errors(exc) from exc


@router.post("/{project_id}/suggest-layout", dependencies=[Depends(_require_layers)])
def post_suggest_layout(
    project_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresMassBlastRepository = Depends(get_mass_blast_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> dict[str, object]:
    """«Предложить посты» (В6): посты на пересечениях дорог с границей зоны для людей,
    станция и укрытие за зоной. Проект не меняется — окно ставит точки в форму."""

    from design.mass_blast_posts import suggest_layout

    organization_id, _ = _identity(session)
    try:
        result = validate_project(repository, organization_id, project_id, economics_repository=economics_repository)
        return suggest_layout((result.get("context") or {}).get("graphics") or {})
    except Exception as exc:
        raise _layer_errors(exc) from exc
