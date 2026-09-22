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

from cost.model.inputs import (
    ModelContext,
    driver_unit,
    formula_number,
    formula_quantity,
    payload_number,
    payload_text,
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
    # Человеко-смены, на которые начислены суточные: ставка у них одна, значит
    # у строки есть и норма, и цена — как у любой другой статьи сметы.
    per_diem_shifts = Decimal("0")

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
        if shifts <= 0:
            continue
        per_shift = _per_shift_headcount(headcount)

        rate_item = _labor_rate(context, position_code)
        if rate_item is None:
            context.warn(f"Для должности {position_code} не задана ставка в «Ставках персонала».")
            continue

        fixed_monthly = payload_number(rate_item, "fixed_monthly_rub")
        # Читаем один раз: норма нужна и экипажу техники (штат ротации), и
        # обычной ставке человеко-смены (F2 ревью PR #80).
        norm_shifts = payload_number(position, "norm_shifts_per_month", Decimal("21"))
        rotation = _crew_rotation(context, position, operation_code, per_shift, fixed_monthly, norm_shifts)
        per_shift, rotation = _apply_crew_scale(context.params.crew_scale, per_shift, rotation)
        fixed_block, fixed_formula = _fixed_amount(fixed_monthly, shifts, per_shift, rotation, norm_shifts)
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
        accrued_total += accrued
        charge = _per_diem(context, position, shifts, per_shift)
        per_diem_total += charge
        if charge > 0:
            per_diem_shifts += shifts * per_shift
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

    if accrued_total > 0:
        contribution_rate = rates.social_contribution_rate + rates.injury_insurance_rate
        contributions = accrued_total * contribution_rate
        context.add_line(
            operation_code="",
            cost_item_code="LABOR_CONTRIBUTIONS",
            cost_item_name="Страховые взносы и НС",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=contributions,
            formula=f"{formula_number(accrued_total)} ₽ × {formula_number(contribution_rate)}",
            section="LABOR",
            quantity_origin="CALC",
            price_origin="REFERENCE",
        )
        reserve = (accrued_total + contributions) * rates.vacation_reserve_rate
        if reserve > 0:
            context.add_line(
                operation_code="",
                cost_item_code="LABOR_VACATION_RESERVE",
                cost_item_name="Резерв отпусков",
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=reserve,
                formula=f"({formula_number(accrued_total)} + {formula_number(contributions)}) ₽ × {formula_number(rates.vacation_reserve_rate)}",
                section="LABOR",
                quantity_origin="CALC",
                price_origin="REFERENCE",
            )

    if per_diem_total > 0:
        context.add_line(
            operation_code="",
            cost_item_code="LABOR_PER_DIEM",
            cost_item_name="Суточные и проживание",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=per_diem_total,
            formula=(
                f"{formula_number(per_diem_shifts)} чел·см × "
                f"({formula_number(context.rates.per_diem_rub)} + {formula_number(context.rates.lodging_rub)}) ₽"
            ),
            section="PER_DIEM",
            quantity=per_diem_shifts,
            unit="чел·см",
            # Ставка берётся из справочника, а не делением суммы на смены:
            # деление вернуло бы её с двоичным хвостом, и «норма × цена» в
            # смете перестала бы сходиться с суммой строки.
            unit_price_rub=per_diem_rate(context),
            quantity_origin="CALC",
            price_origin="REFERENCE",
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


def _per_shift_headcount(explicit: Decimal) -> Decimal:
    """Человек в смене из состава бригады.

    Ноль — прежнее «по экипажу техники»: в смене один человек, а штат на
    ротацию модель выводит сама. Так записан бурильщик в шаблонах, и так же
    очищенное поле численности приходит с вкладки.
    """

    return explicit if explicit > 0 else Decimal("1")


def _apply_crew_scale(
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


def _crew_rotation(
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


def _fixed_amount(
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
            f"за которое платится сделка ({unit}), в паспорте блока не задано или равно нулю."
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
    """Суточные и проживание на одну человеко-смену: ставка одна на всех."""

    return context.rates.per_diem_rub + context.rates.lodging_rub


def _per_diem(
    context: ModelContext, position: ReferenceItem, shifts: Decimal, per_shift: Decimal
) -> Decimal:
    if not bool(position.payload.get("per_diem_applies", True)):
        return Decimal("0")
    if context.site is None or not bool(context.site.payload.get("is_remote", False)):
        return Decimal("0")
    per_shift_rate = per_diem_rate(context)
    if per_shift_rate <= 0:
        return Decimal("0")
    return shifts * per_shift * per_shift_rate
