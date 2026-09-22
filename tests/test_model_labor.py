from decimal import Decimal

import pytest

from cost.model import drilling, labor, logistics
from cost.model.inputs import CrewMember, ModelContext, driver_unit
from cost.v2.schemas.labor import PIECE_DRIVERS
from tests import model_fixtures as fx


def _context(**params) -> ModelContext:
    context = ModelContext(fx.references(), fx.parameters(**params), fx.physical())
    drilling.compute(context)
    return context


def _line(context: ModelContext, code: str):
    return next(line for line in context.lines if line.cost_item_code == code)


def _labor_lines(context: ModelContext) -> list:
    return [line for line in context.lines if line.cost_item_code.startswith("LABOR_")]


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def test_blaster_fixed_and_piece_parts() -> None:
    """55 000 ₽ / 21 смена / 10 взрывов = 5 500 ₽ плюс 700 ₽ за 1000 м³."""

    context = _context(crew=(CrewMember("POS_BLASTER", Decimal("1")),))
    labor.compute(context)

    amount = _line(context, "LABOR_POS_BLASTER").amount_rub
    assert round(float(amount), 2) == 5500 + 700 * 60
    assert context.value("crew_shifts.POS_BLASTER") == Decimal("2.1")


def test_piece_formula_names_driver_unit_not_code() -> None:
    """Сметчик читает в формуле «60 000 м³», а не служебное имя `rock_volume_m3`."""

    context = _context()
    labor.compute(context)

    formulas = {line.cost_item_code: line.formula for line in _labor_lines(context)}
    assert formulas["LABOR_POS_DRILLER"].endswith(" + 150 ₽ × 13\u00a0953,49 п.м. / 1 × 1 чел")
    assert formulas["LABOR_POS_BLASTER"].endswith(" + 700 ₽ × 60\u00a0000 м³ / 1\u00a0000 × 2 чел")
    assert formulas["LABOR_POS_SZM_DRIVER"].endswith(" + 200 ₽ × 42\u00a0000 кг / 1\u00a0000 × 1 чел")
    for formula in formulas.values():
        assert not any(driver in formula for driver in PIECE_DRIVERS), formula


def test_every_piece_driver_has_unit_label() -> None:
    """Драйвер сделки без подписи оставил бы в формуле число без единицы."""

    assert [driver for driver in PIECE_DRIVERS if not driver_unit(driver)] == []


def _physical_without(key: str) -> dict[str, Decimal]:
    physical = fx.physical()
    del physical[key]
    return physical


@pytest.mark.parametrize(
    "physical",
    [_physical_without("explosive_kg"), fx.physical(explosive_kg=0)],
    ids=["missing", "zero"],
)
def test_empty_piece_driver_warns_instead_of_silent_zero(physical: dict[str, Decimal]) -> None:
    """Паспорт без массы ВВ: сделка водителя СЗМ не начислена, и сметчик знает почему.

    Паспорт блока пишет незаполненное поле нулём, а не пропускает его, поэтому
    ноль — такой же пробел в паспорте, как отсутствующая величина.
    """

    context = ModelContext(fx.references(), fx.parameters(), physical)
    drilling.compute(context)
    szm = next(line for line in labor.compute(context) if line.position_code == "POS_SZM_DRIVER")

    assert szm.piece_rub == Decimal("0")
    # Расценка водителя СЗМ в фикстуре — 200 ₽ за 1000 кг.
    assert "200 ₽ × " not in _line(context, "LABOR_POS_SZM_DRIVER").formula
    assert (
        "Сдельная часть должности «Водитель-оператор СЗМ» не начислена: количество, "
        "за которое платится сделка (кг), в паспорте блока не задано или равно нулю."
    ) in context.warnings


