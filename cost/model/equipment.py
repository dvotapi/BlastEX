"""Затраты техники блока, кроме бурового станка: СЗМ и доставщик ВМ.

Амортизация и страховка приходят на блок через смены: месячная сумма делится
на плановые смены типа техники. Буровой станок считается в `drilling.py` —
там же живёт его плановая загрузка.
"""
from __future__ import annotations

from decimal import Decimal

from cost.model.inputs import ModelContext, payload_number, payload_text
from cost.v2.models import CostLayer, ReferenceItem


# Параметр модели → (драйвер смен, операция пакета, префикс статьи).
MACHINES: tuple[tuple[str, str, str, str], ...] = (
    ("szm_code", "szm_shifts", "BULK_CHARGING_SZM", "SZM"),
    ("delivery_truck_code", "delivery_shifts", "VM_DELIVERY_SITE", "VM_TRUCK"),
)


def compute(context: ModelContext) -> None:
    for param_name, shifts_driver, operation_code, prefix in MACHINES:
        code = getattr(context.params, param_name, None)
        equipment = context.item("equipment_types", code)
        shifts = context.value(shifts_driver)
        if equipment is None or shifts <= 0 or not context.has_operation(operation_code):
            continue
        _machine_lines(context, equipment, shifts, operation_code, prefix)


def _machine_lines(
    context: ModelContext,
    equipment: ReferenceItem,
    shifts: Decimal,
    operation_code: str,
    prefix: str,
) -> None:
    plan_shifts = payload_number(equipment, "norm_shifts_per_month")
    asset = _asset(context, equipment.code)

    if asset is not None and plan_shifts > 0:
        life = payload_number(asset, "useful_life_months")
        initial = payload_number(asset, "initial_cost_rub")
        monthly = initial / life if life > 0 else Decimal("0")
        if monthly <= 0:
            monthly = payload_number(asset, "depreciation_per_shift_rub") * plan_shifts
        if monthly > 0:
            context.add_line(
                operation_code=operation_code,
                cost_item_code=f"{prefix}_DEPRECIATION",
                cost_item_name=f"Амортизация: {equipment.name}",
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=monthly / plan_shifts * shifts,
                formula=f"{monthly} ₽/мес / {plan_shifts} см × {shifts} см",
            )
        insurance = payload_number(asset, "insurance_monthly_rub")
        if insurance > 0:
            context.add_line(
                operation_code=operation_code,
                cost_item_code=f"{prefix}_INSURANCE",
                cost_item_name=f"Страхование: {equipment.name}",
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=insurance / plan_shifts * shifts,
                formula=f"{insurance} ₽/мес / {plan_shifts} см × {shifts} см",
            )
    elif asset is None:
        context.warn(
            f"Для техники {equipment.code} не заведено основное средство: "
            "амортизация и страховка не начислены."
        )
    if asset is not None and plan_shifts <= 0:
        context.warn(
            f"Для техники {equipment.code} не заданы плановые смены в месяц: "
            "амортизация и страховка не начислены."
        )

    _maintenance(context, equipment, shifts, plan_shifts, operation_code, prefix)

    per_shift = payload_number(equipment, "inspection_rub_per_shift") + payload_number(
        equipment, "medical_rub_per_shift"
    )
    if per_shift > 0:
        context.add_line(
            operation_code=operation_code,
            cost_item_code=f"{prefix}_INSPECTION",
            cost_item_name=f"Выпуск на линию и медосмотр: {equipment.name}",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=shifts * per_shift,
            formula=f"{shifts} см × {per_shift} ₽/см",
        )

    spare_parts = payload_number(equipment, "spare_parts_rub_per_shift")
    if spare_parts > 0:
        context.add_line(
            operation_code=operation_code,
            cost_item_code=f"{prefix}_SPARE_PARTS",
            cost_item_name=f"Запчасти: {equipment.name}",
            layer=CostLayer.VARIABLE,
            amount_rub=shifts * spare_parts,
            formula=f"{shifts} см × {spare_parts} ₽/см",
        )


def _maintenance(
    context: ModelContext,
    equipment: ReferenceItem,
    shifts: Decimal,
    plan_shifts: Decimal,
    operation_code: str,
    prefix: str,
) -> None:
    mode = payload_text(equipment, "maintenance_mode", "PER_SHIFT")
    if mode == "MONTHLY_BUDGET":
        budget = payload_number(equipment, "maintenance_monthly_rub")
        if budget <= 0 or plan_shifts <= 0:
            return
        amount = budget / plan_shifts * shifts
        formula = f"{budget} ₽/мес / {plan_shifts} см × {shifts} см"
    else:
        rate = payload_number(equipment, "maintenance_rub_per_shift")
        if rate <= 0:
            return
        maintenance_shifts = shifts * (
            Decimal("1") + payload_number(equipment, "maintenance_ratio")
        )
        amount = maintenance_shifts * rate
        formula = f"{maintenance_shifts} см × {rate} ₽/см"
    context.add_line(
        operation_code=operation_code,
        cost_item_code=f"{prefix}_MAINTENANCE",
        cost_item_name=f"ТОиР: {equipment.name}",
        layer=CostLayer.PROJECT_DIRECT,
        amount_rub=amount,
        formula=formula,
    )


def _asset(context: ModelContext, equipment_type_code: str) -> ReferenceItem | None:
    for item in context.items("equipment_assets"):
        if payload_text(item, "equipment_type_code") == equipment_type_code:
            return item
    return None
