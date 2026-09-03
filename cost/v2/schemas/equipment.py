"""Схемы разделов «Техника»: типы, основные средства, пулы, нормы, условия бурения."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RefField, ReferencePayload, UnitField, field_error

__all__ = [
    "EquipmentTypePayload",
    "EquipmentAssetPayload",
    "ResourcePoolPayload",
    "ResourceNormPayload",
    "DrillingConditionPayload",
]


class EquipmentTypePayload(ReferencePayload):
    kind: Literal["DRILL_RIG", "SZM", "HAZMAT_TRUCK", "LIGHT_VEHICLE", "TRACTOR"] = Field(
        default="DRILL_RIG", description="Вид техники"
    )
    operation_code: str | None = RefField(
        "operations", title="Операция", description="Операция, чьи смены потребляет техника", default=None
    )
    norm_shifts_per_month: Decimal = UnitField(
        "см/мес", title="Смен в месяц", description="Плановая загрузка: смен в месяц", default=Decimal("21"), ge=0
    )
    maintenance_ratio: Decimal = UnitField(
        "доля", title="Доля ТОиР", description="Смен ТОиР на одну рабочую смену", default=Decimal("0"), ge=0, le=1
    )
    maintenance_mode: Literal["PER_SHIFT", "MONTHLY_BUDGET"] = Field(
        default="PER_SHIFT",
        description="ТОиР по сменам (износ от наработки) или месячным бюджетом (делится на плановые смены)",
    )
    maintenance_rub_per_shift: Decimal = UnitField("₽/см", description="ТОиР за смену", default=Decimal("0"))
    maintenance_monthly_rub: Decimal | None = UnitField(
        "₽/мес", description="Бюджет ТОиР в месяц (для режима MONTHLY_BUDGET)", default=None
    )
    spare_parts_rub_per_shift: Decimal = UnitField("₽/см", description="Запчасти за смену", default=Decimal("0"))
    inspection_rub_per_shift: Decimal = UnitField("₽/см", description="Выпуск на линию", default=Decimal("0"))
    medical_rub_per_shift: Decimal = UnitField("₽/см", description="Медосмотр водителя", default=Decimal("0"))
    fuel_l_per_h: Decimal | None = UnitField("л/ч", description="Расход топлива в час", default=None)
    fuel_l_per_km: Decimal | None = UnitField("л/км", description="Расход топлива на километр", default=None)
    capacity: Decimal | None = UnitField(
        "ед.", title="Ёмкость", description="Грузоподъёмность или ёмкость — для вывода смен и рейсов", default=None
    )
    capacity_unit: str | None = RefField("units", description="Единица ёмкости", default=None)

    @model_validator(mode="after")
    def _monthly_budget_needs_amount(self) -> "EquipmentTypePayload":
        if self.maintenance_mode == "MONTHLY_BUDGET" and self.maintenance_monthly_rub is None:
            field_error(
                type(self), "maintenance_monthly_rub", "Для режима «месячный бюджет» нужно указать бюджет ТОиР в месяц"
            )
        return self


class EquipmentAssetPayload(ReferencePayload):
    equipment_type_code: str = RefField("equipment_types", description="Тип техники")
    production_unit_code: str | None = RefField(
        "production_units", title="Юнит", description="Юнит, за которым закреплена единица", default=None
    )
    initial_cost_rub: Decimal = UnitField("₽", description="Первоначальная стоимость", default=Decimal("0"))
    useful_life_months: Decimal = UnitField(
        "мес", title="Срок использования", description="Срок полезного использования", default=Decimal("60"), ge=0
    )
    insurance_monthly_rub: Decimal = UnitField("₽/мес", description="Страхование (ОСАГО)", default=Decimal("0"))
    inventory_number: str | None = Field(default=None, description="Инвентарный номер")
    # Cost V1 хранил амортизацию уже посчитанной за смену; поле сохраняется при
    # импорте, пока запись не переведут на первоначальную стоимость и срок.
    productive_shifts_per_month: Decimal | None = UnitField(
        "см/мес", title="Плановые смены (V1)", description="Плановые смены из Cost V1", default=None
    )
    depreciation_per_shift_rub: Decimal | None = UnitField(
        "₽/см", title="Амортизация за смену (V1)", description="Амортизация за смену из Cost V1", default=None
    )
    equipment_type: str | None = Field(default=None, title="Вид техники (V1)", description="Вид техники из Cost V1")
    fuel_l_per_h: Decimal | None = UnitField(
        "л/ч", title="Расход топлива (V1)", description="Расход топлива из Cost V1", default=None
    )


class ResourcePoolPayload(ReferencePayload):
    unit: str | None = RefField("units", description="Единица мощности", default=None)
    resource_kind: str | None = Field(default=None, title="Вид ресурса", description="Вид ресурса, например STORAGE_AREA")
    capacity_unit: str | None = Field(default=None, title="Единица ёмкости", description="Единица ёмкости, например m2")
    monthly_capacity: Decimal | None = UnitField("ед./мес", description="Месячная мощность", default=None)
    fixed_cost_rub: Decimal = UnitField("₽/мес", description="Постоянная стоимость пула", default=Decimal("0"))
    variable_rate_rub: Decimal = UnitField("₽/ед.", description="Переменная ставка", default=Decimal("0"))
    step_capacity: Decimal | None = UnitField("ед.", description="Ёмкость одной ступени", default=None)
    step_cost_rub: Decimal | None = UnitField("₽/мес", description="Стоимость ступени", default=None)
    capacity_mode: str | None = Field(default=None, title="Режим ёмкости", description="Режим ёмкости, например RENT")
    cost_layer: str | None = Field(default=None, description="Слой себестоимости")
    allocation_driver: str | None = Field(default=None, description="Драйвер распределения")
    consumption_norms: list[dict] = Field(
        default_factory=list, title="Нормы потребления", description="Нормы потребления ёмкости материалами"
    )


class ResourceNormPayload(ReferencePayload):
    operation_code: str = RefField("operations", description="Операция")
    resource_code: str = RefField("resource_pools", description="Ресурсный пул")
    norm_per_unit: Decimal = UnitField(
        "ед.", title="Норма на единицу", description="Норма ресурса на единицу драйвера", default=Decimal("0")
    )
    driver: str | None = Field(default=None, description="Драйвер нормы")


class DrillingConditionPayload(ReferencePayload):
    """Норма бурения для сочетания «станок × порода × карьер».

    Подбор идёт по убыванию точности: станок + карьер → станок + порода →
    станок по умолчанию (порода не указана). Поэтому запись без породы — не
    ошибка, а обязательный запасной вариант для каждого станка.
    """

    equipment_type_code: str = RefField("equipment_types", description="Буровой станок")
    rock_code: str | None = RefField(
        "rocks", description="Порода; пусто — норма по умолчанию для станка", default=None
    )
    site_code: str | None = RefField("sites", title="Карьер", description="Карьер, если норма уточняется", default=None)
    tech_speed_m_per_h: Decimal = UnitField(
        "м/ч", title="Техническая скорость", description="Техническая скорость бурения", default=Decimal("0")
    )
    unproductive_h_per_shift: Decimal = UnitField(
        "ч/см", title="Непроизводительное время", description="Непроизводительное время в смену", default=Decimal("0")
    )
    fuel_l_per_m: Decimal = UnitField("л/м", description="Расход топлива на метр", default=Decimal("0"))
    bit_life_m: Decimal | None = UnitField("м", description="Ресурс коронки", default=None)
    hammer_life_m: Decimal | None = UnitField("м", description="Ресурс ППУ", default=None)
    rods_life_m: Decimal | None = UnitField("м", title="Ресурс штанг", description="Ресурс штанг и переводников", default=None)
    casing_m_per_m: Decimal = UnitField(
        "м/м", description="Обсадка на метр бурения", default=Decimal("0")
    )
    # Ресурс задаёт норму износа, материал — цену. Без явной ссылки модель не
    # знает, чью цену делить на ресурс, поэтому пара «ресурс + материал»
    # заполняется вместе.
    bit_material_code: str | None = RefField(
        "materials", title="Коронка", description="Материал коронки — источник цены", default=None
    )
    hammer_material_code: str | None = RefField(
        "materials", title="ППУ", description="Материал ППУ — источник цены", default=None
    )
    rods_material_code: str | None = RefField(
        "materials", title="Штанги", description="Материал штанг и переводников — источник цены", default=None
    )
    casing_material_code: str | None = RefField(
        "materials", title="Обсадная труба", description="Материал обсадки — источник цены", default=None
    )
