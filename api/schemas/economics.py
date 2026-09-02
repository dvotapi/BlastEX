"""Pydantic-контракты REST API экономической модели Cost V2."""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.cost import BlockGeometrySchema
from cost.v2.models import (
    CapacityChoice,
    EconomicScenario,
    MonthlyPlan,
    OperationOverride,
    ReferenceItem,
    ServiceLine,
    SiteConditions,
)


class ReferenceItemSchema(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=300)
    payload: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    valid_from: str | None = None
    valid_to: str | None = None
    source: str = ""
    comment: str = ""
    revision: int = Field(1, ge=1)

    def to_domain(self) -> ReferenceItem:
        return ReferenceItem.from_dict(self.model_dump())


class ReferenceSnapshotSchema(BaseModel):
    revision_id: str
    published_at: str | None = None
    published_by: str
    sections: dict[str, list[ReferenceItemSchema]]
    section_catalog: list[dict[str, str]] = Field(default_factory=list)
    group_catalog: list[dict[str, str]] = Field(default_factory=list)


class ReferenceValidateRequest(BaseModel):
    sections: dict[str, list[ReferenceItemSchema]]


class ReferencePublishRequest(ReferenceValidateRequest):
    base_revision: str
    comment: str = ""


class ReferenceValidationIssueSchema(BaseModel):
    level: Literal["error", "warning"]
    section: str
    code: str
    message: str
    # Пусто, если ошибка относится к записи целиком, а не к отдельному полю.
    field: str = ""


class ReferenceValidationResponse(BaseModel):
    valid: bool
    issues: list[ReferenceValidationIssueSchema]


class TechnicalDriverRequest(BaseModel):
    block: BlockGeometrySchema
    existing_physical: dict[str, Decimal] = Field(default_factory=dict)
    source_id: str | None = None


class TechnicalDriverResponse(BaseModel):
    source_type: Literal["BLAST_GEOMETRY"]
    source_id: str | None = None
    physical: dict[str, Decimal]
    lineage: dict[str, str]


class ReferenceRevisionSchema(BaseModel):
    id: str
    organization_id: str
    sequence_no: int
    published_at: str
    published_by: str
    comment: str


