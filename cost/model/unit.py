"""Постоянные затраты юнита и их доля в блоке.

База распределения — плановый объём юнита: только она показывает, как доля
постоянных затрат в цене м³ падает с ростом загрузки. Склад ВМ считается
здесь же, потому что его площадь зависит от месячного плана, а не от блока.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

from cost.model.inputs import (
    CapacityWarning,
    ModelContext,
    payload_number,
    payload_text,
)
from cost.v2.models import CostLayer, ReferenceItem


STORAGE_RESOURCE_KIND = "STORAGE_AREA"

CATEGORY_NAMES: dict[str, str] = {
    "INDIRECT_LABOR": "Косвенный персонал юнита",
    "FACILITY": "Содержание базы и помещений",
    "INSURANCE": "Страхование",
    "PPE": "СИЗ и охрана труда",
    "OTHER": "Прочие постоянные затраты юнита",
}


def unit_share(context: ModelContext) -> Decimal:
    plan = context.params.unit_plan_volume_m3
    if plan <= 0:
        context.warn(
            "Не задан плановый объём юнита: постоянные затраты юнита не распределены на блок."
        )
        return Decimal("0")
    share = context.block_volume_m3 / plan
    context.set_value(
        "unit_allocation_share",
        share,
        f"{context.block_volume_m3} м³ блока / {plan} м³ плана юнита",
    )
    return share


def compute(context: ModelContext) -> None:
    share = unit_share(context)
    if share <= 0:
        return
    unit_code = payload_text(context.site, "production_unit_code")
    for item in context.items("unit_fixed_costs"):
        scope = payload_text(item, "scope", "UNIT")
        item_unit = payload_text(item, "production_unit_code")
        if scope == "UNIT" and unit_code and item_unit and item_unit != unit_code:
            continue
        monthly = _monthly_amount(context, item)
        if monthly <= 0:
            continue
        category = payload_text(item, "category", "OTHER")
        context.add_line(
            operation_code="",
            cost_item_code=f"UNIT_{item.code}",
            cost_item_name=f"{CATEGORY_NAMES.get(category, category)}: {item.name}",
            layer=CostLayer.PRODUCTION,
            amount_rub=monthly * share,
            formula=f"{monthly} ₽/мес × доля блока {share}",
        )
    _storage(context, share)


def _monthly_amount(context: ModelContext, item: ReferenceItem) -> Decimal:
    """Сумма затраты в месяц; для косвенного персонала — из ставок."""

    if payload_text(item, "category") != "INDIRECT_LABOR":
        return payload_number(item, "monthly_rub")
    position_code = payload_text(item, "position_code")
    headcount = payload_number(item, "headcount", Decimal("1"))
    rate = next(
        (
            row
            for row in context.items("labor_rates")
            if payload_text(row, "position_code") == position_code
        ),
        None,
    )
    if rate is None:
        context.warn(
            f"Для косвенной должности {position_code} не задана ставка: "
            "затрата юнита не начислена."
        )
        return Decimal("0")
    rates = context.rates
    accrued = payload_number(rate, "fixed_monthly_rub") * headcount
    if rates.salary_basis == "NET" and rates.income_tax_rate < 1:
        accrued = accrued / (Decimal("1") - rates.income_tax_rate)
    contributions = accrued * (rates.social_contribution_rate + rates.injury_insurance_rate)
    return accrued + contributions + (accrued + contributions) * rates.vacation_reserve_rate


def _storage(context: ModelContext, share: Decimal) -> None:
    """Аренда склада ВМ: площадь по месячной потребности, ступенька — по пулу."""

    pool = next(
        (
            item
            for item in context.items("resource_pools")
            if payload_text(item, "resource_kind") == STORAGE_RESOURCE_KIND
        ),
        None,
    )
    if pool is None:
        return
    plan_volume = context.params.unit_plan_volume_m3
    block_volume = context.block_volume_m3
    if plan_volume <= 0 or block_volume <= 0:
        return
    scale = plan_volume / block_volume

    required = Decimal("0")
    parts: list[str] = []
    for norm in pool.payload.get("consumption_norms", []) or []:
        driver = str(norm.get("driver", ""))
        per_capacity = Decimal(str(norm.get("units_per_capacity", 0) or 0))
        if not driver or per_capacity <= 0:
            continue
        monthly_units = context.value(driver) * scale
        needed = monthly_units / per_capacity
        parts.append(f"{driver}: {monthly_units} / {per_capacity}")
        required = max(required, needed)
    if required <= 0:
        return
    required_area = required.to_integral_value(rounding=ROUND_CEILING)
    context.set_value(
        "warehouse_area_m2", required_area, "⌈max(" + "; ".join(parts) + ")⌉ по плану юнита"
    )

    capacity = payload_number(pool, "monthly_capacity")
    monthly = payload_number(pool, "fixed_cost_rub")
    formula = f"{monthly} ₽/мес базовой аренды"
    if capacity > 0 and required_area > capacity:
        step_capacity = payload_number(pool, "step_capacity", Decimal("1"))
        step_cost = payload_number(pool, "step_cost_rub")
        if step_capacity <= 0:
            step_capacity = Decimal("1")
        steps = ((required_area - capacity) / step_capacity).to_integral_value(
            rounding=ROUND_CEILING
        )
        monthly += steps * step_cost
        formula += f" + {steps} ступ. × {step_cost} ₽"
        context.add_capacity(
            CapacityWarning(
                resource_code=pool.code,
                resource_name=pool.name,
                required=required_area,
                available=capacity,
                unit="м²",
                message=(
                    f"Складу требуется {required_area} м² при плане "
                    f"{plan_volume} м³/мес, доступно {capacity} м²: "
                    f"добавлено {steps} ступ. аренды."
                ),
            )
        )
    if monthly <= 0:
        return
    context.add_line(
        operation_code="WAREHOUSE_PICKING",
        cost_item_code="UNIT_WAREHOUSE_RENT",
        cost_item_name=f"Аренда склада ВМ: {pool.name}",
        layer=CostLayer.PRODUCTION,
        amount_rub=monthly * share,
        formula=f"{formula} × доля блока {share}",
    )
