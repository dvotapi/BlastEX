"""Доля стоимости последнего метра в марже метра (решения §2.2)."""
from __future__ import annotations

from decimal import Decimal

from cost.model.payroll import CrewCost, Scale, ScaleTier, margin_check, premium_cost_factor
from tests.payroll_fixtures import CURVE_X, cents, file_inputs

D = Decimal
FACTOR, _ = premium_cost_factor(file_inputs())
CREW = (
    CrewCost("P_DRILLER", "Машинист", D("1"), CURVE_X, FACTOR),
    CrewCost("P_ASSISTANT", "Помощник", D("1"), CURVE_X, FACTOR),
)
PLAN_PACE = D("2000") / D("13")


def check(**overrides):
    fields = {
        "main_scale": CURVE_X,
        "crew": CREW,
        "pace": PLAN_PACE,
        "meters_factor": D("1"),
        "price": D("800"),
        "variable": D("250"),
        "threshold": D("0.70"),
        **overrides,
    }
    return margin_check(**fields)


def test_crew_of_two_on_curve_x() -> None:
    result = check()
    assert result.status == "CHECKED"
    assert result.margin == D("550")
    assert cents(result.ceiling.crew_share * 100) == D("96.46")
    assert cents(result.plan.crew_share * 100) == D("57.78")
    assert cents(result.ceiling.main_share * 100) == D("30.67")
    assert [flag.code for flag in result.flags] == ["MARGIN_SHARE_ABOVE_WARN"]
    assert "на потолке" in result.flags[0].message


def test_more_normalized_meters_per_physical_meter_raise_the_share() -> None:
    result = check(meters_factor=D("1.2"))
    assert abs(result.ceiling.crew_share - check().ceiling.crew_share * D("1.2")) < D("1e-20")


def test_headcount_multiplies_the_crew_cost() -> None:
    two_drillers = (CrewCost("P_DRILLER", "Машинист", D("2"), CURVE_X, FACTOR),)
    assert abs(check(crew=two_drillers).ceiling.crew_share - check().ceiling.crew_share) < D("1e-20")


def test_without_price_the_share_is_not_checked() -> None:
    result = check(price=None)
    assert result.status == "NOT_CHECKED"
    assert result.plan is None and result.ceiling is None and result.flags == ()


def test_non_positive_margin_gives_a_warning_and_no_share() -> None:
    result = check(price=D("250"))
    assert result.status == "NO_MARGIN"
    assert result.plan is None
    assert result.warnings


def test_position_without_a_scale_is_not_applicable() -> None:
    assert check(main_scale=None).status == "NOT_APPLICABLE"


def test_step_scale_has_no_ceiling_and_warns_by_the_plan_pace() -> None:
    step = Scale("STEP", tiers=(ScaleTier(D("100"), D("45")), ScaleTier(None, D("400"))))
    crew = (CrewCost("P_DRILLER", "Машинист", D("1"), step, FACTOR),)
    result = check(main_scale=step, crew=crew)
    assert result.ceiling is None
    assert cents(result.plan.crew_share * 100) == cents(D("400") * FACTOR / D("550") * 100)
    assert "при плановом темпе" in result.flags[0].message


def test_crew_without_scales_does_not_report_a_zero_share() -> None:
    result = check(crew=())
    assert result.status == "NOT_CHECKED"
    assert result.plan is None and result.flags == ()
    assert any("нет сдельщиков" in warning for warning in result.warnings)
