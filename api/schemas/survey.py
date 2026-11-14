"""Pydantic-схемы съёмки к проекту блока (TASK-014, PR 5а): чтение, оценка, применение."""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.schemas.design import (
    AsDrilledHoleSchema,
    BlastDesignSchema,
    ChargeGenerateRequest,
    HoleLoadSchema,
    HoleSchema,
    SurveyApplicationSchema,
)
from design.survey.read import MAX_SURVEY_ROWS

SurveyFormat = Literal["PNEZD_CSV", "PENZD_CSV", "PNEZ_TXT", "DXF_POINTS", "TABLE"]
MatchBy = Literal["name", "nearest", "manual", ""]
MatchIssue = Literal["", "unmatched_point", "duplicate_point", "missing_point"]
VerdictCode = Literal["ok", "underdrill", "overdrill", "offset", "angle", "burden", "spacing", "no_depth"]
ToleranceSource = Literal["passport", "parent_passport", "default"]

NAME_MAX_LENGTH = 120
FILE_NAME_MAX_LENGTH = 255
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SurveyedPointSchema(BaseModel):
    """Точка съёмки: x — восток, y — север (как `Point3`); чего нет в файле — None."""

    model_config = ConfigDict(from_attributes=True, allow_inf_nan=False)

    name: str = Field(max_length=NAME_MAX_LENGTH)
    x: float
    y: float
    z: float | None = None
    depth_m: float | None = None
    angle_deg: float | None = None
    azimuth_deg: float | None = None
    wet: bool | None = None
    water_depth_m: float | None = None
    line: int = 0


class SurveyReadResponse(BaseModel):
    points: list[SurveyedPointSchema]
    format: SurveyFormat
    # Ключ (`name`, `east`, `north`, `z`, `depth`, …) → заголовок колонки файла; у профилей — пусто.
    columns: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    sha256: str
    file_name: str


class SurveyMatchSchema(BaseModel):
    """Сопоставление: скважина и точка; у проблемы одна из сторон может отсутствовать."""

    hole_id: str | None = None
    point: SurveyedPointSchema | None = None
    by: MatchBy = ""
    issue: MatchIssue = ""


class HoleVerdictSchema(BaseModel):
    """Оценка скважины по допускам; `point` — её точка съёмки."""

    hole_id: str
    point: SurveyedPointSchema
    codes: list[VerdictCode]
    offset_m: float | None = None
    depth_delta_m: float | None = None
    required_length_m: float | None = None
    angle_delta_deg: float | None = None
    burden_delta_pct: float | None = None
    spacing_delta_pct: float | None = None
    unchanged: bool = False


class SurveyTolerancesSchema(BaseModel):
    """Допуски оценки и откуда они: паспорт блока, паспорт проекта-родителя или умолчания."""

    depth_m: float
    collar_m: float
    angle_deg: float
    burden_pct: float
    spacing_pct: float
    source: ToleranceSource
    # Паспорт на бурение, чья ревизия дала допуски; у умолчаний — пусто.
    passport_no: str = ""
    revision_no: int | None = None
    passport_design_id: str = ""


class SurveyEvaluateRequest(BaseModel):
    design: BlastDesignSchema
    # Сохранённый проект: по нему ищется паспорт на бурение (и родитель копии).
    design_id: str = Field(default="", max_length=200)
    points: list[SurveyedPointSchema] = Field(default_factory=list, max_length=MAX_SURVEY_ROWS)
    # Пусто — блок паспорта на бурение (префикс имён точек «66-1-01»).
    block: str = Field(default="", max_length=NAME_MAX_LENGTH)
    # Имя точки → id скважины: ручная привязка.
    manual: dict[str, str] = Field(default_factory=dict, max_length=MAX_SURVEY_ROWS)
    # Имена пропущенных точек.
    skip: list[str] = Field(default_factory=list, max_length=MAX_SURVEY_ROWS)


class SurveyEvaluateResponse(BaseModel):
    matches: list[SurveyMatchSchema]
    verdicts: list[HoleVerdictSchema]
    tolerances: SurveyTolerancesSchema
    # При перестановке X и Y по близости сопоставляется больше точек.
    swap_suggested: bool = False
    # Блок, по которому сопоставлялись имена точек.
    block: str = ""
    warnings: list[str] = Field(default_factory=list)


class SurveyApplyRequest(SurveyEvaluateRequest):
    file_name: str = Field(default="", max_length=FILE_NAME_MAX_LENGTH)
    file_sha256: str = Field(default="", max_length=64)
    # Дата съёмки, ГГГГ-ММ-ДД; пусто — не указана.
    survey_date: str = ""
    # Параметры расчёта зарядов: нужны, если у проекта есть заряды (скважины в нём не читаются).
    charge: ChargeGenerateRequest | None = None

    @field_validator("survey_date")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        try:
            if not _ISO_DATE.match(value):
                raise ValueError
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("Дата съёмки — в виде ГГГГ-ММ-ДД.") from None
        return value


class SurveyApplyResponse(BaseModel):
    holes: list[HoleSchema]
    # None — заряды не трогались (их нет или нечем пересчитать): документ оставляет свои.
    loads: list[HoleLoadSchema] | None = None
    as_drilled_holes: list[AsDrilledHoleSchema]
    survey_application: SurveyApplicationSchema
    changed_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
