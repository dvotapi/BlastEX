"""Шкала сдельной премии: кривая X машиниста, линейная кривая, ступени (TASK-010 §2.3)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.payroll import PayrollInputError, Scale, ScaleTier, pace_flags, piece_premium, scale_series
from tests.payroll_fixtures import CURVE_X, cents

D = Decimal
THIRTEEN = D("13")


def premium(meters: str | int, shifts: str | int = 13, scale: Scale = CURVE_X) -> Decimal:
    return piece_premium(D(meters), scale, D(shifts)).total


@pytest.mark.parametrize(
    ("meters", "expected"),
    [(1500, "67500.00"), (1800, "85271.62"), (2000, "102804.58"), (2400, "156000.67"), (3000, "257196.67")],
)
def test_curve_x_premium_for_a_13_shift_rotation(meters: int, expected: str) -> None:
    assert cents(premium(meters)) == D(expected)


def test_nodes_with_four_digits_match_the_exact_nodes() -> None:
    exact = Scale("CURVE_POWER", D(1500) / THIRTEEN, D("45"), D(2400) / THIRTEEN, D("168.66"))
    for meters in (1500, 1800, 2000, 2400, 3000):
        assert abs(premium(meters) - premium(meters, scale=exact)) <= D("0.01")


def test_rounded_nodes_and_169_rub_drift_from_the_method() -> None:
    rounded = Scale("CURVE_POWER", D("115.4"), D("45"), D("184.6"), D("169"))
    assert cents(premium(2400, scale=rounded)) == D("156116.59")


def test_gamma_is_derived_from_the_nodes() -> None:
    assert CURVE_X.gamma.quantize(D("0.000001")) == D("2.811088")
    exact = Scale("CURVE_POWER", D(1500) / THIRTEEN, D("45"), D(2400) / THIRTEEN, D("168.66"))
    assert exact.gamma.quantize(D("0.000001")) == D("2.811090")


def test_premium_per_shift_at_norm_and_ceiling() -> None:
    assert cents(CURVE_X.per_shift(CURVE_X.norm_per_shift)) == D("5192.31")
    assert cents(CURVE_X.per_shift(CURVE_X.ceiling_per_shift)) == D("12000.05")


def test_meter_price_grows_faster_with_every_200_meters() -> None:
    def rate(meters: int) -> Decimal:
        return CURVE_X.rate_at(D(meters) / THIRTEEN)

    steps = [rate(2000) - rate(1800), rate(2200) - rate(2000), rate(2400) - rate(2200)]
    for step, expected in zip(steps, (D("25.8971"), D("31.0397"), D("36.5958"))):
        assert abs(step - expected) <= D("0.05")
    assert steps[0] < steps[1] < steps[2]


def test_meter_price_is_constant_above_the_ceiling() -> None:
    assert CURVE_X.rate_at(CURVE_X.ceiling_per_shift) == D("168.66")
    assert CURVE_X.rate_at(D(3000) / THIRTEEN) == D("168.66")


@pytest.mark.parametrize("scale_type", ["CURVE_POWER", "CURVE_LINEAR"])
def test_premium_and_price_are_continuous_at_the_nodes(scale_type: str) -> None:
    scale = Scale(scale_type, CURVE_X.norm_per_shift, D("45"), CURVE_X.ceiling_per_shift, D("168.66"))
    eps = D("0.000001")
    for node in (scale.norm_per_shift, scale.ceiling_per_shift):
        assert abs(scale.per_shift(node + eps) - scale.per_shift(node - eps)) < D("0.001")
        assert abs(scale.rate_at(node + eps) - scale.rate_at(node - eps)) < D("0.01")


@pytest.mark.parametrize("scale_type", ["CURVE_POWER", "CURVE_LINEAR"])
def test_premium_per_shift_is_convex(scale_type: str) -> None:
    scale = Scale(scale_type, CURVE_X.norm_per_shift, D("45"), CURVE_X.ceiling_per_shift, D("168.66"))
    values = [scale.per_shift(D(pace)) for pace in range(0, 260, 5)]
    second = [values[i + 1] - 2 * values[i] + values[i - 1] for i in range(1, len(values) - 1)]
    assert all(diff >= D("-0.000001") for diff in second)


STEP = Scale(
    "STEP",
    tiers=(
        ScaleTier(D(1500) / THIRTEEN, D("45")),
        ScaleTier(D(1800) / THIRTEEN, D("75")),
        ScaleTier(D(2400) / THIRTEEN, D("110")),
        ScaleTier(None, D("140")),
    ),
)
LINEAR = Scale("CURVE_LINEAR", CURVE_X.norm_per_shift, D("45"), CURVE_X.ceiling_per_shift, D("168.66"))


def test_every_shape_pays_rate_norm_below_the_norm() -> None:
    for scale in (CURVE_X, LINEAR, STEP):
        assert scale.per_shift(D("100")) == D("4500")


@pytest.mark.parametrize(("meters", "expected"), [(1800, 87183), (2000, 107175), (2400, 163647), (3000, 264843)])
def test_linear_curve_is_a_trapezoid(meters: int, expected: int) -> None:
    assert premium(meters, scale=LINEAR).quantize(D("1")) == D(expected)


@pytest.mark.parametrize(
    ("meters", "expected"),
    [(1500, "67500"), (1800, "90000"), (2000, "112000"), (2400, "156000"), (3000, "240000")],
)
def test_step_scale_sums_the_tiers(meters: int, expected: str) -> None:
    result = piece_premium(D(meters), STEP, THIRTEEN)
    assert cents(result.total) == D(expected)
    assert cents(sum((tier.amount for tier in result.tiers), D("0"))) == D(expected)
    assert cents(sum((tier.units for tier in result.tiers), D("0"))) == D(meters)


def test_premium_is_paid_on_the_mean_pace_not_per_shift() -> None:
    assert cents(premium(1980, 12)) == D("109857.35")
    per_shift = 6 * CURVE_X.per_shift(D("100")) + 6 * CURVE_X.per_shift(D("230"))
    assert cents(per_shift) == D("144927.72")


def test_premium_is_proportional_only_below_the_norm() -> None:
    assert premium(2400) != D("1.2") * premium(2000)
    assert cents(D("1.2") * premium(2000)) == D("123365.50")
    assert cents(premium(1200)) == cents(D("1.2") * premium(1000)) == D("54000")


def test_breakdown_shows_pace_rates_and_mean_price() -> None:
    result = piece_premium(D("2000"), CURVE_X, THIRTEEN)
    assert result.pace == D("2000") / THIRTEEN
    assert cents(result.last_rate) == D("101.02")
    assert result.mean_rate == result.total / D("2000")
    assert "gamma" in result.lineage and "2,811088" in result.lineage["gamma"]


def test_zero_output_pays_nothing() -> None:
    result = piece_premium(D("0"), CURVE_X, THIRTEEN)
    assert result.total == 0
    assert result.mean_rate is None


def test_zero_effective_shifts_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError):
        piece_premium(D("100"), CURVE_X, D("0"))


def test_pace_flag_above_one_and_a_fifth_of_the_ceiling() -> None:
    assert [flag.code for flag in pace_flags(CURVE_X, D("230"))] == ["PACE_ABOVE_CEILING"]
    assert pace_flags(CURVE_X, D("220")) == ()
    assert pace_flags(STEP, D("500")) == ()


def test_series_contains_nodes_pace_and_reaches_beyond_the_ceiling() -> None:
    pace = D("2000") / THIRTEEN
    series = scale_series(CURVE_X, pace)
    paces = [point.pace for point in series]
    assert {CURVE_X.norm_per_shift, CURVE_X.ceiling_per_shift, pace} <= set(paces)
    assert paces == sorted(paces)
    assert series[0].pace == 0 and series[0].per_shift == 0
    assert paces[-1] == CURVE_X.ceiling_per_shift * D("1.3")
    rates = [point.rate for point in series]
    assert rates == sorted(rates)
    assert series[-1].rate == D("168.66")
