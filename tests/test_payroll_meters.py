"""Приведённые метры: коэффициенты крепости и диаметра, договорной коэффициент (TASK-010 §2.1)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.payroll import DifficultyTables, MeterItem, PayrollInputError, hardness_factor, normalized_meters
from tests.payroll_fixtures import TABLES

D = Decimal
TWO_ROCKS = [MeterItem(D("800"), D("152"), D("10")), MeterItem(D("900"), D("250"), D("17"))]


def test_two_rocks_on_one_site_need_no_manual_averaging() -> None:
    meters = normalized_meters(TWO_ROCKS, TABLES)
    assert meters.total == D("2571.2")
    assert meters.physical == D("1700")
    assert [(row.k_f, row.k_d) for row in meters.rows] == [(D("1.0"), D("1")), (D("1.2"), D("1.64"))]
    assert meters.factor == D("2571.2") / D("1700")
    assert "16 < f ≤ 18 → 1,2" in meters.lineage["k_f.1"]
    assert "Ø 250 мм → 1,64" in meters.lineage["k_d.1"]


def test_contract_coefficient_multiplies_the_normalized_meters() -> None:
    assert normalized_meters(TWO_ROCKS, TABLES, D("1.1")).total == D("2571.2") * D("1.1")


def test_diameter_missing_from_the_table_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError, match="133"):
        normalized_meters([MeterItem(D("100"), D("133"), D("10"))], TABLES)


def test_empty_tables_give_one_with_a_warning() -> None:
    meters = normalized_meters([MeterItem(D("100"), D("133"), D("17"))], DifficultyTables())
    assert meters.total == D("100")
    assert len(meters.warnings) == 2


@pytest.mark.parametrize(
    ("f", "k"),
    [("7.99", "0.9"), ("8", "0.9"), ("8.01", "1.0"), ("12", "1.0"), ("16.01", "1.2"), ("18", "1.2"), ("18.5", "1.3"), ("20", "1.3")],
)
def test_upper_bound_of_a_hardness_band_is_included(f: str, k: str) -> None:
    factor, _, warning = hardness_factor(D(f), TABLES.hardness)
    assert factor == D(k)
    assert warning == ""


def test_hardness_above_the_scale_takes_the_last_band_with_a_warning() -> None:
    factor, _, warning = hardness_factor(D("25"), TABLES.hardness)
    assert factor == D("1.3")
    assert "выше шкалы" in warning


def test_rock_without_hardness_gives_one_with_a_warning() -> None:
    factor, _, warning = hardness_factor(None, TABLES.hardness)
    assert factor == D("1")
    assert "не задана крепость" in warning


def test_diameter_written_with_a_trailing_zero_is_the_same_diameter() -> None:
    meters = normalized_meters([MeterItem(D("100"), D("152.0"), D("10"))], TABLES)
    assert meters.total == D("100")
