"""Превью ФОТ должности: план и факт, приведённые метры, доля в марже, график (TASK-010)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.payroll import DowntimeEntry, PayrollInputError
from cost.model.payroll_preview import PreviewItem, PreviewRequest, payroll_preview
from tests import model_fixtures as fx
from tests.payroll_fixtures import cents, payroll_references

D = Decimal
FIXED_ROWS = ("SALARY", "HAZARD", "NIGHT", "HOLIDAYS", "INTERSHIFT_REST", "SHIFT_ALLOWANCE")


def preview(snapshot=None, **fields):
    request = PreviewRequest(**{"position_code": "P_DRILLER", "site_code": "SITE_LOM", "year": 2026, **fields})
    return payroll_preview(snapshot or payroll_references(), request)


def test_plan_takes_the_site_rotation_minus_maintenance() -> None:
    result = preview(meters_total=D("2400"))
    assert result.shifts.effective == D("13")
    assert cents(result.premium.total) == D("156000.67")
    assert result.result.amount("PIECE_PREMIUM") == result.premium.total
    assert result.flags == ()
    assert result.margin.status == "NOT_CHECKED"
    assert result.margin.plan is None


def test_margin_share_in_two_points_with_the_warning_on_the_ceiling() -> None:
    result = preview(meters_total=D("2000"), price_rub_per_m=D("800"), variable_rub_per_m=D("250"))
    margin = result.margin
    assert margin.status == "CHECKED"
    assert [member.position_code for member in margin.crew] == ["P_DRILLER", "P_ASSISTANT"]
    assert cents(margin.ceiling.crew_share * 100) == D("96.46")
    assert cents(margin.plan.crew_share * 100) == D("57.78")
    assert cents(margin.ceiling.main_share * 100) == D("30.67")
    assert [flag.code for flag in result.flags] == ["MARGIN_SHARE_ABOVE_WARN"]


def test_explicit_crew_replaces_the_default() -> None:
    result = preview(
        meters_total=D("2000"), price_rub_per_m=D("800"), variable_rub_per_m=D("250"), crew=(("P_DRILLER", D("1")),)
    )
    assert cents(result.margin.ceiling.crew_share * 100) == D("48.23")
    assert result.flags == ()


def test_no_price_means_the_share_is_not_checked() -> None:
    result = preview(meters_total=D("2000"))
    assert result.margin.status == "NOT_CHECKED"
    assert result.margin.ceiling is None


def test_non_positive_margin_gives_no_share_and_a_warning() -> None:
    result = preview(meters_total=D("2000"), price_rub_per_m=D("200"), variable_rub_per_m=D("250"))
    assert result.margin.status == "NO_MARGIN"
    assert result.margin.plan is None
    assert any("Маржа метра" in warning for warning in result.warnings)


def test_meters_by_rock_and_diameter() -> None:
    items = (PreviewItem(D("800"), D("152"), rock_code="ROCK_F10"), PreviewItem(D("900"), D("250"), rock_code="ROCK_F17"))
    result = preview(items=items, price_rub_per_m=D("800"), variable_rub_per_m=D("250"))
    assert result.meters.total == D("2571.2")
    assert result.meters.factor == D("2571.2") / D("1700")
    plan_pace = D("2571.2") / D("13")
    assert result.premium.pace == plan_pace
    # Стоимость последнего погонного метра — приведённых метров на погонный больше.
    expected = 2 * result.margin.crew[0].cost_factor * D("168.66") * result.meters.factor / D("550")
    assert result.margin.ceiling.crew_share == expected


def test_contract_coefficient_of_the_site_enters_the_meters() -> None:
    sites = (fx.item("SITE_LOM", "Ломовское", {"contract_k": "1.1"}),)
    items = (PreviewItem(D("1000"), D("152"), f=D("10")),)
    result = preview(payroll_references(sites=sites), items=items)
    assert result.meters.total == D("1100")
    assert "contract_k" in result.lineage


def test_fact_with_downtime_keeps_the_fixed_part() -> None:
    plan = preview(meters_total=D(24000) / D(13))
    fact = preview(
        meters_total=D(24000) / D(13), shifts=D("13"), downtime=(DowntimeEntry("DT_RIG_REPAIR", D("33")),)
    )
    assert fact.shifts.effective == D("10")
    assert cents(fact.premium.total) == D("120000.52")
    for code in FIXED_ROWS:
        assert fact.result.amount(code) == plan.result.amount(code)


def test_downtime_for_the_whole_rotation_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError):
        preview(meters_total=D("2000"), shifts=D("13"), downtime=(DowntimeEntry("DT_RIG_REPAIR", D("143")),))


def test_downtime_without_shifts_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError):
        preview(meters_total=D("2000"), downtime=(DowntimeEntry("DT_RIG_REPAIR", D("11")),))


def test_flags_for_downtime_and_pace() -> None:
    result = preview(meters_total=D("3000"), shifts=D("13"), downtime=(DowntimeEntry("DT_WAIT_BLOCK", D("40")),))
    assert [flag.code for flag in result.flags] == ["DOWNTIME_OVER_25", "PACE_ABOVE_CEILING"]


def test_time_bonus_position_has_no_premium() -> None:
    result = preview(position_code="P_STOREKEEPER", meters_total=D("100"))
    assert result.premium is None
    assert result.margin.status == "NOT_APPLICABLE"
    assert result.result.amount("PIECE_PREMIUM") == 0
    assert result.series == ()
    assert any("Повременная" in warning for warning in result.warnings)
    assert any("МРОТ" in warning for warning in result.warnings)


def test_missing_output_pays_no_premium_with_a_warning() -> None:
    result = preview()
    assert result.premium.total == 0
    assert any("Выработка не задана" in warning for warning in result.warnings)


def test_series_and_dict_for_the_api() -> None:
    body = preview(meters_total=D("2000"), price_rub_per_m=D("800"), variable_rub_per_m=D("250")).to_dict()
    assert body["premium"]["gamma"] == pytest.approx(2.811088, abs=1e-6)
    assert body["series"][0] == {"pace": 0.0, "rate": 45.0, "per_shift": 0.0}
    assert body["margin"]["ceiling"]["crew_share"] == pytest.approx(0.9646, abs=1e-4)
    assert body["rows"][-1]["code"] == "COMPANY_COST"
    assert body["flags"][0]["code"] == "MARGIN_SHARE_ABOVE_WARN"
    assert "premium_cost_factor" in body["lineage"]


def test_rock_without_hardness_counts_with_one_and_a_warning() -> None:
    result = preview(items=(PreviewItem(D("1000"), D("152"), rock_code="ROCK_NO_F"),))
    assert result.meters.total == D("1000")
    assert any("не задана крепость" in warning for warning in result.warnings)


def test_piece_bonus_position_counts_plain_output() -> None:
    snapshot = payroll_references(
        positions=(
            *payroll_references().sections["positions"],
            fx.item("P_DRIVER", "Водитель", {"category": "INDIRECT", "pay_system": "PIECE_BONUS", "output_unit": "KM"}),
        ),
        labor_rates=(
            *payroll_references().sections["labor_rates"],
            fx.item(
                "LR_DRIVER",
                "Водитель",
                {
                    "position_code": "P_DRIVER",
                    "fixed_monthly_rub": "40000",
                    "scale_type": "STEP",
                    "tiers": [{"upto_per_shift": "200", "rate": "10"}, {"upto_per_shift": None, "rate": "15"}],
                },
            ),
        ),
    )
    # Ø 133 мм в таблице сложности нет: без приведения таблица не читается.
    items = (PreviewItem(D("2000"), D("152")), PreviewItem(D("1250"), D("133")))
    result = preview(snapshot, position_code="P_DRIVER", items=items)
    assert result.meters.total == D("3250")
    assert result.meters.rows == ()
    assert result.premium.pace == D("250")
    assert result.premium.total == D("13") * (D("200") * 10 + D("50") * 15)
    assert result.margin.status == "NOT_APPLICABLE"


def test_unknown_crew_member_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError, match="NOPE"):
        preview(meters_total=D("2000"), crew=(("NOPE", D("1")),))


def test_share_on_a_total_of_normalized_meters_is_flagged() -> None:
    """Сумма приведённых метров не знает погонных: доля — на приведённый метр, и это сказано."""
    result = preview(meters_total=D("2000"), price_rub_per_m=D("800"), variable_rub_per_m=D("250"))
    assert result.margin.status == "CHECKED"
    assert any("Метры заданы суммой" in warning for warning in result.warnings)
    assert not any("Метры заданы суммой" in warning for warning in preview(meters_total=D("2000")).warnings)


def test_share_is_not_applicable_to_output_without_normalized_meters() -> None:
    """Расценка водителя за километр с маржой метра бурения не сравнивается."""
    snapshot = payroll_references(
        positions=(
            *payroll_references().sections["positions"],
            fx.item("P_DRIVER", "Водитель", {"category": "INDIRECT", "pay_system": "PIECE_BONUS", "output_unit": "KM"}),
        ),
        labor_rates=(
            *payroll_references().sections["labor_rates"],
            fx.item(
                "LR_DRIVER",
                "Водитель",
                {"position_code": "P_DRIVER", "scale_type": "STEP", "tiers": [{"upto_per_shift": None, "rate": "15"}]},
            ),
        ),
    )
    result = preview(
        snapshot, position_code="P_DRIVER", meters_total=D("3000"), price_rub_per_m=D("800"), variable_rub_per_m=D("250")
    )
    assert cents(result.premium.total) == D("45000")
    assert result.margin.status == "NOT_APPLICABLE"
    assert result.flags == ()