def test_driller_shifts_follow_rig_and_rotation_follows_plan() -> None:
    """Смены бурильщика — смены станка; в смене один человек, штат на ротацию — из плана станка."""

    context = _context()
    labor.compute(context)

    assert context.value("crew_shifts.POS_DRILLER") == context.value("rig_shifts")
    assert context.value("crew_per_shift.POS_DRILLER") == Decimal("1")
    # ⌈40 смен станка × 1 чел / 15 смен человека⌉
    assert context.value("crew_rotation.POS_DRILLER") == Decimal("3")
    assert context.lineage["crew_rotation.POS_DRILLER"] == "⌈40 см RIG_JK830 × 1 чел / 15 см человека⌉"

    fewer_shifts = _context(rig_plan_shifts=Decimal("25"))
    labor.compute(fewer_shifts)
    assert fewer_shifts.value("crew_rotation.POS_DRILLER") == Decimal("2")

    # Ноль в плане станка — норматив типа, как у амортизации станка в `drilling.py`.
    no_plan = _context(rig_plan_shifts=Decimal("0"))
    labor.compute(no_plan)
    assert no_plan.value("crew_rotation.POS_DRILLER") == Decimal("3")


def test_driller_block_payroll_pays_each_metre_once() -> None:
    """Блок 60 000 м³: 13 953,49 м за 116,28 смены станка, оклад 60 000 ₽, расценка 150 ₽/м.

    До TASK-010 PR 0b: 60 000 / 15 × 116,28 × 3 + 150 × 13 953,49 × 3 = 7 674 418,60 ₽ —
    каждый метр и каждая смена станка оплачивались трём людям ротации, ФОТ со
    взносами и резервом 12 010 772,09 ₽. Теперь оклад штата делится на плановые
    смены станка, а сделка идёт одному человеку в смене: 4 094 581,40 ₽.
    """

    context = _context(crew=(CrewMember("POS_DRILLER", Decimal("0")),))
    driller = labor.compute(context)[0]

    assert driller.headcount == Decimal("1")
    assert driller.rotation_headcount == Decimal("3")
    # 60 000 × 3 / 40 см × 116,28 см
    assert _money(driller.fixed_rub) == Decimal("523255.81")
    # 150 × 13 953,49 × 1
    assert _money(driller.piece_rub) == Decimal("2093023.26")

    line = _line(context, "LABOR_POS_DRILLER")
    assert _money(line.amount_rub) == Decimal("2616279.07")
    assert line.quantity == context.value("rig_shifts")
    assert line.formula.startswith("60\u00a0000 ₽/мес × 3 чел / 40 см × 116,28 см")
    contributions = _line(context, "LABOR_CONTRIBUTIONS").amount_rub
    reserve = _line(context, "LABOR_VACATION_RESERVE").amount_rub
    assert _money(contributions) == Decimal("795872.09")
    assert _money(reserve) == Decimal("682430.23")
    assert _money(line.amount_rub + contributions + reserve) == Decimal("4094581.40")


def test_crew_scale_applies_to_the_rounded_rotation() -> None:
    """Множитель чувствительности ложится на уже округлённый штат.

    Бурильщик с 0 в составе — один человек в смене, штат ⌈40 / 15⌉ = 3. Если
    умножить людей в смене до округления, ⌈40 × 1,1 / 15⌉ = 3 оставит оклад
    прежним. С множителем после округления оклад и сделка растут ровно на 10 %:
    523 255,81 × 1,1 и 2 093 023,26 × 1,1.
    """

    crew = (CrewMember("POS_DRILLER", Decimal("0")),)
    driller = labor.compute(_context(crew=crew, crew_scale=Decimal("1.1")))[0]

    assert driller.headcount == Decimal("1.1")
    assert driller.rotation_headcount == Decimal("3.3")
    assert _money(driller.fixed_rub) == Decimal("575581.40")
    assert _money(driller.piece_rub) == Decimal("2302325.58")


def test_rig_plan_shifts_move_the_fixed_part_only() -> None:
    """25 смен станка: штат 2, смена станка стоит 4 800 ₽ оклада вместо 4 500; сделка та же."""

    context = _context(crew=(CrewMember("POS_DRILLER", Decimal("0")),), rig_plan_shifts=Decimal("25"))
    driller = labor.compute(context)[0]

    assert driller.rotation_headcount == Decimal("2")
    assert _money(driller.fixed_rub) == Decimal("558139.53")
    assert _money(driller.piece_rub) == Decimal("2093023.26")
    assert _money(driller.accrued_rub) == Decimal("2651162.79")


def test_two_people_per_shift_share_one_rotation() -> None:
    """Двое в смене при 35 сменах станка: штат ⌈35 × 2 / 15⌉ = 5, а не 2 × ⌈35 / 15⌉ = 6."""

    context = _context(crew=(CrewMember("POS_DRILLER", Decimal("2")),), rig_plan_shifts=Decimal("35"))
    driller = labor.compute(context)[0]

    assert driller.rotation_headcount == Decimal("5")
    assert _money(driller.fixed_rub) == Decimal("996677.74")
    assert _money(driller.piece_rub) == Decimal("4186046.51")
    assert _line(context, "LABOR_POS_DRILLER").quantity == context.value("rig_shifts") * 2


def test_zero_headcount_is_one_person_per_shift() -> None:
    """0 в составе бригады — прежнее «по экипажу техники»: один человек в смене."""

    zero = _context(crew=(CrewMember("POS_DRILLER", Decimal("0")),))
    one = _context(crew=(CrewMember("POS_DRILLER", Decimal("1")),))

    assert labor.compute(zero)[0].accrued_rub == labor.compute(one)[0].accrued_rub
    assert zero.lineage["crew_per_shift.POS_DRILLER"] == "в составе 0 — один человек в смене"
    assert one.lineage["crew_per_shift.POS_DRILLER"] == "человек в смене"


def test_crew_fixed_part_follows_machine_plan_shifts() -> None:
    """Водитель СЗМ: оклад штата — на плановые смены СЗМ; без плана — по норме смен с предупреждением."""

    crew = (CrewMember("POS_SZM_DRIVER", Decimal("1"), Decimal("4")),)

    planned = _context(crew=crew, machine_plan_shifts={"SZM_12T": Decimal("10")})
    labor.compute(planned)
    # 50 000 × ⌈10 / 20⌉ / 10 см × 4 см + 200 × 42 000 / 1000
    assert _line(planned, "LABOR_POS_SZM_DRIVER").amount_rub == Decimal("28400")
    assert planned.value("crew_rotation.POS_SZM_DRIVER") == Decimal("1")
    assert not [warning for warning in planned.warnings if "оклад должности" in warning]

    no_plan = _context(crew=crew, machine_plan_shifts={"SZM_12T": Decimal("0")})
    labor.compute(no_plan)
    # 50 000 / 20 см × 4 см × 1 чел + 8 400
    assert _line(no_plan, "LABOR_POS_SZM_DRIVER").amount_rub == Decimal("18400")
    assert "crew_rotation.POS_SZM_DRIVER" not in no_plan.values
    assert (
        "Для техники SZM_12T не заданы плановые смены в месяц: "
        "оклад должности POS_SZM_DRIVER посчитан по норме смен человека."
    ) in no_plan.warnings


def test_pieceworker_without_salary_gets_no_false_salary_warning() -> None:
    """У сдельщика без оклада нет плановых смен техники — предупреждать об окладе нечего."""

    references = fx.references(
        labor_rates=(
            fx.item(
                "LR_SZM_PIECE",
                "Водитель-оператор СЗМ (сделка)",
                {"position_code": "POS_SZM_DRIVER", "piece_rate_rub": "200"},
            ),
        )
    )
    crew = (CrewMember("POS_SZM_DRIVER", Decimal("1"), Decimal("4")),)
    context = ModelContext(
        references,
        fx.parameters(crew=crew, machine_plan_shifts={"SZM_12T": Decimal("0")}),
        fx.physical(),
    )
    drilling.compute(context)
    labor.compute(context)

    line = _line(context, "LABOR_POS_SZM_DRIVER")
    # Оклада нет (fixed_monthly_rub не задан) — только сделка: 200 × 42 000 / 1000 × 1 чел.
    assert line.amount_rub == Decimal("8400")
    assert not [warning for warning in context.warnings if "оклад должности" in warning]


def test_per_diem_counts_people_in_shift_not_rotation() -> None:
    rates_item = fx.item(
        "ORG_RATES_DEFAULT",
        "Ставки организации",
        {"per_diem_rub": "1000", "lodging_rub": "1000"},
    )
    context = ModelContext(
        fx.references(organization_rates=(rates_item,)),
        fx.parameters(crew=(CrewMember("POS_DRILLER", Decimal("0")),)),
        fx.physical(),
    )
    drilling.compute(context)
    labor.compute(context)

    per_diem = _line(context, "LABOR_PER_DIEM")
    # 116,28 чел·см × 2 000 ₽; со штатом ротации было 697 674,42 ₽.
    assert per_diem.quantity == context.value("rig_shifts")
    assert _money(per_diem.amount_rub) == Decimal("232558.14")


def test_indirect_position_stays_out_of_block_labor() -> None:
    context = _context(crew=(CrewMember("POS_WAREHOUSE_HEAD", Decimal("1")),))
    labor.compute(context)

    assert _labor_lines(context) == []
    assert not [warning for warning in context.warnings if "POS_WAREHOUSE_HEAD" in warning]


def test_position_without_package_operation_is_skipped() -> None:
    """Пакет «франко-скважина» не содержит взрыва — взрывника в расчёте нет."""

    context = ModelContext(
        fx.references(),
        fx.parameters(package_code="VM_IN_HOLE", crew=(CrewMember("POS_BLASTER", Decimal("2")),)),
        fx.physical(),
    )
    labor.compute(context)

    assert context.lines == []
    assert context.warnings == []


def test_contributions_and_vacation_reserve_follow_organization_rates() -> None:
    context = _context(crew=(CrewMember("POS_BLASTER", Decimal("1")),))
    labor.compute(context)

    accrued = _line(context, "LABOR_POS_BLASTER").amount_rub
    contributions = _line(context, "LABOR_CONTRIBUTIONS").amount_rub
    reserve = _line(context, "LABOR_VACATION_RESERVE").amount_rub
    assert contributions == accrued * Decimal("0.3042")
    assert reserve == (accrued + contributions) * Decimal("0.20")


def test_net_salary_basis_grosses_up_accrual() -> None:
    references = fx.references(
        organization_rates=(
            fx.item(
                "ORG_RATES_DEFAULT",
                "Ставки организации",
                {"salary_basis": "NET", "income_tax_rate": "0.13"},
            ),
        )
    )
    context = ModelContext(
        references,
        fx.parameters(crew=(CrewMember("POS_BLASTER", Decimal("1")),)),
        fx.physical(),
    )
    labor.compute(context)

    gross = _line(context, "LABOR_POS_BLASTER").amount_rub
    assert round(float(gross), 2) == round((5500 + 42000) / 0.87, 2)


def test_net_salary_basis_applies_to_crew_rotation_position() -> None:
    """Экипаж техники при NET: строка = (оклад по плановым сменам + сделка) ÷ (1 − НДФЛ)."""

    references = fx.references(
        organization_rates=(
            fx.item(
                "ORG_RATES_DEFAULT",
                "Ставки организации",
                {"salary_basis": "NET", "income_tax_rate": "0.13"},
            ),
        )
    )
    context = ModelContext(
        references,
        fx.parameters(crew=(CrewMember("POS_DRILLER", Decimal("0")),)),
        fx.physical(),
    )
    drilling.compute(context)
    labor.compute(context)

    line = _line(context, "LABOR_POS_DRILLER")
    # Как в test_driller_block_payroll_pays_each_metre_once: оклад штата
    # 60 000 × 3 / 40 см × 116,2790697666… см = 523 255,8139500…, сделка
    # 150 × 13 953,488372 = 2 093 023,2558. Сумма 2 616 279,06975 ÷ (1 − 0,13)
    # = 3 007 217,321551724137931034483 ₽.
    assert _money(line.amount_rub) == Decimal("3007217.32")
    assert line.formula.endswith(" ÷ (1 − НДФЛ)")


