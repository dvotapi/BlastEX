"""Схемы разделов «Материалы»: номенклатура, цены, нормативные потери."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from cost.v2.schemas.base import RefField, ReferencePayload, UnitField

__all__ = [
    "NomenclatureRole",
    "MaterialPayload",
    "MaterialPricePayload",
    "MaterialLossNormPayload",
]


# Роль позиции в смете блока. `material_kind` остаётся свободным текстом из
# Cost V1 («ВВ», «СИ», «ТМЦ», у части записей пусто) и машинному разбору не
# поддаётся, поэтому связь номенклатуры с расчётом задаёт отдельное поле:
# по нему вкладка «Экономика блока» наполняет списки выбора, а модель
# сопоставляет позицию с драйвером технического паспорта.
NomenclatureRole = Literal[
    "EXPLOSIVE",
    "BOOSTER",
    "NSI_DOWNHOLE",
    "NSI_SURFACE",
    "NSI_START",
    "DETONATOR_ELECTRIC",
    "DRILL_TOOL",
    "OTHER",
]


class MaterialPayload(ReferencePayload):
    unit: str | None = RefField("units", description="Единица измерения", default=None)
    material_kind: str | None = Field(default=None, description="Вид: ВВ, СВ, СИ, ТМЦ")
    nomenclature_role: NomenclatureRole = Field(
        default="OTHER",
        title="Роль в смете",
        description=(
            "Чем позиция становится в расчёте блока: основное ВВ, промежуточный "
            "детонатор, скважинное, поверхностное или стартовое НСИ, "
            "электродетонатор, буровой инструмент"
        ),
    )
    category: str | None = Field(default=None, description="Категория номенклатуры")
    power_mj_kg: Decimal | None = UnitField(
        "МДж/кг", title="Энергия ВВ", description="Энергия взрывчатого вещества", default=None
    )
    mass_kg: Decimal | None = UnitField("кг", description="Масса единицы", default=None)
    length_m: Decimal | None = UnitField("м", description="Длина единицы", default=None)
    lifetime_m: Decimal | None = UnitField("м", title="Ресурс", description="Ресурс бурового инструмента", default=None)
    diameter_mm: Decimal | None = UnitField("мм", title="Диаметр", description="Диаметр инструмента", default=None)
    thread_type: str | None = Field(
        default=None, title="Хвостовик / резьба", description="Тип хвостовика или резьбы"
    )
    delay_ms: Decimal | None = UnitField("мс", title="Замедление", description="Стандартный интервал замедления СИ", default=None)
    storage_class: Literal["BULK", "CARTRIDGE", "NSI", "NONE"] = Field(
        default="NONE", description="Класс хранения — определяет потребление ёмкости склада ВМ"
    )
    delivery_route_kind: Literal["FROM_WAREHOUSE", "DIRECT_TO_SITE"] = Field(
        default="FROM_WAREHOUSE", title="Маршрут доставки", description="Откуда доставляется на объект"
    )
    density_t_m3: Decimal | None = UnitField("т/м³", description="Плотность", default=None)
    chart_label: str | None = Field(
        default=None, title="Подпись на схеме", description="Короткая подпись ВВ на схеме заряда"
    )


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