class MonthlyPlanSchema(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    billed_quantity: Decimal = Field(Decimal("0"), ge=0)
    physical: dict[str, Decimal] = Field(default_factory=dict)
    technical_passport_id: str | None = None

    def to_domain(self) -> MonthlyPlan:
        return MonthlyPlan.from_dict(self.model_dump())


class OperationOverrideSchema(BaseModel):
    operation_code: str
    executor: Literal[
        "OWN", "CUSTOMER", "SUBCONTRACTOR", "THIRD_PARTY_SUPPLIER", "OUT_OF_SCOPE"
    ] = "OWN"
    enabled: bool | None = None
    quantity: Decimal | None = Field(None, ge=0)
    subcontract_rate_rub: Decimal | None = Field(None, ge=0)
    supervision_cost_rub: Decimal = Field(Decimal("0"), ge=0)

    def to_domain(self) -> OperationOverride:
        return OperationOverride.from_dict(self.model_dump())


class SiteConditionsSchema(BaseModel):
    bench_surface_condition_code: str = "PREPARED"
    uncleared_rock_share_pct: Decimal = Field(Decimal("0"), ge=0, le=100)
    drilling_productivity_factor: Decimal = Field(Decimal("1"), gt=0)
    stakeout_mode: Literal[
        "CUSTOMER_CONTROL_POINTS", "CUSTOMER_ALL_HOLES", "CONTRACTOR_ALL_HOLES"
    ] = "CUSTOMER_ALL_HOLES"
    refueling_available: bool = True
    customer_provides_fuel: bool = False
    maintenance_box_available: bool = True
    canteen_available: bool = True
    accommodation_available: bool = True
    meal_cost_rub_person_day: Decimal = Field(Decimal("0"), ge=0)
    accommodation_cost_rub_person_night: Decimal = Field(Decimal("0"), ge=0)
    own_fuel_delivery_cost_rub_trip: Decimal = Field(Decimal("0"), ge=0)
    mobile_maintenance_cost_rub_shift: Decimal = Field(Decimal("0"), ge=0)
    infrastructure_comment: str = ""

    def to_domain(self) -> SiteConditions:
        return SiteConditions.from_dict(self.model_dump())


class ServiceLineSchema(BaseModel):
    id: str
    name: str
    package_code: str
    customer_code: str = ""
    site_code: str = ""
    billing_unit: str
    market_price_rub: Decimal = Field(Decimal("0"), ge=0)
    monthly_plans: list[MonthlyPlanSchema] = Field(default_factory=list)
    operation_overrides: list[OperationOverrideSchema] = Field(default_factory=list)
    site_conditions: SiteConditionsSchema = Field(default_factory=SiteConditionsSchema)
    options: dict[str, Any] = Field(default_factory=dict)
    replaces_service_line_id: str | None = None

    def to_domain(self) -> ServiceLine:
        return ServiceLine.from_dict(self.model_dump())


class CapacityChoiceSchema(BaseModel):
    resource_code: str
    mode: Literal["OVERTIME", "RENT", "SUBCONTRACT", "NEW_ASSET"] = "OVERTIME"
    excess_rate_rub: Decimal = Field(Decimal("0"), ge=0)
    step_capacity: Decimal = Field(Decimal("0"), ge=0)
    step_cost_rub: Decimal = Field(Decimal("0"), ge=0)

    def to_domain(self) -> CapacityChoice:
        return CapacityChoice.from_dict(self.model_dump())


class EconomicScenarioSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    name: str = Field(..., min_length=1, max_length=300)
    description: str = ""
    production_unit_code: str = Field(..., min_length=1, max_length=80)
    baseline_service_lines: list[ServiceLineSchema] = Field(default_factory=list)
    candidate_service_lines: list[ServiceLineSchema] = Field(default_factory=list)
    capacity_choices: list[CapacityChoiceSchema] = Field(default_factory=list)
    reference_revision_id: str | None = None

    def to_domain(self) -> EconomicScenario:
        return EconomicScenario.from_dict(self.model_dump())


class StoredScenarioSchema(EconomicScenarioSchema):
    organization_id: str
    created_at: str
    created_by: str
    updated_at: str
    updated_by: str


class CalculationRunSchema(BaseModel):
    id: str
    organization_id: str
    scenario_id: str | None
    reference_revision_id: str
    formula_version: str
    input_snapshot: dict[str, Any]
    result: dict[str, Any]
    created_at: str
    created_by: str
    calculation_scope: Literal["EVENT", "SITE", "UNIT"] = "UNIT"
    technical_passport_id: str | None = None
    site_code: str = ""
    period: str = ""
    technical_formula_version: str = ""


class TechnicalPassportCreateSchema(BaseModel):
    site_code: str = Field(..., min_length=1, max_length=80)
    object_name: str = Field(..., min_length=1, max_length=300)
    previous_passport_id: str | None = None
    reference_revision_id: str | None = None
    formula_version: str = Field("blast-geometry-v1", min_length=1, max_length=80)
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    selected_variant: dict[str, Any] = Field(default_factory=dict)
    block: BlockGeometrySchema
    existing_physical: dict[str, Decimal] = Field(default_factory=dict)


class TechnicalPassportSchema(BaseModel):
    id: str
    organization_id: str
    site_code: str
    object_name: str
    version_no: int
    previous_passport_id: str | None = None
    reference_revision_id: str
    formula_version: str
    input_snapshot: dict[str, Any]
    selected_variant: dict[str, Any]
    block_snapshot: dict[str, Any]
    physical: dict[str, Decimal]
    lineage: dict[str, str]
    created_at: str
    created_by: str


class EventCalculationRequest(BaseModel):
    technical_passport_id: str
    name: str = Field("Один взрыв", min_length=1, max_length=300)
    production_unit_code: str = Field(..., min_length=1, max_length=80)
    package_code: str = Field(..., min_length=1, max_length=80)
    customer_code: str = ""
    billing_unit: str = "M3"
    billed_quantity: Decimal | None = Field(None, ge=0)
    market_price_rub: Decimal = Field(Decimal("0"), ge=0)
    month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    operation_overrides: list[OperationOverrideSchema] = Field(default_factory=list)
    site_conditions: SiteConditionsSchema = Field(default_factory=SiteConditionsSchema)
    options: dict[str, Any] = Field(default_factory=dict)
    reference_revision_id: str | None = None
