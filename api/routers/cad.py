"""REST-роутер импорта чертежа маркшейдера (TASK-013).

Префикс `/design/cad`, а не `/spatial`: роутер `spatial` — ML-слой, на
проде он выключен (`BLASTEX_INTELLIGENCE_ENABLED`), а импорт чертежа нужен
всегда.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from api.schemas.cad import (
    MAX_SITUATION_REFERENCES,
    CadAreaBasisRequest,
    CadAreaBasisResponse,
    CadContourLinesRequest,
    CadContourLinesResponse,
    CadContourRequest,
    CadContourResponse,
    CadCrsResponse,
    CadCrsSchema,
    CadImportResponse,
    CadMetaResponse,
    CadParamsSchema,
    CadRolesRequest,
    CadRolesResponse,
    CadSiteSourcesResponse,
    CadSituationCatalogueResponse,
    CadSituationGeometryResponse,
    CadSourceMetaRequest,
    CadSourceMetaResponse,
    CadSourceSchema,
    CadSurfaceRequest,
    CadSurfaceResponse,
)
from api.security import require_internal_access
from api.services import cad_contour_service, cad_service, cad_situation_service, cad_surface_service
from api.services.cad_service import CadImportError, get_cad_repository
from api.services.economics_service import get_economics_repository
from api.services.legacy_references import current_reference_snapshot
from cost.v2.models import ReferenceSnapshot
from cost.v2.repository import EconomicsRepository
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


def current_work_object_name(
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> str:
    """Активный объект организации: сервер берёт его сам, клиент имя не передаёт."""

    organization_id, _ = _identity(session)
    return cad_service.active_work_object_name(repository, organization_id)


@router.get("/meta", response_model=CadMetaResponse)
def get_meta() -> CadMetaResponse:
    return cad_service.meta()


@router.post("/sources", response_model=CadImportResponse, status_code=status.HTTP_201_CREATED)
async def post_sources(
    files: list[UploadFile] = File(...),
    scale: float = Form(1.0),
    label_radius_m: float = Form(3.0),
    floor_z_m: float | None = Form(None),
    bench_height_m: float = Form(10.0),
    survey_date: str = Form(""),
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
    snapshot: ReferenceSnapshot = Depends(current_reference_snapshot),
    work_object_name: str = Depends(current_work_object_name),
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
        # Число файлов — до чтения: иначе сотня загрузок по 40 МБ легла бы в память.
        if len(files) > cad_service.MAX_FILES:
            raise CadImportError(f"За один раз можно загрузить не больше {cad_service.MAX_FILES} файлов.")
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


@router.get("/sources", response_model=CadSiteSourcesResponse)
def get_site_sources(
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
    snapshot: ReferenceSnapshot = Depends(current_reference_snapshot),
    work_object_name: str = Depends(current_work_object_name),
) -> CadSiteSourcesResponse:
    """«Чертежи объекта»: загруженные файлы активного объекта работ."""

    organization_id, _ = _identity(session)
    site_code = cad_service.resolve_site_code(snapshot, work_object_name)
    return cad_situation_service.list_sources(repository, organization_id, site_code)


@router.get("/situation", response_model=CadSituationCatalogueResponse)
def get_situation(
    source_ids: list[str] = Query(default_factory=list, max_length=MAX_SITUATION_REFERENCES),
    site_source_id: str | None = Query(default=None, max_length=36),
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
    snapshot: ReferenceSnapshot = Depends(current_reference_snapshot),
    work_object_name: str = Depends(current_work_object_name),
) -> CadSituationCatalogueResponse:
    """Серии ситуации объекта паспорта: по источникам ссылки, без ссылки — активного объекта.

    `site_source_id` — источник, по которому только находится объект (контур
    паспорта без запомненных версий): его версия не закрепляется.
    """

    organization_id, _ = _identity(session)
    site_code = cad_service.resolve_site_code(snapshot, work_object_name)
    return cad_situation_service.catalogue(
        repository, organization_id, site_code, source_ids, site_source_id=site_source_id
    )


@router.get("/sources/{source_id}/situation", response_model=CadSituationGeometryResponse)
def get_source_situation(
    source_id: str,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadSituationGeometryResponse:
    """Геометрия ситуации одного источника по слоям."""

    organization_id, _ = _identity(session)
    try:
        return cad_situation_service.source_situation(repository, organization_id, source_id)
    except CadSourceNotFound as exc:
        raise _http(exc) from exc


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: str,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> Response:
    """Удалить загруженный чертёж насовсем: паспорта сохраняют контур и кровлю."""

    organization_id, _ = _identity(session)
    try:
        cad_situation_service.delete_source(repository, organization_id, source_id)
    except CadSourceNotFound as exc:
        raise _http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.patch("/sources/{source_id}", response_model=CadSourceMetaResponse)
def patch_source(
    source_id: str,
    request: CadSourceMetaRequest,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadSourceMetaResponse:
    """Название и дата съёмки источника: по ним он попадает в серию ситуации."""

    organization_id, _ = _identity(session)
    try:
        return cad_service.update_meta(repository, organization_id, source_id, request)
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc


@router.put("/sources/{source_id}/crs", response_model=CadCrsResponse)
def put_crs(
    source_id: str,
    request: CadCrsSchema,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadCrsResponse:
    """СК объекта источника: задаётся один раз, следующие файлы её наследуют."""

    organization_id, actor = _identity(session)
    try:
        return cad_service.save_crs(repository, organization_id, actor, source_id, request)
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


@router.post("/sources/{source_id}/contour/lines", response_model=CadContourLinesResponse)
def post_contour_lines(
    source_id: str,
    request: CadContourLinesRequest,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadContourLinesResponse:
    """Линии для контура: места разреза в пересечениях и сшитые бровки."""

    organization_id, _ = _identity(session)
    try:
        return cad_contour_service.lines(repository, organization_id, source_id, request)
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc


@router.post("/sources/{source_id}/contour", response_model=CadContourResponse)
def post_contour(
    source_id: str,
    request: CadContourRequest,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadContourResponse:
    """Предпросмотр контура блока: ошибки контура — в ответе, а не HTTP-кодом."""

    organization_id, _ = _identity(session)
    try:
        return cad_contour_service.contour(repository, organization_id, source_id, request)
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc


@router.post("/sources/{source_id}/surface", response_model=CadSurfaceResponse)
def post_surface(
    source_id: str,
    request: CadSurfaceRequest,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadSurfaceResponse:
    """Предпросмотр кровли блока: ошибки построения — в ответе, ошибки входа — 422."""

    organization_id, _ = _identity(session)
    try:
        return cad_surface_service.surface(repository, organization_id, source_id, request)
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc


@router.put("/sources/{source_id}/area-basis", response_model=CadAreaBasisResponse)
def put_area_basis(
    source_id: str,
    request: CadAreaBasisRequest,
    session: dict = Depends(require_internal_access),
    repository: CadRepository = Depends(get_cad_repository),
) -> CadAreaBasisResponse:
    """Какую площадь маркшейдер объекта называет площадью блока — хранится на объекте."""

    organization_id, actor = _identity(session)
    try:
        return cad_service.save_area_basis(repository, organization_id, actor, source_id, request.area_basis)
    except (CadImportError, CadSourceNotFound) as exc:
        raise _http(exc) from exc
