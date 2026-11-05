"""Статьи ФОТ должности на блоке и их раскладка в кольце цены метра (решение владельца 05.11.2026).

Должность методики раскладывается на оклад, межвахту, ночные, праздничные,
вахтовые, вредность, РК, резерв отпусков, отчисления и премиальную часть —
строки `payroll_month` на блок; должность на ставках — на оклад, премиальную
часть и свою долю строк взносов, резерва и суточных операции.
"""
from __future__ import annotations

from decimal import Decimal

from cost.model import drilling_sensitivity as ds
from cost.model.engine import compute_block_economics
from cost.model.inputs import PARAMETERS_VERSION, ModelParameters
from tests import model_fixtures as fx
from tests import test_model_block_payroll as bp

D = Decimal
EPS = D("0.000001")


def _methodology():
    params = fx.parameters(crew=bp.CREW, payroll_source="PAYROLL")
    return compute_block_economics(fx.snapshot(), params, bp._references(), as_of=bp.AS_OF), params


def _line(result, code: str):
    return next(line for line in result.lines if line.cost_item_code == code)


def _parts_sum(parts) -> Decimal:
    return sum((part.amount_rub for part in parts), D("0"))


def test_methodology_parts_add_up_to_the_position_line() -> None:
    result, _ = _methodology()
    for code in bp.CREW_CODES:
        line = _line(result, f"LABOR_{code}")
        parts = result.payroll_parts[line.cost_item_code]
        assert abs(_parts_sum(parts) - line.amount_rub) < EPS
        assert all(part.absorbs is None for part in parts)
    driller = {part.code: part for part in result.payroll_parts["LABOR_P_DRILLER"]}
    # Сдельщик: оклад, межвахта, премия, РК и начисления на всё это.
    for code in ("SALARY", "INTERSHIFT_REST", "HOLIDAYS", "REGIONAL", "PREMIUM", "CONTRIBUTIONS", "VACATION_RESERVE"):
        assert driller[code].amount_rub > 0, code
    assert driller["SALARY"].label == "Оклад"
    assert driller["PREMIUM"].label == "Премиальная часть"
    assert driller["CONTRIBUTIONS"].label == "Отчисления"


def test_premium_part_is_the_premium_of_the_block_before_charges() -> None:
    """Премиальная часть — p(m)/m × M × чел; РК, взносы и резервы на неё — в своих статьях."""

    result, _ = _methodology()
    payroll = result.payroll
    driller = next(item for item in payroll["positions"] if item["position_code"] == "P_DRILLER")
    premium = next(part for part in result.payroll_parts["LABOR_P_DRILLER"] if part.code == "PREMIUM")
    # Переменная часть строки (с начислениями) больше чистой премии.
    assert premium.amount_rub < D(str(driller["variable_rub"]))


def test_rates_parts_absorb_charges_and_per_diem_of_the_operation() -> None:
    params = fx.parameters()
    result = compute_block_economics(fx.snapshot(), params, fx.references())
    labor_items = [
        line
        for line in result.lines
        if line.operation_code == "PRODUCTION_DRILLING" and line.cost_item_code.startswith("LABOR_") and line.cost_item_code in result.payroll_parts
    ]
    assert labor_items
    for line in labor_items:
        parts = {part.code: part for part in result.payroll_parts[line.cost_item_code]}
        own = parts["SALARY"].amount_rub + (parts["PREMIUM"].amount_rub if "PREMIUM" in parts else D("0"))
        assert abs(own - line.amount_rub) < EPS
    for item in ("LABOR_CONTRIBUTIONS", "LABOR_VACATION_RESERVE"):
        line = next(
            line for line in result.lines if line.cost_item_code == item and line.operation_code == "PRODUCTION_DRILLING"
        )
        absorbed = sum(
            (
                part.amount_rub
                for labor_line in labor_items
                for part in result.payroll_parts[labor_line.cost_item_code]
                if part.absorbs == item
            ),
            D("0"),
        )
        assert abs(absorbed - line.amount_rub) < EPS


