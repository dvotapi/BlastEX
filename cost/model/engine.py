"""Сборка экономики блока: натуральные величины → строки → слои → цены.

Движок ничего не знает о БД и HTTP: на вход — снимок технического паспорта,
параметры модели и снимок справочников, на выходе — строки Cost V2 по слоям.
Отсутствие записи в справочнике не исключение, а предупреждение и нулевая
строка: сметчик должен увидеть незаполненное место, а не ошибку 500.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Any, Mapping

from cost.model import drilling, equipment, labor, logistics, markup, unit
from cost.model.inputs import (
    BlockEconomics,
    ModelContext,
    ModelParameters,
    payload_number,
    payload_text,
)
from cost.v2.models import CostLayer, ReferenceItem, ReferenceSnapshot, decimal_value
from cost.v2.technical_adapter import TechnicalDriverSnapshot


def compute_block_economics(
    snapshot: TechnicalDriverSnapshot | Mapping[str, Any],
    params: ModelParameters,
    references: ReferenceSnapshot,
    *,
    passport_name: str = "Блок",
) -> BlockEconomics:
    physical, lineage = _snapshot_parts(snapshot)
    context = ModelContext(
        references,
        params,
        physical,
        passport_lineage=lineage,
        passport_name=passport_name,
    )

    # Порядок важен: смены станка и СЗМ нужны ФОТ и затратам техники.
    drilling.compute(context)
    logistics.compute(context)
    labor.compute(context)
    equipment.compute(context)
    _cost_rule_lines(context)
    unit.compute(context)

    lines = tuple(context.lines)
    totals = markup.layer_totals(lines)
    prices, markup_values = markup.apply(context, totals)
    return BlockEconomics(
        lines=lines,
        layer_totals=totals,
        price_per_m3=prices,
        natural=context.natural(),
        capacity=tuple(context.capacity),
        warnings=tuple(context.warnings),
        markup=markup_values,
        block_volume_m3=context.block_volume_m3,
    )


def _snapshot_parts(
    snapshot: TechnicalDriverSnapshot | Mapping[str, Any],
) -> tuple[dict[str, Decimal], dict[str, str]]:
    if isinstance(snapshot, TechnicalDriverSnapshot):
        return dict(snapshot.physical), dict(snapshot.lineage)
    data = dict(snapshot)
    physical = data.get("physical", data)
    lineage = data.get("lineage", {}) or {}
    return (
        {str(key): decimal_value(value) for key, value in dict(physical).items()},
        {str(key): str(value) for key, value in dict(lineage).items()},
    )


def _cost_rule_lines(context: ModelContext) -> None:
    """Статьи вида «цена × драйвер» — правила затрат, а не код.

    Материалы, ВМ и прочие линейные статьи задаются в справочнике `cost_rules`
    и попадают сюда без изменения модели.
    """

    for rule in context.items("cost_rules"):
        operation_code = payload_text(rule, "operation_code")
        if not operation_code:
            # Затраты юнита без операции распределяются через `unit_fixed_costs`;
            # начислять их ещё и здесь значит посчитать дважды.
            continue
        if not context.has_operation(operation_code):
            continue
        amount, formula = _rule_amount(context, rule)
        if amount == 0:
            continue
        context.add_line(
            operation_code=operation_code,
            cost_item_code=payload_text(rule, "cost_item_code") or rule.code,
            cost_item_name=rule.name,
            layer=_layer(payload_text(rule, "cost_layer", CostLayer.VARIABLE.value)),
            amount_rub=amount,
            formula=formula,
            resource_code=payload_text(rule, "resource_code"),
        )


def _rule_amount(context: ModelContext, rule: ReferenceItem) -> tuple[Decimal, str]:
    driver_name = payload_text(rule, "driver")
    driver_value = context.value(driver_name) if driver_name else Decimal("0")
    rate = payload_number(rule, "rate_rub")
    fixed = payload_number(rule, "fixed_rub")
    step_capacity = payload_number(rule, "step_capacity")
    step_cost = payload_number(rule, "step_cost_rub")

    amount = Decimal("0")
    parts: list[str] = []
    if driver_name and rate != 0:
        if driver_name not in context.values:
            context.warn(
                f"Правило затрат {rule.code}: драйвер «{driver_name}» "
                "отсутствует в натуральных величинах блока."
            )
        amount += rate * driver_value
        parts.append(f"{rate} ₽ × {driver_value} {driver_name}")
    if fixed != 0:
        amount += fixed
        parts.append(f"{fixed} ₽ на блок")
    if step_capacity > 0 and step_cost != 0:
        steps = (driver_value / step_capacity).to_integral_value(rounding=ROUND_CEILING)
        amount += steps * step_cost
        parts.append(f"{steps} ступ. × {step_cost} ₽")
    return amount, "; ".join(parts)


def _layer(value: str) -> CostLayer:
    try:
        return CostLayer(value)
    except ValueError:
        return CostLayer.VARIABLE
