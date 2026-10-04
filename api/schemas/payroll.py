"""Схемы превью ФОТ должности (TASK-010): `POST /economics/payroll/preview`."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PayrollMeterItemSchema(BaseModel):
    """Метры одной породы и диаметра: крепость — из породы справочника или числом."""

    meters: Decimal = Field(..., ge=0)
    diameter_mm: Decimal = Field(..., gt=0)
    rock_code: str | None = Field(None, min_length=1, max_length=80)
    f: Decimal | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _one_hardness_source(self) -> "PayrollMeterItemSchema":
        if self.rock_code is not None and self.f is not None:
            raise ValueError("Крепость задаётся породой или числом f, не обоими сразу.")
        return self


class PayrollDowntimeSchema(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    hours: Decimal = Field(..., ge=0)


class PayrollCrewMemberSchema(BaseModel):
    position_code: str = Field(..., min_length=1, max_length=80)
    headcount: Decimal = Field(Decimal("1"), gt=0)


class PayrollPreviewRequest(BaseModel):
    position_code: str = Field(..., min_length=1, max_length=80)
    site_code: str = Field(..., min_length=1, max_length=80)
    # Месяц расчёта «ГГГГ-ММ»: по его году выбираются параметры ФОТ.
    month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    # Пусто — актуальная опубликованная ревизия справочников.
    reference_revision_id: str = ""
    # Пусто — план: вахта объекта минус плановое ТОиР.
    shifts: Decimal | None = Field(None, gt=0)
    downtime: list[PayrollDowntimeSchema] = Field(default_factory=list)
    items: list[PayrollMeterItemSchema] = Field(default_factory=list)
    meters_total: Decimal | None = Field(
        None,
        ge=0,
        description=(
            "Приведённые метры (выработка) одной суммой: договорной коэффициент объекта к ним не применяется, "
            "а доля в марже считается на приведённый метр. Для доли на погонный метр задайте items."
        ),
    )
    crew: list[PayrollCrewMemberSchema] = Field(default_factory=list)
    price_rub_per_m: Decimal | None = Field(None, ge=0)
    variable_rub_per_m: Decimal | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> "PayrollPreviewRequest":
        if self.items and self.meters_total is not None:
            raise ValueError("Метры задаются списком по породам или одной суммой, не обоими сразу.")
        if self.downtime and self.shifts is None:
            raise ValueError("Простои задаются вместе с фактическими сменами вахты.")
        codes = [member.position_code for member in self.crew]
        if len(codes) != len(set(codes)):
            raise ValueError("Должность в экипаже указывается один раз: людей в смене задаёт headcount.")
        return self


class PayrollRowSchema(BaseModel):
    code: str
    name: str
    kind: Literal["ACCRUAL", "SUBTOTAL", "INFO", "COST", "TOTAL"]
    amount_rub: float
    formula: str


class PayrollMeterRowSchema(BaseModel):
    label: str
    meters: float
    f: float | None
    k_f: float
    diameter_mm: float
    k_d: float
    normalized: float


class PayrollMetersSchema(BaseModel):
    total: float
    physical: float
    contract_k: float
    factor: float
    rows: list[PayrollMeterRowSchema]


class PayrollShiftsSchema(BaseModel):
    shifts: float
    effective: float
    excusable_hours: float
    maintenance_hours: float
    written_off_share: float | None


class PayrollTierSchema(BaseModel):
    lower: float
    upper: float | None
    rate: float
    units: float
    amount: float


class PayrollPremiumSchema(BaseModel):
    scale_type: str
    gamma: float | None
    norm_per_shift: float | None
    rate_norm: float | None
    ceiling_per_shift: float | None
    rate_ceiling: float | None
    output: float
    effective_shifts: float
    pace: float
    per_shift: float
    last_rate: float
    mean_rate: float | None
    total: float
    tiers: list[PayrollTierSchema]


class PayrollSharePointSchema(BaseModel):
    pace: float
    crew_share: float
    main_share: float


class PayrollCrewCostSchema(BaseModel):
    position_code: str
    name: str
    headcount: float
    cost_factor: float


class PayrollMarginSchema(BaseModel):
    status: Literal["CHECKED", "NOT_CHECKED", "NO_MARGIN", "NOT_APPLICABLE"]
    threshold: float
    price_rub_per_m: float | None
    variable_rub_per_m: float | None
    margin_rub_per_m: float | None
    plan: PayrollSharePointSchema | None
    ceiling: PayrollSharePointSchema | None
    crew: list[PayrollCrewCostSchema]


class PayrollSeriesPointSchema(BaseModel):
    pace: float
    rate: float
    per_shift: float


class PayrollFlagSchema(BaseModel):
    code: Literal["DOWNTIME_OVER_25", "PACE_ABOVE_CEILING", "MARGIN_SHARE_ABOVE_WARN"]
    message: str


class PayrollPreviewResponse(BaseModel):
    reference_revision_id: str
    position_code: str
    position_name: str
    site_code: str
    year: int
    rows: list[PayrollRowSchema]
    gross_rub: float
    company_cost_rub: float
    meters: PayrollMetersSchema | None
    shifts: PayrollShiftsSchema
    premium: PayrollPremiumSchema | None
    premium_cost_factor: float
    premium_cost_factor_formula: str
    margin: PayrollMarginSchema
    series: list[PayrollSeriesPointSchema]
    flags: list[PayrollFlagSchema]
    warnings: list[str]
    lineage: dict[str, str]
