from decimal import Decimal

from cost.model import drilling, labor
from cost.model.inputs import CrewMember, ModelContext
from tests import model_fixtures as fx


def _context(**params) -> ModelContext:
    context = ModelContext(fx.references(), fx.parameters(**params), fx.physical())
    drilling.compute(context)
    return context


def _line(context: ModelContext, code: str):
    return next(line for line in context.lines if line.cost_item_code == code)


def _labor_lines(context: ModelContext) -> list:
    return [line for line in context.lines if line.cost_item_code.startswith("LABOR_")]


def test_blaster_fixed_and_piece_parts() -> None:
    """55 000 ₽ / 21 смена / 10 взрывов = 5 500 ₽ плюс 700 ₽ за 1000 м³."""

    context = _context(crew=(CrewMember("POS_BLASTER", Decimal("1")),))
    labor.compute(context)

    amount = _line(context, "LABOR_POS_BLASTER").amount_rub
    assert round(float(amount), 2) == 5500 + 700 * 60
    assert context.value("crew_shifts.POS_BLASTER") == Decimal("2.1")


def test_driller_shifts_follow_rig_and_headcount_follows_plan() -> None:
    context = _context()
    labor.compute(context)

    assert context.value("crew_shifts.POS_DRILLER") == context.value("rig_shifts")
    assert context.value("crew_headcount.POS_DRILLER") == Decimal("3")

    fewer_shifts = _context(rig_plan_shifts=Decimal("25"))
    labor.compute(fewer_shifts)
    assert fewer_shifts.value("crew_headcount.POS_DRILLER") == Decimal("2")


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
