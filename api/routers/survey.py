"""REST API съёмки к проекту блока (TASK-014, PR 5а): чтение файла маркшейдера,
оценка скважин по допускам паспорта на бурение и «Применить к проекту».

Ничего не сохраняет: результат «Применить» документ кладёт сам.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from api.schemas.survey import (
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
from design.drilling_passport_repository import PostgresDrillingPassportRepository
from design.survey.read import MAX_SURVEY_BYTES, SurveyReadError, read_survey

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


@router.post("/read", response_model=SurveyReadResponse)
async def post_read(
    file: UploadFile = File(...),
    format: SurveyFormat | None = Form(None),
    swap_xy: bool | None = Form(None),
    columns: str = Form(""),
) -> SurveyReadResponse:
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
        raise HTTPException(422, str(exc)) from exc
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
