"""ФОТ прямого персонала блока: постоянная часть, сделка, взносы и вахта.

Должность попадает в расчёт, только если её операция входит в пакет работ.
Косвенный персонал здесь не считается — он распределяется по объёму юнита
(`cost/model/unit.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

from cost.model.inputs import ModelContext, payload_number, payload_text
from cost.v2.models import CostLayer, ReferenceItem


# Операция должности → драйвер смен, выведенный из производительности техники.
DERIVED_SHIFT_DRIVERS: dict[str, str] = {
    "PRODUCTION_DRILLING": "rig_shifts",
    "CONTOUR_DRILLING": "rig_shifts",
    "BULK_CHARGING_SZM": "szm_shifts",
    "VM_DELIVERY_SITE": "delivery_shifts",
    "COMPONENT_DELIVERY": "delivery_shifts",
}

# Операции бурения: при субподряде их персонал считает подрядчик, поэтому
# собственный экипаж на блок не начисляется.
DRILLING_OPERATIONS = frozenset({"PRODUCTION_DRILLING", "CONTOUR_DRILLING"})

# Техника, чья месячная загрузка задаёт численность экипажа должности.
CREW_EQUIPMENT_PARAM: dict[str, str] = {
    "PRODUCTION_DRILLING": "rig_code",
    "CONTOUR_DRILLING": "rig_code",
    "BULK_CHARGING_SZM": "szm_code",
    "VM_DELIVERY_SITE": "delivery_truck_code",
    "COMPONENT_DELIVERY": "delivery_truck_code",
}


@dataclass(frozen=True)
class LaborLine:
    position_code: str
    position_name: str
    operation_code: str
    headcount: Decimal
    shifts_per_block: Decimal
    fixed_rub: Decimal
    piece_rub: Decimal
    accrued_rub: Decimal


def crew_members(context: ModelContext) -> tuple[tuple[str, Decimal, Decimal | None], ...]:
    """Состав бригады: параметры вкладки, иначе шаблон пакета."""

    if context.params.crew:
        return tuple(
            (member.position_code, member.headcount, member.shifts_per_block)
            for member in context.params.crew
        )
    template = next(
        (
            item
            for item in context.items("crew_templates")
            if payload_text(item, "package_code") == context.params.package_code
        ),
        None,
    )
    if template is None:
        return ()
    return tuple(
        (
            str(member.get("position_code", "")),
            payload_number_dict(member, "headcount", Decimal("1")),
            None,
        )
        for member in template.payload.get("members", [])
    )


def payload_number_dict(data: dict, key: str, default: Decimal) -> Decimal:
    value = data.get(key)
    if value in (None, ""):
        return default
    return Decimal(str(value))


def compute(context: ModelContext) -> tuple[LaborLine, ...]:
    rates = context.rates
    results: list[LaborLine] = []
    accrued_total = Decimal("0")
    per_diem_total = Decimal("0")

    for position_code, headcount, manual_shifts in crew_members(context):
        position = context.item("positions", position_code)
        if position is None:
            context.warn(f"Должность {position_code} не найдена в справочнике.")
            continue
        if payload_text(position, "category", "DIRECT") != "DIRECT":
            # Косвенный персонал — постоянная затрата юнита, а не блока.
            continue
        operation_code = payload_text(position, "operation_code")
        if not context.has_operation(operation_code):
            continue
        if (
            context.params.drilling_executor == "SUBCONTRACTOR"
            and operation_code in DRILLING_OPERATIONS
        ):
            # Бурение на субподряде оплачивается ставкой за метр: свой
            # бурильщик на блоке не работает, иначе смены считаются дважды.
            continue

        shifts = _shifts_per_block(context, position, operation_code, manual_shifts)
        crew_size = _headcount(context, position, operation_code, headcount)
        if shifts <= 0 or crew_size <= 0:
            continue

        rate_item = _labor_rate(context, position_code)
        if rate_item is None:
            context.warn(f"Для должности {position_code} не задана ставка в «Ставках персонала».")
            continue

        norm_shifts = payload_number(position, "norm_shifts_per_month", Decimal("21"))
        fixed_monthly = payload_number(rate_item, "fixed_monthly_rub")
        rate_per_shift = fixed_monthly / norm_shifts if norm_shifts > 0 else Decimal("0")
        fixed_block = rate_per_shift * shifts * crew_size

        piece_block, piece_formula = _piece_amount(context, position, rate_item, crew_size)
        accrued = fixed_block + piece_block
        if rates.salary_basis == "NET" and rates.income_tax_rate < 1:
            accrued = accrued / (Decimal("1") - rates.income_tax_rate)

        context.set_value(
            f"crew_shifts.{position_code}", shifts, f"смен на блок должности {position_code}"
        )
        context.set_value(f"crew_headcount.{position_code}", crew_size, "численность на блок")

        context.add_line(
            operation_code=operation_code,
            cost_item_code=f"LABOR_{position_code}",
            cost_item_name=f"ФОТ: {position.name}",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=accrued,
            formula=(
                f"{fixed_monthly} ₽/мес / {norm_shifts} см × {shifts} см × {crew_size} чел"
                + (f" + {piece_formula}" if piece_formula else "")
                + (" ÷ (1 − НДФЛ)" if rates.salary_basis == "NET" else "")
            ),
        )
        accrued_total += accrued
        per_diem_total += _per_diem(context, position, shifts, crew_size)
        results.append(
            LaborLine(
                position_code=position_code,
                position_name=position.name,
                operation_code=operation_code,
                headcount=crew_size,
                shifts_per_block=shifts,
                fixed_rub=fixed_block,
                piece_rub=piece_block,
                accrued_rub=accrued,
            )
        )

    if accrued_total > 0:
        contribution_rate = rates.social_contribution_rate + rates.injury_insurance_rate
        contributions = accrued_total * contribution_rate
        context.add_line(
            operation_code="",
            cost_item_code="LABOR_CONTRIBUTIONS",
            cost_item_name="Страховые взносы и НС",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=contributions,
            formula=f"{accrued_total} ₽ × {contribution_rate}",
        )
        reserve = (accrued_total + contributions) * rates.vacation_reserve_rate
        if reserve > 0:
            context.add_line(
                operation_code="",
                cost_item_code="LABOR_VACATION_RESERVE",
                cost_item_name="Резерв отпусков",
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=reserve,
                formula=f"({accrued_total} + {contributions}) ₽ × {rates.vacation_reserve_rate}",
            )

    if per_diem_total > 0:
        context.add_line(
            operation_code="",
            cost_item_code="LABOR_PER_DIEM",
            cost_item_name="Суточные и проживание",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=per_diem_total,
            formula=(
                f"чел-смены × ({context.rates.per_diem_rub} + {context.rates.lodging_rub}) ₽"
            ),
        )

    return tuple(results)


def _shifts_per_block(
    context: ModelContext,
    position: ReferenceItem,
    operation_code: str,
    manual_shifts: Decimal | None,
) -> Decimal:
    if manual_shifts is not None:
        return manual_shifts
    driver = DERIVED_SHIFT_DRIVERS.get(operation_code)
    if driver:
        derived = context.value(driver)
        if derived > 0:
            return derived
    norm_shifts = payload_number(position, "norm_shifts_per_month", Decimal("21"))
    norm_operations = payload_number(position, "norm_operations_per_month")
    if norm_operations > 0:
        return norm_shifts / norm_operations
    context.warn(
        f"Для должности {position.code} не задан норматив операций в месяц: "
        "смены на блок посчитаны как одна смена."
    )
    return Decimal("1")


def _headcount(
    context: ModelContext,
    position: ReferenceItem,
    operation_code: str,
    explicit: Decimal,
) -> Decimal:
    if explicit > 0:
        return explicit
    param_name = CREW_EQUIPMENT_PARAM.get(operation_code)
    equipment_code = getattr(context.params, param_name, None) if param_name else None
    equipment = context.item("equipment_types", equipment_code)
    if equipment is None:
        return Decimal("1")
    # Численность экипажа выводится из плановой загрузки техники: при плане в
    # 25 смен вместо 40 экипажу хватает двух человек вместо трёх.
    equipment_shifts = payload_number(equipment, "norm_shifts_per_month")
    if param_name == "rig_code" and context.params.rig_plan_shifts is not None:
        equipment_shifts = context.params.rig_plan_shifts
    person_shifts = payload_number(position, "norm_shifts_per_month", Decimal("21"))
    if equipment_shifts <= 0 or person_shifts <= 0:
        return Decimal("1")
    return (equipment_shifts / person_shifts).to_integral_value(rounding=ROUND_CEILING)


def _labor_rate(context: ModelContext, position_code: str) -> ReferenceItem | None:
    """Ставка: должность + условие бурения → должность без условия."""

    rows = [
        item
        for item in context.items("labor_rates")
        if payload_text(item, "position_code") == position_code
    ]
    if not rows:
        return None
    condition_code = _current_condition_code(context)
    if condition_code:
        exact = next(
            (item for item in rows if payload_text(item, "condition_code") == condition_code),
            None,
        )
        if exact is not None:
            return exact
    return next((item for item in rows if not payload_text(item, "condition_code")), rows[0])


def _current_condition_code(context: ModelContext) -> str:
    lineage = context.lineage.get("drilling_condition", "")
    if not lineage.startswith("drilling_conditions."):
        return ""
    return lineage.removeprefix("drilling_conditions.").split(" ", 1)[0]


def _piece_amount(
    context: ModelContext,
    position: ReferenceItem,
    rate_item: ReferenceItem,
    headcount: Decimal,
) -> tuple[Decimal, str]:
    """Сдельная часть начисляется каждому в бригаде: расценка — на человека."""

    piece_rate = payload_number(rate_item, "piece_rate_rub")
    driver_name = payload_text(position, "piece_driver")
    if piece_rate <= 0 or not driver_name:
        return Decimal("0"), ""
    piece_unit = payload_number(position, "piece_unit", Decimal("1"))
    if piece_unit <= 0:
        piece_unit = Decimal("1")
    driver_value = context.value(driver_name)
    amount = piece_rate * driver_value / piece_unit * headcount
    return (
        amount,
        f"{piece_rate} ₽ × {driver_value} {driver_name} / {piece_unit} × {headcount} чел",
    )


def _per_diem(
    context: ModelContext, position: ReferenceItem, shifts: Decimal, headcount: Decimal
) -> Decimal:
    if not bool(position.payload.get("per_diem_applies", True)):
        return Decimal("0")
    if context.site is None or not bool(context.site.payload.get("is_remote", False)):
        return Decimal("0")
    per_shift = context.rates.per_diem_rub + context.rates.lodging_rub
    if per_shift <= 0:
        return Decimal("0")
    return shifts * headcount * per_shift
