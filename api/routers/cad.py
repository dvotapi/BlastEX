"""REST-роутер импорта чертежа маркшейдера (TASK-013).

Префикс `/design/cad`, а не `/spatial`: роутер `spatial` — ML-слой, на
проде он выключен (`BLASTEX_INTELLIGENCE_ENABLED`), а импорт чертежа нужен
всегда.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from api.schemas.cad import (
    CadImportResponse,
    CadMetaResponse,
    CadParamsSchema,
    CadRolesRequest,
    CadRolesResponse,
    CadSourceSchema,
)
from api.security import require_internal_access
from api.services import cad_service
from api.services.cad_service import CadImportError, get_cad_repository
from api.services.legacy_references import current_reference_snapshot
from cost.v2.models import ReferenceSnapshot
from design.spatial.cad.repository import CadRepository, CadSourceNotFound

router = APIRouter(prefix="/design/cad", tags=["cad"])

NOT_FOUND = "Импорт чертежа не найден."


def _identity(session: dict) -> tuple[str, str]:
    return str(session.get("org") or "default"), str(session.get("sub") or "")


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, CadSourceNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    if isinstance(exc, CadImportError):
        return HTTPException(status_code=exc.status_code, detail=exc.message)
    raise exc


@router.get("/meta", response_model=CadMetaResponse)
def get_meta() -> CadMetaResponse:
    return cad_service.meta()


@router.post("/sources", response_model=CadImportResponse, status_code=status.HTTP_201_CREATED)
async def post_sources(
    files: list[UploadFile] = File(...),
    work_object_name: str = Form(""),
    scale: float = Form(1.0),
    label_radius_m: float = Form(3.0),
    floor_z_m: float | None = Form(None),
    bench_height_m: float = Form(10.0),
    survey_date: str = Form(""),
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
    snapshot: ReferenceSnapshot = Depends(current_reference_snapshot),
) -> CadImportResponse:
    organization_id, actor = _identity(session)
    try:
        params = CadParamsSchema(
            scale=scale, label_radius_m=label_radius_m, floor_z_m=floor_z_m, bench_height_m=bench_height_m
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Параметры разбора вне допустимых пределов.") from exc

    uploads: list[tuple[str, bytes]] = []
    try:
        for upload in files:
            name = upload.filename or "drawing.dxf"
            # Читаем на байт больше предела: сам предел — ещё допустимый размер.
            content = await upload.read(cad_service.MAX_FILE_BYTES + 1)
            cad_service.check_file_size(name, len(content))
            uploads.append((name, content))
        # Конвертация DWG (до двух минут), разбор и запись синхронные — вне
        # цикла событий, иначе на это время замер бы весь API.
        return await run_in_threadpool(
            cad_service.import_files,
            repository,
            organization_id,
            actor,
            uploads,
            params,
            work_object_name,
            cad_service.parse_survey_date(survey_date),
            snapshot,
        )
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc
    finally:
        for upload in files:
            await upload.close()


@router.get("/sources/{source_id}", response_model=CadSourceSchema)
def get_source(
    source_id: str,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadSourceSchema:
    organization_id, _ = _identity(session)
    try:
        return cad_service.get_source(repository, organization_id, source_id)
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc


@router.post("/sources/{source_id}/reparse", response_model=CadSourceSchema)
def post_reparse(
    source_id: str,
    params: CadParamsSchema,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadSourceSchema:
    organization_id, _ = _identity(session)
    try:
        return cad_service.reparse(repository, organization_id, source_id, params)
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc


@router.put("/sources/{source_id}/roles", response_model=CadRolesResponse)
def put_roles(
    source_id: str,
    request: CadRolesRequest,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadRolesResponse:
    organization_id, actor = _identity(session)
    try:
        return cad_service.save_roles(repository, organization_id, actor, source_id, request)
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc
