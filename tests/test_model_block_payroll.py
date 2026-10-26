"""Строки ФОТ экипажа бурения блока по методике TASK-010 (PR 3a, Т4, Т9, Т11, Т14).

Фикстура — блок `tests/model_fixtures.py` (12 м/ч, смена 11 ч, станок 40 смен),
экипаж бурения — машинист и помощник из `tests/payroll_fixtures.py` на кривой X
(норма 115,3846, потолок 184,6154, 45 / 168,66 ₽), ставки взносов файла
(СФР 15 %, травматизм 2,1 %, доп. тариф 3.2 — 4 %): затраты на рубль премии
1,572827.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from cost.model import block_payroll, drilling, labor, logistics, materials
from cost.model.engine import compute_block_economics
from cost.model.inputs import CrewMember, ModelContext
from cost.model.payroll import PayrollInputError, payroll_month
from cost.model.payroll_inputs import payroll_inputs
from cost.v2.models import CostLayer
from tests import model_fixtures as fx
from tests import payroll_fixtures as pfx

D = Decimal
CENT = D("0.01")
AS_OF = date(2026, 10, 1)

BIT_250 = fx.item(
    "MAT_BIT_250",
    "Коронка 250",
    {"unit": "PIECE", "material_kind": "ТМЦ", "storage_class": "NONE", "nomenclature_role": "DRILL_TOOL", "diameter_mm": "250"},
)
ROCKS = (*fx.ROCKS, *pfx.PAYROLL_SECTIONS["rocks"])
CREW_POSITIONS = tuple(
    fx.item(item.code, item.name, {**item.payload, "norm_shifts_per_month": "15"})
    for item in pfx.PAYROLL_SECTIONS["positions"]
    if item.code in ("P_DRILLER", "P_ASSISTANT")
)
LABOR_RATES = (
    *(rate for rate in fx.LABOR_RATES if rate.code != "LR_DRILLER"),
    *pfx.PAYROLL_SECTIONS["labor_rates"],
)
CREW = (
    CrewMember("P_DRILLER", D("1")),
    CrewMember("P_ASSISTANT", D("1")),
    CrewMember("POS_BLASTER", D("2")),
    CrewMember("POS_SZM_DRIVER", D("1")),
)
CREW_CODES = ("P_DRILLER", "P_ASSISTANT")


def _condition(code: str, **payload: str):
    base = {key: value for key, value in fx.DRILLING_CONDITIONS[0].payload.items() if key not in ("rock_code", "bit_material_code")}
    return fx.item(code, f"JK830 {code}", {**base, **payload})


COND_BASE = _condition("COND_BASE")
COND_F17 = _condition("COND_F17", rock_code="ROCK_F17", bit_material_code="MAT_BIT_250")


def _site(**payload):
    site = fx.SITES[0]
    data = {key: value for key, value in {**site.payload, **payload}.items() if value is not None}
    return fx.item(site.code, site.name, data)


def _references(*, site: dict | None = None, **overrides):
    sections = {
        "rocks": ROCKS,
        "materials": (*fx.MATERIALS, BIT_250),
        "positions": (*fx.POSITIONS, *CREW_POSITIONS),
        "labor_rates": LABOR_RATES,
        "sites": (_site(**(site or {})),),
        "payroll_params": pfx.PAYROLL_SECTIONS["payroll_params"],
        "organization_rates": pfx.PAYROLL_SECTIONS["organization_rates"],
        "drilling_difficulty": pfx.PAYROLL_SECTIONS["drilling_difficulty"],
    }
    sections.update(overrides)
    return fx.references(**sections)


def _context(references=None, physical=None, **params) -> ModelContext:
    return ModelContext(
        references or _references(),
        fx.parameters(**{"crew": CREW, "payroll_source": "PAYROLL", **params}),
        physical or fx.physical(),
        as_of=AS_OF,
    )


def _run(context: ModelContext):
    norms = drilling.compute(context)
    return norms, block_payroll.compute(context, norms)


def _position(result, code: str):
    return next(position for position in result.positions if position.position_code == code)


def _line(lines, code: str):
    return next(line for line in lines if line.cost_item_code == code)


def _labor_lines(lines) -> dict:
    return {line.cost_item_code: line for line in lines if line.cost_item_code.startswith("LABOR_")}


def _inputs(references, code: str):
    inputs, _, _ = payroll_inputs(references, position_code=code, site_code="SITE_MAIN", year=AS_OF.year)
    return inputs


# --- c_var и эффективные смены ------------------------------------------------


def test_c_var_is_70_93_on_fixture_at_k_one() -> None:
    """Базовая строка, f 12, коронка без Ø: m_план = 120, k̄ = 1, c_var = p(120) / 120 × 1,572827."""

    context = _context()
    _, result = _run(context)

    assert result is not None
    assert result.pace.pace == D("120")
    assert result.normalized_meters == context.value("drilling_m")
    assert result.effective_shifts == D("13")
    for code in CREW_CODES:
        assert _position(result, code).c_var_rub_per_reduced_m.quantize(CENT) == D("70.93")
    assert context.payroll_positions == set(CREW_CODES)


def test_variable_part_independent_of_site_maintenance_shifts() -> None:
    """ТОиР объекта 2 → 4: S_эфф 13 → 11, а c_var, переменная и постоянная части те же."""

    _, base = _run(_context())
    _, more = _run(_context(_references(site={"maintenance_shifts": "4"})))

    assert base.effective_shifts == D("13")
    assert more.effective_shifts == D("11")
    for code in CREW_CODES:
        a, b = _position(base, code), _position(more, code)
        assert abs(a.c_var_rub_per_reduced_m - b.c_var_rub_per_reduced_m) <= CENT
        assert abs(a.variable_rub - b.variable_rub) <= CENT
        assert abs(a.fixed_rub - b.fixed_rub) <= CENT


# --- Приведённые метры блока ---------------------------------------------------


def test_m_block_is_meters_times_1_968_for_f17_d250() -> None:
    context = _context(_references(site={"rock_code": "ROCK_F17"}, drilling_conditions=(COND_F17,)))
    _, result = _run(context)

    assert result.pace.diameter_mm == D("250")
    assert result.normalized_meters == context.value("drilling_m") * D("1.968")


def test_block_meters_split_by_site_geology() -> None:
    """Геология 50/50, f 10 и f 17, Ø 250 строки, договорной k 1,1."""

    geology = [{"rock_code": "ROCK_F10", "share": "0.5"}, {"rock_code": "ROCK_F17", "share": "0.5"}]
    references = _references(
        site={"rock_code": "ROCK_F17", "geology": geology, "contract_k": "1.1"},
        drilling_conditions=(COND_F17,),
    )
    context = _context(references)
    _, result = _run(context)

    drilling_m = context.value("drilling_m")
    expected = drilling_m * (D("0.5") * D("1.0") + D("0.5") * D("1.2")) * D("1.64") * D("1.1")
    assert abs(result.normalized_meters - expected) <= D("0.000001")


def test_block_meters_single_rock_and_no_rock_fallbacks() -> None:
    # Одна порода объекта: f 17 → 1,2; коронки у строки нет → k_d = 1 с предупреждением.
    single = _context(_references(site={"rock_code": "ROCK_F17"}, drilling_conditions=(COND_BASE,)))
    _, result = _run(single)
    assert result.normalized_meters == single.value("drilling_m") * D("1.2")
    assert any("диаметра" in w and "приведённых метров" in w for w in single.warnings)

    # Ни геологии, ни породы: k_f = 1 и предупреждение.
    none = _context(_references(site={"rock_code": None}, drilling_conditions=(COND_BASE,)))
    _, result = _run(none)
    assert result.normalized_meters == none.value("drilling_m")
    assert any("порода" in w.lower() and "крепости" in w and "приведённых метров" in w for w in none.warnings)


def test_pace_not_multiplied_by_block_k() -> None:
    """Порода блока двигает M_блока, но не темп: m_план — по строке матрицы (Т9)."""

    paces, meters = set(), []
    for geology in (
        [{"rock_code": "ROCK_F10", "share": "1"}],
        [{"rock_code": "ROCK_F17", "share": "1"}],
        [{"rock_code": "ROCK_F10", "share": "0.5"}, {"rock_code": "ROCK_F17", "share": "0.5"}],
    ):
        context = _context(_references(site={"rock_code": "ROCK_F17", "geology": geology}, drilling_conditions=(COND_BASE,)))
        _, result = _run(context)
        paces.add(result.pace.pace)
        meters.append(result.normalized_meters / context.value("drilling_m"))
    assert paces == {D("120")}
    assert meters == [D("1.0"), D("1.2"), D("1.1")]

    # Строка f 17 / Ø 250: темп — 120 × 1,968 строки, а не × 1,968 ещё раз за блок.
    context = _context(_references(site={"rock_code": "ROCK_F17"}, drilling_conditions=(COND_F17,)))
    _, result = _run(context)
    assert result.pace.pace == D("120") * D("1.968")
    assert result.normalized_meters == context.value("drilling_m") * D("1.968")


# --- Строки и двойной счёт -----------------------------------------------------


def test_payroll_mode_has_no_double_labor() -> None:
    references = _references()
    context = _context(references)
    _, result = _run(context)
    lines_before = len(context.lines)
    labor_lines = labor.compute(context)

    # labor.compute не считает машиниста и помощника: ни строки, ни взносов, ни суточных.
    assert {line.position_code for line in labor_lines} == {"POS_BLASTER", "POS_SZM_DRIVER"}
    produced = [line.cost_item_code for line in context.lines[lines_before:]]
    assert not any(code in ("LABOR_P_DRILLER", "LABOR_P_ASSISTANT") for code in produced)
    accrued = sum((line.accrued_rub for line in labor_lines), D("0"))
    rates = context.rates
    contributions = _line(context.lines, "LABOR_CONTRIBUTIONS").amount_rub
    assert contributions == accrued * (rates.social_contribution_rate + rates.injury_insurance_rate)
    reserve = _line(context.lines, "LABOR_VACATION_RESERVE").amount_rub
    assert reserve == (accrued + contributions) * rates.vacation_reserve_rate
    per_diem = _line(context.lines, "LABOR_PER_DIEM")
    assert per_diem.quantity == sum((line.shifts_per_block * line.headcount for line in labor_lines), D("0"))

    # Сумма строк ФОТ методики — затраты компании по payroll_month: постоянная часть
    # при премии 0 и прирост затрат от премии на приведённых метрах блока.
    for code in CREW_CODES:
        inputs = _inputs(references, code)
        position = _position(result, code)
        rotation = context.value(f"crew_rotation.{code}")
        base = payroll_month(inputs, D("0")).company_cost
        fixed = base * rotation / D("40") * context.value("rig_shifts")
        premium = inputs.position.scale.per_shift(result.pace.pace) / result.pace.pace * result.normalized_meters
        variable = payroll_month(inputs, premium).company_cost - base
        line = _line(context.lines, f"LABOR_{code}")
        assert abs(line.amount_rub - (fixed + variable)) <= CENT
        assert line.amount_rub == position.amount_rub == position.fixed_rub + position.variable_rub


def test_rates_mode_unchanged() -> None:
    """RATES: block_payroll ничего не делает, строки LABOR_* те же, что без него."""

    references = _references()
    economics = compute_block_economics(
        fx.snapshot(), fx.parameters(crew=CREW), references, as_of=AS_OF
    )
    # Тот же порядок модулей, что в движке, но без block_payroll.
    plain = ModelContext(references, fx.parameters(crew=CREW), fx.physical(), as_of=AS_OF)
    norms = drilling.compute(plain)
    logistics.compute(plain)
    materials.compute(plain)
    assert block_payroll.compute(plain, norms) is None
    assert plain.payroll_positions == set()
    labor.compute(plain)

    assert _labor_lines(economics.lines) == _labor_lines(plain.lines)
    assert all(line.price_origin != "PAYROLL" for line in economics.lines)


def test_engine_payroll_mode_writes_methodology_lines_once() -> None:
    economics = compute_block_economics(
        fx.snapshot(), fx.parameters(crew=CREW, payroll_source="PAYROLL"), _references(), as_of=AS_OF
    )
    codes = [line.cost_item_code for line in economics.lines]
    for code in CREW_CODES:
        assert codes.count(f"LABOR_{code}") == 1
        assert _line(economics.lines, f"LABOR_{code}").price_origin == "PAYROLL"


def test_shifts_override_changes_fixed_part_only() -> None:
    _, base = _run(_context())
    norms = drilling.compute(_context())
    crew = (
        CrewMember("P_DRILLER", D("1"), norms.rig_shifts * 2),
        *CREW[1:],
    )
    _, doubled = _run(_context(crew=crew))

    a, b = _position(base, "P_DRILLER"), _position(doubled, "P_DRILLER")
    assert abs(b.fixed_rub - 2 * a.fixed_rub) <= CENT
    assert b.variable_rub == a.variable_rub
    assert b.c_var_rub_per_reduced_m == a.c_var_rub_per_reduced_m
    # Помощник без поправки не меняется.
    assert _position(doubled, "P_ASSISTANT") == _position(base, "P_ASSISTANT")


def test_manual_shifts_mark_quantity_origin_manual() -> None:
    context = _context()
    norms = drilling.compute(context)
    crew = (CrewMember("P_DRILLER", D("1"), norms.rig_shifts), *CREW[1:])
    manual = _context(crew=crew)
    _run(manual)

    assert _line(manual.lines, "LABOR_P_DRILLER").quantity_origin == "MANUAL"
    assert _line(manual.lines, "LABOR_P_ASSISTANT").quantity_origin == "NORM"


def test_fixed_part_uses_rig_plan_shifts() -> None:
    """Постоянная часть = затраты(0) × штат ротации / плановые смены станка × смены блока."""

    references = _references()
    inputs = _inputs(references, "P_DRILLER")
    base_cost = payroll_month(inputs, D("0")).company_cost

    def fixed(context: ModelContext) -> Decimal:
        _, result = _run(context)
        return _position(result, "P_DRILLER").fixed_rub

    base = _context(references)
    base_fixed = fixed(base)
    # 40 смен станка, 15 смен человека, 1 в смене → штат 3.
    assert base.value("crew_rotation.P_DRILLER") == D("3")
    assert abs(base_fixed - base_cost * 3 / 40 * base.value("rig_shifts")) <= CENT

    # Вдвое больше метров — вдвое больше смен блока и постоянной части.
    double_m = _context(references, fx.physical(drilling_m=fx.physical()["drilling_m"] * 2))
    assert abs(fixed(double_m) - 2 * base_fixed) <= CENT

    # Плановые смены станка 60: штат ⌈60 / 15⌉ = 4, делитель 60.
    plan_60 = _context(references, rig_plan_shifts=D("60"))
    assert abs(fixed(plan_60) - base_cost * 4 / 60 * plan_60.value("rig_shifts")) <= CENT

    # S_эфф (ТОиР объекта) постоянную часть не трогает.
    more_maintenance = _context(_references(site={"maintenance_shifts": "5"}))
    assert abs(fixed(more_maintenance) - base_fixed) <= CENT


def test_fixed_part_without_rotation_uses_position_norm_shifts() -> None:
    """Плановых смен станка нет — оклад по норме смен должности, как в `labor`."""

    rigs = tuple(
        fx.item(rig.code, rig.name, {**rig.payload, "norm_shifts_per_month": "0"}) if rig.code == "RIG_JK830" else rig
        for rig in fx.EQUIPMENT_TYPES
    )
    references = _references(equipment_types=rigs)
    context = _context(references, rig_plan_shifts=D("0"))
    _, result = _run(context)

    base_cost = payroll_month(_inputs(references, "P_DRILLER"), D("0")).company_cost
    expected = base_cost / D("15") * context.value("rig_shifts") * D("1")
    assert abs(_position(result, "P_DRILLER").fixed_rub - expected) <= CENT


def test_crew_scale_scales_people_and_rotation() -> None:
    _, base = _run(_context())
    _, scaled = _run(_context(crew_scale=D("1.1")))

    a, b = _position(base, "P_DRILLER"), _position(scaled, "P_DRILLER")
    assert b.headcount == D("1.1")
    assert abs(b.variable_rub - a.variable_rub * D("1.1")) <= CENT
    assert abs(b.fixed_rub - a.fixed_rub * D("1.1")) <= CENT


# --- Когда методика не применяется ---------------------------------------------


def test_missing_payroll_params_falls_back_to_rates_with_warning() -> None:
    context = _context(_references(payroll_params=()))
    _, result = _run(context)

    assert result is None
    assert context.payroll_positions == set()
    assert not any(line.price_origin == "PAYROLL" for line in context.lines)
    messages = [w for w in context.warnings if "по ставкам" in w]
    assert len(messages) == 1
    assert "Параметры ФОТ" in messages[0] or "параметров ФОТ" in messages[0].lower()


def test_one_crew_position_without_rate_returns_whole_crew_to_rates() -> None:
    rates = tuple(rate for rate in LABOR_RATES if rate.code != "LR_ASSISTANT")
    references = _references(labor_rates=rates)
    economics = compute_block_economics(
        fx.snapshot(), fx.parameters(crew=CREW, payroll_source="PAYROLL"), references, as_of=AS_OF
    )

    assert not any(line.price_origin == "PAYROLL" for line in economics.lines)
    driller = _line(economics.lines, "LABOR_P_DRILLER")
    assert driller.price_origin != "PAYROLL"
    messages = [w for w in economics.warnings if "по ставкам" in w]
    assert len(messages) == 1
    assert "Помощник машиниста" in messages[0]


def test_piece_position_without_scale_returns_whole_crew_to_rates() -> None:
    rates = tuple(
        fx.item(rate.code, rate.name, {"position_code": "P_ASSISTANT", "fixed_monthly_rub": "27093"})
        if rate.code == "LR_ASSISTANT"
        else rate
        for rate in LABOR_RATES
    )
    context = _context(_references(labor_rates=rates))
    _, result = _run(context)

    assert result is None
    assert context.payroll_positions == set()
    assert any("Помощник машиниста" in w and "шкал" in w and "по ставкам" in w for w in context.warnings)


def test_time_pay_crew_position_gets_fixed_part_only() -> None:
    positions = tuple(
        fx.item(item.code, item.name, {**item.payload, "pay_system": "TIME_BONUS"}) if item.code == "P_ASSISTANT" else item
        for item in (*fx.POSITIONS, *CREW_POSITIONS)
    )
    context = _context(_references(positions=positions))
    _, result = _run(context)

    assistant = _position(result, "P_ASSISTANT")
    assert assistant.c_var_rub_per_reduced_m == 0
    assert assistant.variable_rub == 0
    assert assistant.fixed_rub > 0
    assert context.payroll_positions == set(CREW_CODES)


def test_subcontract_skips_payroll() -> None:
    context = _context(drilling_executor="SUBCONTRACTOR")
    norms, result = _run(context)

    assert norms is None
    assert result is None
    assert context.payroll_positions == set()


def test_no_drilling_no_payroll() -> None:
    context = _context(physical=fx.physical(drilling_m=0))
    norms, result = _run(context)

    assert norms is None
    assert result is None
    assert context.payroll_positions == set()
    assert not any("по ставкам" in w for w in context.warnings)


def test_no_norm_no_payroll() -> None:
    context = _context()
    assert block_payroll.compute(context, None) is None
    assert context.payroll_positions == set()


# --- Происхождение строки ------------------------------------------------------


def test_line_origin_is_payroll_and_code_kept() -> None:
    context = _context()
    _, result = _run(context)

    line = _line(context.lines, "LABOR_P_DRILLER")
    assert line.price_origin == "PAYROLL"
    assert line.cost_item_name == "ФОТ: Машинист буровой установки"
    assert line.layer == CostLayer.PROJECT_DIRECT
    assert line.section == "LABOR"
    assert line.operation_code == "PRODUCTION_DRILLING"
    assert line.quantity_origin == "NORM"
    assert line.unit == "чел·см"
    assert "₽/прив. м" in line.formula and " + " in line.formula
    assert context.value("payroll_c_var.P_DRILLER") == _position(result, "P_DRILLER").c_var_rub_per_reduced_m
    assert context.value("payroll_effective_shifts") == D("13")
    assert "ТОиР" in context.lineage["payroll_effective_shifts"]
    assert "1,572827" in context.lineage["payroll_c_var.P_DRILLER"]
    assert "COND_GRANITE" in context.lineage["payroll_planned_pace"]


def test_block_payroll_module_documents_the_formulas() -> None:
    doc = block_payroll.__doc__ or ""
    assert "M_блока" in doc and "c_var" in doc and "payroll_positions" in doc


# --- Правки ревью (раунд 1) ----------------------------------------------------


def _org_rates(**payload: str):
    item = pfx.PAYROLL_SECTIONS["organization_rates"][0]
    return (fx.item(item.code, item.name, {**item.payload, **payload}),)


def _lodging_warnings(context: ModelContext) -> list[str]:
    return [w for w in context.warnings if w.startswith("Проживание экипажа бурения")]


def test_lodging_is_not_lost_silently_on_remote_site() -> None:
    context = _context(_references(organization_rates=_org_rates(lodging_rub="500")))
    _, result = _run(context)

    assert result is not None
    assert _lodging_warnings(context) == [
        "Проживание экипажа бурения (500 ₽/чел·см) в режиме «ФОТ по методике» не начислено: "
        "методика учитывает только суточные/вахтовую надбавку."
    ]


def test_no_lodging_warning_without_lodging_or_off_remote_site() -> None:
    no_lodging = _context()
    _run(no_lodging)
    assert _lodging_warnings(no_lodging) == []

    city = _context(_references(site={"is_remote": False}, organization_rates=_org_rates(lodging_rub="500")))
    _, result = _run(city)
    assert result is not None
    assert _lodging_warnings(city) == []


def test_no_lodging_warning_when_crew_has_no_per_diem() -> None:
    """Проживание ставки начисляют только должностям с `per_diem_applies`: без них предупреждать не о чем."""

    positions = tuple(
        fx.item(item.code, item.name, {**item.payload, "per_diem_applies": False}) if item.code in CREW_CODES else item
        for item in (*fx.POSITIONS, *CREW_POSITIONS)
    )
    context = _context(_references(positions=positions, organization_rates=_org_rates(lodging_rub="500")))
    _, result = _run(context)
    assert result is not None
    assert _lodging_warnings(context) == []

    # Хотя бы одна должность экипажа с суточными — предупреждение остаётся.
    one = tuple(
        fx.item(item.code, item.name, {**item.payload, "per_diem_applies": False}) if item.code == "P_ASSISTANT" else item
        for item in (*fx.POSITIONS, *CREW_POSITIONS)
    )
    context = _context(_references(positions=one, organization_rates=_org_rates(lodging_rub="500")))
    _run(context)
    assert len(_lodging_warnings(context)) == 1


def test_crew_without_shifts_writes_nothing() -> None:
    crew = (CrewMember("P_DRILLER", D("1"), D("0")), CrewMember("P_ASSISTANT", D("1"), D("0")), *CREW[2:])
    context = _context(crew=crew)
    _, result = _run(context)

    assert result is None
    assert context.payroll_positions == set()
    assert not any(key.startswith("payroll_") for key in context.values)
    assert not any(line.price_origin == "PAYROLL" for line in context.lines)


def test_zero_planned_pace_falls_back_to_rates(monkeypatch) -> None:
    """Нулевой темп (mean_rate = None) — откат на ставки с предупреждением, не TypeError."""

    real = block_payroll.planned_pace
    monkeypatch.setattr(
        block_payroll, "planned_pace", lambda context, norms, tables=None: replace(real(context, norms, tables), pace=D("0"))
    )
    context = _context()
    _, result = _run(context)

    assert result is None
    assert context.payroll_positions == set()
    assert [w for w in context.warnings if "по ставкам" in w] == [
        "ФОТ экипажа бурения посчитан по ставкам, а не по методике: "
        "плановый темп равен нулю — цену приведённого метра не посчитать."
    ]


def test_fallback_after_meters_leaves_no_meter_warnings(monkeypatch) -> None:
    """Откат после приведения метров: предупреждения о породе блока не остаются в смете."""

    def broken(*args, **kwargs):
        raise PayrollInputError("месячный ФОТ не считается.")

    monkeypatch.setattr(block_payroll, "payroll_month", broken)
    context = _context(_references(site={"rock_code": "ROCK_NO_F"}, drilling_conditions=(COND_BASE,)))
    _, result = _run(context)

    assert result is None
    assert not any("приведённых метров" in w for w in context.warnings)
    assert len([w for w in context.warnings if "по ставкам" in w]) == 1


def test_shared_inputs_are_read_once_per_run(monkeypatch) -> None:
    """Год, объект и ставки, «Сложность бурения» — один раз на расчёт, а не на каждую должность экипажа."""

    from cost.model import pace as pace_module

    calls = {"context": 0, "tables": 0}
    real_context, real_tables = block_payroll.payroll_context, block_payroll.difficulty_tables

    def counted_context(*args, **kwargs):
        calls["context"] += 1
        return real_context(*args, **kwargs)

    def counted_tables(*args, **kwargs):
        calls["tables"] += 1
        return real_tables(*args, **kwargs)

    monkeypatch.setattr(block_payroll, "payroll_context", counted_context)
    monkeypatch.setattr(block_payroll, "difficulty_tables", counted_tables)
    monkeypatch.setattr(pace_module, "difficulty_tables", counted_tables)
    _, result = _run(_context())

    assert result is not None and len(result.positions) == 2
    assert calls == {"context": 1, "tables": 1}


def test_block_meter_items_returns_warnings_without_writing_context() -> None:
    context = _context(_references(site={"rock_code": None}, drilling_conditions=(COND_BASE,)))
    norms = drilling.compute(context)
    pace = block_payroll.planned_pace(context, norms)
    before = list(context.warnings)

    items, warnings = block_payroll.block_meter_items(context, pace)
    assert len(items) == 1 and items[0].f is None
    assert warnings == (
        "У объекта работ не задана ни плановая геология, ни порода: "
        "коэффициент крепости приведённых метров блока принят 1.",
    )
    assert context.warnings == before
