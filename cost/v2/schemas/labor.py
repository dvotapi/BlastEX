"""Схемы разделов «Персонал»: должности, ставки, составы бригад."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RateField, RefField, ReferencePayload, UnitField, field_error

__all__ = [
    "PositionPayload",
    "LaborRatePayload",
    "CrewTemplatePayload",
    "ScaleTier",
    "WorkConditionsClass",
    "PIECE_DRIVERS",
    "WORK_CONDITIONS_CLASSES",
    "HAZARDOUS_CLASSES",
    "CURVE_SCALES",
]

PieceDriver = Literal["rock_volume_m3", "explosive_kg", "drilling_m", "holes"]
PIECE_DRIVERS: tuple[str, ...] = ("rock_volume_m3", "explosive_kg", "drilling_m", "holes")

WorkConditionsClass = Literal["1", "2", "3.1", "3.2", "3.3", "3.4", "4"]
WORK_CONDITIONS_CLASSES: tuple[str, ...] = ("1", "2", "3.1", "3.2", "3.3", "3.4", "4")
# Классы, за которые платится дополнительный тариф взносов (ст. 428 НК РФ):
# у оптимального и допустимого классов его нет.
HAZARDOUS_CLASSES: tuple[str, ...] = ("3.1", "3.2", "3.3", "3.4", "4")

ScaleType = Literal["CURVE_POWER", "CURVE_LINEAR", "STEP"]
CURVE_SCALES: tuple[str, ...] = ("CURVE_POWER", "CURVE_LINEAR")
_CURVE_FIELDS: tuple[str, ...] = ("norm_per_shift", "rate_norm", "ceiling_per_shift", "rate_ceiling")


class PositionPayload(ReferencePayload):
    category: Literal["DIRECT", "INDIRECT"] = Field(
        default="DIRECT", title="Категория", description="Прямой персонал блока или косвенный персонал юнита"
    )
    operation_code: str | None = RefField(
        "operations",
        title="Операция пакета",
        description="Операция пакета, к которой привязан норматив (только для прямого персонала)",
        default=None,
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
        "ед.", title="За единиц драйвера", description="Расценка задаётся за столько единиц драйвера", default=Decimal("1"), ge=0
    )
    per_diem_applies: bool = Field(default=True, title="Суточные и проживание", description="Начисляются суточные и проживание")
    # Методика ФОТ (TASK-010): нормы должности. Деньги — оклад, шкала, КПЭ —
    # живут в «Ставках персонала».
    department: Literal["DRILLING_BLASTING", "TRANSPORT", "WAREHOUSE", "MAINTENANCE"] | None = Field(
        default=None,
        title="Участок",
        description="Участок штатного расписания: буровзрывной, транспорт и спецтехника, склад и производство, техобслуживание",
    )
    pay_system: Literal["PIECE_PROGRESSIVE", "PIECE_BONUS", "TIME_BONUS"] = Field(
        default="TIME_BONUS",
        title="Система оплаты",
        description=(
            "Сдельно-прогрессивная и сдельно-премиальная — премия по шкале ставки; "
            "повременно-премиальная — без сдельной премии"
        ),
    )
    work_conditions_class: WorkConditionsClass | None = Field(
        default=None,
        title="Класс условий труда",
        description="Класс по СОУТ: задаёт доп. тариф взносов, а 3.3, 3.4 и 4 — 36-часовую неделю (ст. 92 ТК РФ)",
    )
    week_hours_override: Literal["40", "36"] | None = Field(
        default=None,
        title="Рабочая неделя вручную",
        description="Пусто — неделя выводится из класса условий труда: 3.3, 3.4 и 4 — 36 ч, остальные — 40 ч",
    )
    hazard_pct: Decimal = RateField(
        title="Надбавка за вредность", description="Доля оклада", default=Decimal("0")
    )
    extra_vacation_days: Decimal = UnitField(
        "дн",
        title="Дополнительный отпуск",
        description="Дней дополнительного отпуска в год — база резерва",
        default=Decimal("0"),
        le=366,
    )
    night_hours_per_shift: Decimal = UnitField(
        "ч/см", title="Ночных часов в смене", description="Ночных часов в ночную смену", default=Decimal("0"), le=24
    )
    output_unit: str | None = RefField(
        "units",
        title="Единица выработки",
        description="В чём считается сдельная выработка: м, км, рейс, т, м³",
        default=None,
    )
    output_source: Literal["OWN_OUTPUT", "SECTION_OUTPUT"] = Field(
        default="OWN_OUTPUT",
        title="Чья выработка",
        description="Своя выработка или выработка участка (горнорабочий); в плане выработка участка — выработка юнита",
    )
    difficulty: Literal["PLAIN", "NORMALIZED_METERS"] = Field(
        default="PLAIN",
        title="Приведение выработки",
        description="Приведённые метры — метры бурения × коэффициенты крепости породы и диаметра коронки",
    )

    @model_validator(mode="after")
    def _direct_needs_operation(self) -> "PositionPayload":
        # Прямой персонал попадает в себестоимость блока через операцию пакета:
        # без неё модель не знает, к какому этапу отнести человеко-смены.
        if self.category == "DIRECT" and not self.operation_code:
            field_error(type(self), "operation_code", "У прямого персонала должна быть указана операция пакета")
        if self.category == "INDIRECT" and self.operation_code:
            field_error(
                type(self),
                "operation_code",
                "Косвенный персонал не привязывается к операции — он распределяется по объёму юнита",
                self.operation_code,
            )
        return self


class ScaleTier(ReferencePayload):
    upto_per_shift: Decimal | None = UnitField(
        "ед./см",
        title="До выработки за смену",
        description="Верхняя граница ступени; у последней ступени пусто",
        default=None,
    )
    rate: Decimal = UnitField(
        "₽/ед.", title="Расценка", description="Цена единицы выработки внутри ступени", default=Decimal("0")
    )


class LaborRatePayload(ReferencePayload):
    position_code: str = RefField("positions", description="Должность")
    fixed_monthly_rub: Decimal = UnitField(
        "₽/мес", description="Постоянная часть оплаты", default=Decimal("0")
    )
    piece_rate_rub: Decimal = UnitField(
        "₽",
        title="Сдельная расценка",
        description=(
            "Цена за столько единиц драйвера сдельной оплаты, сколько указано у должности "
            "в поле «За единиц драйвера» — например, за 1000 м³"
        ),
        default=Decimal("0"),
    )
    condition_code: str | None = RefField(
        "drilling_conditions",
        title="Условие бурения",
        description="Условие бурения, если расценка зависит от породы",
        default=None,
    )
    kpi_bonus_pct: Decimal = RateField(
        title="Премия КПЭ",
        description="Премия за ОРД и КПЭ при выполнении плана на 100 %, доля оклада",
        default=Decimal("0"),
    )
    # Шкала лежит плоско, а не вложенным объектом: форма справочника не умеет
    # вложенный объект, а объединение вариантов затёрла бы строкой (Т5).
    scale_type: ScaleType | None = Field(
        default=None,
        title="Шкала сдельной премии",
        description="Степенная или линейная кривая цены единицы между нормой и потолком либо ступени; пусто — шкалы нет",
    )
    norm_per_shift: Decimal | None = UnitField(
        "ед./см",
        title="Норма за смену",
        description=(
            "До нормы цена единицы равна расценке на норме. Норма и потолок — загрузка станка: "
            "метры на смену = скорость бурения × чистое время; у машиниста — приведённые метры при f 10 и Ø 152 мм"
        ),
        default=None,
    )
    rate_norm: Decimal | None = UnitField(
        "₽/ед.", title="Расценка на норме", description="Цена единицы выработки до нормы", default=None
    )
    ceiling_per_shift: Decimal | None = UnitField(
        "ед./см",
        title="Потолок за смену",
        description="Выработка, при которой станок бурит всю смену; выше потолка цена единицы постоянна",
        default=None,
    )
    rate_ceiling: Decimal | None = UnitField(
        "₽/ед.", title="Расценка на потолке", description="Цена единицы на потолке и выше", default=None
    )
    tiers: list[ScaleTier] = Field(
        default_factory=list,
        title="Ступени шкалы",
        description="Ступени по выработке за смену для шкалы «Ступени»; расценки не убывают",
    )

    @model_validator(mode="after")
    def _scale_is_consistent(self) -> "LaborRatePayload":
        if self.scale_type is None:
            for name in _CURVE_FIELDS:
                if getattr(self, name) is not None:
                    field_error(
                        type(self), name, "Поле заполняется только вместе с типом шкалы сдельной премии", getattr(self, name)
                    )
            if self.tiers:
                field_error(type(self), "tiers", "Ступени заполняются только у шкалы «Ступени»")
            return self
        if self.condition_code:
            # Коэффициент породы уже в приведённых метрах: расценка по условию
            # бурения учла бы породу второй раз (Т1).
            field_error(
                type(self),
                "condition_code",
                "Шкала сдельной премии задаётся ставкой без условия бурения: породу учитывают приведённые метры",
                self.condition_code,
            )
        if self.scale_type == "STEP":
            self._check_tiers()
        else:
            self._check_curve()
        return self

    def _check_curve(self) -> None:
        if self.tiers:
            field_error(type(self), "tiers", "У кривой ступени не заполняются")
        norm, rate_norm = self.norm_per_shift, self.rate_norm
        ceiling, rate_ceiling = self.ceiling_per_shift, self.rate_ceiling
        if norm is None or rate_norm is None or ceiling is None or rate_ceiling is None:
            missing = next(name for name in _CURVE_FIELDS if getattr(self, name) is None)
            field_error(type(self), missing, "Для кривой нужны норма, потолок и обе расценки")
        if norm <= 0:
            field_error(type(self), "norm_per_shift", "Норма должна быть больше нуля", norm)
        if ceiling <= norm:
            field_error(type(self), "ceiling_per_shift", "Потолок должен быть выше нормы", ceiling)
        if rate_norm <= 0:
            field_error(type(self), "rate_norm", "Расценка на норме должна быть больше нуля", rate_norm)
        if rate_ceiling < rate_norm:
            field_error(type(self), "rate_ceiling", "Расценка на потолке не может быть ниже расценки на норме", rate_ceiling)

    def _check_tiers(self) -> None:
        for name in _CURVE_FIELDS:
            if getattr(self, name) is not None:
                field_error(type(self), name, "У шкалы «Ступени» поля кривой не заполняются", getattr(self, name))
        if not self.tiers:
            field_error(type(self), "tiers", "Для шкалы «Ступени» нужна хотя бы одна ступень")
        last = len(self.tiers) - 1
        for index, tier in enumerate(self.tiers):
            where = ("tiers", index, "upto_per_shift")
            if index < last and tier.upto_per_shift is None:
                field_error(type(self), where, "Верхняя граница не задаётся только у последней ступени")
            if index == last and tier.upto_per_shift is not None:
                field_error(
                    type(self), where, "У последней ступени верхней границы нет: выше неё действует её расценка",
                    tier.upto_per_shift,
                )
            if index == 0:
                if tier.upto_per_shift is not None and tier.upto_per_shift <= 0:
                    field_error(type(self), where, "Граница первой ступени должна быть больше нуля", tier.upto_per_shift)
                continue
            previous = self.tiers[index - 1]
            # Граница предыдущей ступени задана: пустую отсекла проверка выше.
            if (
                previous.upto_per_shift is not None
                and tier.upto_per_shift is not None
                and tier.upto_per_shift <= previous.upto_per_shift
            ):
                field_error(type(self), where, "Границы ступеней должны возрастать", tier.upto_per_shift)
            if tier.rate < previous.rate:
                # Убывающая расценка ломает выпуклость: премия за смену перестала
                # бы расти ускоренно.
                field_error(
                    type(self), ("tiers", index, "rate"), "Расценка ступени не может быть ниже предыдущей", tier.rate
                )


class CrewMember(ReferencePayload):
    position_code: str = RefField("positions", description="Должность")
    headcount: Decimal = UnitField(
        "чел",
        title="Человек в смене",
        description="Сколько человек должности работает в одной смене; штат на ротацию модель выводит из плановых смен техники",
        default=Decimal("1"),
        ge=0,
    )


class CrewTemplatePayload(ReferencePayload):
    package_code: str = RefField("work_packages", description="Пакет работ")
    members: list[CrewMember] = Field(default_factory=list, description="Состав бригады")
