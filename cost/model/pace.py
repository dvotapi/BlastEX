"""Плановый темп машиниста по строке матрицы условий бурения (TASK-010, Т9).

m_план = v_commercial × k_f(крепость породы строки) × k_d(Ø коронки строки).
Коэффициенты блока сюда не входят — только в приведённые метры блока
(M_блока): на строке f 17 / Ø 250 темп 120 × 1,968 = 236 м/смену — ожидаемое
значение строки, а ошибкой было бы умножить его ещё раз на k блока
(сложность учлась бы дважды). Строка без породы или коронки считается базовой (k = 1)
с предупреждением; отсутствующая запись — тоже предупреждение, не ошибка.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

from cost.model.drilling import DrillingNorms
from cost.model.inputs import ModelContext, payload_number, payload_text
from cost.model.payroll import ONE, DifficultyTables, PayrollInputError, fn, hardness_factor
from cost.model.payroll_inputs import difficulty_tables, rock_hardness


@dataclass(frozen=True)
class PlannedPace:
    # Плановый темп, м/смену: аргумент шкалы машиниста.
    pace: Decimal
    k_hardness: Decimal
    k_diameter: Decimal
    # Ø коронки строки: по нему же приводятся метры блока.
    diameter_mm: Decimal | None
    condition_code: str
    warnings: tuple[str, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)
    # Название записи условий бурения: человеку показывается оно, а не код.
    condition_name: str = ""


def _tables(context: ModelContext, warnings: list[str]) -> DifficultyTables:
    try:
        return difficulty_tables(context.references)
    except PayrollInputError as exc:
        warnings.append(f"{exc} Коэффициенты планового темпа приняты 1.")
        return DifficultyTables(source="drilling_difficulty (запись не читается)")


def _hardness(
    context: ModelContext, condition_code: str, rock_code: str, tables: DifficultyTables, warnings: list[str]
) -> tuple[Decimal, str]:
    if not rock_code:
        warnings.append(
            f"В строке условий бурения {condition_code} не задана порода: "
            "плановый темп по базовой строке, коэффициент крепости принят 1."
        )
        return ONE, "порода не задана → 1"
    try:
        f = rock_hardness(context.references, rock_code)
    except PayrollInputError as exc:
        warnings.append(f"{exc} Коэффициент крепости планового темпа ({condition_code}) принят 1.")
        return ONE, f"порода {rock_code} не найдена → 1"
    if f is None:
        rock = context.item("rocks", rock_code)
        name = rock.name if rock is not None else rock_code
        warnings.append(
            f"У породы «{name}» ({rock_code}) строки условий бурения {condition_code} "
            "не задана крепость f: коэффициент крепости планового темпа принят 1."
        )
        return ONE, f"{rock_code}: крепость не задана → 1"
    k_f, note, warning = hardness_factor(f, tables.hardness, tables.hardness_scale_max)
    if warning:
        warnings.append(warning)
    return k_f, f"{rock_code}: {note}"


def _diameter(
    context: ModelContext, condition_code: str, bit_code: str, tables: DifficultyTables, warnings: list[str]
) -> tuple[Decimal, Decimal | None, str]:
    if not bit_code:
        warnings.append(
            f"В строке условий бурения {condition_code} не задана коронка: "
            "плановый темп по базовой строке, коэффициент диаметра принят 1."
        )
        return ONE, None, "коронка не задана → 1"
    material = context.item("materials", bit_code)
    if material is None:
        warnings.append(
            f"Коронка {bit_code} строки условий бурения {condition_code} не найдена "
            "в номенклатуре: коэффициент диаметра принят 1."
        )
        return ONE, None, f"коронка {bit_code} не найдена → 1"
    diameter = payload_number(material, "diameter_mm")
    if diameter <= 0:
        warnings.append(
            f"У коронки «{material.name}» ({bit_code}) не задан диаметр: "
            "коэффициент диаметра планового темпа принят 1."
        )
        return ONE, None, f"{bit_code}: диаметр не задан → 1"
    if not tables.diameter:
        warnings.append("В «Сложности бурения» нет таблицы диаметров: коэффициент диаметра принят 1.")
        return ONE, diameter, "таблица диаметров пуста → 1"
    k_d = tables.diameter.get(diameter)
    if k_d is None:
        # В приведении метров это ошибка входа, а темп считается дальше: k = 1.
        warnings.append(
            f"Диаметра коронки {bit_code} Ø {fn(diameter)} мм нет в таблице «Сложность бурения»: "
            "коэффициент диаметра планового темпа принят 1."
        )
        return ONE, diameter, f"{bit_code}: Ø {fn(diameter)} мм вне таблицы → 1"
    return k_d, diameter, f"{bit_code}: Ø {fn(diameter)} мм → {fn(k_d)}"


def planned_pace(
    context: ModelContext, norms: DrillingNorms, tables: DifficultyTables | None = None
) -> PlannedPace:
    """Плановый темп по строке матрицы, подобранной для блока (`norms.condition`).

    `tables` — уже прочитанная «Сложность бурения» (ФОТ блока читает её один
    раз на расчёт); без неё таблица читается здесь.
    """

    v_commercial = norms.v_commercial_m_per_shift
    condition = norms.condition
    warnings: list[str] = []
    if condition is None:
        warnings.append("Строка условий бурения не подобрана: плановый темп без коэффициентов сложности.")
        return PlannedPace(
            v_commercial, ONE, ONE, None, "", tuple(warnings),
            {"planned_pace": f"v_коммерч = {fn(v_commercial)} (строка не подобрана)"},
        )

    if tables is None:
        tables = _tables(context, warnings)
    k_f, f_note = _hardness(context, condition.code, payload_text(condition, "rock_code"), tables, warnings)
    k_d, diameter, d_note = _diameter(
        context, condition.code, payload_text(condition, "bit_material_code"), tables, warnings
    )
    pace = v_commercial * k_f * k_d
    lineage = {
        "condition": f"drilling_conditions.{condition.code}",
        "k_f": f"{tables.source}: {f_note}",
        "k_d": f"{tables.source}: {d_note}",
        "planned_pace": (
            f"{condition.name or condition.code}: {fn(v_commercial)} × {fn(k_f)} × {fn(k_d)} = {fn(pace)} м/смену"
        ),
    }
    return PlannedPace(pace, k_f, k_d, diameter, condition.code, tuple(dict.fromkeys(warnings)), lineage,
                       condition_name=condition.name or "")
