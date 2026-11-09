"""PDF паспорта на бурение (TASK-015, PR 2): формат чисел и отрисовка."""
from __future__ import annotations

import pytest

from design.reporting.drill import fmt

NBSP = " "


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (2280.5, 1, f"2{NBSP}280,5"),
        (29366.4, 0, f"29{NBSP}366"),
        (12.884, 2, "12,88"),
        (10.0, 1, "10,0"),
        (1234567.0, 0, f"1{NBSP}234{NBSP}567"),
        (-0.04, 1, "0,0"),
        (None, 1, "—"),
    ],
)
def test_num(value, digits, expected):
    assert fmt.num(value, digits) == expected


def test_trimmed_number():
    assert fmt.short(1.5) == "1,5"
    assert fmt.short(1.0) == "1"
    assert fmt.short(None) == "—"


def test_date():
    assert fmt.date("2026-10-06") == "06.10.2026"
    assert fmt.date("") == "—"
    assert fmt.date("06.10.2026") == "06.10.2026"


def test_range():
    assert fmt.num_range(10.0, 13.84) == "10,0 – 13,8"
    assert fmt.num_range(10.0, 10.0) == "10,0"
    assert fmt.num_range(None, None) == "—"
