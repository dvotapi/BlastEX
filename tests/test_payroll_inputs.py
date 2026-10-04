"""Входы методики ФОТ из снимка справочников (TASK-010): год, оклад, объект, ставки."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from cost.model.payroll import PayrollInputError, payroll_month
from cost.model.payroll_inputs import difficulty_tables, downtime_reasons, payroll_inputs, rock_hardness
from cost.v2.payroll_params import payroll_params_for_year
from cost.v2.payroll_defaults import PAYROLL_PARAMS
from tests import model_fixtures as fx
from tests.payroll_fixtures import cents, payroll_references

D = Decimal


def read(position: str = "P_DRILLER", site: str = "SITE_LOM", year: int = 2026, **sections):
    return payroll_inputs(payroll_references(**sections), position_code=position, site_code=site, year=year)


def test_file_regression_through_the_references() -> None:
    inputs, _, warnings = read()
    assert warnings == ()
    assert inputs.position.salary == D("27093")
    assert inputs.position.week_hours == 40
    assert inputs.position.scale.scale_type == "CURVE_POWER"
    assert inputs.site.shift_days_on == D("15") and inputs.site.maintenance_shifts == D("2")
    assert inputs.rates.extra_tariffs["3.2"] == D("0.04")
    result = payroll_month(inputs, D("170000"), work_days_month=D("21.5"))
    assert cents(result.company_cost) == D("358103.01")


def test_position_without_a_rate_gets_the_minimum_wage() -> None:
    inputs, _, warnings = read("P_STOREKEEPER")
    assert inputs.position.salary == D("27093")
    assert inputs.position.scale is None
    assert any("МРОТ 27" in warning for warning in warnings)


def test_zero_salary_in_the_rate_is_a_blank_too() -> None:
    rates = (fx.item("LR_DRILLER", "Машинист", {"position_code": "P_DRILLER", "fixed_monthly_rub": "0"}),)
    inputs, _, warnings = read(labor_rates=rates)
    assert inputs.position.salary == D("27093")
    assert any("МРОТ" in warning for warning in warnings)


def test_rate_with_a_drilling_condition_only_is_used_with_a_warning() -> None:
    rates = (
        fx.item(
            "LR_DRILLER",
            "Машинист",
            {"position_code": "P_DRILLER", "fixed_monthly_rub": "60000", "condition_code": "COND_1"},
        ),
    )
    inputs, _, warnings = read(labor_rates=rates)
    assert inputs.position.salary == D("60000")
    assert any("COND_1" in warning for warning in warnings)


def test_missing_year_falls_back_to_the_latest_past_year() -> None:
    inputs, _, warnings = read(year=2027)
    assert inputs.calendar.year == 2026
    assert "Параметров ФОТ за 2027 год нет — взяты за 2026 год." in warnings


def test_no_payroll_params_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError, match="Параметры ФОТ"):
        read(payroll_params=())


@pytest.mark.parametrize(("position", "site"), [("NOPE", "SITE_LOM"), ("P_DRILLER", "NOPE")])
def test_unknown_position_or_site_is_an_input_error(position: str, site: str) -> None:
    with pytest.raises(PayrollInputError, match="NOPE"):
        read(position, site)


def test_site_from_before_the_payroll_fields_uses_the_company_schedule() -> None:
    inputs, _, _ = read(sites=(fx.item("SITE_LOM", "Ломовское", {}),))
    assert (inputs.site.shift_days_on, inputs.site.shift_days_off, inputs.site.travel_days) == (D("15"), D("15"), D("2"))
    assert inputs.site.regional_coefficient == D("0.15")


def test_missing_organization_rates_warn_and_use_defaults() -> None:
    inputs, _, warnings = read(organization_rates=())
    assert inputs.rates.sfr_rate == D("0.30")
    assert inputs.rates.shift_hours == D("11")
    assert any("Ставки и надбавки организации" in warning for warning in warnings)


def test_tables_reasons_and_rock_hardness_are_read_from_the_snapshot() -> None:
    snapshot = payroll_references()
    tables = difficulty_tables(snapshot)
    assert tables.diameter[D("250")] == D("1.64")
    assert tables.hardness[0].f_from is None and tables.hardness[-1].f_to is None
    reasons = downtime_reasons(snapshot)
    assert reasons["DT_PLANNED_MAINTENANCE"].planned_maintenance is True
    assert reasons["DT_LATE"].excusable is False
    assert rock_hardness(snapshot, "ROCK_F17") == D("17")
    assert rock_hardness(snapshot, "ROCK_NO_F") is None
    with pytest.raises(PayrollInputError):
        rock_hardness(snapshot, "NOPE")


def test_snapshot_without_difficulty_gives_empty_tables() -> None:
    tables = difficulty_tables(payroll_references(drilling_difficulty=()))
    assert tables.hardness == () and dict(tables.diameter) == {}


def _params(code: str, year: str, *, active: bool = True):
    item = fx.item(code, code, {**PAYROLL_PARAMS, "year": year})
    return item if active else replace(item, is_active=False)


def test_payroll_params_choice_prefers_exact_then_past_then_future() -> None:
    items = [_params("P2025", "2025"), _params("P2026", "2026"), _params("P2028", "2028")]
    assert payroll_params_for_year(items, 2026).item.code == "P2026"
    assert payroll_params_for_year(items, 2027).item.code == "P2026"
    assert payroll_params_for_year(items, 2027).note
    assert payroll_params_for_year(items[2:], 2026).item.code == "P2028"


def test_payroll_params_choice_skips_inactive_and_invalid_records() -> None:
    broken = fx.item("BROKEN", "Битая", {"year": "2026"})
    assert payroll_params_for_year([broken, _params("OFF", "2026", active=False)], 2026) is None


def test_broken_published_record_is_an_input_error_with_its_code() -> None:
    rates = (fx.item("LR_DRILLER", "Машинист", {"position_code": "P_DRILLER", "scale_type": "CURVE_POWER", "rate_norm": "45"}),)
    with pytest.raises(PayrollInputError, match="LR_DRILLER"):
        read(labor_rates=rates)
