"""Сборка экономики блока: натуральные величины → строки → слои → цены.

Движок ничего не знает о БД и HTTP: на вход — снимок технического паспорта,
параметры модели и снимок справочников, на выходе — строки Cost V2 по слоям.
Отсутствие записи в справочнике не исключение, а предупреждение и нулевая
строка: сметчик должен увидеть незаполненное место, а не ошибку 500.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING
from typing import Any, Mapping

from cost.model import drilling, equipment, labor, logistics, markup, materials, services, unit
from cost.model.inputs import (
    BlockEconomics,
    ModelContext,
    ModelParameters,
    payload_number,
    payload_text,
)
from cost.v2.models import CostLayer, ReferenceItem, ReferenceSnapshot, decimal_value
from cost.v2.models import ESTIMATE_SECTIONS, EstimateSection
from cost.v2.technical_adapter import TechnicalDriverSnapshot


def compute_block_economics(
    snapshot: TechnicalDriverSnapshot | Mapping[str, Any],
    params: ModelParameters,
    references: ReferenceSnapshot,
    *,
    passport_name: str = "Блок",
    as_of: date | None = None,
) -> BlockEconomics:
    physical, lineage = _snapshot_parts(snapshot)
    context = ModelContext(
        references,
        params,
        physical,
        passport_lineage=lineage,
        passport_name=passport_name,
        as_of=as_of,
    )

    # Порядок важен: смены станка и СЗМ нужны ФОТ и затратам техники, а
    # разделение массы ВВ на насыпную и патронированную — статьям ВМ.
    drilling.compute(context)
    logistics.compute(context)
    nomenclature = materials.compute(context)
    labor.compute(context)
    equipment.compute(context)
    rules = _cost_rule_lines(
        context,
        blocked_pairs=nomenclature.charged_operation_drivers,
        blocked_items=nomenclature.charged_cost_items,
    )
    # Услуги — после правил: уступать нужно только правилу, которое
    # действительно дало строку, иначе заготовка с нулевой ставкой молча
    # убрала бы услугу из сметы.
    services.compute(context, charged_items=rules.cost_items)
    # Роль без наименования или цены — не ошибка, пока статью закрывает
    # правило затрат; говорить об этом можно только после прохода правил.
    materials.report_gaps(context, nomenclature, rules.drivers)
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


# Драйверы, которых у блока может законно не быть: патронов нет — нет и
# тонно-километров со склада. Правило с таким драйвером даёт ноль без
# предупреждения; предупреждение остаётся для опечатки в имени драйвера.
OPTIONAL_DRIVERS = frozenset(
    {
        "vm_tkm",
        "component_tkm",
        "cartridge_kg",
        "bulk_kg",
        "szm_shifts",
        "szm_trips",
        "delivery_shifts",
        "delivery_trips",
        "emulsion_shifts",
        "emulsion_trips",
        "rig_shifts",
        "rig_maintenance_shifts",
        "mobilization_trip_km",
        "contour_drilling_m",
        "excavator_hours",
        "stakeout_holes",
    }
)


@dataclass(frozen=True)
class RuleOutcome:
    """Что начислили правила затрат: драйверы и статьи давших строку правил."""

    drivers: set[str]
    cost_items: set[str]


def _cost_rule_lines(
    context: ModelContext,
    *,
    blocked_pairs: set[tuple[str, str]],
    blocked_items: set[str],
) -> RuleOutcome:
    """Статьи вида «цена × драйвер» — правила затрат, а не код.

    Материалы, ВМ и прочие линейные статьи задаются в справочнике `cost_rules`
    и попадают сюда без изменения модели. Правило уступает выбранной
    номенклатуре, если считает ту же статью или ту же пару «операция +
    драйвер»: масса ВВ — общий драйвер и для самой стоимости ВВ, и для,
    например, комплектации склада, поэтому одного драйвера мало, а статья
    ловит правило, стоящее на другой операции заряжания.
    Возвращает драйверы и статьи правил, давших строку: по ним модули
    материалов и услуг решают, о чём предупреждать и чему уступать.
    """

    charged: set[str] = set()
    charged_items: set[str] = set()
    for rule in context.items("cost_rules"):
        operation_code = payload_text(rule, "operation_code")
        if not operation_code:
            # Затраты юнита без операции распределяются через `unit_fixed_costs`;
            # начислять их ещё и здесь значит посчитать дважды.
            continue
        if not context.has_operation(operation_code):
            continue
        driver_name = payload_text(rule, "driver")
        cost_item_code = payload_text(rule, "cost_item_code") or rule.code
        if cost_item_code in blocked_items or (operation_code, driver_name) in blocked_pairs:
            # Молча пропустить нельзя: сметчик должен понимать, почему правило
            # справочника не видно в смете.
            context.warn(
                f"Правило затрат {rule.code} начисляет то же, что и выбранная "
                "номенклатура блока: в смете осталась строка по выбранному наименованию."
            )
            continue
        amount, formula = _rule_amount(context, rule)
        if amount == 0:
            continue
        if driver_name:
            charged.add(driver_name)
        charged_items.add(cost_item_code)
        context.add_line(
            operation_code=operation_code,
            cost_item_code=cost_item_code,
            cost_item_name=rule.name,
            layer=_layer(payload_text(rule, "cost_layer", CostLayer.VARIABLE.value)),
            amount_rub=amount,
            formula=formula,
            resource_code=payload_text(rule, "resource_code"),
            section=_section(payload_text(rule, "estimate_section")),
        )
    return RuleOutcome(drivers=charged, cost_items=charged_items)


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
        if driver_name not in context.values and driver_name not in OPTIONAL_DRIVERS:
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


def _section(value: str) -> EstimateSection:
    """Раздел сметы правила; незнакомое значение — «Общепроизводственные»."""

    return value if value in ESTIMATE_SECTIONS else "OVERHEAD"


def _layer(value: str) -> CostLayer:
    try:
        return CostLayer(value)
    except ValueError:
        return CostLayer.VARIABLE
