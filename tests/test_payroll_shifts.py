"""Эффективные смены, флаги простоев и защита входа (TASK-010 §2.3, решения §2.3, Т12)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.payroll import (
    DowntimeEntry,
    PayrollInputError,
    effective_shifts,
    piece_premium,
    plan_effective_shifts,
)
from tests.payroll_fixtures import CURVE_X, REASONS, cents

D = Decimal


def fact(shifts: str | int, *downtime: tuple[str, str | int]):
    return effective_shifts(D(shifts), D("11"), [DowntimeEntry(code, D(hours)) for code, hours in downtime], REASONS)


def premium(meters: Decimal, shifts: Decimal) -> Decimal:
    return piece_premium(meters, CURVE_X, shifts).total


def test_plan_is_rotation_minus_planned_maintenance() -> None:
    plan = plan_effective_shifts(D("15"), D("2"))
    assert plan.effective == D("13")
    assert plan.flags == ()
    assert cents(premium(D("2400"), plan.effective)) == D("156000.67")


def test_three_idle_shifts_not_by_drillers_fault() -> None:
    shifts = fact(13, ("DT_RIG_REPAIR", 33))
    assert shifts.effective == D("10")
    assert cents(premium(D(24000) / D(13), shifts.effective)) == D("120000.52")


def test_seven_idle_hours_raise_the_premium_for_the_same_meters() -> None:
    shifts = fact(13, ("DT_WEATHER", 7))
    assert shifts.effective == D("13") - D("7") / D("11")
    assert cents(premium(D("2000"), shifts.effective)) == D("108400.68")
    assert cents(premium(D("2000"), D("11"))) == D("126920.54")


def test_downtime_by_drillers_fault_is_not_written_off() -> None:
    shifts = fact(13, ("DT_FAULT_BREAKDOWN", 7))
    assert shifts.effective == D("13")
    assert shifts.excusable_hours == 0
    assert cents(premium(D("2000"), shifts.effective)) == D("102804.58")


def test_writing_off_more_than_a_quarter_raises_a_flag() -> None:
    shifts = fact(13, ("DT_WAIT_BLOCK", 40))
    assert shifts.written_off_share == D("40") / D("143")
    assert [flag.code for flag in shifts.flags] == ["DOWNTIME_OVER_25"]
    assert "27,97 %" in shifts.flags[0].message
    assert shifts.effective == D("13") - D("40") / D("11")


def test_planned_maintenance_neither_raises_nor_hides_the_flag() -> None:
    with_maintenance = fact(15, ("DT_PLANNED_MAINTENANCE", 22), ("DT_WAIT_BLOCK", 40))
    assert with_maintenance.written_off_share == D("40") / D("143")
    assert [flag.code for flag in with_maintenance.flags] == ["DOWNTIME_OVER_25"]
    assert with_maintenance.maintenance_hours == D("22")
    only_maintenance = fact(15, ("DT_PLANNED_MAINTENANCE", 22))
    assert only_maintenance.flags == ()
    assert only_maintenance.effective == D("13")


@pytest.mark.parametrize("hours", [143, 150])
def test_downtime_for_the_whole_rotation_is_an_input_error(hours: int) -> None:
    with pytest.raises(PayrollInputError):
        fact(13, ("DT_RIG_REPAIR", hours))


def test_unknown_downtime_code_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError, match="DT_NOPE"):
        fact(13, ("DT_NOPE", 5))


def test_maintenance_for_the_whole_rotation_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError):
        plan_effective_shifts(D("2"), D("2"))
