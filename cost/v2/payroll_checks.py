"""Перекрёстные проверки ревизии для методики ФОТ (TASK-010).

Правила внутри одной записи — шкала ставки, интервалы крепости, доли геологии —
живут в схемах разделов. Здесь то, что видно только по нескольким разделам
сразу. Проверяется весь черновик, и ошибка блокирует публикацию любых правок
организации, поэтому пустой новый раздел — предупреждение, а ошибка возможна
только в заполненном (Т15).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from cost.v2.models import ReferenceItem, finite_decimal
from cost.v2.references import ValidationIssue
from cost.v2.schemas.labor import CURVE_SCALES, HAZARDOUS_CLASSES
from cost.v2.schemas.organization import SitePayload

__all__ = ["payroll_issues"]

EMPTY_SECTION_MESSAGES: dict[str, str] = {
    "payroll_params": "Не заведены параметры года: ФОТ по методике не рассчитается.",
    "drilling_difficulty": "Не заведены коэффициенты сложности бурения: приведённые метры не посчитать.",
    "downtime_reasons": "Не заведены причины простоев: простой не по вине машиниста не списать.",
}

# Расхождение планового ТОиР объекта с долей ТОиР станка, после которого
# источники считаются разными (Т16).
MAINTENANCE_TOLERANCE_SHIFTS = Decimal("0.5")
DEFAULT_SHIFT_HOURS = Decimal("11")


def payroll_issues(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_empty_sections(sections))
    issues.extend(_duplicate_years(sections))
    issues.extend(_single_difficulty(sections))
    issues.extend(_bit_diameters(sections))
    issues.extend(_ceiling_above_rigs(sections))
    issues.extend(_maintenance_against_rigs(sections))
    issues.extend(_missing_extra_tariffs(sections))
    return issues


def _active(sections: Mapping[str, Sequence[ReferenceItem]], section: str) -> list[ReferenceItem]:
    return [item for item in sections.get(section, ()) if item.is_active]


def _rows(value: Any) -> Sequence[Mapping[str, Any]]:
    """Список строк подраздела payload, если тип совпадает; иначе пусто.

    Схема раздела отдельно отвергает нелистовое значение как ошибку —
    здесь достаточно не упасть и не проверять то, чего нет.
    """

    return value if isinstance(value, (list, tuple)) else ()


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _empty_sections(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    return [
        ValidationIssue("warning", section, "", message)
        for section, message in EMPTY_SECTION_MESSAGES.items()
        if not _active(sections, section)
    ]


def _duplicate_years(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    first: dict[Decimal, str] = {}
    for item in _active(sections, "payroll_params"):
        year = finite_decimal(item.payload.get("year"))
        if year is None:
            continue
        if year in first:
            issues.append(
                ValidationIssue(
                    "error",
                    "payroll_params",
                    item.code,
                    f"Параметры {_plain(year)} года уже заведены записью {first[year]}.",
                    field="year",
                )
            )
            continue
        first[year] = item.code
    return issues


def _single_difficulty(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    items = _active(sections, "drilling_difficulty")
    return [
        ValidationIssue(
            "error",
            "drilling_difficulty",
            item.code,
            f"Действует одна запись коэффициентов сложности бурения, уже есть {items[0].code}.",
        )
        for item in items[1:]
    ]


def _bit_diameters(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    """Каждая коронка из условий бурения должна иметь коэффициент диаметра."""

    difficulty = next(iter(_active(sections, "drilling_difficulty")), None)
    if difficulty is None:
        return []
    table = {
        diameter
        for row in _rows(difficulty.payload.get("diameter"))
        if isinstance(row, Mapping) and (diameter := finite_decimal(row.get("diameter_mm"))) is not None
    }
    materials = {item.code: item for item in _active(sections, "materials")}
    issues: list[ValidationIssue] = []
    reported: set[str] = set()
    for condition in _active(sections, "drilling_conditions"):
        material = materials.get(str(condition.payload.get("bit_material_code") or ""))
        if material is None or material.code in reported:
            continue
        reported.add(material.code)
        diameter = finite_decimal(material.payload.get("diameter_mm"))
        if diameter is None:
            issues.append(
                ValidationIssue(
                    "warning",
                    "materials",
                    material.code,
                    "У коронки из условий бурения не задан диаметр: коэффициент диаметра для неё не проверен.",
                    field="diameter_mm",
                )
            )
        elif diameter not in table:
            issues.append(
                ValidationIssue(
                    "error",
                    "drilling_difficulty",
                    difficulty.code,
                    f"Нет коэффициента для коронки Ø {_plain(diameter)} мм ({material.name}).",
                    field="diameter",
                )
            )
    return issues


def _ceiling_above_rigs(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    """Потолок шкалы машиниста выше того, что станок бурит за смену по базовым условиям."""

    rates = next(iter(_active(sections, "organization_rates")), None)
    shift_hours = finite_decimal(rates.payload.get("shift_hours")) if rates is not None else None
    shift_hours = shift_hours or DEFAULT_SHIFT_HOURS
    per_shift = [
        speed * max(shift_hours - (finite_decimal(item.payload.get("unproductive_h_per_shift")) or Decimal("0")), Decimal("0"))
        for item in _active(sections, "drilling_conditions")
        # Базовая строка — без породы и карьера: шкала задана для базовых условий.
        if not item.payload.get("rock_code") and not item.payload.get("site_code")
        and (speed := finite_decimal(item.payload.get("tech_speed_m_per_h"))) is not None
    ]
    if not per_shift:
        return []
    best = max(per_shift)
    normalized = {
        item.code for item in _active(sections, "positions") if item.payload.get("difficulty") == "NORMALIZED_METERS"
    }
    issues: list[ValidationIssue] = []
    for item in _active(sections, "labor_rates"):
        if item.payload.get("scale_type") not in CURVE_SCALES:
            continue
        if str(item.payload.get("position_code") or "") not in normalized:
            continue
        ceiling = finite_decimal(item.payload.get("ceiling_per_shift"))
        if ceiling is None or ceiling <= best:
            continue
        issues.append(
            ValidationIssue(
                "warning",
                "labor_rates",
                item.code,
                f"Потолок {_plain(ceiling)} м/смену выше производительности станков по базовым условиям бурения "
                f"(до {_plain(best)} м/смену): машинист не дойдёт до потолка.",
                field="ceiling_per_shift",
            )
        )
    return issues


def _maintenance_against_rigs(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    """Плановое ТОиР объекта против доли ТОиР станка (Т16).

    Доля ТОиР — смен ТОиР на рабочую смену, поэтому из вахты в `N` смен на
    ТОиР уходит `N × r / (1 + r)`: при 15 сменах и 0,14 — 1,84 смены.
    """

    rigs = [
        (item, ratio)
        for item in _active(sections, "equipment_types")
        if str(item.payload.get("kind") or "DRILL_RIG") == "DRILL_RIG"
        and (ratio := finite_decimal(item.payload.get("maintenance_ratio"))) is not None
        and ratio > 0
    ]
    if not rigs:
        return []
    default_days = SitePayload.model_fields["shift_days_on"].default
    default_shifts = SitePayload.model_fields["maintenance_shifts"].default
    issues: list[ValidationIssue] = []
    for site in _active(sections, "sites"):
        days = finite_decimal(site.payload.get("shift_days_on")) or default_days
        planned = finite_decimal(site.payload.get("maintenance_shifts"))
        planned = default_shifts if planned is None else planned
        for rig, ratio in rigs:
            expected = days * ratio / (1 + ratio)
            if abs(expected - planned) <= MAINTENANCE_TOLERANCE_SHIFTS:
                continue
            issues.append(
                ValidationIssue(
                    "warning",
                    "sites",
                    site.code,
                    f"Плановое ТОиР {_plain(planned)} см за вахту расходится с долей ТОиР станка {rig.name}: "
                    f"{_plain(ratio)} смены ТОиР на рабочую смену дают "
                    f"{_plain(expected.quantize(Decimal('0.01')))} см из {_plain(days)}.",
                    field="maintenance_shifts",
                )
            )
    return issues


def _missing_extra_tariffs(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    rates = next(iter(_active(sections, "organization_rates")), None)
    covered = {
        str(row.get("work_conditions_class"))
        for row in _rows(rates.payload.get("extra_tariffs") if rates is not None else None)
        if isinstance(row, Mapping)
    }
    issues: list[ValidationIssue] = []
    for item in _active(sections, "positions"):
        work_class = item.payload.get("work_conditions_class")
        if work_class not in HAZARDOUS_CLASSES or work_class in covered:
            continue
        issues.append(
            ValidationIssue(
                "warning",
                "positions",
                item.code,
                f"Для класса условий труда {work_class} в «Ставках и надбавках организации» "
                "не задан доп. тариф взносов: расчёт ФОТ возьмёт 0.",
                field="work_conditions_class",
            )
        )
    return issues
