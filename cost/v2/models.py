"""Чистые доменные модели Cost V2.

Модуль намеренно не зависит от FastAPI, Pydantic и SQLAlchemy: один и тот же
расчётный движок используется REST API, тестами и будущими импортёрами.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Mapping


MONEY_QUANT = Decimal("0.01")
QUANTITY_QUANT = Decimal("0.000001")


def decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Безопасно преобразовать входное число в Decimal без float-артефактов."""

    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def quantity(value: Decimal) -> Decimal:
    return value.quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP)


class Executor(str, Enum):
    OWN = "OWN"
    CUSTOMER = "CUSTOMER"
    SUBCONTRACTOR = "SUBCONTRACTOR"
    THIRD_PARTY_SUPPLIER = "THIRD_PARTY_SUPPLIER"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class CostLayer(str, Enum):
    VARIABLE = "variable"
    PROJECT_DIRECT = "project_direct"
    PRODUCTION = "production"
    FULL = "full"


class CostBehavior(str, Enum):
    VARIABLE = "VARIABLE"
    FIXED = "FIXED"
    STEP_FIXED = "STEP_FIXED"
    MIXED = "MIXED"
    EVENT = "EVENT"
    ALLOCATED = "ALLOCATED"


class StakeoutMode(str, Enum):
    CUSTOMER_CONTROL_POINTS = "CUSTOMER_CONTROL_POINTS"
    CUSTOMER_ALL_HOLES = "CUSTOMER_ALL_HOLES"
    CONTRACTOR_ALL_HOLES = "CONTRACTOR_ALL_HOLES"


class CapacityMode(str, Enum):
    OVERTIME = "OVERTIME"
    RENT = "RENT"
    SUBCONTRACT = "SUBCONTRACT"
    NEW_ASSET = "NEW_ASSET"