def test_per_diem_only_on_remote_site() -> None:
    rates_item = fx.item(
        "ORG_RATES_DEFAULT",
        "Ставки организации",
        {"per_diem_rub": "1000", "lodging_rub": "1000"},
    )
    crew = (CrewMember("POS_BLASTER", Decimal("2")),)
    remote = ModelContext(
        fx.references(organization_rates=(rates_item,)),
        fx.parameters(crew=crew),
        fx.physical(),
    )
    labor.compute(remote)
    assert _line(remote, "LABOR_PER_DIEM").amount_rub == Decimal("2.1") * 2 * 2000

    city_site = tuple(
        fx.item(site.code, site.name, {**site.payload, "is_remote": False})
        for site in fx.SITES
    )
    city = ModelContext(
        fx.references(organization_rates=(rates_item,), sites=city_site),
        fx.parameters(crew=crew),
        fx.physical(),
    )
    labor.compute(city)
    assert not [line for line in city.lines if line.cost_item_code == "LABOR_PER_DIEM"]


def test_subcontracted_drilling_removes_own_driller() -> None:
    """Ставка субподряда уже включает бригаду: свой бурильщик не начисляется."""

    own = _context()
    labor.compute(own)
    assert any(line.cost_item_code == "LABOR_POS_DRILLER" for line in own.lines)

    subcontract = _context(drilling_executor="SUBCONTRACTOR")
    labor.compute(subcontract)

    codes = {line.cost_item_code for line in subcontract.lines}
    assert "LABOR_POS_DRILLER" not in codes
    assert "LABOR_POS_BLASTER" in codes
    assert not [w for w in subcontract.warnings if "POS_DRILLER" in w]


def test_delivery_truck_driver_rotation_follows_machine_plan_shifts() -> None:
    """Доставщик ВМ: смены — из рейсов доставщика, штат ротации и оклад — из его плановых смен."""

    references = fx.references(
        positions=(
            *fx.POSITIONS,
            fx.item(
                "POS_VM_DELIVERY_DRIVER",
                "Водитель доставки ВМ",
                {"category": "DIRECT", "operation_code": "VM_DELIVERY_SITE", "norm_shifts_per_month": "20"},
            ),
        ),
        labor_rates=(
            *fx.LABOR_RATES,
            fx.item(
                "LR_VM_DELIVERY",
                "Водитель доставки ВМ",
                {"position_code": "POS_VM_DELIVERY_DRIVER", "fixed_monthly_rub": "50000"},
            ),
        ),
    )
    context = ModelContext(
        references,
        fx.parameters(crew=(CrewMember("POS_VM_DELIVERY_DRIVER", Decimal("1")),)),
        fx.physical(cartridge_kg=Decimal("6000")),
    )
    logistics.compute(context)
    labor.compute(context)

    driver = _line(context, "LABOR_POS_VM_DELIVERY_DRIVER")
    # ⌈6 000 кг / 3 000 кг (TRUCK_3T)⌉ = 2 рейса = 2 смены доставщика.
    assert context.value("crew_shifts.POS_VM_DELIVERY_DRIVER") == Decimal("2")
    # Плановые смены доставщика — норматив типа (20, ручной поправки нет).
    # ⌈20 см × 1 чел / 20 см человека⌉ = 1.
    assert context.value("crew_rotation.POS_VM_DELIVERY_DRIVER") == Decimal("1")
    # 50 000 ₽/мес × 1 чел / 20 см × 2 см
    assert driver.amount_rub == Decimal("50000") * 1 / 20 * 2
