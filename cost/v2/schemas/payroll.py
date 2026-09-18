"""Схемы разделов методики ФОТ (TASK-010): параметры года, сложность бурения, простои.

Ставки взносов, травматизма и НДФЛ здесь не хранятся — они в «Ставках и
надбавках организации» (Т2); оклад, шкала и КПЭ — в «Ставках персонала» (Т1).
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RateField, ReferencePayload, UnitField, field_error

__all__ = [
    "PayrollParamsPayload",
    "HardnessBand",
    "DiameterFactor",
    "DrillingDifficultyPayload",
    "DowntimeReasonPayload",
]


class PayrollParamsPayload(ReferencePayload):
    """Параметры года: календарь, МРОТ, годовые нормы часов, порог доли в марже."""

    year: int = UnitField("год", title="Год", description="Год производственного календаря", ge=2000, le=2100)
    mrot: Decimal = UnitField(
        "₽/мес", title="МРОТ", description="Минимальный размер оплаты труда — оклад должности без ставки"
    )
    annual_hours_40: Decimal = UnitField(
        "ч", title="Годовая норма при 40 ч/нед", description="Годовая норма часов при 40-часовой неделе"
    )
    annual_hours_36: Decimal = UnitField(
        "ч", title="Годовая норма при 36 ч/нед", description="Годовая норма часов при 36-часовой неделе (ст. 92 ТК РФ)"
    )
    work_days_year: Decimal = UnitField(
        "дн",
        title="Рабочих дней в году",
        description="По производственному календарю; делитель межвахтового отдыха — рабочих дней / 12",
        le=366,
    )
    holidays_year: Decimal = UnitField(
        "дн", title="Праздничных дней в году", description="Нерабочих праздничных дней по календарю", le=366
    )
    night_pct: Decimal = RateField(
        title="Доплата за ночные", description="Доля часовой ставки за ночной час", default=Decimal("0.20")
    )
    vacation_days_base: Decimal = UnitField(
        "дн",
        title="Основной отпуск",
        description="Дней основного оплачиваемого отпуска — база резерва",
        default=Decimal("28"),
        le=366,
    )
    margin_share_warn: Decimal = RateField(
        title="Порог доли в марже",
        description=(
            "Предупреждение, если стоимость последнего метра по экипажу станка с начислениями "
            "выше этой доли маржи метра"
        ),
        default=Decimal("0.70"),
    )

    @model_validator(mode="after")
    def _calendar_is_consistent(self) -> "PayrollParamsPayload":
        if self.work_days_year <= 0:
            field_error(type(self), "work_days_year", "Рабочих дней в году должно быть больше нуля", self.work_days_year)
        if self.annual_hours_40 <= 0:
            field_error(type(self), "annual_hours_40", "Годовая норма часов должна быть больше нуля", self.annual_hours_40)
        if self.annual_hours_36 <= 0 or self.annual_hours_36 > self.annual_hours_40:
            field_error(
                type(self),
                "annual_hours_36",
                "Норма при 36-часовой неделе больше нуля и не больше нормы при 40-часовой",
                self.annual_hours_36,
            )
        return self


class HardnessBand(ReferencePayload):
    f_from: Decimal | None = UnitField(
        "f", title="Крепость от", description="Нижняя граница, не включается; у первой строки пусто", default=None
    )
    f_to: Decimal | None = UnitField(
        "f", title="Крепость до", description="Верхняя граница, включается; у последней строки пусто", default=None
    )
    k: Decimal = UnitField("", title="Коэффициент", description="Множитель приведённых метров", default=Decimal("1"))


class DiameterFactor(ReferencePayload):
    diameter_mm: Decimal = UnitField("мм", title="Диаметр коронки", description="Диаметр коронки")
    k: Decimal = UnitField(
        "", title="Коэффициент", description="Множитель приведённых метров; стартовое значение Ø / 152", default=Decimal("1")
    )


class DrillingDifficultyPayload(ReferencePayload):
    """Коэффициенты приведения метров к базовым условиям: f = 10, Ø 152 мм, k = 1."""

    hardness: list[HardnessBand] = Field(
        default_factory=list,
        title="Крепость породы",
        description=(
            "Интервалы f_from < f ≤ f_to по возрастанию, без разрывов; база f = 10 → k = 1. "
            "Первая строка без нижней границы, последняя без верхней"
        ),
    )
    diameter: list[DiameterFactor] = Field(
        default_factory=list,
        title="Диаметр коронки",
        description="Коэффициент на каждый диаметр коронок из условий бурения; база Ø 152 мм → k = 1",
    )

    @model_validator(mode="after")
    def _tables_are_consistent(self) -> "DrillingDifficultyPayload":
        self._check_hardness()
        seen: set[Decimal] = set()
        for index, row in enumerate(self.diameter):
            if row.diameter_mm <= 0:
                field_error(type(self), ("diameter", index, "diameter_mm"), "Диаметр должен быть больше нуля", row.diameter_mm)
            if row.diameter_mm in seen:
                field_error(type(self), ("diameter", index, "diameter_mm"), "Диаметр уже есть в таблице", row.diameter_mm)
            seen.add(row.diameter_mm)
            if row.k <= 0:
                field_error(type(self), ("diameter", index, "k"), "Коэффициент должен быть больше нуля", row.k)
        return self

    def _check_hardness(self) -> None:
        last = len(self.hardness) - 1
        for index, band in enumerate(self.hardness):
            if band.k <= 0:
                field_error(type(self), ("hardness", index, "k"), "Коэффициент должен быть больше нуля", band.k)
            if index == 0 and band.f_from is not None:
                field_error(
                    type(self),
                    ("hardness", 0, "f_from"),
                    "У первой строки нижней границы нет: она охватывает всю крепость до верхней границы",
                    band.f_from,
                )
            if index == last and band.f_to is not None:
                field_error(
                    type(self),
                    ("hardness", index, "f_to"),
                    "У последней строки верхней границы нет: крепость выше шкалы берёт её коэффициент",
                    band.f_to,
                )
            if index < last and band.f_to is None:
                field_error(type(self), ("hardness", index, "f_to"), "Верхняя граница не задаётся только у последней строки")
            if index > 0:
                previous_to = self.hardness[index - 1].f_to
                if band.f_from is None or band.f_from != previous_to:
                    field_error(
                        type(self),
                        ("hardness", index, "f_from"),
                        f"Интервалы крепости идут без разрыва: нижняя граница равна верхней границе предыдущей строки ({previous_to})",
                        band.f_from,
                    )
            if band.f_from is not None and band.f_to is not None and band.f_to <= band.f_from:
                field_error(type(self), ("hardness", index, "f_to"), "Верхняя граница должна быть больше нижней", band.f_to)


class DowntimeReasonPayload(ReferencePayload):
    """Код простоя. Часы простоя не по вине машиниста вычитаются из эффективных смен вахты."""

    excusable: bool = Field(
        default=False,
        title="Не по вине машиниста",
        description="Часы простоя вычитаются из эффективных смен и не снижают темп машиниста",
    )
    planned_maintenance: bool = Field(
        default=False,
        title="Плановое ТОиР",
        description="Плановое ТОиР станка: в проверку «списано больше 25 % часов вахты» не входит",
    )

    @model_validator(mode="after")
    def _maintenance_is_excusable(self) -> "DowntimeReasonPayload":
        if self.planned_maintenance and not self.excusable:
            field_error(type(self), "planned_maintenance", "Плановое ТОиР — простой не по вине машиниста: отметьте оба признака")
        return self
