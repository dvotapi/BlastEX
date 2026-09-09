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


class ServiceChargeSchema(BaseModel):
    """Услуга, введённая на вкладке: сумма живёт в параметрах прогона."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=300)
    amount_rub: Decimal = Field(Decimal("0"), ge=0)
    layer: Literal["variable", "project_direct", "production"] = "project_direct"
    operation_code: str = Field(..., min_length=1, max_length=80)
    per_shift: bool = False


class ServiceToReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: ServiceChargeSchema


class ServiceToReferenceResponse(BaseModel):
    section: Literal["cost_rules"]
    code: str
    created: bool
    reference_revision_id: str


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
    emulsion_truck_code: str | None = None
    # Код типа техники → плановые смены в месяц; пусто — норматив справочника.
    machine_plan_shifts: dict[str, Decimal] = Field(default_factory=dict)
    crew: list[CrewMemberSchema] = Field(default_factory=list)
    services: list[ServiceChargeSchema] = Field(default_factory=list)
    drilling_executor: Literal["OWN", "SUBCONTRACTOR"] = "OWN"
    # Роль номенклатуры → код материала; пустое значение означает «не выбрано».
    nomenclature: dict[str, str] = Field(default_factory=dict)
    electric_detonators_qty: Decimal = Field(Decimal("0"), ge=0)
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
    # Раздел бумажной сметы и колонки нормы: интерфейс группирует и считает
    # по ним, а не разбирает формулу.
    section: str = "OVERHEAD"
    quantity: float | None = None
    unit: str = ""
    unit_price_rub: float | None = None
    # Роль номенклатуры («основное ВВ»): постоянна для статьи, в отличие от
    # cost_item_name, которое называет выбранный материал. Пусто у строк без
    # выбора номенклатуры.
    role_label: str | None = None


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
    # Ревизия справочников, на которой посчитано: при пустой ревизии в
    # параметрах это актуальная, и сметчик должен видеть какая.
    reference_revision_id: str = ""


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


class VariantRequest(BaseModel):
    """Один столбец сметы: имя и свой набор параметров."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    parameters: ModelParametersSchema


class VariantsRequest(BaseModel):
    """Инвариант «одна ревизия на все колонки» — здесь, а не в докстринге
    маршрута: `VariantRequest.parameters.reference_revision_id` разделяет тип
    с одиночным расчётом (`BlockEconomicsRequest`), где своя ревизия у
    каждого запроса осмысленна, и без отдельного поля здесь у запроса не
    было бы места сказать, что все варианты считаются на одном снимке."""

    model_config = ConfigDict(extra="forbid")

    technical_passport_id: str = Field(..., min_length=1)
    # Пусто — актуальная ревизия, как и в ModelParametersSchema. Поля
    # `reference_revision_id` внутри параметров вариантов на выбор снимка не
    # влияют: см. `block_economics_variants` в api/routers/block_economics.py.
    reference_revision_id: str = ""
    # Четыре колонки — предел читаемой таблицы и предел бумажной сметы.
    variants: list[VariantRequest] = Field(..., min_length=1, max_length=4)


class VariantResultSchema(BaseModel):
    name: str
    economics: BlockEconomicsSchema


class VariantsResponse(BaseModel):
    reference_revision_id: str
    variants: list[VariantResultSchema]


class SensitivityRowSchema(BaseModel):
    code: str
    label: str
    base_price_rub_m3: float
    price_minus_rub_m3: float
    price_plus_rub_m3: float
    delta_rub_m3: float


class SensitivityResponse(BaseModel):
    rows: list[SensitivityRowSchema]
    reference_revision_id: str = ""


class ModelDefaultsResponse(BaseModel):
    parameters: ModelParametersSchema
    passport: dict[str, Any]
    package_operations: list[str]
    # Операции пакета с подписями: селект услуги показывает название, не код.
    operations: list[dict[str, str]] = Field(default_factory=list)
    # Роль номенклатуры → позиции с ценой на дату расчёта.
    nomenclature: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    rigs: list[dict[str, str]]
    szm: list[dict[str, str]]
    delivery_trucks: list[dict[str, str]]
    emulsion_trucks: list[dict[str, str]] = Field(default_factory=list)
    positions: list[dict[str, str]]
    packages: list[dict[str, str]]
    sites: list[dict[str, str]]
    reference_revision_id: str