def test_ring_shows_positions_with_their_payroll_parts_and_block_sums() -> None:
    result, params = _methodology()
    prices = ds.prices(result, params, bp._references())
    drilling_m = result.natural.values["drilling_m"]
    crew = next(item for item in prices.components if item.code == "CREW_PAYROLL")
    driller = next(part for part in crew.parts if part.code.startswith("LABOR_P_DRILLER#"))
    # Одна и та же должность в экипаже видна подстрокой: у неё есть раскладка.
    assert driller.label
    assert [sub.label for sub in driller.parts][0] == "Оклад"
    assert abs(sum((sub.rub_per_m for sub in driller.parts), D("0")) - driller.rub_per_m) < EPS
    for item in (crew, driller, *driller.parts):
        assert item.rub is not None
        assert abs(item.rub - item.rub_per_m * drilling_m) < D("0.0001")
    assert "rub" in crew.to_dict() and "parts" in crew.to_dict()["parts"][0]


def test_rates_ring_moves_charges_into_positions_and_keeps_the_price() -> None:
    params = fx.parameters()
    result = compute_block_economics(fx.snapshot(), params, fx.references())
    prices = ds.prices(result, params, fx.references())
    drilling_lines = [line for line in result.lines if line.operation_code in ("PRODUCTION_DRILLING", "CONTOUR_DRILLING")]
    total = sum((line.amount_rub for line in drilling_lines), D("0")) / result.natural.values["drilling_m"]
    assert abs(prices.with_payroll - total) < EPS
    # Взносы и резерв принадлежат должностям — отдельной группы нет.
    assert not any(item.code == "PAYROLL_CHARGES" for item in prices.components)
    crew = next(item for item in prices.components if item.code == "CREW_PAYROLL")
    labels = {sub.label for part in crew.parts for sub in part.parts}
    assert {"Оклад", "Отчисления", "Резерв отпусков"} <= labels


def test_methodology_is_the_default_payroll_source() -> None:
    assert ModelParameters.from_dict({}).payroll_source == "PAYROLL"
    assert ModelParameters.from_dict({"payroll_source": "RATES"}).payroll_source == "RATES"
    assert ModelParameters.from_dict({"payroll_source": "что-то"}).payroll_source == "PAYROLL"
    assert ModelParameters.from_dict({}).to_dict()["parameters_version"] == PARAMETERS_VERSION == 2


def test_kpi_bonus_and_northern_allowance_are_their_own_parts() -> None:
    """Премия КПЭ — в премиальной части, северная надбавка — отдельной статьёй; сумма — строка."""

    rates = tuple(
        fx.item(item.code, item.name, {**item.payload, "kpi_bonus_pct": "0.1"}) if item.code == "LR_DRILLER" else item
        for item in bp.LABOR_RATES
    )
    references = bp._references(labor_rates=rates, site={"northern_pct": "0.3"})
    params = fx.parameters(crew=bp.CREW, payroll_source="PAYROLL")
    result = compute_block_economics(fx.snapshot(), params, references, as_of=bp.AS_OF)
    plain, _ = _methodology()

    line = _line(result, "LABOR_P_DRILLER")
    parts = {part.code: part.amount_rub for part in result.payroll_parts["LABOR_P_DRILLER"]}
    assert abs(sum(parts.values(), D("0")) - line.amount_rub) < EPS
    assert parts["NORTHERN"] > 0
    before = {part.code: part.amount_rub for part in plain.payroll_parts["LABOR_P_DRILLER"]}
    # КПЭ — 10 % оклада сверху премии; оклад не меняется.
    assert abs(parts["SALARY"] - before["SALARY"]) < EPS
    assert abs(parts["PREMIUM"] - before["PREMIUM"] - parts["SALARY"] * D("0.1")) < EPS


def test_net_salary_gross_up_is_split_between_salary_and_premium() -> None:
    """Оклад «на руки»: НДФЛ сверху делится между окладом и сдельной частью, сумма — строка."""

    rates = (fx.item("ORG_RATES_NET", "Ставки организации", {"salary_basis": "NET", "income_tax_rate": "0.13"}),)
    params = fx.parameters()
    gross = compute_block_economics(fx.snapshot(), params, fx.references())
    net = compute_block_economics(fx.snapshot(), params, fx.references(organization_rates=rates))
    for result in (gross, net):
        for line in result.lines:
            if line.cost_item_code.startswith("LABOR_") and line.cost_item_code in result.payroll_parts:
                own = sum(
                    (part.amount_rub for part in result.payroll_parts[line.cost_item_code] if part.absorbs is None),
                    D("0"),
                )
                assert abs(own - line.amount_rub) < EPS
    salary_gross = next(p for p in gross.payroll_parts["LABOR_POS_DRILLER"] if p.code == "SALARY").amount_rub
    salary_net = next(p for p in net.payroll_parts["LABOR_POS_DRILLER"] if p.code == "SALARY").amount_rub
    assert salary_net > salary_gross
