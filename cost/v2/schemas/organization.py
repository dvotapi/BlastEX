"""Схемы разделов «Организация»: юниты, контрагенты, карьеры, ставки организации."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RUB, RateField, RefField, ReferencePayload, UnitField, field_error
from cost.v2.schemas.labor import WorkConditionsClass

__all__ = [
    "ProductionUnitPayload",
    "CounterpartyPayload",
    "SitePayload",
    "OrganizationRatesPayload",
    "GeologyShare",
    "ExtraTariff",
    "GEOLOGY_TOLERANCE",
]

# Доли вида 1/3 точной десятичной записи не имеют: сумма 0,333 × 3 = 0,999
# должна проходить.
GEOLOGY_TOLERANCE = Decimal("0.001")


class GeologyShare(ReferencePayload):
    rock_code: str = RefField("rocks", title="Порода", description="Порода объекта")
    share: Decimal = RateField(title="Доля", description="Доля породы в плановом объёме бурения", default=Decimal("0"))


class ExtraTariff(ReferencePayload):
    work_conditions_class: WorkConditionsClass = Field(title="Класс условий труда", description="Класс по СОУТ")
    rate: Decimal = RateField(
        title="Доп. тариф", description="Дополнительный тариф страховых взносов", default=Decimal("0")
    )


class ProductionUnitPayload(ReferencePayload):
    plan_volume_m3: Decimal | None = UnitField(
        "м³/мес",
        title="Плановый объём",
        description="Плановый объём юнита в месяц — база распределения постоянных затрат",
        default=None,
    )
    base_code: str | None = RefField(
        "bases", title="База юнита", description="Производственная база юнита", default=None
    )
    region: str | None = Field(default=None, description="Регион работы")


class CounterpartyPayload(ReferencePayload):
    role: Literal["CUSTOMER", "SUPPLIER", "SUBCONTRACTOR"] = Field(
        default="CUSTOMER", description="Роль контрагента"
    )
    inn: str | None = Field(default=None, description="ИНН")
    short_name: str | None = Field(
        default=None,
        title="Краткое наименование",
        description='Как в журнале буровых работ, например АО "Теплогорский карьер"',
    )


class SitePayload(ReferencePayload):
    customer_code: str | None = RefField("counterparties", description="Заказчик объекта", default=None)
    customer_legal_name: str | None = Field(
        default=None,
        title="Заказчик текстом",
        description="Наименование заказчика из журнала, если контрагента нет в справочнике",
    )
    short_name: str | None = Field(
        default=None,
        max_length=5,
        title="Краткое имя",
        description="Код объекта в журнале буровых работ (до 5 символов)",
    )
    mineral_type: str | None = Field(
        default=None,
        title="Полезное ископаемое",
        description="Вид сырья по журналу, например «нерудные материалы»",
    )
    production_unit_code: str | None = RefField(
        "production_units", description="Юнит, обслуживающий объект", default=None
    )
    rock_code: str | None = RefField("rocks", description="Порода по умолчанию", default=None)
    distance_from_base_km: Decimal | None = UnitField(
        "км", title="Расстояние от базы", description="Расстояние от производственной базы", default=None
    )
    distance_from_warehouse_km: Decimal | None = UnitField(
        "км", description="Расстояние от склада ВМ", default=None
    )
    diesel_price_ton_rub: Decimal | None = UnitField(
        "₽/т", title="Цена ДТ", description="Цена дизельного топлива на объекте", default=None
    )
    customer_provides_fuel: bool = Field(
        default=False, title="Топливо заказчика", description="Топливо предоставляет заказчик"
    )
    blocks_per_mobilization: Decimal | None = UnitField(
        "блоков",
        title="Блоков на мобилизацию",
        description="Сколько блоков приходится на одну мобилизацию",
        default=None,
        ge=0,
    )
    mobilization_rate_rub_per_km: Decimal | None = UnitField(
        "₽/км", description="Ставка мобилизации техники", default=None
    )
    mobilization_km: Decimal | None = UnitField(
        "км", title="Плечо мобилизации", description="Плечо мобилизации техники на объект", default=None
    )
    is_watered: bool = Field(default=False, title="Обводнённость", description="Обводнённость блока по умолчанию")
    # Суточные и проживание начисляются только на вахтовом объекте: на
    # городском карьере бригада ночует дома, и норматив к ней не применяется.
    is_remote: bool = Field(
        default=False, title="Вахтовый объект", description="Начисляются суточные и проживание"
    )
    # Вахта и оплата труда (TASK-010). Умолчания — график компании 15/15:
    # запись, заведённая до появления полей, считается по нему.
    shift_days_on: Decimal = UnitField(
        "дн", title="Дней вахты", description="Рабочих дней за вахту, включая плановое ТОиР", default=Decimal("15")
    )
    shift_days_off: Decimal = UnitField(
        "дн", title="Дней межвахты", description="Дней межвахтового отдыха", default=Decimal("15")
    )
    travel_days: Decimal = UnitField(
        "дн", title="Дней в дороге", description="Дней в пути на вахту и обратно", default=Decimal("2")
    )
    night_shift_share: Decimal = RateField(
        title="Доля ночных смен", description="Доля смен вахты, приходящихся на ночь", default=Decimal("0.5")
    )
    maintenance_shifts: Decimal = UnitField(
        "см",
        title="Плановое ТОиР за вахту",
        description="Смен вахты, которые уходят на плановое ТОиР станка",
        default=Decimal("2"),
    )
    regional_coefficient: Decimal = RateField(
        title="Районный коэффициент", description="Надбавка к начислениям: 0,15 — коэффициент 1,15", default=Decimal("0.15")
    )
    northern_pct: Decimal = RateField(
        title="Северная надбавка", description="Процентная надбавка за стаж в районах Крайнего Севера, доля", default=Decimal("0")
    )
    contract_k: Decimal = UnitField(
        "", title="Договорной коэффициент", description="Множитель приведённых метров по договору объекта", default=Decimal("1")
    )
    geology: list[GeologyShare] = Field(
        default_factory=list,
        title="Плановая геология",
        description="Доли пород объекта — запасной путь, когда у блоков нет паспортов; сумма долей равна 1",
    )

    @model_validator(mode="after")
    def _payroll_fields_are_consistent(self) -> "SitePayload":
        if self.maintenance_shifts >= self.shift_days_on:
            field_error(
                type(self),
                "maintenance_shifts",
                "Плановое ТОиР не может занимать всю вахту: эффективных смен не останется",
                self.maintenance_shifts,
            )
        if self.contract_k <= 0:
            field_error(type(self), "contract_k", "Договорной коэффициент должен быть больше нуля", self.contract_k)
        rocks: set[str] = set()
        for index, row in enumerate(self.geology):
            if row.rock_code in rocks:
                field_error(type(self), ("geology", index, "rock_code"), "Порода уже есть в плановой геологии", row.rock_code)
            rocks.add(row.rock_code)
        total = sum((row.share for row in self.geology), Decimal("0"))
        if self.geology and abs(total - 1) > GEOLOGY_TOLERANCE:
            field_error(type(self), "geology", f"Сумма долей пород — {total}, а должна быть 1", total)
        return self


class OrganizationRatesPayload(ReferencePayload):
    """Ставки и надбавки организации.

    Не расходы, а параметры: НДФЛ, взносы и НДС применяются к итогам расчёта.
    Одна активная запись на организацию, версионируется вместе со снимком.
    """

    income_tax_rate: Decimal = RateField(description="НДФЛ", default=Decimal("0.13"))
    social_contribution_rate: Decimal = RateField(description="Страховые взносы", default=Decimal("0.30"))
    injury_insurance_rate: Decimal = RateField(
        title="Взносы на травматизм", description="Взносы на травматизм по классу риска", default=Decimal("0.0042")
    )
    vacation_reserve_rate: Decimal = RateField(description="Резерв отпусков", default=Decimal("0.20"))
    salary_basis: Literal["GROSS", "NET"] = Field(
        default="GROSS",
        title="Основа окладов",
        description="Оклады в справочнике заданы до НДФЛ (GROSS) или на руки (NET)",
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
    extra_tariffs: list[ExtraTariff] = Field(
        default_factory=list,
        title="Доп. тариф по классам условий труда",
        description="Дополнительный тариф взносов по классу условий труда (ст. 428 НК РФ); у классов 1 и 2 его нет",
    )

    @model_validator(mode="after")
    def _one_tariff_per_class(self) -> "OrganizationRatesPayload":
        seen: set[str] = set()
        for index, tariff in enumerate(self.extra_tariffs):
            if tariff.work_conditions_class in seen:
                field_error(
                    type(self),
                    ("extra_tariffs", index, "work_conditions_class"),
                    "Класс условий труда уже есть в таблице",
                    tariff.work_conditions_class,
                )
            seen.add(tariff.work_conditions_class)
        return self
