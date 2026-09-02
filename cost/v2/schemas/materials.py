"""Схемы разделов «Материалы»: номенклатура, цены, нормативные потери."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from cost.v2.schemas.base import RefField, ReferencePayload, UnitField

__all__ = ["MaterialPayload", "MaterialPricePayload", "MaterialLossNormPayload"]


class MaterialPayload(ReferencePayload):
    unit: str | None = RefField("units", description="Единица измерения", default=None)
    material_kind: str | None = Field(default=None, description="Вид: ВВ, СВ, СИ, ТМЦ")
    category: str | None = Field(default=None, description="Категория номенклатуры")
    power_mj_kg: Decimal | None = UnitField("МДж/кг", description="Энергия взрывчатого вещества", default=None)
    mass_kg: Decimal | None = UnitField("кг", description="Масса единицы", default=None)
    length_m: Decimal | None = UnitField("м", description="Длина единицы", default=None)
    storage_class: Literal["BULK", "CARTRIDGE", "NSI", "NONE"] = Field(
        default="NONE", description="Класс хранения — определяет потребление ёмкости склада ВМ"
    )
    delivery_route_kind: Literal["FROM_WAREHOUSE", "DIRECT_TO_SITE"] = Field(
        default="FROM_WAREHOUSE", description="Откуда доставляется на объект"
    )
    density_t_m3: Decimal | None = UnitField("т/м³", description="Плотность", default=None)


class MaterialPricePayload(ReferencePayload):
    material_code: str = RefField("materials", description="Материал")
    unit: str | None = RefField("units", description="Единица измерения цены", default=None)
    supplier_code: str | None = RefField("counterparties", description="Поставщик", default=None)
    price_rub: Decimal = UnitField("₽/ед.", description="Цена без НДС", default=Decimal("0"))
    delivery_rub: Decimal = UnitField("₽/ед.", description="Доставка в цене", default=Decimal("0"))


class MaterialLossNormPayload(ReferencePayload):
    material_code: str = RefField("materials", description="Материал")
    operation_code: str | None = RefField("operations", description="Операция", default=None)
    loss_rate: Decimal = UnitField(
        "доля", description="Нормативные потери", default=Decimal("0"), ge=0, le=1
    )
