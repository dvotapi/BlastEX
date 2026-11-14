"""REST API съёмки (TASK-014, PR 5а): чтение файла маркшейдера, оценка скважин по
допускам паспорта на бурение и «Применить к проекту» — ничего не сохраняют,
результат «Применить» документ кладёт сам; и «Съёмка старого блока на объекте»
(`/sites/...`) — единственное, что хранится.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from api.schemas.survey import (
    SiteSurveyCreatedSchema,
    SiteSurveyDetailSchema,
    SiteSurveySchema,
    SurveyApplyRequest,
    SurveyApplyResponse,
    SurveyEvaluateRequest,
    SurveyEvaluateResponse,
    SurveyFormat,
    SurveyReadResponse,
)
from api.security import require_internal_access
from api.services import survey_service
from api.services.drilling_passport_service import get_drilling_passport_repository
from api.services.legacy_references import current_reference_snapshot
from api.services.survey_service import get_site_survey_repository
from cost.v2.models import ReferenceSnapshot
from design.drilling_passport_repository import PostgresDrillingPassportRepository
from design.survey.site_repository import SiteSurveyRepository
from design.survey.read import MAX_SURVEY_BYTES, SurveyFile, SurveyReadError, read_survey

router = APIRouter(prefix="/design/survey", tags=["survey"])

DEFAULT_FILE_NAME = "survey.csv"


def _identity(session: dict[str, object]) -> tuple[str, str]:
    return str(session.get("org") or "default"), str(session.get("sub") or "")


def _columns(raw: str) -> dict[str, str] | None:
    if not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise HTTPException(422, "Колонки съёмки не прочитаны.")
    return value


async def _read_upload(
    file: UploadFile, format: SurveyFormat | None, swap_xy: bool | None, columns: str
) -> tuple[SurveyFile, str]:
    name = (file.filename or DEFAULT_FILE_NAME)[:255]
    try:
        mapping = _columns(columns)
        # На байт больше предела: сам предел допустим, лишнее не читаем в память.
        data = await file.read(MAX_SURVEY_BYTES + 1)
    finally:
        await file.close()
    try:
        survey = await run_in_threadpool(read_survey, data, name, format=format, columns=mapping, swap_xy=swap_xy)
    except SurveyReadError as exc:
        # У таблицы — её заголовки: колонки выбираются вручную и файл читается заново.
        detail: str | dict[str, object] = {"message": str(exc), "headers": exc.headers} if exc.headers else str(exc)
        raise HTTPException(422, detail) from exc
    return survey, name


@router.post("/read", response_model=SurveyReadResponse)
async def post_read(
    file: UploadFile = File(...),
    format: SurveyFormat | None = Form(None),
    swap_xy: bool | None = Form(None),
    columns: str = Form(""),
) -> SurveyReadResponse:
    survey, name = await _read_upload(file, format, swap_xy, columns)
    return survey_service.read_response(survey, name)


@router.post("/evaluate", response_model=SurveyEvaluateResponse)
def post_evaluate(
    request: SurveyEvaluateRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> SurveyEvaluateResponse:
    organization_id, _ = _identity(session)
    return survey_service.evaluate(request, organization_id, repository)


@router.post("/apply", response_model=SurveyApplyResponse)
def post_apply(
    request: SurveyApplyRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: PostgresDrillingPassportRepository = Depends(get_drilling_passport_repository),
) -> SurveyApplyResponse:
    organization_id, actor = _identity(session)
    return survey_service.apply(request, organization_id, actor, repository)


# --- съёмка старого блока на объекте ---------------------------------------------


@router.get("/sites/{site_code}", response_model=list[SiteSurveySchema])
def get_site_surveys(
    site_code: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: SiteSurveyRepository = Depends(get_site_survey_repository),
    snapshot: ReferenceSnapshot = Depends(current_reference_snapshot),
) -> list[SiteSurveySchema]:
    organization_id, _ = _identity(session)
    return survey_service.list_site_surveys(snapshot, repository, organization_id, site_code)


@router.get("/sites/{site_code}/{survey_id}", response_model=SiteSurveyDetailSchema)
def get_site_survey(
    site_code: str,
    survey_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: SiteSurveyRepository = Depends(get_site_survey_repository),
) -> SiteSurveyDetailSchema:
    organization_id, _ = _identity(session)
    return survey_service.get_site_survey(repository, organization_id, site_code, survey_id)


@router.post("/sites/{site_code}", response_model=SiteSurveyCreatedSchema, status_code=status.HTTP_201_CREATED)
async def post_site_survey(
    site_code: str,
    file: UploadFile = File(...),
    block_label: str = Form(...),
    survey_date: str = Form(...),
    horizon_m: float | None = Form(None),
    format: SurveyFormat | None = Form(None),
    swap_xy: bool | None = Form(None),
    columns: str = Form(""),
    session: dict[str, object] = Depends(require_internal_access),
    repository: SiteSurveyRepository = Depends(get_site_survey_repository),
    snapshot: ReferenceSnapshot = Depends(current_reference_snapshot),
) -> SiteSurveyCreatedSchema:
    organization_id, actor = _identity(session)
    # Объект проверяется до чтения файла: чужой код не должен стоить разбора.
    survey_service.check_site(snapshot, site_code)
    survey, name = await _read_upload(file, format, swap_xy, columns)
    return survey_service.create_site_survey(
        snapshot,
        repository,
        organization_id,
        actor,
        site_code,
        survey=survey,
        file_name=name,
        block_label=block_label,
        survey_date=survey_date,
        horizon_m=horizon_m,
    )


@router.delete("/sites/{site_code}/{survey_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site_survey(
    site_code: str,
    survey_id: str,
    session: dict[str, object] = Depends(require_internal_access),
    repository: SiteSurveyRepository = Depends(get_site_survey_repository),
) -> Response:
    organization_id, _ = _identity(session)
    survey_service.delete_site_survey(repository, organization_id, site_code, survey_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
