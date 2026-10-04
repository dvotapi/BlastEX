"""Методика ФОТ по объектам (TASK-010): приведённые метры, эффективные смены,
сдельная премия по шкале и месячный ФОТ должности.

Функции чистые: справочники уже прочитаны (`cost/model/payroll_inputs.py`),
здесь только нормы — формулы файла владельца «Расчёт заработной платы» с
исправлениями методики (`Docs/PAYROLL_MODEL.md`). Всё считается в Decimal, а
каждая величина возвращается вместе с формулой, по которой получена.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Sequence

from cost.model.inputs import formula_number

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")

# Верх шкалы Протодьяконова. Крепость выше берёт коэффициент последней строки
# таблицы, но такое значение скорее ошибка ввода — предупреждаем.
PROTODYAKONOV_MAX = Decimal("20")
# Флаги на проверку начальнику участка (TASK-010 §2.3): расчёт не блокируют.
WRITE_OFF_FLAG_SHARE = Decimal("0.25")
PACE_FLAG_RATIO = Decimal("1.2")
# Классы условий труда с 36-часовой неделей (ст. 92 ТК РФ).
SHORT_WEEK_CLASSES = frozenset({"3.3", "3.4", "4"})
CURVE_SCALES = frozenset({"CURVE_POWER", "CURVE_LINEAR"})
# График шкалы: до 1,3 потолка — видно и рост, и постоянную цену выше потолка.
SERIES_SPAN = Decimal("1.3")
SERIES_STEPS = 60


class PayrollInputError(ValueError):
    """Вход, на котором методика не считается: 422 в превью."""


def fn(value: Decimal) -> str:
    return formula_number(value)


def percent(share: Decimal) -> str:
    return f"{fn(share * HUNDRED)} %"


# --- Приведённые метры ------------------------------------------------------


@dataclass(frozen=True)
class HardnessBand:
    """Интервал крепости `f_from < f ≤ f_to`; у первой строки нет низа, у последней — верха."""

    f_from: Decimal | None
    f_to: Decimal | None
    k: Decimal

    def contains(self, f: Decimal) -> bool:
        return (self.f_from is None or f > self.f_from) and (self.f_to is None or f <= self.f_to)

    def label(self) -> str:
        if self.f_from is None and self.f_to is None:
            return "любая f"
        if self.f_from is None:
            return f"f ≤ {fn(self.f_to)}"
        if self.f_to is None:
            return f"f > {fn(self.f_from)}"
        return f"{fn(self.f_from)} < f ≤ {fn(self.f_to)}"


@dataclass(frozen=True)
class DifficultyTables:
    """Коэффициенты приведения метров к базовым условиям: f = 10, Ø 152 мм."""

    hardness: tuple[HardnessBand, ...] = ()
    diameter: Mapping[Decimal, Decimal] = field(default_factory=dict)
    source: str = "drilling_difficulty"


@dataclass(frozen=True)
class MeterItem:
    meters: Decimal
    diameter_mm: Decimal
    f: Decimal | None = None
    label: str = ""


@dataclass(frozen=True)
class NormalizedRow:
    label: str
    meters: Decimal
    f: Decimal | None
    k_f: Decimal
    diameter_mm: Decimal
    k_d: Decimal
    normalized: Decimal


@dataclass(frozen=True)
class NormalizedMeters:
    # M — приведённые метры, аргумент шкалы.
    total: Decimal
    # Погонные метры без коэффициентов.
    physical: Decimal
    contract_k: Decimal = ONE
    rows: tuple[NormalizedRow, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def factor(self) -> Decimal:
        """Приведённых метров на погонный: договорной k × средний коэффициент; без метров — 1."""

        return self.total / self.physical if self.physical > 0 else ONE


def hardness_factor(f: Decimal | None, bands: Sequence[HardnessBand]) -> tuple[Decimal, str, str]:
    """Коэффициент крепости, пояснение для происхождения и предупреждение (пусто — нет)."""

    if f is None:
        return ONE, "крепость не задана → 1", "У породы не задана крепость f: коэффициент крепости принят 1."
    if not bands:
        return ONE, "таблица крепости пуста → 1", "В «Сложности бурения» нет таблицы крепости: коэффициент крепости принят 1."
    band = next((band for band in bands if band.contains(f)), None)
    if band is None:
        # Разрывы не пропускает проверка ревизии; на битой таблице — 1, а не падение.
        return ONE, f"f = {fn(f)} вне таблицы → 1", f"Крепость f = {fn(f)} не попала ни в одну строку таблицы крепости: коэффициент принят 1."
    warning = ""
    if f > PROTODYAKONOV_MAX:
        warning = (
            f"Крепость f = {fn(f)} выше шкалы Протодьяконова (до {fn(PROTODYAKONOV_MAX)}): "
            "взят коэффициент последней строки таблицы."
        )
    return band.k, f"{band.label()} → {fn(band.k)}", warning


def normalized_meters(
    items: Sequence[MeterItem], tables: DifficultyTables, contract_k: Decimal = ONE
) -> NormalizedMeters:
    """M = contract_k × Σ mᵢ × k_f(fᵢ) × k_d(Øᵢ) (TASK-010 §2.1).

    Коэффициент не меняет цену метра, а увеличивает зачтённые метры: на объекте
    с несколькими породами не нужно решать, какие метры в какую ступень попали.
    Диаметра нет в заполненной таблице — ошибка (проверка ревизии такого не
    пускает); пустая таблица — коэффициент 1 с предупреждением.
    """

    rows: list[NormalizedRow] = []
    lineage: dict[str, str] = {}
    warnings: list[str] = []
    for index, entry in enumerate(items):
        k_f, f_note, warning = hardness_factor(entry.f, tables.hardness)
        if warning and warning not in warnings:
            warnings.append(warning)
        if tables.diameter:
            k_d = tables.diameter.get(entry.diameter_mm)
            if k_d is None:
                raise PayrollInputError(
                    f"Диаметра коронки {fn(entry.diameter_mm)} мм нет в таблице «Сложность бурения»."
                )
            d_note = f"Ø {fn(entry.diameter_mm)} мм → {fn(k_d)}"
        else:
            k_d = ONE
            d_note = "таблица диаметров пуста → 1"
            message = "В «Сложности бурения» нет таблицы диаметров: коэффициент диаметра принят 1."
            if message not in warnings:
                warnings.append(message)
        label = entry.label or f"строка {index + 1}"
        rows.append(NormalizedRow(label, entry.meters, entry.f, k_f, entry.diameter_mm, k_d, entry.meters * k_f * k_d))
        lineage[f"k_f.{index}"] = f"{tables.source}: {f_note}"
        lineage[f"k_d.{index}"] = f"{tables.source}: {d_note}"
    physical = sum((row.meters for row in rows), ZERO)
    total = contract_k * sum((row.normalized for row in rows), ZERO)
    lineage["normalized_meters"] = f"{fn(contract_k)} × Σ м × k_f × k_d = {fn(total)}"
    return NormalizedMeters(total, physical, contract_k, tuple(rows), lineage, tuple(warnings))


# --- Шкала и сдельная премия ------------------------------------------------

@dataclass(frozen=True)
class PayrollFlag:
    """Сигнал на проверку начальнику участка; расчёт он не блокирует."""

    code: str
    message: str


@dataclass(frozen=True)
class ScaleTier:
    upto_per_shift: Decimal | None
    rate: Decimal


@dataclass(frozen=True)
class Scale:
    """Шкала сдельной премии ставки: кривая цены единицы или ступени (Т5).

    Согласованность полей проверяет схема ставки (`LaborRatePayload`), здесь
    шкала уже корректна: у кривой есть все четыре узла, у ступеней — верх у
    всех, кроме последней.
    """

    scale_type: str
    norm_per_shift: Decimal | None = None
    rate_norm: Decimal | None = None
    ceiling_per_shift: Decimal | None = None
    rate_ceiling: Decimal | None = None
    tiers: tuple[ScaleTier, ...] = ()
    source: str = ""

    @property
    def is_curve(self) -> bool:
        return self.scale_type in CURVE_SCALES

    @property
    def gamma(self) -> Decimal | None:
        """Показатель степенной кривой: ln(r_потолок / r_норма) / ln(потолок / норма)."""

        if self.scale_type != "CURVE_POWER":
            return None
        return (self.rate_ceiling / self.rate_norm).ln() / (self.ceiling_per_shift / self.norm_per_shift).ln()

    def rate_at(self, pace: Decimal) -> Decimal:
        """Цена единицы при темпе `pace` за смену — цена последнего метра r(m)."""

        if self.scale_type == "STEP":
            for tier in self.tiers:
                if tier.upto_per_shift is None or pace <= tier.upto_per_shift:
                    return tier.rate
            return self.tiers[-1].rate
        if pace <= self.norm_per_shift:
            return self.rate_norm
        if pace >= self.ceiling_per_shift:
            return self.rate_ceiling
        if self.scale_type == "CURVE_POWER":
            return self.rate_norm * (pace / self.norm_per_shift) ** self.gamma
        return self.rate_norm + (self.rate_ceiling - self.rate_norm) * (pace - self.norm_per_shift) / (
            self.ceiling_per_shift - self.norm_per_shift
        )

    def per_shift(self, pace: Decimal) -> Decimal:
        """Премия за смену p(m) — интеграл цены единицы от 0 до m в замкнутом виде."""

        if pace <= 0:
            return ZERO
        if self.scale_type == "STEP":
            return sum((units * rate for _, _, units, rate in self.tier_split(pace)), ZERO)
        norm, ceiling = self.norm_per_shift, self.ceiling_per_shift
        if pace <= norm:
            return self.rate_norm * pace
        top = min(pace, ceiling)
        if self.scale_type == "CURVE_POWER":
            power = self.gamma + 1
            rising = self.rate_norm * norm * ((top / norm) ** power - 1) / power
        else:
            rising = (top - norm) * (self.rate_norm + self.rate_at(top)) / 2
        above = self.rate_ceiling * (pace - ceiling) if pace > ceiling else ZERO
        return self.rate_norm * norm + rising + above

    def tier_split(self, pace: Decimal) -> tuple[tuple[Decimal, Decimal | None, Decimal, Decimal], ...]:
        """Ступени при темпе `pace`: (низ, верх, единиц за смену в ступени, расценка)."""

        rows: list[tuple[Decimal, Decimal | None, Decimal, Decimal]] = []
        lower = ZERO
        for tier in self.tiers:
            upper = tier.upto_per_shift
            top = pace if upper is None else min(pace, upper)
            rows.append((lower, upper, max(ZERO, top - lower), tier.rate))
            if upper is None or pace <= upper:
                break
            lower = upper
        return tuple(rows)

    def breakpoints(self) -> tuple[Decimal, ...]:
        if self.is_curve:
            return (self.norm_per_shift, self.ceiling_per_shift)
        return tuple(tier.upto_per_shift for tier in self.tiers if tier.upto_per_shift is not None)


@dataclass(frozen=True)
class PremiumTier:
    lower: Decimal
    upper: Decimal | None
    rate: Decimal
    # Единиц и рублей за вахту.
    units: Decimal
    amount: Decimal


@dataclass(frozen=True)
class PiecePremium:
    total: Decimal
    output: Decimal
    effective_shifts: Decimal
    pace: Decimal
    per_shift: Decimal
    last_rate: Decimal
    mean_rate: Decimal | None
    tiers: tuple[PremiumTier, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)


def gamma_text(gamma: Decimal) -> str:
    return format(gamma.quantize(Decimal("0.000001")), "f").replace(".", ",")


def piece_premium(output: Decimal, scale: Scale, effective: Decimal) -> PiecePremium:
    """Премия за вахту P = S_эфф × p(M / S_эфф) — на одном темпе вахты (TASK-010 §2.3).

    Посменный расчёт запрещён: кривая выпукла, и рваный ритм (6 смен по 100 м и
    6 по 230) дал бы больше ровного (12 по 165) при тех же метрах.
    """

    if effective <= 0:
        raise PayrollInputError("Эффективных смен должно быть больше нуля.")
    pace = output / effective
    per_shift = scale.per_shift(pace)
    total = effective * per_shift
    tiers: tuple[PremiumTier, ...] = ()
    if scale.scale_type == "STEP":
        tiers = tuple(
            PremiumTier(lower, upper, rate, units * effective, units * effective * rate)
            for lower, upper, units, rate in scale.tier_split(pace)
        )
    lineage = {
        "pace": f"{fn(output)} / {fn(effective)} см = {fn(pace)} за смену",
        "premium": f"{fn(effective)} см × p({fn(pace)}) = {fn(effective)} × {fn(per_shift)} ₽ = {fn(total)} ₽",
    }
    if scale.gamma is not None:
        lineage["gamma"] = (
            f"ln({fn(scale.rate_ceiling)} / {fn(scale.rate_norm)}) / "
            f"ln({fn(scale.ceiling_per_shift)} / {fn(scale.norm_per_shift)}) = {gamma_text(scale.gamma)}"
        )
    return PiecePremium(
        total=total,
        output=output,
        effective_shifts=effective,
        pace=pace,
        per_shift=per_shift,
        last_rate=scale.rate_at(pace),
        mean_rate=total / output if output > 0 else None,
        tiers=tiers,
        lineage=lineage,
    )


def pace_flags(scale: Scale, pace: Decimal) -> tuple[PayrollFlag, ...]:
    """Темп выше 1,2 потолка — сигнал проверить метры или списанные простои."""

    if not scale.is_curve or pace <= PACE_FLAG_RATIO * scale.ceiling_per_shift:
        return ()
    return (
        PayrollFlag(
            "PACE_ABOVE_CEILING",
            f"Темп {fn(pace)} за смену выше {fn(PACE_FLAG_RATIO)} × потолка ({fn(scale.ceiling_per_shift)}): "
            "проверьте метры и списанные простои.",
        ),
    )


# --- График шкалы -----------------------------------------------------------


@dataclass(frozen=True)
class ScalePoint:
    pace: Decimal
    rate: Decimal
    per_shift: Decimal


def scale_series(scale: Scale, pace: Decimal | None = None) -> tuple[ScalePoint, ...]:
    """Точки графика шкалы: цена единицы r(m) и премия за смену p(m).

    Интерфейс рисует график по этим точкам, а не своей формулой (Т6): кривая
    одна — та, по которой посчитана премия. Узлы шкалы и темп входят точно,
    чтобы излом и маркер стояли на своих местах.
    """

    anchors = scale.breakpoints()
    anchor = max(anchors) if anchors else (pace or HUNDRED)
    upper = anchor * SERIES_SPAN
    if pace is not None and pace > upper:
        upper = pace * Decimal("1.1")
    paces = {upper * step / SERIES_STEPS for step in range(SERIES_STEPS + 1)}
    paces.update(anchors)
    if pace is not None:
        paces.add(pace)
    return tuple(ScalePoint(m, scale.rate_at(m), scale.per_shift(m)) for m in sorted(paces))
