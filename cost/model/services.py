"""Ручные услуги прогона: сторонние организации, проживание и питание, медосмотр.

Сумму сметчик вводит на вкладке, и она живёт в параметрах прогона — смета
воспроизводима без справочника. Перенос в «Правила расчёта затрат» — отдельное
действие; после него строка вкладки уступает правилу, иначе услуга была бы
посчитана дважды.
"""
from __future__ import annotations

import re
from decimal import Decimal

from cost.model.inputs import ModelContext, ServiceCharge, payload_text
from cost.model.labor import DERIVED_SHIFT_DRIVERS
from cost.v2.models import CostLayer

# Смены операции для услуг «за смену»: экипажи техники — по её рейсам,
# бурение — по сменам станка.
SHIFT_DRIVERS: dict[str, str] = {
    **DERIVED_SHIFT_DRIVERS,
    "PRODUCTION_DRILLING": "rig_shifts",
    "CONTOUR_DRILLING": "rig_shifts",
}

_TRANSLIT = {
    "а": "A", "б": "B", "в": "V", "г": "G", "д": "D", "е": "E", "ё": "E", "ж": "ZH",
    "з": "Z", "и": "I", "й": "Y", "к": "K", "л": "L", "м": "M", "н": "N", "о": "O",
    "п": "P", "р": "R", "с": "S", "т": "T", "у": "U", "ф": "F", "х": "KH", "ц": "TS",
    "ч": "CH", "ш": "SH", "щ": "SCH", "ъ": "", "ы": "Y", "ь": "", "э": "E", "ю": "YU",
    "я": "YA",
}


def service_code(name: str) -> str:
    """Код записи справочника из названия: латиница, стабилен при повторном переносе."""

    latin = "".join(_TRANSLIT.get(ch, ch) for ch in name.strip().lower()).upper()
    slug = re.sub(r"[^A-Z0-9]+", "_", latin).strip("_")
    return f"SERVICE_{slug or 'X'}"[:80].rstrip("_")


def compute(context: ModelContext) -> None:
    known_rules = {
        payload_text(rule, "cost_item_code") or rule.code for rule in context.items("cost_rules")
    }
    for charge in context.params.services:
        if not charge.name or charge.amount_rub == 0:
            continue
        if charge.operation_code and not context.has_operation(charge.operation_code):
            continue
        code = service_code(charge.name)
        if code in known_rules:
            context.warn(
                f"Услуга «{charge.name}» уже есть в правилах затрат: "
                "строка вкладки пропущена, чтобы не считать её дважды."
            )
            continue
        amount, formula = _amount(context, charge)
        context.add_line(
            operation_code=charge.operation_code,
            cost_item_code=code,
            cost_item_name=charge.name,
            layer=_layer(charge.layer),
            amount_rub=amount,
            formula=formula,
        )


def _amount(context: ModelContext, charge: ServiceCharge) -> tuple[Decimal, str]:
    if not charge.per_shift:
        return charge.amount_rub, "введено на вкладке"
    driver = SHIFT_DRIVERS.get(charge.operation_code, "")
    shifts = context.value(driver) if driver else Decimal("0")
    if shifts <= 0:
        context.warn(
            f"Услуга «{charge.name}»: смены операции {charge.operation_code or '—'} "
            "не выведены, сумма взята как разовая."
        )
        return charge.amount_rub, "введено на вкладке (смен нет, сумма разовая)"
    return charge.amount_rub * shifts, f"{shifts} см × {charge.amount_rub} ₽/см (введено на вкладке)"


def _layer(value: str) -> CostLayer:
    try:
        return CostLayer(value)
    except ValueError:
        return CostLayer.PROJECT_DIRECT


__all__ = ["SHIFT_DRIVERS", "compute", "service_code"]
