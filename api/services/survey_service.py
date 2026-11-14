"""Съёмка к проекту блока (TASK-014, PR 5а): чтение файла, оценка и «Применить».

Сервис ничего не сохраняет: «Применить» возвращает новые скважины, заряды,
факт и запись применения, документ на фронте кладёт их одним действием и
сохраняет обычным `PUT /design/plans/{id}`.

Допуски (план, §0) — из `current_revision_id` последнего изменённого паспорта
на бурение проекта с ревизией (`list_passports` — последний изменённый первым);
нет — по цепочке `parent_design_id` сохранённого проекта («Копия по съёмке»);
нет и там — умолчания с предупреждением (`TOLERANCES_DEFAULT_TEXT`).
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from api import config
from api.schemas.survey import (
    HoleVerdictSchema,
    SurveyApplyRequest,
    SiteSurveyDetailSchema,
    SiteSurveySchema,
    SurveyApplyResponse,
    SurveyedPointSchema,
    SurveyEvaluateRequest,
    SurveyEvaluateResponse,
    SurveyMatchSchema,
    SurveyReadResponse,
    SurveyTolerancesSchema,
)
from api.services.design_service import charge_explosives
from cost.v2.models import ReferenceSnapshot
from design import persistence as design_persistence
from design.drilling_passport_repository import DrillingPassportRepositoryError
from design.lifecycle import STATUS_DRAFT, STATUS_IN_REVIEW, utc_now_iso
from design.models import BlastDesign
from design.survey.site_repository import (
    PostgresSiteSurveyRepository,
    SiteSurveyDuplicateError,
    SiteSurveyNotFoundError,
    SiteSurveyRepository,
)
from design.survey.apply import ChargeInputs, apply_survey
from design.survey.evaluate import (
    HoleVerdict,
    SurveyTolerances,
    applied_points,
    evaluate_survey,
    tolerances_from_payload,
)
from design.survey.match import SurveyMatch, match_survey, swap_detect
from design.survey.read import SurveyedPoint, SurveyFile

TOLERANCES_DEFAULT_TEXT = (
    "У проекта блока нет выпущенной ревизии паспорта на бурение — допуски по умолчанию: "
    "глубина ±0,3 м, устье ±0,3 м, угол ±1°, ЛСПП и расстояние между скважинами ±5 %."
)
TOLERANCES_UNAVAILABLE_TEXT = "Паспорта на бурение сейчас недоступны — допуски по умолчанию."
APPROVED_TEXT = "Проект утверждён: правка по съёмке — через «Копию по съёмке»"
IN_REVIEW_TEXT = "Проект на проверке: верните его в черновик"
# Цепочка копий длиннее не бывает; предел — от зацикленной родословной.
MAX_PARENT_DEPTH = 20

DesignLoader = Callable[[str, str], BlastDesign]


@dataclass(frozen=True)
class ToleranceLookup:
    """Допуски и откуда они: ревизия паспорта проекта или его предка, иначе умолчания."""

    tolerances: SurveyTolerances
    block: str = ""
    passport_no: str = ""
    revision_no: int | None = None
    passport_design_id: str = ""
    warnings: list[str] = field(default_factory=list)

    def schema(self) -> SurveyTolerancesSchema:
        tol = self.tolerances
        return SurveyTolerancesSchema(
            depth_m=tol.depth_m,
            collar_m=tol.collar_m,
            angle_deg=tol.angle_deg,
            burden_pct=tol.burden_pct,
            spacing_pct=tol.spacing_pct,
            source=tol.source,
            passport_no=self.passport_no,
            revision_no=self.revision_no,
            passport_design_id=self.passport_design_id,
        )


def _released_revision(repository: Any, organization_id: str, design_id: str) -> tuple[dict, dict] | None:
    """Последний изменённый паспорт проекта с выпущенной ревизией и сама ревизия."""

    for passport in repository.list_passports(organization_id, design_id):
        revision_id = passport.get("current_revision_id")
        if revision_id:
            return passport, repository.get_revision(organization_id, revision_id)
    return None


def _revision_payload(revision: Mapping[str, Any]) -> Mapping[str, Any]:
    passport = (revision.get("context") or {}).get("passport") or {}
    payload = passport.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def survey_tolerances(
    organization_id: str, design_id: str, repository: Any, load: DesignLoader
) -> ToleranceLookup:
    """Допуски оценки по §0 плана; `load` — чтение сохранённого проекта (родитель копии)."""

    current, source, seen = design_id, "passport", set()
    try:
        while current and current not in seen and len(seen) < MAX_PARENT_DEPTH:
            seen.add(current)
            found = _released_revision(repository, organization_id, current)
            if found is not None:
                passport, revision = found
                payload = _revision_payload(revision)
                return ToleranceLookup(
                    tolerances=tolerances_from_payload(payload, source=source),
                    block=str(payload.get("block") or ""),
                    passport_no=str(passport.get("passport_no") or ""),
                    revision_no=revision.get("revision_no"),
                    passport_design_id=current,
                )
            source = "parent_passport"
            try:
                current = load(organization_id, current).parent_design_id
            except design_persistence.DesignNotFoundError:
                break
    except (DrillingPassportRepositoryError, SQLAlchemyError):
        return ToleranceLookup(SurveyTolerances(), warnings=[TOLERANCES_UNAVAILABLE_TEXT])
    return ToleranceLookup(SurveyTolerances(), warnings=[TOLERANCES_DEFAULT_TEXT])


# --- чтение --------------------------------------------------------------------


def read_response(survey: SurveyFile, file_name: str) -> SurveyReadResponse:
    return SurveyReadResponse(
        points=[SurveyedPointSchema(**point.to_dict()) for point in survey.points],
        format=survey.format,
        columns=survey.columns,
        warnings=survey.warnings,
        sha256=survey.sha256,
        file_name=file_name,
    )


# --- оценка и применение ---------------------------------------------------------


@dataclass
class _Evaluation:
    design: BlastDesign
    points: list[SurveyedPoint]
    lookup: ToleranceLookup
    block: str
    matches: list[SurveyMatch]
    verdicts: list[HoleVerdict]


def _design_id(request: SurveyEvaluateRequest) -> str:
    """Проект запроса: `design_id` или id самого документа; разные — 400."""

    own = request.design.design_id
    if request.design_id and own and own != request.design_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Проект в запросе не совпадает с design_id.")
    return request.design_id or own


def _evaluate(request: SurveyEvaluateRequest, organization_id: str, repository: Any) -> _Evaluation:
    design = BlastDesign.from_dict(request.design.model_dump())
    lookup = survey_tolerances(organization_id, _design_id(request), repository, design_persistence.load_design)
    block = request.block.strip() or lookup.block
    points = [SurveyedPoint.from_dict(point.model_dump()) for point in request.points]
    matches = match_survey(
        design.holes,
        points,
        block=block,
        tol_collar_m=lookup.tolerances.collar_m,
        manual=dict(request.manual),
        skip=set(request.skip),
    )
    verdicts = evaluate_survey(design, matches, lookup.tolerances)
    return _Evaluation(design, points, lookup, block, matches, verdicts)


def _point(point: SurveyedPoint | None) -> SurveyedPointSchema | None:
    return SurveyedPointSchema(**point.to_dict()) if point is not None else None


def evaluate(request: SurveyEvaluateRequest, organization_id: str, repository: Any) -> SurveyEvaluateResponse:
    result = _evaluate(request, organization_id, repository)
    points = applied_points(result.design, result.matches)
    skipped = set(request.skip)
    free = [point for point in result.points if point.name not in skipped]
    return SurveyEvaluateResponse(
        matches=[
            SurveyMatchSchema(hole_id=m.hole_id, point=_point(m.point), by=m.by, issue=m.issue)
            for m in result.matches
        ],
        verdicts=[
            HoleVerdictSchema(
                hole_id=v.hole_id,
                point=_point(points[v.hole_id]),
                codes=v.codes,
                offset_m=v.offset_m,
                depth_delta_m=v.depth_delta_m,
                required_length_m=v.required_length_m,
                angle_delta_deg=v.angle_delta_deg,
                burden_delta_pct=v.burden_delta_pct,
                spacing_delta_pct=v.spacing_delta_pct,
                unchanged=v.unchanged,
            )
            for v in result.verdicts
        ],
        tolerances=result.lookup.schema(),
        swap_suggested=swap_detect(result.design.holes, free, result.lookup.tolerances.collar_m),
        block=result.block,
        warnings=result.lookup.warnings,
    )


def _check_editable(request: SurveyApplyRequest, organization_id: str) -> None:
    """Применять можно только к черновику: сохранённый проект — по его статусу."""

    design_id = _design_id(request)
    lifecycle_status = request.design.lifecycle_status
    if design_id:
        try:
            lifecycle_status = design_persistence.load_design(organization_id, design_id).lifecycle_status
        except design_persistence.DesignNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Проект блока {design_id} не найден.") from exc
    if lifecycle_status == STATUS_IN_REVIEW:
        raise HTTPException(status.HTTP_409_CONFLICT, IN_REVIEW_TEXT)
    if lifecycle_status != STATUS_DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, APPROVED_TEXT)


def _charge(request: SurveyApplyRequest) -> ChargeInputs | None:
    if request.charge is None:
        return None
    explosive, explosives = charge_explosives(request.charge)
    return ChargeInputs(rules=dict(request.charge.rules), explosive=explosive, explosives=explosives)


def apply(request: SurveyApplyRequest, organization_id: str, actor: str, repository: Any) -> SurveyApplyResponse:
    _check_editable(request, organization_id)
    result = _evaluate(request, organization_id, repository)
    applied = apply_survey(
        result.design,
        result.matches,
        result.verdicts,
        file_name=request.file_name,
        file_sha256=request.file_sha256,
        survey_date=request.survey_date,
        actor=actor,
        charge=_charge(request),
        now=utc_now_iso(),
    )
    return SurveyApplyResponse(
        holes=[hole.to_dict() for hole in applied.holes],
        loads=[load.to_dict() for load in applied.loads] if applied.loads is not None else None,
        as_drilled_holes=[item.to_dict() for item in applied.as_drilled_holes],
        survey_application=applied.application.to_dict(),
        changed_ids=applied.changed_ids,
        warnings=[*result.lookup.warnings, *applied.warnings],
    )


# --- съёмка старого блока на объекте ---------------------------------------------


@lru_cache(maxsize=4)
def _postgres_site_repository(database_url: str) -> PostgresSiteSurveyRepository:
    return PostgresSiteSurveyRepository(database_url)


def get_site_survey_repository() -> SiteSurveyRepository:
    return _postgres_site_repository(config.database_url())


def check_site(snapshot: ReferenceSnapshot | None, site_code: str) -> None:
    """`site_code` — код записи справочника «sites», иначе 404."""

    code = (site_code or "").strip()
    if not code or snapshot is None or snapshot.item("sites", code) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Объект «{site_code}» не найден в справочнике.")


def _site_summary(record: Mapping[str, Any]) -> SiteSurveySchema:
    return SiteSurveySchema(
        **{key: record[key] for key in SiteSurveySchema.model_fields if key in record},
        points_count=len(record["points"]),
    )


def _site_detail(record: Mapping[str, Any]) -> SiteSurveyDetailSchema:
    summary = _site_summary(record)
    return SiteSurveyDetailSchema(
        **summary.model_dump(), points=[SurveyedPointSchema(**point) for point in record["points"]]
    )


def list_site_surveys(
    snapshot: ReferenceSnapshot | None, repository: SiteSurveyRepository, organization_id: str, site_code: str
) -> list[SiteSurveySchema]:
    check_site(snapshot, site_code)
    return [_site_summary(record) for record in repository.list(organization_id, site_code)]


def get_site_survey(
    repository: SiteSurveyRepository, organization_id: str, site_code: str, survey_id: str
) -> SiteSurveyDetailSchema:
    return _site_detail(_own_record(repository, organization_id, site_code, survey_id))


def _own_record(repository: SiteSurveyRepository, organization_id: str, site_code: str, survey_id: str) -> dict:
    try:
        record = repository.get(organization_id, survey_id)
    except SiteSurveyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if record["site_code"] != site_code:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Съёмка {survey_id} не найдена.")
    return record


def create_site_survey(
    snapshot: ReferenceSnapshot | None,
    repository: SiteSurveyRepository,
    organization_id: str,
    actor: str,
    site_code: str,
    *,
    survey: SurveyFile,
    file_name: str,
    block_label: str,
    survey_date: str,
    horizon_m: float | None,
) -> SiteSurveyDetailSchema:
    check_site(snapshot, site_code)
    label = block_label.strip()
    if not label:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Укажите блок съёмки.")
    try:
        day = date.fromisoformat(survey_date.strip())
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Дата съёмки — в виде ГГГГ-ММ-ДД."
        ) from None
    if horizon_m is not None and not math.isfinite(horizon_m):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Горизонт — конечное число.")
    record = {
        "site_code": site_code,
        "block_label": label,
        "horizon_m": horizon_m,
        "survey_date": day.isoformat(),
        "file_name": file_name,
        "file_sha256": survey.sha256,
        "points": [point.to_dict() for point in survey.points],
    }
    try:
        created = repository.create(organization_id, actor, record)
    except SiteSurveyDuplicateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _site_detail(created)


def delete_site_survey(repository: SiteSurveyRepository, organization_id: str, site_code: str, survey_id: str) -> None:
    _own_record(repository, organization_id, site_code, survey_id)
    try:
        repository.delete(organization_id, survey_id)
    except SiteSurveyNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
