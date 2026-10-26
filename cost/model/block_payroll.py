"""ФОТ экипажа бурения блока по методике TASK-010 (решение владельца 25.10.2026).

По методике считается только экипаж операций бурения
(`labor.DRILLING_OPERATIONS`) — машинист и помощник; остальные прямые
должности остаются на ставках (`cost/model/labor.py`). Режим включает
параметр вкладки `payroll_source = "PAYROLL"`; при `RATES`, субподряде, без
бурения или без нормы `compute` возвращает None и ничего не меняет.

Раздел «экипаж». Состав берётся из бригады блока — вкладки, иначе шаблона
пакета (`labor.crew_members`), а не из всех сдельщиков организации: вторая
сдельная должность чужой операции или чужого станка долю в марже не завышает.
`crew_roster` — общее правило для явного состава: основная должность, которой
в нём нет, добавляется с одним человеком в смене и предупреждением, иначе её
премия молча выпала бы из доли в марже.

Раздел «строки ФОТ» (Т4, Т9, Т11, Т14). Каждый член — вызов функции
`cost/model/payroll.py`, а не её копия:

- M_блока = drilling_m × k̄ × contract_k (`payroll.normalized_meters` по
  `block_meter_items`): породы — плановая геология объекта, иначе его порода,
  иначе k_f = 1; Ø всех строк — коронки строки матрицы (паспорт блока ни
  породы, ни диаметра не несёт);
- c_var = p(m_план) / m_план × затраты на рубль премии — ₽ на приведённый
  метр на человека; темп — по строке матрицы (`pace.planned_pace`), k блока в
  него не входит. S_эфф вахты в c_var сокращается и показывается справочно;
- переменная часть = c_var × M_блока × человек в смене, только у сдельщика со
  шкалой на приведённых метрах; повременщику — 0;
- постоянная часть = затраты компании при премии 0 (`payroll_month`, уже с
  вахтовой надбавкой) × штат ротации / плановые смены станка × смены блока,
  как оклад в `labor.fixed_amount`; ручная поправка смен вкладки меняет только
  её.

Строка — `LABOR_<должность>` с `price_origin = "PAYROLL"`; код должности
попадает в `context.payroll_positions`, и `labor.compute` её пропускает:
ни второй строки, ни взносов, ни суточных. Методика применяется ко всему
экипажу или ни к кому: нет ставки, нет шкалы у сдельщика, нет «Параметров
ФОТ» года или объекта — весь экипаж на ставках и одно предупреждение
(частичный экипаж исказил бы долю в марже).

Цена метра бурения и доля экипажа в марже (§2.1–§2.2) — `cost/model/block_margin.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Mapping, Sequence

from cost.model import labor
from cost.model.drilling import DrillingNorms
from cost.model.inputs import ModelContext, formula_number, payload_number, payload_text
from cost.model.pace import PlannedPace, planned_pace
from cost.model.payroll import (
    ONE,
    PIECE_PAY_SYSTEMS,
    ZERO,
    CrewCost,
    DifficultyTables,
    MeterItem,
    NormalizedMeters,
    PayrollInputError,
    PayrollInputs,
    Scale,
    fn,
    hardness_factor,
    normalized_meters,
    payroll_month,
    piece_premium,
    plan_effective_shifts,
    premium_cost_factor,
)
from cost.model.payroll_inputs import PayrollContext, difficulty_tables, payroll_context, position_inputs, rock_hardness
from cost.v2.models import CostLayer, ReferenceItem, decimal_value


@dataclass(frozen=True)
class CrewSlot:
    """Должность экипажа бурения на блоке."""

    position_code: str
    # Человек в смене; ноль в составе уже заменён одним человеком.
    headcount: Decimal
    # Ручная поправка смен на блок с вкладки; None — норматив.
    shifts_override: Decimal | None


def crew_roster(
    members: Sequence[tuple[str, Decimal]], main_code: str
) -> tuple[tuple[tuple[str, Decimal], ...], tuple[str, ...]]:
    """Явный состав экипажа с основной должностью.

    Нет основной должности — она ставится первой с одним человеком в смене,
    запрос не отклоняется (решение владельца 04.10.2026).
    """

    roster = tuple(members)
    if any(code == main_code for code, _ in roster):
        return roster, ()
    return (
        ((main_code, Decimal("1")), *roster),
        (
            "Основная должность добавлена в экипаж, один человек в смене: "
            "без неё её сдельная премия не вошла бы в долю в марже.",
        ),
    )


def block_crew(context: ModelContext) -> tuple[CrewSlot, ...]:
    """Экипаж бурения блока: прямые должности операций бурения пакета.

    Должность, которой нет в справочнике, пропускается молча: о ней
    предупреждает `labor.compute`. Ноль в составе — один человек в смене
    (`labor.per_shift_headcount`), как у ставок.
    """

    slots: list[CrewSlot] = []
    for position_code, headcount, manual_shifts in labor.crew_members(context):
        position = context.item("positions", position_code)
        if position is None:
            continue
        if payload_text(position, "category", "DIRECT") != "DIRECT":
            continue
        operation_code = payload_text(position, "operation_code")
        if operation_code not in labor.DRILLING_OPERATIONS or not context.has_operation(operation_code):
            continue
        slots.append(CrewSlot(position_code, labor.per_shift_headcount(headcount), manual_shifts))
    return tuple(slots)


# --- Строки ФОТ -------------------------------------------------------------


@dataclass(frozen=True)
class PositionPayroll:
    position_code: str
    # Человек в смене (с множителем чувствительности).
    headcount: Decimal
    # ₽ на приведённый метр на человека; повременщику — 0.
    c_var_rub_per_reduced_m: Decimal
    fixed_rub: Decimal
    variable_rub: Decimal
    amount_rub: Decimal


@dataclass(frozen=True)
class BlockPayroll:
    positions: tuple[PositionPayroll, ...]
    pace: PlannedPace
    normalized_meters: Decimal
    # План вахты: смены минус плановое ТОиР; в c_var не входит.
    effective_shifts: Decimal
    # Сдельщики экипажа на приведённых метрах — для доли в марже (§2.2);
    # шкала основной — первой такой должности экипажа («получает машинист»).
    crew: tuple[CrewCost, ...] = ()
    main_scale: Scale | None = None
    # Порог доли — `margin_share_warn` календаря «Параметров ФОТ» года.
    threshold: Decimal = ZERO
    lineage: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _Pending:
    """Посчитанная должность, ещё не записанная в контекст."""

    result: PositionPayroll
    position: ReferenceItem
    operation_code: str
    shifts: Decimal
    manual: bool
    rotation: labor.CrewRotation | None
    formula: str
    c_var_source: str
    # Затраты на рубль премии должности — и для c_var, и для доли в марже.
    cost_factor: Decimal = ZERO
    warnings: tuple[str, ...] = field(default_factory=tuple)


def compute(context: ModelContext, norms: DrillingNorms | None) -> BlockPayroll | None:
    """Строки ФОТ экипажа бурения по методике; None — блок считается по ставкам."""

    params = context.params
    if params.payroll_source != "PAYROLL" or norms is None:
        return None
    if params.drilling_executor == "SUBCONTRACTOR" or context.value("drilling_m") <= 0:
        return None
    crew = block_crew(context)
    if not crew:
        return None
    try:
        pending, payroll, meters_source, effective_source = _plan(context, norms, crew)
    except (PayrollInputError, ArithmeticError) as exc:
        # Всё или ничего: ни одна строка ещё не записана, labor посчитает весь
        # экипаж по ставкам.
        context.warn(f"ФОТ экипажа бурения посчитан по ставкам, а не по методике: {exc}")
        return None
    if not pending:
        # У всех должностей экипажа ноль смен: методике нечего писать, а
        # `labor` пропустит их так же.
        return None
    _write(context, pending, payroll, meters_source, effective_source)
    return payroll


def _plan(
    context: ModelContext, norms: DrillingNorms, crew: Sequence[CrewSlot]
) -> tuple[tuple[_Pending, ...], BlockPayroll, str, str]:
    """Весь расчёт без записи в контекст: ошибка любой должности возвращает экипаж на ставки."""

    site_code = context.params.site_code
    if not site_code:
        raise PayrollInputError("не выбран объект работ — вахта и надбавки методики берутся из него.")
    readings: list[tuple[CrewSlot, ReferenceItem, PayrollInputs, tuple[str, ...]]] = []
    shared: PayrollContext | None = None
    for slot in crew:
        position = context.item("positions", slot.position_code)
        if not _has_rate(context, slot.position_code):
            raise PayrollInputError(f"у должности «{position.name}» нет ставки в «Ставках персонала».")
        if shared is None:
            # Год, объект и ставки — один раз на расчёт; читаются после проверки
            # ставки первой должности, как раньше, чтобы причина отката не сменилась.
            shared = payroll_context(context.references, site_code=site_code, year=context.as_of.year)
        inputs, warnings = position_inputs(context.references, shared, slot.position_code)
        pay = inputs.position
        if pay.pay_system in PIECE_PAY_SYSTEMS and not pay.is_piece_on_meters:
            raise PayrollInputError(
                f"у сдельной должности «{position.name}» нет шкалы сдельной премии за приведённые метры."
            )
        readings.append((slot, position, inputs, warnings))

    site = readings[0][2].site
    effective = plan_effective_shifts(site.shift_days_on, site.maintenance_shifts)
    # «Сложность бурения» — одна на темп и приведённые метры; нечитаемая
    # запись возвращает экипаж на ставки.
    tables = difficulty_tables(context.references)
    pace = planned_pace(context, norms, tables)
    meters, meter_warnings = _block_meters(context, pace, tables, site.contract_k)

    pending: list[_Pending] = []
    crew_costs: list[CrewCost] = []
    for slot, position, inputs, warnings in readings:
        item = _position_payroll(context, norms, slot, position, inputs, pace, meters.total, effective.effective)
        if item is None:
            continue
        pending.append(replace(item, warnings=(*warnings, *item.warnings)))
        if inputs.position.is_piece_on_meters:
            crew_costs.append(
                CrewCost(slot.position_code, position.name, item.result.headcount, inputs.position.scale, item.cost_factor)
            )
    meters_source, effective_source = meters.lineage["normalized_meters"], effective.lineage["effective_shifts"]
    payroll = BlockPayroll(
        positions=tuple(item.result for item in pending),
        pace=replace(pace, warnings=(*pace.warnings, *meter_warnings)),
        normalized_meters=meters.total,
        effective_shifts=effective.effective,
        crew=tuple(crew_costs),
        main_scale=crew_costs[0].scale if crew_costs else None,
        threshold=readings[0][2].calendar.margin_share_warn,
        lineage={
            "planned_pace": pace.lineage.get("planned_pace", ""),
            "normalized_meters": meters_source,
            "effective_shifts": effective_source,
            **{f"c_var.{item.result.position_code}": item.c_var_source for item in pending},
        },
    )
    return tuple(pending), payroll, meters_source, effective_source


def _has_rate(context: ModelContext, position_code: str) -> bool:
    return any(payload_text(item, "position_code") == position_code for item in context.items("labor_rates"))


def _position_payroll(
    context: ModelContext,
    norms: DrillingNorms,
    slot: CrewSlot,
    position: ReferenceItem,
    inputs: PayrollInputs,
    pace: PlannedPace,
    block_meters: Decimal,
    effective: Decimal,
) -> _Pending | None:
    shifts = slot.shifts_override if slot.shifts_override is not None else norms.rig_shifts
    if shifts <= 0:
        # Как у ставок: должность без смен на блоке не работает.
        return None
    operation_code = payload_text(position, "operation_code")
    base = payroll_month(inputs, ZERO)
    base_cost = base.company_cost
    norm_shifts = payload_number(position, "norm_shifts_per_month", Decimal("21"))
    rotation = labor.crew_rotation(context, position, operation_code, slot.headcount, base_cost, norm_shifts)
    per_shift, rotation = labor.apply_crew_scale(context.params.crew_scale, slot.headcount, rotation)
    fixed, fixed_formula = labor.fixed_amount(base_cost, shifts, per_shift, rotation, norm_shifts)

    cost_factor, factor_formula = premium_cost_factor(inputs)
    pay = inputs.position
    if pay.is_piece_on_meters:
        # Премия на среднем темпе вахты: P / M = p(m) / m, S_эфф сокращается.
        premium = piece_premium(pace.pace * effective, pay.scale, effective)
        if premium.mean_rate is None:
            raise PayrollInputError("плановый темп равен нулю — цену приведённого метра не посчитать.")
        c_var = premium.mean_rate * cost_factor
        c_var_source = f"p({fn(pace.pace)}) / {fn(pace.pace)} × {factor_formula}"
        variable = c_var * block_meters * per_shift
        formula = (
            f"{fixed_formula} + {formula_number(c_var)} ₽/прив. м × "
            f"{formula_number(block_meters)} прив. м × {formula_number(per_shift)} чел"
        )
    else:
        c_var, variable, formula = ZERO, ZERO, fixed_formula
        c_var_source = "повременная оплата: премии по шкале нет"
    result = PositionPayroll(
        position_code=slot.position_code,
        headcount=per_shift,
        c_var_rub_per_reduced_m=c_var,
        fixed_rub=fixed,
        variable_rub=variable,
        amount_rub=fixed + variable,
    )
    return _Pending(
        result=result,
        position=position,
        operation_code=operation_code,
        shifts=shifts,
        manual=slot.shifts_override is not None,
        rotation=rotation,
        formula=formula,
        c_var_source=c_var_source,
        cost_factor=cost_factor,
        warnings=base.warnings,
    )


def _write(
    context: ModelContext,
    pending: Sequence[_Pending],
    payroll: BlockPayroll,
    meters_source: str,
    effective_source: str,
) -> None:
    for message in payroll.pace.warnings:
        context.warn(message)
    lodging = context.rates.lodging_rub
    per_diem_crew = any(bool(item.position.payload.get("per_diem_applies", True)) for item in pending)
    if context.site is not None and bool(context.site.payload.get("is_remote", False)) and lodging > 0 and per_diem_crew:
        # Проживание — статья ставок (`labor._per_diem`), методика его не несёт:
        # не начисляем, но и не теряем молча. Должности без суточных его и в
        # ставках не получают — о них предупреждать не о чем.
        context.warn(
            f"Проживание экипажа бурения ({formula_number(lodging)} ₽/чел·см) в режиме «ФОТ по методике» "
            "не начислено: методика учитывает только суточные/вахтовую надбавку."
        )
    context.set_value("payroll_planned_pace", payroll.pace.pace, payroll.pace.lineage.get("planned_pace", ""))
    context.set_value("payroll_normalized_meters", payroll.normalized_meters, meters_source)
    context.set_value("payroll_effective_shifts", payroll.effective_shifts, effective_source)
    for item in pending:
        for message in item.warnings:
            context.warn(message)
        code = item.result.position_code
        context.payroll_positions.add(code)
        context.set_value(f"crew_shifts.{code}", item.shifts, f"смен на блок должности {code}")
        context.set_value(f"crew_per_shift.{code}", item.result.headcount, "человек в смене")
        if item.rotation is not None:
            context.set_value(
                f"crew_rotation.{code}",
                item.rotation.headcount,
                f"⌈{item.rotation.plan_shifts} см {item.rotation.equipment_code} × {item.result.headcount} чел / "
                f"{item.rotation.person_shifts} см человека⌉",
            )
        context.set_value(f"payroll_c_var.{code}", item.result.c_var_rub_per_reduced_m, item.c_var_source)
        context.add_line(
            operation_code=item.operation_code,
            cost_item_code=f"LABOR_{code}",
            cost_item_name=f"ФОТ: {item.position.name}",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=item.result.amount_rub,
            formula=item.formula,
            section="LABOR",
            quantity=item.shifts * item.result.headcount,
            unit="чел·см",
            quantity_origin="MANUAL" if item.manual else "NORM",
            price_origin="PAYROLL",
        )


# --- Приведённые метры блока -------------------------------------------------


def block_meter_items(context: ModelContext, pace: PlannedPace) -> tuple[tuple[MeterItem, ...], tuple[str, ...]]:
    """Строки приведения метров блока: породы объекта, Ø — коронки строки матрицы.

    Плановая геология объекта делит метры по долям; без неё — одна строка по
    породе объекта, без породы — строка с f = None (k_f = 1, предупреждение).
    Нет Ø — в строке 0 мм, коэффициент диаметра подставляет `_block_meters`.
    Предупреждения возвращаются, а не пишутся в контекст: расчёт ещё может
    откатиться на ставки.
    """

    warnings: list[str] = []
    drilling_m = context.value("drilling_m")
    diameter = pace.diameter_mm or ZERO
    site = context.site
    geology = site.payload.get("geology") if site is not None else None
    rows = [
        (str(row.get("rock_code") or ""), decimal_value(row.get("share")))
        for row in (geology or [])
        if isinstance(row, Mapping)
    ]
    rows = [(code, share) for code, share in rows if code and share > 0]
    if not rows:
        rock_code = payload_text(site, "rock_code")
        if not rock_code:
            warnings.append(
                "У объекта работ не задана ни плановая геология, ни порода: "
                "коэффициент крепости приведённых метров блока принят 1."
            )
            return (MeterItem(drilling_m, diameter, None, "порода не задана"),), tuple(warnings)
        rows = [(rock_code, ONE)]
    items = tuple(MeterItem(drilling_m * share, diameter, _rock_f(context, code, warnings), code) for code, share in rows)
    return items, tuple(warnings)


def _rock_f(context: ModelContext, rock_code: str, warnings: list[str]) -> Decimal | None:
    try:
        f = rock_hardness(context.references, rock_code)
    except PayrollInputError as exc:
        warnings.append(f"{exc} Коэффициент крепости приведённых метров блока принят 1.")
        return None
    if f is None:
        rock = context.item("rocks", rock_code)
        warnings.append(
            f"У породы «{rock.name}» ({rock_code}) объекта не задана крепость f: "
            "коэффициент крепости приведённых метров блока принят 1."
        )
    return f


def _block_meters(
    context: ModelContext, pace: PlannedPace, tables: DifficultyTables, contract_k: Decimal
) -> tuple[NormalizedMeters, tuple[str, ...]]:
    """M_блока и предупреждения приведения (о крепости без f — уже названной выше — не повторяются)."""

    items, item_warnings = block_meter_items(context, pace)
    warnings: list[str] = []
    diameter = pace.diameter_mm
    if diameter is None or (tables.diameter and diameter not in tables.diameter):
        # Ø строки не определён или его нет в таблице: в приведении метров это
        # ошибка входа, а блок считается дальше с k_d = 1 — как плановый темп.
        where = f"строки условий бурения {pace.condition_code}" if pace.condition_code else "строки условий бурения"
        warnings.append(
            f"Ø коронки {where} не задан: коэффициент диаметра приведённых метров блока принят 1."
            if diameter is None
            else f"Ø {fn(diameter)} мм коронки {where} нет в таблице «Сложность бурения»: "
            "коэффициент диаметра приведённых метров блока принят 1."
        )
        tables = replace(tables, diameter={ZERO: ONE})
        items = tuple(replace(item, diameter_mm=ZERO) for item in items)
    warnings.extend(item_warnings)
    meters = normalized_meters(items, tables, contract_k)
    unnamed_f = hardness_factor(None, ())[2]
    warnings.extend(message for message in meters.warnings if message != unnamed_f)
    return meters, tuple(warnings)
