"""Схемы остальных разделов: инфраструктура, операции, БВР, рынок.

Разделы здесь либо системные (единицы, операции, пакеты — их наполняет код,
а не пользователь), либо небольшие, и заводить под каждый отдельный модуль
незачем.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from cost.v2.schemas.base import RefField, ReferencePayload, UnitField

__all__ = [
    "UnitPayload",
    "OperationPayload",
    "WorkPackagePayload",
    "BasePayload",
    "WarehousePayload",
    "RoutePayload",
    "RockPayload",
    "BlastDesignParameterPayload",
    "BenchSurfaceConditionPayload",
    "StakeoutModePayload",
    "SiteInfrastructurePayload",
    "SubcontractRatePayload",
    "MarketPricePayload",
]


class UnitPayload(ReferencePayload):
    symbol: str = Field(default="", description="Обозначение")
    dimension: str = Field(default="", title="Размерность", description="Размерность: mass, length, volume, time, count")
    factor_to_base: Decimal | None = UnitField(
        "", title="Коэффициент к базовой", description="Коэффициент перевода в базовую единицу", default=None
    )


class OperationPayload(ReferencePayload):
    stage: str | None = Field(default=None, description="Этап работ")
    unit: str | None = RefField("units", description="Единица измерения операции", default=None)
    driver: str | None = Field(default=None, description="Драйвер объёма операции")
    resource_code: str | None = RefField(
        "resource_pools", title="Ресурсный пул", description="Ресурсный пул, чью мощность потребляет операция", default=None
    )
    description: str | None = Field(default=None, description="Описание")


class WorkPackagePayload(ReferencePayload):
    operations: list[Any] = Field(default_factory=list, description="Состав операций пакета")
    description: str | None = Field(default=None, description="Описание пакета")


class BasePayload(ReferencePayload):
    production_unit_code: str | None = RefField("production_units", description="Юнит", default=None)
    address: str | None = Field(default=None, description="Адрес")
    monthly_rub: Decimal | None = UnitField("₽/мес", description="Содержание базы", default=None)


class WarehousePayload(ReferencePayload):
    production_unit_code: str | None = RefField("production_units", description="Юнит", default=None)
    resource_code: str | None = RefField("resource_pools", description="Пул ёмкости склада", default=None)
    area_m2: Decimal | None = UnitField("м²", description="Площадь хранения", default=None)
    licence_number: str | None = Field(default=None, description="Номер лицензии")


class RoutePayload(ReferencePayload):
    from_code: str | None = Field(default=None, description="Откуда")
    to_code: str | None = Field(default=None, description="Куда")
    distance_km: Decimal | None = UnitField("км", description="Расстояние", default=None)
    cargo_kind: str | None = Field(default=None, description="Тип груза")


class RockPayload(ReferencePayload):
    density_t_m3: Decimal | None = UnitField("т/м³", description="Плотность", default=None)
    hardness_f: Decimal | None = UnitField("f", description="Крепость по Протодьяконову", default=None)
    fracture_class: str | None = Field(default=None, description="Класс трещиноватости")


class BlastDesignParameterPayload(ReferencePayload):
    value: Decimal | None = UnitField("", description="Значение норматива", default=None)
    unit: str | None = RefField("units", description="Единица измерения", default=None)
    description: str | None = Field(default=None, description="Описание")


class BenchSurfaceConditionPayload(ReferencePayload):
    productivity_factor: Decimal = UnitField(
        "доля", description="Поправка производительности", default=Decimal("1"), ge=0
    )


class StakeoutModePayload(ReferencePayload):
    contractor_share: Decimal = UnitField(
        "доля", title="Доля подрядчика", description="Доля скважин, выносимых подрядчиком", default=Decimal("1"), ge=0, le=1
    )


class SiteInfrastructurePayload(ReferencePayload):
    required_fields: list[str] = Field(
        default_factory=list, title="Заполняемые поля", description="Поля, заполняемые по объекту"
    )


class SubcontractRatePayload(ReferencePayload):
    counterparty_code: str | None = RefField("counterparties", description="Субподрядчик", default=None)
    operation_code: str | None = RefField("operations", description="Операция", default=None)
    unit: str | None = RefField("units", description="Единица", default=None)
    rate_rub: Decimal = UnitField("₽/ед.", description="Ставка без НДС", default=Decimal("0"))


class MarketPricePayload(ReferencePayload):
    scope: Literal["BLOCK", "M3", "TON"] = Field(default="M3", description="База цены")
    price_rub: Decimal = UnitField("₽/ед.", description="Рыночная цена без НДС", default=Decimal("0"))
    site_code: str | None = RefField("sites", description="Объект", default=None)
