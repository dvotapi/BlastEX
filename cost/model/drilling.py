"""Нормы бурения: скорость → смены станка → износ оснастки, ДТ и постоянные.

Стоимость метра делится на переменную часть (не зависит от загрузки) и
постоянную часть станка, которая распределяется по плановым сменам. Именно
поэтому плановые смены — параметр вкладки, а не константа в формуле.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cost.model.inputs import ModelContext, payload_number, payload_text
from cost.v2.models import CostLayer, ReferenceItem


DRILLING_OPERATION = "PRODUCTION_DRILLING"

# Материалы оснастки: код поля условия бурения → (название строки, поле ресурса).
TOOLING_PARTS: tuple[tuple[str, str, str], ...] = (
    ("bit_material_code", "bit_life_m", "коронка"),
    ("hammer_material_code", "hammer_life_m", "ППУ"),
    ("rods_material_code", "rods_life_m", "штанги и переводники"),
)


@dataclass(frozen=True)
class DrillingNorms:
    condition: ReferenceItem | None
    v_commercial_m_per_shift: Decimal
    rig_shifts: Decimal
    maintenance_shifts: Decimal
    plan_shifts: Decimal
    plan_metres: Decimal
    variable_rub_per_m: Decimal
    fixed_rub_per_m: Decimal

    @property
    def cost_rub_per_m(self) -> Decimal:
        return self.variable_rub_per_m + self.fixed_rub_per_m


def pick_condition(
    context: ModelContext, rig_code: str | None, rock_code: str | None, site_code: str | None
) -> tuple[ReferenceItem | None, str]:
    """Подбор нормы бурения: станок + карьер → станок + порода → станок.

    Возвращает запись и строку происхождения: пользователь должен видеть, по
    какой именно норме посчитан блок.
    """

    if not rig_code:
        return None, "не задан буровой станок"
    rows = [
        item
        for item in context.items("drilling_conditions")
        if payload_text(item, "equipment_type_code") == rig_code
    ]
    if not rows:
        return None, f"нет условий бурения для станка {rig_code}"

    def by(site: bool, rock: bool) -> ReferenceItem | None:
        for item in rows:
            item_site = payload_text(item, "site_code")
            item_rock = payload_text(item, "rock_code")
            if site and item_site != (site_code or ""):
                continue
            if not site and item_site:
                continue
            if rock and item_rock != (rock_code or ""):
                continue
            if not rock and item_rock:
                continue
            return item
        return None

    if site_code:
        exact = by(site=True, rock=True) or by(site=True, rock=False)
        if exact is not None:
            return exact, f"drilling_conditions.{exact.code} (станок + карьер)"
    if rock_code:
        by_rock = by(site=False, rock=True)
        if by_rock is not None:
            return by_rock, f"drilling_conditions.{by_rock.code} (станок + порода)"
    default = by(site=False, rock=False)
    if default is not None:
        return default, f"drilling_conditions.{default.code} (норма станка по умолчанию)"
    return None, f"нет нормы по умолчанию для станка {rig_code}"


def material_price(context: ModelContext, material_code: str) -> Decimal:
    """Цена материала из `material_prices`: цена плюс доставка в цене."""

    prices = [
        item
        for item in context.items("material_prices")
        if payload_text(item, "material_code") == material_code
    ]
    if not prices:
        return Decimal("0")
    # Последняя по valid_from запись — цена «на дату расчёта».
    prices.sort(key=lambda item: (item.valid_from is not None, item.valid_from or ""), reverse=True)
    row = prices[0]
    return payload_number(row, "price_rub") + payload_number(row, "delivery_rub")


def compute(context: ModelContext) -> DrillingNorms | None:
    """Натуральные величины и строки затрат бурения.

    Возвращает ``None``, если бурения нет в пакете: тогда ни строк, ни
    предупреждений быть не должно.
    """

    if not context.has_operation(DRILLING_OPERATION):
        return None
    drilling_m = context.value("drilling_m")
    if drilling_m <= 0:
        return None

    if context.params.drilling_executor == "SUBCONTRACTOR":
        _subcontract_lines(context, drilling_m)
        return None

    params = context.params
    rock_code = payload_text(context.site, "rock_code") or None
    condition, lineage = pick_condition(context, params.rig_code, rock_code, params.site_code)
    context.lineage["drilling_condition"] = lineage
    rig_type = context.item("equipment_types", params.rig_code)
    if condition is None or rig_type is None:
        context.warn(
            "Бурение не рассчитано: "
            + (lineage if condition is None else f"тип техники {params.rig_code} не найден")
            + ". Строки бурения нулевые."
        )
        context.set_value("rig_shifts", Decimal("0"), lineage)
        return None

    tech_speed = payload_number(condition, "tech_speed_m_per_h")
    unproductive = payload_number(condition, "unproductive_h_per_shift")
    shift_hours = context.rates.shift_hours
    productive_hours = shift_hours - unproductive
    if tech_speed <= 0 or productive_hours <= 0:
        context.warn(
            f"В условии бурения {condition.code} не задана техническая скорость "
            "или непроизводительное время больше смены."
        )
        return None

    v_commercial = tech_speed * productive_hours
    rig_shifts = drilling_m / v_commercial
    maintenance_ratio = payload_number(rig_type, "maintenance_ratio")
    maintenance_shifts = rig_shifts * maintenance_ratio
    plan_shifts = params.rig_plan_shifts or payload_number(
        rig_type, "norm_shifts_per_month", Decimal("0")
    )
    plan_metres = plan_shifts * v_commercial

    context.set_value(
        "v_commercial_m_per_shift",
        v_commercial,
        f"{tech_speed} м/ч × ({shift_hours} − {unproductive}) ч",
    )
    context.set_value("rig_shifts", rig_shifts, f"{drilling_m} м / {v_commercial} м/см")
    context.set_value(
        "rig_maintenance_shifts", maintenance_shifts, f"{rig_shifts} см × {maintenance_ratio}"
    )
    context.set_value("rig_plan_shifts", plan_shifts, "параметр модели")
    context.set_value("rig_plan_metres", plan_metres, f"{plan_shifts} см × {v_commercial} м/см")

    variable_per_m = _tooling_lines(context, condition, drilling_m)
    variable_per_m += _fuel_line(context, condition, drilling_m)
    variable_per_m += _spare_parts_line(context, rig_type, rig_shifts, drilling_m)
    fixed_per_m = _fixed_lines(
        context, rig_type, rig_shifts, maintenance_shifts, plan_shifts, plan_metres
    )
    variable_per_m += _inspection_line(context, rig_type, rig_shifts + maintenance_shifts, drilling_m)

    context.set_value("drilling_variable_rub_per_m", variable_per_m, "сумма переменных строк / м")
    context.set_value("drilling_fixed_rub_per_m", fixed_per_m, "постоянные станка / плановый погонаж")
    context.set_value("drilling_rub_per_m", variable_per_m + fixed_per_m, "переменная + постоянная")

    return DrillingNorms(
        condition=condition,
        v_commercial_m_per_shift=v_commercial,
        rig_shifts=rig_shifts,
        maintenance_shifts=maintenance_shifts,
        plan_shifts=plan_shifts,
        plan_metres=plan_metres,
        variable_rub_per_m=variable_per_m,
        fixed_rub_per_m=fixed_per_m,
    )


def _tooling_lines(
    context: ModelContext, condition: ReferenceItem, drilling_m: Decimal
) -> Decimal:
    total = Decimal("0")
    per_m = Decimal("0")
    parts: list[str] = []
    for code_field, life_field, label in TOOLING_PARTS:
        material_code = payload_text(condition, code_field)
        life = payload_number(condition, life_field)
        if not material_code or life <= 0:
            continue
        price = material_price(context, material_code)
        if price <= 0:
            context.warn(f"Нет цены материала {material_code} ({label}) для бурения.")
            continue
        quantity = drilling_m / life
        context.set_value(
            f"drilling_{code_field.removesuffix('_material_code')}_pcs",
            quantity,
            f"{drilling_m} м / {life} м",
        )
        per_m += price / life
        total += quantity * price
        parts.append(f"{label}: {drilling_m} / {life} × {price} ₽")

    casing_per_m = payload_number(condition, "casing_m_per_m")
    casing_code = payload_text(condition, "casing_material_code")
    if casing_per_m > 0 and casing_code:
        price = material_price(context, casing_code)
        casing_m = drilling_m * casing_per_m
        context.set_value("drilling_casing_m", casing_m, f"{drilling_m} м × {casing_per_m} м/м")
        per_m += casing_per_m * price
        total += casing_m * price
        parts.append(f"обсадка: {casing_m} м × {price} ₽")

    if total > 0:
        context.add_line(
            operation_code=DRILLING_OPERATION,
            cost_item_code="DRILL_TOOLING",
            cost_item_name="Буровая оснастка",
            layer=CostLayer.VARIABLE,
            amount_rub=total,
            formula="; ".join(parts),
        )
    return per_m


def _fuel_line(context: ModelContext, condition: ReferenceItem, drilling_m: Decimal) -> Decimal:
    fuel_l_per_m = payload_number(condition, "fuel_l_per_m")
    if fuel_l_per_m <= 0:
        return Decimal("0")
    litres = drilling_m * fuel_l_per_m
    context.set_value("drilling_fuel_l", litres, f"{drilling_m} м × {fuel_l_per_m} л/м")
    if context.site is not None and bool(context.site.payload.get("customer_provides_fuel")):
        context.warn("Топливо на объекте предоставляет заказчик: ДТ бурения не начислено.")
        return Decimal("0")
    price = context.diesel_price_l()
    if price <= 0:
        context.warn("Не задана цена ДТ на объекте: топливо бурения не начислено.")
        return Decimal("0")
    context.add_line(
        operation_code=DRILLING_OPERATION,
        cost_item_code="DRILL_FUEL",
        cost_item_name="ДТ на бурение",
        layer=CostLayer.VARIABLE,
        amount_rub=litres * price,
        formula=f"{drilling_m} м × {fuel_l_per_m} л/м × {price} ₽/л",
    )
    return fuel_l_per_m * price


def _spare_parts_line(
    context: ModelContext, rig_type: ReferenceItem, rig_shifts: Decimal, drilling_m: Decimal
) -> Decimal:
    rate = payload_number(rig_type, "spare_parts_rub_per_shift")
    if rate <= 0:
        return Decimal("0")
    amount = rig_shifts * rate
    context.add_line(
        operation_code=DRILLING_OPERATION,
        cost_item_code="DRILL_SPARE_PARTS",
        cost_item_name="Запчасти и расходники станка",
        layer=CostLayer.VARIABLE,
        amount_rub=amount,
        formula=f"{rig_shifts} см × {rate} ₽/см",
    )
    return amount / drilling_m if drilling_m > 0 else Decimal("0")


def _fixed_lines(
    context: ModelContext,
    rig_type: ReferenceItem,
    rig_shifts: Decimal,
    maintenance_shifts: Decimal,
    plan_shifts: Decimal,
    plan_metres: Decimal,
) -> Decimal:
    if plan_shifts <= 0:
        context.warn(
            "Не заданы плановые смены станка: постоянная часть бурения не распределена."
        )
        return Decimal("0")

    asset = _rig_asset(context, rig_type.code)
    # Станок амортизируется и в сменах ТОиР: они входят в наработку блока.
    charged_shifts = rig_shifts + maintenance_shifts
    monthly = Decimal("0")
    if asset is not None:
        life = payload_number(asset, "useful_life_months")
        initial = payload_number(asset, "initial_cost_rub")
        depreciation_month = initial / life if life > 0 else Decimal("0")
        if depreciation_month <= 0:
            # Записи, перенесённые из Cost V1, хранят амортизацию за смену.
            depreciation_month = payload_number(asset, "depreciation_per_shift_rub") * plan_shifts
        insurance_month = payload_number(asset, "insurance_monthly_rub")
        if depreciation_month > 0:
            amount = depreciation_month / plan_shifts * charged_shifts
            monthly += depreciation_month
            context.add_line(
                operation_code=DRILLING_OPERATION,
                cost_item_code="DRILL_DEPRECIATION",
                cost_item_name="Амортизация бурового станка",
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=amount,
                formula=f"{depreciation_month} ₽/мес / {plan_shifts} см × {charged_shifts} см",
            )
        if insurance_month > 0:
            monthly += insurance_month
            context.add_line(
                operation_code=DRILLING_OPERATION,
                cost_item_code="DRILL_INSURANCE",
                cost_item_name="Страхование бурового станка",
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=insurance_month / plan_shifts * charged_shifts,
                formula=f"{insurance_month} ₽/мес / {plan_shifts} см × {charged_shifts} см",
            )
    else:
        context.warn(
            f"Для станка {rig_type.code} не заведено основное средство: "
            "амортизация и страховка не начислены."
        )

    maintenance_monthly = _maintenance_lines(
        context, rig_type, rig_shifts, maintenance_shifts, plan_shifts
    )
    monthly += maintenance_monthly
    return monthly / plan_metres if plan_metres > 0 else Decimal("0")


def _inspection_line(
    context: ModelContext, rig_type: ReferenceItem, shifts: Decimal, drilling_m: Decimal
) -> Decimal:
    per_shift = payload_number(rig_type, "inspection_rub_per_shift") + payload_number(
        rig_type, "medical_rub_per_shift"
    )
    if per_shift <= 0:
        return Decimal("0")
    amount = shifts * per_shift
    context.add_line(
        operation_code=DRILLING_OPERATION,
        cost_item_code="DRILL_INSPECTION",
        cost_item_name="Выпуск на линию и медосмотр экипажа станка",
        layer=CostLayer.VARIABLE,
        amount_rub=amount,
        formula=f"{shifts} см × {per_shift} ₽/см",
    )
    return amount / drilling_m if drilling_m > 0 else Decimal("0")


def _maintenance_lines(
    context: ModelContext,
    rig_type: ReferenceItem,
    rig_shifts: Decimal,
    maintenance_shifts: Decimal,
    plan_shifts: Decimal,
) -> Decimal:
    mode = payload_text(rig_type, "maintenance_mode", "PER_SHIFT")
    if mode == "MONTHLY_BUDGET":
        budget = payload_number(rig_type, "maintenance_monthly_rub")
        if budget <= 0:
            return Decimal("0")
        context.add_line(
            operation_code=DRILLING_OPERATION,
            cost_item_code="DRILL_MAINTENANCE",
            cost_item_name="ТОиР бурового станка",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=budget / plan_shifts * rig_shifts,
            formula=f"{budget} ₽/мес / {plan_shifts} см × {rig_shifts} см",
        )
        return budget
    rate = payload_number(rig_type, "maintenance_rub_per_shift")
    if rate <= 0:
        return Decimal("0")
    shifts = rig_shifts + maintenance_shifts
    context.add_line(
        operation_code=DRILLING_OPERATION,
        cost_item_code="DRILL_MAINTENANCE",
        cost_item_name="ТОиР бурового станка",
        layer=CostLayer.PROJECT_DIRECT,
        amount_rub=shifts * rate,
        formula=f"({rig_shifts} + {maintenance_shifts}) см × {rate} ₽/см",
    )
    return Decimal("0")


def _rig_asset(context: ModelContext, rig_code: str) -> ReferenceItem | None:
    for item in context.items("equipment_assets"):
        if payload_text(item, "equipment_type_code") == rig_code:
            return item
    return None


def _subcontract_lines(context: ModelContext, drilling_m: Decimal) -> None:
    rate_item = next(
        (
            item
            for item in context.items("subcontract_rates")
            if payload_text(item, "operation_code") == DRILLING_OPERATION
        ),
        None,
    )
    rate = payload_number(rate_item, "rate_rub")
    if rate <= 0:
        context.warn(
            "Не задана субподрядная ставка бурения: строка субподряда нулевая."
        )
    context.set_value("rig_shifts", Decimal("0"), "бурение на субподряде")
    context.add_line(
        operation_code=DRILLING_OPERATION,
        cost_item_code="DRILL_SUBCONTRACT",
        cost_item_name="Субподряд: бурение",
        layer=CostLayer.VARIABLE,
        amount_rub=drilling_m * rate,
        formula=f"{drilling_m} м × {rate} ₽/м",
    )

    params = context.params
    rig_type = context.item("equipment_types", params.rig_code)
    asset = _rig_asset(context, params.rig_code) if params.rig_code else None
    if rig_type is None or asset is None:
        return
    plan_shifts = params.rig_plan_shifts or payload_number(rig_type, "norm_shifts_per_month")
    life = payload_number(asset, "useful_life_months")
    monthly = (
        payload_number(asset, "initial_cost_rub") / life if life > 0 else Decimal("0")
    ) + payload_number(asset, "insurance_monthly_rub")
    if monthly <= 0 or plan_shifts <= 0:
        return
    share = _unit_share(context)
    amount = monthly * share
    context.add_line(
        operation_code=DRILLING_OPERATION,
        cost_item_code="DRILL_UNALLOCATED_FIXED",
        cost_item_name="Нераспределённые постоянные станка",
        layer=CostLayer.FULL,
        amount_rub=amount,
        formula=f"{monthly} ₽/мес × доля блока {share}",
    )
    context.warn(
        "Бурение на субподряде: постоянные затраты собственного станка "
        "показаны как нераспределённые затраты юнита."
    )


def _unit_share(context: ModelContext) -> Decimal:
    plan = context.params.unit_plan_volume_m3
    if plan <= 0:
        return Decimal("0")
    return context.block_volume_m3 / plan
