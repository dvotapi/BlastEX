"""REST API паспорта на бурение (TASK-015): черновик, проверка, ревизия, PDF, DXF / DWG,
файл выноса для GNSS, ведомость координат и архив.

Подключается при включённом флаге `drill_passport` (`BLASTEX_DRILL_PASSPORT_ENABLED`,
с PR 6 включён по умолчанию); выключен — маршрутов нет, 404.
"""
from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

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
    XLSX_MEDIA_TYPE,
    coords_document,
    create_passport,
    create_revision,
    get_drilling_passport_repository,
    holes_drawing,
    list_passports,
    package_zip,
    passport_pdf,
    preview_pdf,
    repository_error,
    stakeout_export,
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


@router.get("", response_model=list[DrillingPassportSchema])
def get_passports(
    design_id: str | None = Query(default=None, max_length=200, description="Проект блока; пусто — все паспорта"),
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> list[DrillingPassportSchema]:
    """Паспорта организации (проекта блока), последний изменённый первым (PR 6)."""

    organization_id, _ = _identity(session)
    try:
        items = list_passports(repository, organization_id, design_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return [DrillingPassportSchema.model_validate(item) for item in items]


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


@router.get("/{passport_id}/preview.pdf", response_class=Response)
def get_preview_pdf(
    passport_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
    economics_repository: EconomicsRepository = Depends(get_economics_repository),
) -> Response:
    """PDF текущего черновика с пометкой «черновик» — предпросмотр без ревизии (PR 6)."""

    organization_id, _ = _identity(session)
    try:
        pdf, filename = preview_pdf(repository, economics_repository, organization_id, passport_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}"},
    )


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


@router.get("/revisions/{revision_id}/passport.pdf", response_class=Response)
def get_passport_pdf(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> Response:
    """PDF паспорта на бурение по форме v0.7 — только из неизменяемой ревизии."""

    organization_id, _ = _identity(session)
    try:
        pdf, filename = passport_pdf(repository, organization_id, revision_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


DRAWING_MEDIA_TYPES = {"dxf": "image/vnd.dxf", "dwg": "image/vnd.dwg"}


def _holes_response(
    repository: PostgresDrillingPassportRepository,
    session: dict[str, object],
    revision_id: str,
    fmt: Literal["dxf", "dwg"],
) -> Response:
    organization_id, _ = _identity(session)
    try:
        exported, filename = holes_drawing(repository, organization_id, revision_id, fmt)
    except Exception as exc:
        raise _fail(exc) from exc
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    if exported.warning:
        # Заголовок HTTP — только ASCII: текст предупреждения в percent-encoding.
        headers["X-BlastEX-Warning"] = quote(exported.warning)
    return Response(content=exported.data, media_type=DRAWING_MEDIA_TYPES[exported.format], headers=headers)


@router.get("/revisions/{revision_id}/holes.dxf", response_class=Response)
def get_holes_dxf(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> Response:
    """DXF R2010 скважин ревизии в СК объекта (TASK-015, PR 4)."""

    return _holes_response(repository, session, revision_id, "dxf")


@router.get("/revisions/{revision_id}/holes.dwg", response_class=Response)
def get_holes_dwg(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> Response:
    """DWG R2000 скважин ревизии; не вышло — DXF и заголовок `X-BlastEX-Warning`."""

    return _holes_response(repository, session, revision_id, "dwg")


def _attachment(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/revisions/{revision_id}/stakeout", response_class=Response)
def get_stakeout(
    revision_id: str,
    profile: str | None = Query(default=None, max_length=64, description="Код профиля; пусто — профиль объекта"),
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> Response:
    """Файл выноса устьев для GNSS-приёмника по профилю (TASK-015, PR 5)."""

    organization_id, _ = _identity(session)
    try:
        data, filename, media_type = stakeout_export(repository, organization_id, revision_id, profile)
    except Exception as exc:
        raise _fail(exc) from exc
    return _attachment(data, media_type, filename)


def _coords_response(
    repository: PostgresDrillingPassportRepository,
    session: dict[str, object],
    revision_id: str,
    fmt: Literal["pdf", "xlsx"],
) -> Response:
    organization_id, _ = _identity(session)
    try:
        data, filename = coords_document(repository, organization_id, revision_id, fmt)
    except Exception as exc:
        raise _fail(exc) from exc
    return _attachment(data, "application/pdf" if fmt == "pdf" else XLSX_MEDIA_TYPE, filename)


@router.get("/revisions/{revision_id}/coords.pdf", response_class=Response)
def get_coords_pdf(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> Response:
    """Ведомость координат скважин — PDF по эталону v0.6 (TASK-015, PR 5)."""

    return _coords_response(repository, session, revision_id, "pdf")


@router.get("/revisions/{revision_id}/coords.xlsx", response_class=Response)
def get_coords_xlsx(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> Response:
    """Ведомость координат скважин — XLSX в формате маркшейдера (TASK-015, PR 5)."""

    return _coords_response(repository, session, revision_id, "xlsx")


@router.get("/revisions/{revision_id}/package.zip", response_class=Response)
def get_package_zip(
    revision_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> Response:
    """Всё вместе: паспорт, DXF, файл выноса, ведомость PDF и XLSX (TASK-015, PR 5)."""

    organization_id, _ = _identity(session)
    try:
        data, filename = package_zip(repository, organization_id, revision_id)
    except Exception as exc:
        raise _fail(exc) from exc
    return _attachment(data, "application/zip", filename)
