"""REST API паспорта на бурение (TASK-015, PR 1): черновик, проверка, ревизия.

Подключается только при включённом флаге `drill_passport`
(`BLASTEX_DRILL_PASSPORT_ENABLED`); без него маршрутов нет — 404.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas.drilling_passport import (
    DrillingPassportCreateSchema,
    DrillingPassportRevisionCreateSchema,
    DrillingPassportRevisionSchema,
    DrillingPassportSchema,
    DrillingPassportUpdateSchema,
    DrillingPassportValidationSchema,
)
from api.security import require_human, require_internal_access
from api.services.drilling_passport_service import (
    create_passport,
    create_revision,
    get_drilling_passport_repository,
    repository_error,
    update_passport,
    validate_passport,
)
from api.services.economics_service import get_economics_repository
from cost.v2.repository import EconomicsRepository
from design.drilling_passport_repository import PostgresDrillingPassportRepository

router = APIRouter(prefix="/design/drilling-passports", tags=["drilling-passport"])


def _identity(session: dict[str, object]) -> tuple[str, str]:
    return str(session.get("org") or "default"), str(session.get("sub") or "unknown")


def _fail(exc: Exception) -> HTTPException:
    return repository_error(exc)


@router.post("", response_model=DrillingPassportSchema, status_code=status.HTTP_201_CREATED)
def post_passport(
    request: DrillingPassportCreateSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> DrillingPassportSchema:
    organization_id, actor = _identity(session)
    try:
        created = create_passport(repository, economics_repository, organization_id, actor, request)
    except Exception as exc:
        raise _fail(exc) from exc
    return DrillingPassportSchema.model_validate(created)


@router.get("/{passport_id}", response_model=DrillingPassportSchema)
def get_passport(
    passport_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> DrillingPassportSchema:
    organization_id, _ = _identity(session)
    try:
        return DrillingPassportSchema.model_validate(repository.get_passport(organization_id, passport_id))
    except Exception as exc:
        raise _fail(exc) from exc


@router.put("/{passport_id}", response_model=DrillingPassportSchema)
def put_passport(
    passport_id: str,
    request: DrillingPassportUpdateSchema,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> DrillingPassportSchema:
    organization_id, actor = _identity(session)
    try:
        updated = update_passport(repository, organization_id, actor, passport_id, request)
    except Exception as exc:
        raise _fail(exc) from exc
    return DrillingPassportSchema.model_validate(updated)


@router.post("/{passport_id}/validate", response_model=DrillingPassportValidationSchema)
def post_validate(
    passport_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> DrillingPassportValidationSchema:
    organization_id, _ = _identity(session)
    try:
        result = validate_passport(repository, economics_repository, organization_id, passport_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return DrillingPassportValidationSchema.model_validate(result)


@router.post(
    "/{passport_id}/revisions",
    response_model=DrillingPassportRevisionSchema,
    status_code=status.HTTP_201_CREATED,
)
def post_revision(
    passport_id: str,
    request: DrillingPassportRevisionCreateSchema,
    # Ревизию выпускает вошедший человек: внутренний ключ решений не принимает (PR #110).
    session: dict[str, object] = Depends(require_human),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> DrillingPassportRevisionSchema:
    organization_id, actor = _identity(session)
    try:
        revision = create_revision(
            repository, economics_repository, organization_id, actor, passport_id,
            request.expected_version, request.acknowledged_warnings,
        )
    except Exception as exc:
        raise _fail(exc) from exc
    return DrillingPassportRevisionSchema.model_validate(revision)


@router.get("/revisions/{revision_id}", response_model=DrillingPassportRevisionSchema)
def get_revision(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> DrillingPassportRevisionSchema:
    organization_id, _ = _identity(session)
    try:
        return DrillingPassportRevisionSchema.model_validate(repository.get_revision(organization_id, revision_id))
    except Exception as exc:
        raise _fail(exc) from exc
