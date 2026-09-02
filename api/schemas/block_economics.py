"""Контракты REST API вкладки «Экономика» — модель себестоимости блока."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from cost.model.inputs import ModelParameters


class CrewMemberSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_code: str = Field(..., min_length=1, max_length=80)
    headcount: Decimal = Field(Decimal("1"), ge=0)
    # Пусто — взять норматив должности либо вывести из производительности техники.
    shifts_per_block: Decimal | None = Field(None, ge=0)


class ModelParametersSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_code: str = Field(..., min_length=1, max_length=80)
    site_code: str = Field("", max_length=80)
    reference_revision_id: str = ""
    unit_plan_volume_m3: Decimal = Field(Decimal("0"), ge=0)
    rig_code: str | None = None
    rig_plan_shifts: Decimal | None = Field(None, ge=0)
    szm_code: str | None = None
    delivery_truck_code: str | None = None
    crew: list[CrewMemberSchema] = Field(default_factory=list)
    drilling_executor: Literal["OWN", "SUBCONTRACTOR"] = "OWN"
    overhead_rate: Decimal | None = Field(None, ge=0, le=1)
    target_margin_rate: Decimal | None = Field(None, ge=0, le=1)
    vat_rate: Decimal | None = Field(None, ge=0, le=1)

    def to_domain(self) -> ModelParameters:
        return ModelParameters.from_dict(self.model_dump(mode="json"))


class BlockEconomicsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_passport_id: str = Field(..., min_length=1)
    parameters: ModelParametersSchema


class BlockEconomicsRunRequest(BlockEconomicsRequest):
    name: str = Field(..., min_length=1, max_length=300)


class CostLineSchema(BaseModel):
    month: str = ""
    service_line_id: str = ""
    service_line_name: str = ""
    operation_code: str = ""
    cost_item_code: str
    cost_item_name: str
    layer: str
    amount_rub: float
    formula: str = ""
    resource_code: str = ""


class NaturalDriversSchema(BaseModel):
    values: dict[str, str]
    lineage: dict[str, str]
    warnings: list[str] = Field(default_factory=list)


class CapacityWarningSchema(BaseModel):
    resource_code: str
    resource_name: str
    required: float
    available: float | None = None
    unit: str
    message: str


class BlockEconomicsSchema(BaseModel):
    model_version: str
    block_volume_m3: float
    lines: list[CostLineSchema]
    layer_totals: dict[str, float]
    price_per_m3: dict[str, float]
    markup: dict[str, float]
    natural: NaturalDriversSchema
    capacity: list[CapacityWarningSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EconomicsRunSchema(BaseModel):
    id: str
    organization_id: str
    name: str
    technical_passport_id: str
    package_code: str
    reference_revision_id: str
    parameters: dict[str, Any]
    result: dict[str, Any]
    created_at: str
    created_by: str


class EconomicsRunSummarySchema(BaseModel):
    id: str
    name: str
    technical_passport_id: str
    package_code: str
    reference_revision_id: str
    created_at: str
    created_by: str
    price_per_m3: dict[str, float] = Field(default_factory=dict)


class RunCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_ids: list[str] = Field(..., min_length=2, max_length=3)


class CompareCellSchema(BaseModel):
    run_id: str
    amount_rub: float


class CompareRowSchema(BaseModel):
    cost_item_code: str
    cost_item_name: str
    layer: str
    amounts: list[CompareCellSchema]
    delta_rub: float


class RunCompareResponse(BaseModel):
    runs: list[EconomicsRunSummarySchema]
    rows: list[CompareRowSchema]
    price_per_m3: dict[str, list[float]]
    delta_price_per_m3: dict[str, float]


class SensitivityRowSchema(BaseModel):
    code: str
    label: str
    base_price_rub_m3: float
    price_minus_rub_m3: float
    price_plus_rub_m3: float
    delta_rub_m3: float


class SensitivityResponse(BaseModel):
    rows: list[SensitivityRowSchema]


class ModelDefaultsResponse(BaseModel):
    parameters: ModelParametersSchema
    passport: dict[str, Any]
    package_operations: list[str]
    rigs: list[dict[str, str]]
    szm: list[dict[str, str]]
    delivery_trucks: list[dict[str, str]]
    positions: list[dict[str, str]]
    packages: list[dict[str, str]]
    sites: list[dict[str, str]]
    reference_revision_id: str