@dataclass(frozen=True)
class ReferenceItem:
    code: str
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    valid_from: date | None = None
    valid_to: date | None = None
    source: str = ""
    comment: str = ""
    revision: int = 1

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReferenceItem":
        return cls(
            code=str(data.get("code", "")).strip(),
            name=str(data.get("name", "")).strip(),
            payload=dict(data.get("payload") or {}),
            is_active=bool(data.get("is_active", True)),
            valid_from=_parse_date(data.get("valid_from")),
            valid_to=_parse_date(data.get("valid_to")),
            source=str(data.get("source", "")),
            comment=str(data.get("comment", "")),
            revision=int(data.get("revision", 1)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "payload": self.payload,
            "is_active": self.is_active,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "source": self.source,
            "comment": self.comment,
            "revision": self.revision,
        }


@dataclass(frozen=True)
class ReferenceSnapshot:
    revision_id: str
    sections: dict[str, tuple[ReferenceItem, ...]]
    published_at: datetime | None = None
    published_by: str = ""

    def active_items(self, section: str) -> tuple[ReferenceItem, ...]:
        return tuple(item for item in self.sections.get(section, ()) if item.is_active)

    def item(self, section: str, code: str) -> ReferenceItem | None:
        return next((item for item in self.active_items(section) if item.code == code), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_by": self.published_by,
            "sections": {
                key: [item.to_dict() for item in values]
                for key, values in self.sections.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReferenceSnapshot":
        raw_sections = dict(data.get("sections") or {})
        return cls(
            revision_id=str(data.get("revision_id", "")),
            published_at=_parse_datetime(data.get("published_at")),
            published_by=str(data.get("published_by", "")),
            sections={
                str(section): tuple(ReferenceItem.from_dict(item) for item in items)
                for section, items in raw_sections.items()
            },
        )


@dataclass(frozen=True)
class MonthlyPlan:
    month: str
    billed_quantity: Decimal
    physical: dict[str, Decimal] = field(default_factory=dict)
    technical_passport_id: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MonthlyPlan":
        return cls(
            month=str(data.get("month", "")),
            billed_quantity=decimal_value(data.get("billed_quantity")),
            physical={
                str(key): decimal_value(value)
                for key, value in dict(data.get("physical") or {}).items()
            },
            technical_passport_id=(
                str(data["technical_passport_id"])
                if data.get("technical_passport_id")
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "billed_quantity": str(self.billed_quantity),
            "physical": {key: str(value) for key, value in self.physical.items()},
            "technical_passport_id": self.technical_passport_id,
        }


@dataclass(frozen=True)
class OperationOverride:
    operation_code: str
    executor: Executor = Executor.OWN
    enabled: bool | None = None
    quantity: Decimal | None = None
    subcontract_rate_rub: Decimal | None = None
    supervision_cost_rub: Decimal = Decimal("0")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OperationOverride":
        raw_quantity = data.get("quantity")
        raw_rate = data.get("subcontract_rate_rub")
        return cls(
            operation_code=str(data.get("operation_code", "")),
            executor=Executor(str(data.get("executor", Executor.OWN.value))),
            enabled=data.get("enabled") if data.get("enabled") is None else bool(data.get("enabled")),
            quantity=None if raw_quantity in (None, "") else decimal_value(raw_quantity),
            subcontract_rate_rub=None if raw_rate in (None, "") else decimal_value(raw_rate),
            supervision_cost_rub=decimal_value(data.get("supervision_cost_rub")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_code": self.operation_code,
            "executor": self.executor.value,
            "enabled": self.enabled,
            "quantity": str(self.quantity) if self.quantity is not None else None,
            "subcontract_rate_rub": (
                str(self.subcontract_rate_rub) if self.subcontract_rate_rub is not None else None
            ),
            "supervision_cost_rub": str(self.supervision_cost_rub),
        }


@dataclass(frozen=True)
class SiteConditions:
    bench_surface_condition_code: str = "PREPARED"
    uncleared_rock_share_pct: Decimal = Decimal("0")
    drilling_productivity_factor: Decimal = Decimal("1")
    stakeout_mode: StakeoutMode = StakeoutMode.CUSTOMER_ALL_HOLES
    refueling_available: bool = True
    customer_provides_fuel: bool = False
    maintenance_box_available: bool = True
    canteen_available: bool = True
    accommodation_available: bool = True
    meal_cost_rub_person_day: Decimal = Decimal("0")
    accommodation_cost_rub_person_night: Decimal = Decimal("0")
    own_fuel_delivery_cost_rub_trip: Decimal = Decimal("0")
    mobile_maintenance_cost_rub_shift: Decimal = Decimal("0")
    infrastructure_comment: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "SiteConditions":
        data = data or {}
        return cls(
            bench_surface_condition_code=str(data.get("bench_surface_condition_code", "PREPARED")),
            uncleared_rock_share_pct=decimal_value(data.get("uncleared_rock_share_pct")),
            drilling_productivity_factor=decimal_value(
                data.get("drilling_productivity_factor"), Decimal("1")
            ),
            stakeout_mode=StakeoutMode(
                str(data.get("stakeout_mode", StakeoutMode.CUSTOMER_ALL_HOLES.value))
            ),
            refueling_available=bool(data.get("refueling_available", True)),
            customer_provides_fuel=bool(data.get("customer_provides_fuel", False)),
            maintenance_box_available=bool(data.get("maintenance_box_available", True)),
            canteen_available=bool(data.get("canteen_available", True)),
            accommodation_available=bool(data.get("accommodation_available", True)),
            meal_cost_rub_person_day=decimal_value(data.get("meal_cost_rub_person_day")),
            accommodation_cost_rub_person_night=decimal_value(
                data.get("accommodation_cost_rub_person_night")
            ),
            own_fuel_delivery_cost_rub_trip=decimal_value(
                data.get("own_fuel_delivery_cost_rub_trip")
            ),
            mobile_maintenance_cost_rub_shift=decimal_value(
                data.get("mobile_maintenance_cost_rub_shift")
            ),
            infrastructure_comment=str(data.get("infrastructure_comment", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bench_surface_condition_code": self.bench_surface_condition_code,
            "uncleared_rock_share_pct": str(self.uncleared_rock_share_pct),
            "drilling_productivity_factor": str(self.drilling_productivity_factor),
            "stakeout_mode": self.stakeout_mode.value,
            "refueling_available": self.refueling_available,
            "customer_provides_fuel": self.customer_provides_fuel,
            "maintenance_box_available": self.maintenance_box_available,
            "canteen_available": self.canteen_available,
            "accommodation_available": self.accommodation_available,
            "meal_cost_rub_person_day": str(self.meal_cost_rub_person_day),
            "accommodation_cost_rub_person_night": str(self.accommodation_cost_rub_person_night),
            "own_fuel_delivery_cost_rub_trip": str(self.own_fuel_delivery_cost_rub_trip),
            "mobile_maintenance_cost_rub_shift": str(self.mobile_maintenance_cost_rub_shift),
            "infrastructure_comment": self.infrastructure_comment,
        }


@dataclass(frozen=True)
class ServiceLine:
    id: str
    name: str
    package_code: str
    customer_code: str
    site_code: str
    billing_unit: str
    market_price_rub: Decimal
    monthly_plans: tuple[MonthlyPlan, ...]
    operation_overrides: tuple[OperationOverride, ...] = ()
    site_conditions: SiteConditions = field(default_factory=SiteConditions)
    options: dict[str, Any] = field(default_factory=dict)
    replaces_service_line_id: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ServiceLine":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            package_code=str(data.get("package_code", "")),
            customer_code=str(data.get("customer_code", "")),
            site_code=str(data.get("site_code", "")),
            billing_unit=str(data.get("billing_unit", "")),
            market_price_rub=decimal_value(data.get("market_price_rub")),
            monthly_plans=tuple(
                MonthlyPlan.from_dict(item) for item in data.get("monthly_plans", [])
            ),
            operation_overrides=tuple(
                OperationOverride.from_dict(item)
                for item in data.get("operation_overrides", [])
            ),
            site_conditions=SiteConditions.from_dict(data.get("site_conditions")),
            options=dict(data.get("options") or {}),
            replaces_service_line_id=(
                str(data["replaces_service_line_id"])
                if data.get("replaces_service_line_id")
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "package_code": self.package_code,
            "customer_code": self.customer_code,
            "site_code": self.site_code,
            "billing_unit": self.billing_unit,
            "market_price_rub": str(self.market_price_rub),
            "monthly_plans": [item.to_dict() for item in self.monthly_plans],
            "operation_overrides": [item.to_dict() for item in self.operation_overrides],
            "site_conditions": self.site_conditions.to_dict(),
            "options": self.options,
            "replaces_service_line_id": self.replaces_service_line_id,
        }


@dataclass(frozen=True)
class CapacityChoice:
    resource_code: str
    mode: CapacityMode
    excess_rate_rub: Decimal = Decimal("0")
    step_capacity: Decimal = Decimal("0")
    step_cost_rub: Decimal = Decimal("0")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CapacityChoice":
        return cls(
            resource_code=str(data.get("resource_code", "")),
            mode=CapacityMode(str(data.get("mode", CapacityMode.OVERTIME.value))),
            excess_rate_rub=decimal_value(data.get("excess_rate_rub")),
            step_capacity=decimal_value(data.get("step_capacity")),
            step_cost_rub=decimal_value(data.get("step_cost_rub")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_code": self.resource_code,
            "mode": self.mode.value,
            "excess_rate_rub": str(self.excess_rate_rub),
            "step_capacity": str(self.step_capacity),
            "step_cost_rub": str(self.step_cost_rub),
        }


@dataclass(frozen=True)
class EconomicScenario:
    id: str
    name: str
    production_unit_code: str
    baseline_service_lines: tuple[ServiceLine, ...]
    candidate_service_lines: tuple[ServiceLine, ...] = ()
    capacity_choices: tuple[CapacityChoice, ...] = ()
    reference_revision_id: str | None = None
    description: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EconomicScenario":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            production_unit_code=str(data.get("production_unit_code", "")),
            baseline_service_lines=tuple(
                ServiceLine.from_dict(item)
                for item in data.get("baseline_service_lines", [])
            ),
            candidate_service_lines=tuple(
                ServiceLine.from_dict(item)
                for item in data.get("candidate_service_lines", [])
            ),
            capacity_choices=tuple(
                CapacityChoice.from_dict(item) for item in data.get("capacity_choices", [])
            ),
            reference_revision_id=(
                str(data["reference_revision_id"])
                if data.get("reference_revision_id")
                else None
            ),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "production_unit_code": self.production_unit_code,
            "baseline_service_lines": [line.to_dict() for line in self.baseline_service_lines],
            "candidate_service_lines": [line.to_dict() for line in self.candidate_service_lines],
            "capacity_choices": [item.to_dict() for item in self.capacity_choices],
            "reference_revision_id": self.reference_revision_id,
        }


@dataclass(frozen=True)
class CostLine:
    month: str
    service_line_id: str
    service_line_name: str
    operation_code: str
    cost_item_code: str
    cost_item_name: str
    layer: CostLayer
    amount_rub: Decimal
    formula: str
    resource_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "service_line_id": self.service_line_id,
            "service_line_name": self.service_line_name,
            "operation_code": self.operation_code,
            "cost_item_code": self.cost_item_code,
            "cost_item_name": self.cost_item_name,
            "layer": self.layer.value,
            "amount_rub": float(money(self.amount_rub)),
            "formula": self.formula,
            "resource_code": self.resource_code,
        }


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
