"""ФОТ прямого персонала блока: постоянная часть, сделка, взносы и вахта.

Должность попадает в расчёт, только если её операция входит в пакет работ.
Косвенный персонал здесь не считается — он распределяется по объёму юнита
(`cost/model/unit.py`).

Численность двух видов: `headcount` состава бригады — люди в смене, им идут
сделка и суточные; штат на ротацию экипажа техники модель выводит из плановых
смен машины, и на него приходится только месячный оклад.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_CEILING
from typing import Iterable, Mapping

from cost.model.inputs import (
    ModelContext,
    PayrollPart,
    driver_unit,
    formula_number,
    formula_quantity,
    payload_number,
    payload_text,
    payroll_parts,
)
from cost.v2.models import CostLayer, ReferenceItem


# Операция должности → драйвер смен, выведенный из производительности техники.
DERIVED_SHIFT_DRIVERS: dict[str, str] = {
    "PRODUCTION_DRILLING": "rig_shifts",
    "CONTOUR_DRILLING": "rig_shifts",
    "BULK_CHARGING_SZM": "szm_shifts",
    "VM_DELIVERY_SITE": "delivery_shifts",
    "COMPONENT_DELIVERY": "emulsion_shifts",
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
    "COMPONENT_DELIVERY": "emulsion_truck_code",
}


@dataclass(frozen=True)
class LaborLine:
    position_code: str
    position_name: str
    operation_code: str
    # Человек в смене: столько людей должности одновременно работает в одной смене.
    headcount: Decimal
    shifts_per_block: Decimal
    fixed_rub: Decimal
    piece_rub: Decimal
    accrued_rub: Decimal
    # Штат на ротацию экипажа техники; None — должность не экипаж техники или
    # у техники нет плановых смен.
    rotation_headcount: Decimal | None = None


@dataclass(frozen=True)
class CrewRotation:
    """Штат экипажа техники, закрывающий её плановые смены."""

    equipment_code: str
    plan_shifts: Decimal
    person_shifts: Decimal
    headcount: Decimal


def template_crew(
    templates: Iterable[ReferenceItem], package_code: str, rig_class: str | None
) -> tuple[tuple[str, Decimal], ...]:
    """Состав из шаблонов пакета: общие (без класса станка) и подходящие под класс.

    Шаблон с `rig_class` действует только для станков этого класса: экипаж
    бурения зависит от типа машины (гусеничный интегрированный — один
    машинист, станок с отдельным компрессором — машинист и помощник), а
    остальная бригада блока от станка не зависит.
    """

    members: list[tuple[str, Decimal]] = []
    for item in templates:
        if payload_text(item, "package_code") != package_code:
            continue
        template_class = payload_text(item, "rig_class")
        if template_class and template_class != (rig_class or ""):
            continue
        members.extend(
            (str(member.get("position_code", "")), payload_number_dict(member, "headcount", Decimal("1")))
            for member in item.payload.get("members", [])
        )
    return tuple(members)


def rig_specific_crew(
    templates: Iterable[ReferenceItem], package_code: str, rig_class: str | None
) -> tuple[tuple[str, Decimal], ...]:
    """Только состав класса станка (без общих шаблонов): им черновик заменяет экипаж при смене станка."""

    if not rig_class:
        return ()
    members: list[tuple[str, Decimal]] = []
    for item in templates:
        if payload_text(item, "package_code") == package_code and payload_text(item, "rig_class") == rig_class:
            members.extend(
                (str(member.get("position_code", "")), payload_number_dict(member, "headcount", Decimal("1")))
                for member in item.payload.get("members", [])
            )
    return tuple(members)


def crew_members(context: ModelContext) -> tuple[tuple[str, Decimal, Decimal | None], ...]:
    """Состав бригады: параметры вкладки, иначе шаблоны пакета (с учётом станка)."""

    if context.params.crew:
        return tuple(
            (member.position_code, member.headcount, member.shifts_per_block)
            for member in context.params.crew
        )
    return tuple(
        (code, headcount, None)
        for code, headcount in template_crew(
            context.items("crew_templates"),
            context.params.package_code,
            payload_text(context.item("equipment_types", context.params.rig_code), "rig_class") or None,
        )
    )


def payload_number_dict(data: dict, key: str, default: Decimal) -> Decimal:
    value = data.get(key)
    if value in (None, ""):
        return default
    return Decimal(str(value))


def compute(context: ModelContext) -> tuple[LaborLine, ...]:
    rates = context.rates
    results: list[LaborLine] = []
    # Начисленный ФОТ, суточные и их человеко-смены — по операциям: взносы,
    # резерв отпусков и суточные идут строкой той операции, где работают люди,
    # иначе цена метра бурения (строки операций бурения) их не видит.
    accrued_by_operation: dict[str, Decimal] = {}
    per_diem_by_operation: dict[str, Decimal] = {}
    # Человеко-смены, на которые начислены суточные: ставка у них одна, значит
    # у строки есть и норма, и цена — как у любой другой статьи сметы.
    per_diem_shifts: dict[str, Decimal] = {}

    # Человеко-смены на вахте по операциям: проживание и питание положены и
    # должностям методики ФОТ, хотя их ФОТ считает `block_payroll`.
    camp_shifts: dict[str, Decimal] = {}

    for position_code, headcount, manual_shifts in crew_members(context):
        if position_code in context.payroll_positions:
            # Должность уже посчитана методикой ФОТ (`block_payroll`): вторая
            # строка, взносы и суточные на неё дали бы двойной ФОТ (Т4).
            # Проживание и питание — не ФОТ: смены и людей в смене берём из методики.
            position = context.item("positions", position_code)
            if position is not None and on_watch(context, position):
                operation_code = payload_text(position, "operation_code")
                quantity = context.values.get(f"crew_shifts.{position_code}", Decimal("0")) * context.values.get(
                    f"crew_per_shift.{position_code}", Decimal("0")
                )
                camp_shifts[operation_code] = camp_shifts.get(operation_code, Decimal("0")) + quantity
            continue
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
        if shifts <= 0:
            continue
        per_shift = per_shift_headcount(headcount)

        rate_item = _labor_rate(context, position_code)
        if rate_item is None:
            context.warn(f"Для должности {position_code} не задана ставка в «Ставках персонала».")
            continue

        fixed_monthly = payload_number(rate_item, "fixed_monthly_rub")
        # Читаем один раз: норма нужна и экипажу техники (штат ротации), и
        # обычной ставке человеко-смены (F2 ревью PR #80).
        norm_shifts = payload_number(position, "norm_shifts_per_month", Decimal("21"))
        # Персонал участка со сменами на блок — ставка человеко-смены, без штата ротации техники.
        rotation = (
            None
            if block_shifts(position) > 0
            else crew_rotation(context, position, operation_code, per_shift, fixed_monthly, norm_shifts)
        )
        per_shift, rotation = apply_crew_scale(context.params.crew_scale, per_shift, rotation)
        fixed_block, fixed_formula = fixed_amount(fixed_monthly, shifts, per_shift, rotation, norm_shifts)
        piece_block, piece_formula = _piece_amount(context, position, rate_item, per_shift)
        accrued = fixed_block + piece_block
        if rates.salary_basis == "NET" and rates.income_tax_rate < 1:
            accrued = accrued / (Decimal("1") - rates.income_tax_rate)

        context.set_value(
            f"crew_shifts.{position_code}", shifts, f"смен на блок должности {position_code}"
        )
        context.set_value(
            f"crew_per_shift.{position_code}",
            per_shift,
            "человек в смене" if headcount > 0 else "в составе 0 — один человек в смене",
        )
        if rotation is not None:
            context.set_value(
                f"crew_rotation.{position_code}",
                rotation.headcount,
                f"⌈{rotation.plan_shifts} см {rotation.equipment_code} × {per_shift} чел / "
                f"{rotation.person_shifts} см человека⌉",
            )

        context.add_line(
            operation_code=operation_code,
            cost_item_code=f"LABOR_{position_code}",
            cost_item_name=f"ФОТ: {position.name}",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=accrued,
            formula=(
                fixed_formula
                + (f" + {piece_formula}" if piece_formula else "")
                + (" ÷ (1 − НДФЛ)" if rates.salary_basis == "NET" else "")
            ),
            section="LABOR",
            # Цены за единицу нет: оклад, сдельная часть и НДФЛ дают разную
            # ставку за смену, одним числом её не назвать.
            quantity=shifts * per_shift,
            unit="чел·см",
            # Смены — ручная поправка вкладки, если сметчик её задал,
            # иначе норматив должности или производительность техники.
            quantity_origin="MANUAL" if manual_shifts is not None else "NORM",
        )
        accrued_by_operation[operation_code] = accrued_by_operation.get(operation_code, Decimal("0")) + accrued
        if on_watch(context, position):
            camp_shifts[operation_code] = camp_shifts.get(operation_code, Decimal("0")) + shifts * per_shift
        charge = _per_diem(context, position, shifts, per_shift)
        context.payroll_parts[f"LABOR_{position_code}"] = _rate_parts(
            context, fixed_block, piece_block, accrued, charge
        )
        if charge > 0:
            per_diem_by_operation[operation_code] = per_diem_by_operation.get(operation_code, Decimal("0")) + charge
            per_diem_shifts[operation_code] = per_diem_shifts.get(operation_code, Decimal("0")) + shifts * per_shift
        results.append(
            LaborLine(
                position_code=position_code,
                position_name=position.name,
                operation_code=operation_code,
                headcount=per_shift,
                shifts_per_block=shifts,
                fixed_rub=fixed_block,
                piece_rub=piece_block,
                accrued_rub=accrued,
                rotation_headcount=rotation.headcount if rotation is not None else None,
            )
        )

    _charge_lines(context, accrued_by_operation)
    _per_diem_lines(context, per_diem_by_operation, per_diem_shifts)
    _camp_lines(context, camp_shifts)

    return tuple(results)


def _operation_label(context: ModelContext, operation_code: str) -> str:
    operation = context.item("operations", operation_code) if operation_code else None
    return operation.name if operation is not None else (operation_code or "бригада")


# Статья должности, которая лежит в смете отдельной строкой операции.
_ABSORBED_ITEMS = {
    "CONTRIBUTIONS": "LABOR_CONTRIBUTIONS",
    "VACATION_RESERVE": "LABOR_VACATION_RESERVE",
    "PER_DIEM": "LABOR_PER_DIEM",
}


def _rate_parts(
    context: ModelContext, fixed: Decimal, piece: Decimal, accrued: Decimal, per_diem: Decimal
) -> tuple[PayrollPart, ...]:
    """Статьи ФОТ должности на ставках: оклад, премиальная часть и её доля взносов, резерва и суточных.

    Взносы и резерв — по тем же формулам, что строки операции в `_charge_lines`
    (они линейны по начисленному), суточные — `_per_diem` должности. НДФЛ
    сверху оклада «на руки» делится между окладом и сдельной частью.
    """

    rates = context.rates
    base = fixed + piece
    gross_up = accrued / base if base > 0 else Decimal("1")
    contributions = accrued * (rates.social_contribution_rate + rates.injury_insurance_rate) if accrued > 0 else Decimal("0")
    reserve = (accrued + contributions) * rates.vacation_reserve_rate if accrued > 0 else Decimal("0")
    return payroll_parts(
        {
            "SALARY": fixed * gross_up,
            "PREMIUM": piece * gross_up,
            "PER_DIEM": per_diem,
            "VACATION_RESERVE": reserve,
            "CONTRIBUTIONS": contributions,
        },
        _ABSORBED_ITEMS,
    )


def _charge_lines(context: ModelContext, accrued_by_operation: Mapping[str, Decimal]) -> None:
    """Страховые взносы и резерв отпусков — строкой на операцию начисленного ФОТ.

    Сумма по блоку та же, что у одной общей строки: взносы линейны по ФОТ.
    Строка операции бурения входит в цену метра, как и сам ФОТ экипажа.
    """

    rates = context.rates
    contribution_rate = rates.social_contribution_rate + rates.injury_insurance_rate
    for operation_code, accrued in accrued_by_operation.items():
        if accrued <= 0:
            continue
        label = _operation_label(context, operation_code)
        contributions = accrued * contribution_rate
        context.add_line(
            operation_code=operation_code,
            cost_item_code="LABOR_CONTRIBUTIONS",
            cost_item_name=f"Страховые взносы и НС: {label}",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=contributions,
            formula=f"{formula_number(accrued)} ₽ × {formula_number(contribution_rate)}",
            section="LABOR",
            quantity_origin="CALC",
            price_origin="REFERENCE",
        )
        reserve = (accrued + contributions) * rates.vacation_reserve_rate
        if reserve > 0:
            context.add_line(
                operation_code=operation_code,
                cost_item_code="LABOR_VACATION_RESERVE",
                cost_item_name=f"Резерв отпусков: {label}",
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=reserve,
                formula=f"({formula_number(accrued)} + {formula_number(contributions)}) ₽ × {formula_number(rates.vacation_reserve_rate)}",
                section="LABOR",
                quantity_origin="CALC",
                price_origin="REFERENCE",
            )


def _per_diem_lines(
    context: ModelContext,
    per_diem_by_operation: Mapping[str, Decimal],
    per_diem_shifts: Mapping[str, Decimal],
) -> None:
    """Суточные — строкой на операцию, как проживание и питание."""

    for operation_code, amount in per_diem_by_operation.items():
        if amount <= 0:
            continue
        quantity = per_diem_shifts.get(operation_code, Decimal("0"))
        context.add_line(
            operation_code=operation_code,
            cost_item_code="LABOR_PER_DIEM",
            cost_item_name=f"Суточные: {_operation_label(context, operation_code)}",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=amount,
            formula=f"{formula_number(quantity)} чел·см × {formula_number(context.rates.per_diem_rub)} ₽",
            section="PER_DIEM",
            quantity=quantity,
            unit="чел·см",
            # Ставка берётся из справочника, а не делением суммы на смены:
            # деление вернуло бы её с двоичным хвостом, и «норма × цена» в
            # смете перестала бы сходиться с суммой строки.
            unit_price_rub=per_diem_rate(context),
            quantity_origin="CALC",
            price_origin="REFERENCE",
        )


def block_shifts(position: ReferenceItem | None) -> Decimal:
    """Смены на блок, заданные должности (слесарь, механик участка); 0 — не задано.

    Такая должность — персонал участка, а не экипаж техники: её смены не берутся
    у станка, штат ротации и методика ФОТ к ней не применяются.
    """

    return payload_number(position, "shifts_per_block") if position is not None else Decimal("0")


def _shifts_per_block(
    context: ModelContext,
    position: ReferenceItem,
    operation_code: str,
    manual_shifts: Decimal | None,
) -> Decimal:
    if manual_shifts is not None:
        return manual_shifts
    if block_shifts(position) > 0:
        return block_shifts(position)
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


def per_shift_headcount(explicit: Decimal) -> Decimal:
    """Человек в смене из состава бригады.

    Ноль — прежнее «по экипажу техники»: в смене один человек, а штат на
    ротацию модель выводит сама. Так записан бурильщик в шаблонах, и так же
    очищенное поле численности приходит с вкладки.
    """

    return explicit if explicit > 0 else Decimal("1")


def apply_crew_scale(
    scale: Decimal, per_shift: Decimal, rotation: CrewRotation | None
) -> tuple[Decimal, CrewRotation | None]:
    """Множитель чувствительности — на людей в смене и на округлённый штат.

    Штат считается по составу бригады и округляется вверх до множителя: иначе
    водитель СЗМ при +10 % получил бы ⌈1,1⌉ = 2 человека и двойной оклад, а
    при −10 % — прежний. С множителем после округления ФОТ меняется ровно на
    ±10 %, как остальные строки чувствительности.
    """

    if scale == 1:
        return per_shift, rotation
    if rotation is not None:
        rotation = replace(rotation, headcount=rotation.headcount * scale)
    return per_shift * scale, rotation


def crew_rotation(
    context: ModelContext,
    position: ReferenceItem,
    operation_code: str,
    per_shift: Decimal,
    fixed_monthly: Decimal,
    norm_shifts: Decimal,
) -> CrewRotation | None:
    """Штат экипажа техники: ⌈плановые смены машины × человек в смене / норма смен человека⌉.

    None — у операции нет техники, техника не выбрана или у неё нет плановых
    смен: тогда оклад считается по норме смен должности.
    """

    param_name = CREW_EQUIPMENT_PARAM.get(operation_code)
    if not param_name:
        return None
    equipment = context.item("equipment_types", getattr(context.params, param_name, None))
    if equipment is None:
        return None
    plan_shifts = _equipment_plan_shifts(context, param_name, equipment)
    if plan_shifts <= 0:
        if fixed_monthly > 0:
            # У сдельщика без оклада нечего пересчитывать по плановым сменам
            # техники — предупреждение о нём вводит в заблуждение.
            context.warn(
                f"Для техники {equipment.code} не заданы плановые смены в месяц: "
                f"оклад должности {position.code} посчитан по норме смен человека."
            )
        return None
    person_shifts = norm_shifts
    if person_shifts <= 0:
        return None
    # Двое в смене при 35 сменах станка и норме 15 — пять человек, а не 2 × 3:
    # недобор смен одного закрывает другой.
    headcount = (plan_shifts * per_shift / person_shifts).to_integral_value(rounding=ROUND_CEILING)
    return CrewRotation(equipment.code, plan_shifts, person_shifts, headcount)


def _equipment_plan_shifts(context: ModelContext, param_name: str, equipment: ReferenceItem) -> Decimal:
    """Плановые смены машины — та же база, что у её амортизации.

    Станок: параметр вкладки, пусто и ноль — норматив типа (`drilling.py`).
    Остальная техника: `machine_plan_shifts`, ноль — «загрузки нет» (`equipment.py`).
    """

    if param_name == "rig_code":
        return context.params.rig_plan_shifts or payload_number(equipment, "norm_shifts_per_month")
    return context.machine_plan_shifts(equipment)


def fixed_amount(
    fixed_monthly: Decimal,
    shifts: Decimal,
    per_shift: Decimal,
    rotation: CrewRotation | None,
    norm_shifts: Decimal,
) -> tuple[Decimal, str]:
    """Постоянная часть на блок.

    Экипаж техники получает оклад за месяц при любой загрузке машины, поэтому
    месячный ФОТ штата делится на плановые смены машины — как её амортизация.
    Остальным — ставка человеко-смены: оклад / норма смен.
    """

    if rotation is not None:
        return (
            fixed_monthly * rotation.headcount / rotation.plan_shifts * shifts,
            f"{formula_number(fixed_monthly)} ₽/мес × {formula_number(rotation.headcount)} чел / {formula_number(rotation.plan_shifts)} см × {formula_number(shifts)} см",
        )
    rate_per_shift = fixed_monthly / norm_shifts if norm_shifts > 0 else Decimal("0")
    return (
        rate_per_shift * shifts * per_shift,
        f"{formula_number(fixed_monthly)} ₽/мес / {formula_number(norm_shifts)} см × {formula_number(shifts)} см × {formula_number(per_shift)} чел",
    )


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
    per_shift: Decimal,
) -> tuple[Decimal, str]:
    """Сдельная часть — каждому, кто работает в смене: расценка на человека.

    Штат на ротацию сюда не входит: метры блока бурит смена, а не весь штат.
    """

    piece_rate = payload_number(rate_item, "piece_rate_rub")
    driver_name = payload_text(position, "piece_driver")
    if piece_rate <= 0 or not driver_name:
        return Decimal("0"), ""
    unit = driver_unit(driver_name)
    driver_value = context.values.get(driver_name, Decimal("0"))
    if driver_value <= 0:
        # Молча обнулить сделку нельзя: ФОТ стал бы меньше без объяснения.
        # Ноль — тот же пробел: паспорт блока пишет незаполненное поле нулём.
        context.warn(
            f"Сдельная часть должности «{position.name}» не начислена: количество, "
            f"за которое платится сделка{f' ({unit})' if unit else ''}, "
            "в паспорте блока не задано или равно нулю."
        )
        return Decimal("0"), ""
    piece_unit = payload_number(position, "piece_unit", Decimal("1"))
    if piece_unit <= 0:
        piece_unit = Decimal("1")
    amount = piece_rate * driver_value / piece_unit * per_shift
    return (
        amount,
        f"{formula_number(piece_rate)} ₽ × {formula_quantity(driver_value, unit)} / {formula_number(piece_unit)} × {formula_number(per_shift)} чел",
    )


def per_diem_rate(context: ModelContext) -> Decimal:
    """Суточные на одну человеко-смену: ставка одна на всех."""

    return context.rates.per_diem_rub


def camp_rate(context: ModelContext) -> Decimal:
    """Проживание и питание на одну человеко-смену: ставки одни на всех."""

    return context.rates.lodging_rub + context.rates.meals_rub


def on_watch(context: ModelContext, position: ReferenceItem) -> bool:
    """Должности положены суточные, проживание и питание: флаг должности и вахтовый объект."""

    if not bool(position.payload.get("per_diem_applies", True)):
        return False
    return context.site is not None and bool(context.site.payload.get("is_remote", False))


def _per_diem(
    context: ModelContext, position: ReferenceItem, shifts: Decimal, per_shift: Decimal
) -> Decimal:
    if not on_watch(context, position):
        return Decimal("0")
    per_shift_rate = per_diem_rate(context)
    if per_shift_rate <= 0:
        return Decimal("0")
    return shifts * per_shift * per_shift_rate


def _camp_lines(context: ModelContext, person_shifts: Mapping[str, Decimal]) -> None:
    """Проживание и питание — строкой на операцию, где работают люди.

    Это не ФОТ: взносы на них не начисляются, и при методике ФОТ они не
    входят в затраты компании по `payroll_month` (там только суточные как
    вахтовая надбавка). Поэтому строка одна для обоих источников ФОТ, а
    операция строки относит долю экипажа станка к бурению — в цену метра.
    """

    rate = camp_rate(context)
    if rate <= 0:
        return
    for operation_code, quantity in person_shifts.items():
        if quantity <= 0:
            continue
        name = _operation_label(context, operation_code)
        context.add_line(
            operation_code=operation_code,
            cost_item_code=f"CAMP_{operation_code or 'CREW'}",
            cost_item_name=f"Проживание и питание: {name}",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=quantity * rate,
            formula=(
                f"{formula_number(quantity)} чел·см × "
                f"({formula_number(context.rates.lodging_rub)} + {formula_number(context.rates.meals_rub)}) ₽"
            ),
            section="PER_DIEM",
            quantity=quantity,
            unit="чел·см",
            unit_price_rub=rate,
            quantity_origin="CALC",
            price_origin="REFERENCE",
        )
