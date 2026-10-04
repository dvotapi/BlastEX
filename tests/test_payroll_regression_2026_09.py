"""Регрессия по файлу владельца «Расчёт заработной платы» (лист «Постоянная часть»).

Премия 170 000 ₽ — как в файле (2 000 м × 85 ₽). Затраты компании без НДФЛ:
358 103,01 ₽ против 391 010,22 ₽ в файле, где НДФЛ прибавлен к начисленному.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from cost.model.payroll import (
    extra_tariff_rate,
    payroll_month,
    piece_premium,
    premium_cost_factor,
    week_hours_for,
)
from tests.payroll_fixtures import CURVE_X, cents, file_inputs

D = Decimal
FILE_PREMIUM = D("170000")


def test_file_with_its_divisor_21_5() -> None:
    result = payroll_month(file_inputs(), FILE_PREMIUM, work_days_month=D("21.5"))
    assert cents(result.amount("INTERSHIFT_REST")) == D("18902.09")
    assert cents(result.gross) == D("253132.36")
    assert cents(result.amount("NDFL")) == D("32907.21")
    assert cents(result.amount("NET")) == D("232125.16")
    assert cents(result.company_cost) == D("358103.01")


def test_calendar_divisor_is_work_days_over_twelve() -> None:
    result = payroll_month(file_inputs(), FILE_PREMIUM)
    assert cents(result.amount("INTERSHIFT_REST")) == D("19743.89")
    assert cents(result.gross) == D("254100.42")
    assert cents(result.company_cost) == D("359427.01")


def test_income_tax_is_withheld_not_added_to_company_cost() -> None:
    result = payroll_month(file_inputs(), FILE_PREMIUM, work_days_month=D("21.5"))
    cost_rows = sum((row.amount for row in result.rows if row.kind == "COST"), D("0"))
    assert abs(result.company_cost - (result.gross + cost_rows)) < D("1e-18")
    assert cents(result.company_cost + result.amount("NDFL")) == D("391010.22")
    assert {row.code for row in result.rows if row.kind == "INFO"} == {"NDFL", "NET"}


def test_rows_follow_the_file_order() -> None:
    codes = [row.code for row in payroll_month(file_inputs(), FILE_PREMIUM).rows]
    assert codes == [
        "SALARY", "HAZARD", "NIGHT", "HOLIDAYS", "INTERSHIFT_REST", "PIECE_PREMIUM", "KPI_BONUS",
        "REGIONAL", "NORTHERN", "GROSS", "NDFL", "SHIFT_ALLOWANCE", "NET", "SFR", "EXTRA_TARIFF",
        "INJURY", "RESERVE_EXTRA_VACATION", "RESERVE_VACATION", "COMPANY_COST",
    ]


def test_cost_per_premium_ruble_matches_the_finite_difference() -> None:
    inputs = file_inputs()
    factor, formula = premium_cost_factor(inputs)
    difference = payroll_month(inputs, D("170001")).company_cost - payroll_month(inputs, FILE_PREMIUM).company_cost
    assert abs(factor - difference) < D("1e-9")
    assert abs(factor - D("1.572827209")) < D("1e-9")
    assert cents(D("168.66") * factor) == D("265.27")
    assert "1,572827" in formula


def test_curve_premium_enters_every_derived_row() -> None:
    inputs = file_inputs()
    premium = piece_premium(D("2000"), CURVE_X, D("13")).total
    factor, _ = premium_cost_factor(inputs)
    with_premium = payroll_month(inputs, premium)
    without = payroll_month(inputs, D("0"))
    assert with_premium.amount("PIECE_PREMIUM") == premium
    assert abs(with_premium.company_cost - without.company_cost - premium * factor) < D("1e-6")
    assert with_premium.amount("SFR") > without.amount("SFR")


def test_kpi_bonus_is_a_share_of_the_salary() -> None:
    result = payroll_month(file_inputs(kpi_bonus_pct=D("0.1")), D("0"))
    assert result.amount("KPI_BONUS") == D("2709.3")
    assert result.gross > payroll_month(file_inputs(), D("0")).gross


@pytest.mark.parametrize(
    ("work_class", "override", "hours"),
    [("3.2", None, 40), ("3.3", None, 36), ("3.4", None, 36), ("4", None, 36), (None, None, 40), ("3.3", "40", 40), ("3.2", "36", 36)],
)
def test_week_hours_follow_the_work_conditions_class(work_class: str | None, override: str | None, hours: int) -> None:
    assert week_hours_for(work_class, override) == hours


def test_short_week_raises_the_hour_rate() -> None:
    forty = payroll_month(file_inputs(), D("0")).amount("NIGHT")
    thirty_six = payroll_month(file_inputs(week_hours=36), D("0")).amount("NIGHT")
    assert abs(thirty_six - forty * D("1972") / D("1774.4")) < D("1e-18")


def test_classes_one_and_two_pay_no_extra_tariff() -> None:
    result = payroll_month(file_inputs(work_conditions_class="2"), FILE_PREMIUM)
    assert result.amount("EXTRA_TARIFF") == 0
    assert result.warnings == ()


def test_hazardous_class_without_tariff_row_warns() -> None:
    inputs = file_inputs()
    inputs = replace(inputs, rates=replace(inputs.rates, extra_tariffs={}))
    rate, warning = extra_tariff_rate(inputs.position, inputs.rates)
    assert rate == 0
    assert "3.2" in warning
    assert payroll_month(inputs, FILE_PREMIUM).warnings == (warning,)
