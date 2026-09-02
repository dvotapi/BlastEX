"""Схемы разделов «Персонал»: должности, ставки, составы бригад."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RefField, ReferencePayload, UnitField

__all__ = ["PositionPayload", "LaborRatePayload", "CrewTemplatePayload", "PIECE_DRIVERS"]

PieceDriver = Literal["rock_volume_m3", "explosive_kg", "drilling_m", "holes"]
PIECE_DRIVERS: tuple[str, ...] = ("rock_volume_m3", "explosive_kg", "drilling_m", "holes")


class PositionPayload(ReferencePayload):
    category: Literal["DIRECT", "INDIRECT"] = Field(
        default="DIRECT", description="Прямой персонал блока или косвенный персонал юнита"
    )
    operation_code: str | None = RefField(
        "operations", description="Операция пакета, к которой привязан норматив (только для прямого персонала)", default=None
    )
    norm_shifts_per_month: Decimal = UnitField(
        "см/мес", description="Нормативных смен в месяц", default=Decimal("21")
    )
    norm_operations_per_month: Decimal | None = UnitField(
        "оп/мес", description="Нормативных операций (взрывов, зарядок) в месяц", default=None
    )
    piece_driver: PieceDriver | None = Field(
        default=None, description="Драйвер сдельной оплаты"
    )
    piece_unit: Decimal = UnitField(
        "ед.", description="Расценка задаётся за столько единиц драйвера", default=Decimal("1"), ge=0
    )
    per_diem_applies: bool = Field(default=True, description="Начисляются суточные и проживание")

    @model_validator(mode="after")
    def _direct_needs_operation(self) -> "PositionPayload":
        # Прямой персонал попадает в себестоимость блока через операцию пакета:
        # без неё модель не знает, к какому этапу отнести человеко-смены.
        if self.category == "DIRECT" and not self.operation_code:
            raise ValueError("У прямого персонала должна быть указана операция пакета")
        if self.category == "INDIRECT" and self.operation_code:
            raise ValueError("Косвенный персонал не привязывается к операции — он распределяется по объёму юнита")
        return self


class LaborRatePayload(ReferencePayload):
    position_code: str = RefField("positions", description="Должность")
    fixed_monthly_rub: Decimal = UnitField(
        "₽/мес", description="Постоянная часть оплаты", default=Decimal("0")
    )
    piece_rate_rub: Decimal = UnitField(
        "₽", description="Сдельная расценка за piece_unit единиц драйвера должности", default=Decimal("0")
    )
    condition_code: str | None = RefField(
        "drilling_conditions", description="Условие бурения, если расценка зависит от породы", default=None
    )


class CrewMember(ReferencePayload):
    position_code: str = RefField("positions", description="Должность")
    headcount: Decimal = UnitField("чел", description="Численность", default=Decimal("1"), ge=0)


class CrewTemplatePayload(ReferencePayload):
    package_code: str = RefField("work_packages", description="Пакет работ")
    members: list[CrewMember] = Field(default_factory=list, description="Состав бригады")
