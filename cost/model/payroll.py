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
