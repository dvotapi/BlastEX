"""Схемы разделов «Затраты»: центры, статьи, правила, распределение, постоянные юнита."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RefField, ReferencePayload, UnitField, field_error

__all__ = [
    "CostCenterPayload",
    "CostItemPayload",
    "CostRulePayload",
    "AllocationRulePayload",
    "UnitFixedCostPayload",
]


class CostCenterPayload(ReferencePayload):
    production_unit_code: str | None = RefField("production_units", description="Юнит", default=None)
    kind: str | None = Field(default=None, description="Вид центра затрат")


class CostItemPayload(ReferencePayload):
    kind: str | None = Field(
        default=None, title="Вид статьи", description="Служебный вид статьи: behavior_type / cost_layer"
    )
    cost_center_code: str | None = RefField("cost_centers", description="Центр затрат", default=None)
    # Статьи, перенесённые из постоянных затрат Cost V1: сумма сохранена, но
    # классификация по слою и поведению делается человеком после импорта.
    legacy_section: str | None = Field(default=None, title="Раздел сметы (V1)", description="Раздел сметы Cost V1")
    amount_rub: Decimal | None = UnitField("₽", title="Сумма (V1)", description="Сумма из Cost V1", default=None)
    requires_cost_v2_classification: bool = Field(
        default=False, title="Требует классификации", description="Требует классификации по слою и поведению"
    )


class CostRulePayload(ReferencePayload):
    operation_code: str | None = RefField("operations", description="Операция", default=None)
    resource_code: str | None = RefField("resource_pools", description="Ресурсный пул", default=None)
    cost_item_code: str | None = RefField("cost_items", description="Статья затрат", default=None)
    behavior_type: str = Field(default="variable", description="Тип поведения затраты")
    cost_layer: str = Field(default="project_direct", description="Слой себестоимости")
    driver: str | None = Field(default=None, description="Драйвер начисления")
    rate_rub: Decimal | None = UnitField("₽/ед.", description="Ставка за единицу драйвера", default=None)
    fixed_rub: Decimal | None = UnitField("₽", description="Постоянная сумма", default=None)
    step_capacity: Decimal | None = UnitField("ед.", description="Ёмкость ступени", default=None)
    step_cost_rub: Decimal | None = UnitField("₽", description="Стоимость ступени", default=None)


class AllocationRulePayload(ReferencePayload):
    cost_item_code: str | None = RefField("cost_items", description="Распределяемая статья", default=None)
    driver: str = Field(default="rock_volume_m3", description="Драйвер распределения")
    target_layer: str | None = Field(default=None, title="Целевой слой", description="Слой, на который распределяется")


class UnitFixedCostPayload(ReferencePayload):
    """Постоянная затрата юнита или организации.

    Всё, что не зависит от блока: косвенный персонал, содержание базы, СИЗ,
    связь, охрана, лицензии. Распределяется на блоки по плановому объёму, а не
    сидит константой в правилах затрат — «одна затрата живёт в одном месте».
    """

    production_unit_code: str | None = RefField("production_units", description="Юнит", default=None)
    scope: Literal["UNIT", "ORGANIZATION"] = Field(
        default="UNIT", title="Область", description="Затрата юнита или всей организации"
    )
    category: Literal["INDIRECT_LABOR", "FACILITY", "INSURANCE", "PPE", "OTHER"] = Field(
        default="OTHER", description="Категория затраты"
    )
    position_code: str | None = RefField(
        "positions", description="Должность — только для косвенного персонала", default=None
    )
    headcount: Decimal | None = UnitField(
        "чел", description="Численность — только для косвенного персонала", default=None
    )
    monthly_rub: Decimal | None = UnitField(
        "₽/мес", description="Сумма в месяц; для косвенного персонала считается из ставок", default=None
    )
    allocation_driver: str = Field(
        default="rock_volume_m3", title="Драйвер распределения", description="Драйвер распределения на блоки"
    )

    @model_validator(mode="after")
    def _labor_needs_position(self) -> "UnitFixedCostPayload":
        if self.category == "INDIRECT_LABOR":
            if not self.position_code:
                field_error(type(self), "position_code", "Для косвенного персонала нужно указать должность")
            if self.headcount is None:
                field_error(type(self), "headcount", "Для косвенного персонала нужно указать численность")
        elif self.monthly_rub is None:
            field_error(type(self), "monthly_rub", "Для затраты, не связанной с персоналом, нужна сумма в месяц")
        return self
