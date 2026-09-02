"""Схемы разделов «Организация»: юниты, контрагенты, карьеры, ставки организации."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from cost.v2.schemas.base import RUB, RateField, RefField, ReferencePayload, UnitField

__all__ = [
    "ProductionUnitPayload",
    "CounterpartyPayload",
    "SitePayload",
    "OrganizationRatesPayload",
]


class ProductionUnitPayload(ReferencePayload):
    plan_volume_m3: Decimal | None = UnitField(
        "м³/мес", description="Плановый объём юнита в месяц — база распределения постоянных затрат", default=None
    )
    base_code: str | None = RefField("bases", description="Производственная база юнита", default=None)
    region: str | None = Field(default=None, description="Регион работы")


class CounterpartyPayload(ReferencePayload):
    role: Literal["CUSTOMER", "SUPPLIER", "SUBCONTRACTOR"] = Field(
        default="CUSTOMER", description="Роль контрагента"
    )
    inn: str | None = Field(default=None, description="ИНН")


class SitePayload(ReferencePayload):
    customer_code: str | None = RefField("counterparties", description="Заказчик объекта", default=None)
    production_unit_code: str | None = RefField(
        "production_units", description="Юнит, обслуживающий объект", default=None
    )
    rock_code: str | None = RefField("rocks", description="Порода по умолчанию", default=None)
    distance_from_base_km: Decimal | None = UnitField(
        "км", description="Расстояние от производственной базы", default=None
    )
    distance_from_warehouse_km: Decimal | None = UnitField(
        "км", description="Расстояние от склада ВМ", default=None
    )
    diesel_price_ton_rub: Decimal | None = UnitField(
        "₽/т", description="Цена дизельного топлива на объекте", default=None
    )
    customer_provides_fuel: bool = Field(default=False, description="Топливо предоставляет заказчик")
    blocks_per_mobilization: Decimal | None = UnitField(
        "блоков", description="Сколько блоков приходится на одну мобилизацию", default=None, ge=0
    )
    mobilization_rate_rub_per_km: Decimal | None = UnitField(
        "₽/км", description="Ставка мобилизации техники", default=None
    )
    mobilization_km: Decimal | None = UnitField(
        "км", description="Плечо мобилизации техники на объект", default=None
    )
    is_watered: bool = Field(default=False, description="Обводнённость блока по умолчанию")


class OrganizationRatesPayload(ReferencePayload):
    """Ставки и надбавки организации.

    Не расходы, а параметры: НДФЛ, взносы и НДС применяются к итогам расчёта.
    Одна активная запись на организацию, версионируется вместе со снимком.
    """

    income_tax_rate: Decimal = RateField(description="НДФЛ", default=Decimal("0.13"))
    social_contribution_rate: Decimal = RateField(description="Страховые взносы", default=Decimal("0.30"))
    injury_insurance_rate: Decimal = RateField(
        description="Взносы на травматизм по классу риска", default=Decimal("0.0042")
    )
    vacation_reserve_rate: Decimal = RateField(description="Резерв отпусков", default=Decimal("0.20"))
    salary_basis: Literal["GROSS", "NET"] = Field(
        default="GROSS", description="Оклады в справочнике заданы до НДФЛ (GROSS) или на руки (NET)"
    )
    overhead_rate: Decimal = RateField(description="Общехозяйственные расходы", default=Decimal("0.10"))
    target_margin_rate: Decimal = RateField(description="Целевая рентабельность", default=Decimal("0.10"))
    vat_rate: Decimal = RateField(description="НДС", default=Decimal("0.20"))
    per_diem_rub: Decimal = UnitField(
        "₽/чел-смена", description="Суточные", default=Decimal("0")
    )
    lodging_rub: Decimal = UnitField(
        "₽/чел-смена", description="Проживание", default=Decimal("0")
    )
    shift_hours: Decimal = UnitField("ч", description="Продолжительность смены", default=Decimal("11"))
