"""Что двигает цену метра бурения: ручки, чувствительность и «что если».

Фикстура — блок `tests/model_fixtures.py` (12 м/ч, смена 11 ч, станок 40
смен); экипаж на методике — `tests/test_model_block_payroll.py` (машинист на
кривой X: норма 115,3846, потолок 184,6154, 45 / 168,66 ₽).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model import drilling_sensitivity as ds
from cost.model.engine import compute_block_economics
from tests import model_fixtures as fx
from tests import test_model_block_payroll as bp

D = Decimal


def _payroll_params(**overrides):
    return fx.parameters(crew=bp.CREW, payroll_source="PAYROLL", **overrides)


def test_prices_split_rig_lines_and_crew_payroll() -> None:
    """Без ФОТ — `drilling_rub_per_m`; с ФОТ — плюс строки ФОТ экипажа бурения на метр."""

    result = compute_block_economics(fx.snapshot(), fx.parameters(), fx.references())
    prices = ds.prices(result, fx.parameters())

    assert prices.without_payroll == result.natural.values["drilling_rub_per_m"]
    driller = next(line for line in result.lines if line.cost_item_code == "LABOR_POS_DRILLER")
    assert prices.with_payroll == prices.without_payroll + driller.amount_rub / result.natural.values["drilling_m"]
    assert prices.payroll_source == "RATES" and not prices.payroll_applied


def test_prices_are_none_for_subcontract() -> None:
    params = fx.parameters(drilling_executor="SUBCONTRACTOR")
    result = compute_block_economics(fx.snapshot(), params, fx.references())
    prices = ds.prices(result, params)
    assert prices.without_payroll is None and prices.with_payroll is None


def test_knobs_follow_the_chosen_condition_and_references() -> None:
    knobs = {knob.code: knob for knob in ds.knobs(fx.parameters(), fx.references(), fx.physical())}

    assert knobs["TECH_SPEED"].base == D("12")
    assert knobs["TECH_SPEED"].source == "drilling_conditions.COND_GRANITE.tech_speed_m_per_h"
    assert knobs["UNPRODUCTIVE_H"].base == D("1")
    assert knobs["DIESEL_PRICE"].base == D("52200")
    assert knobs["BIT_LIFE"].base == D("700") and knobs["BIT_PRICE"].base == D("35000")
    assert knobs["RIG_PLAN_SHIFTS"].draft_param and knobs["RIG_PLAN_SHIFTS"].base == D("40")
    assert knobs["CREW_SCALE"].base == D("1")
    # Обсадки среди ручек нет: в списке только коронка, ППУ и штанги.
    assert "CASING_LIFE" not in knobs


def test_sensitivity_is_sorted_by_absolute_effect_on_price_with_payroll() -> None:
    result = ds.compute(fx.snapshot(), fx.parameters(), fx.references())

    deltas = [abs(row.delta) for row in result.rows]
    assert deltas == sorted(deltas, reverse=True)
    assert {row.knob.code for row in result.rows} >= {"TECH_SPEED", "DIESEL_PRICE", "CREW_SCALE", "BIT_LIFE"}
    speed = next(row for row in result.rows if row.knob.code == "TECH_SPEED")
    # Быстрее бурим — меньше смен станка и дешевле метр.
    assert speed.price_plus < result.base.with_payroll < speed.price_minus
    # На ставках шкалы премии у бурильщика нет — блока премии нет.
    assert result.premium is None


def test_premium_knobs_move_price_only_in_payroll_mode() -> None:
    references = bp._references()
    on_payroll = ds.compute(fx.snapshot(), _payroll_params(), references, as_of=bp.AS_OF)
    on_rates = ds.compute(fx.snapshot(), fx.parameters(crew=bp.CREW), references, as_of=bp.AS_OF)

    assert on_payroll.premium is not None and on_payroll.premium.applies
    assert on_payroll.premium.position_code == "P_DRILLER"
    assert [row.knob.code for row in on_payroll.premium_rows] == [
        "PREMIUM_NORM",
        "PREMIUM_RATE_NORM",
        "PREMIUM_CEILING",
        "PREMIUM_RATE_CEILING",
    ]
    rate_norm = next(row for row in on_payroll.premium_rows if row.knob.code == "PREMIUM_RATE_NORM")
    assert rate_norm.knob.base == D("45")
    assert rate_norm.price_plus > on_payroll.base.with_payroll > rate_norm.price_minus

    assert on_rates.premium is not None and not on_rates.premium.applies
    assert "Методика ФОТ" in on_rates.premium.note
    assert all(row.delta == 0 for row in on_rates.premium_rows)
    assert on_rates.base.payroll_source == "RATES"


def test_what_if_leaves_references_and_params_untouched() -> None:
    references = bp._references()
    params = _payroll_params()
    condition_before = dict(references.item("drilling_conditions", "COND_GRANITE").payload)
    rate_before = dict(references.item("labor_rates", "LR_DRILLER").payload)

    base, changed = ds.what_if(
        fx.snapshot(),
        params,
        references,
        {"TECH_SPEED": D("15"), "PREMIUM_RATE_NORM": D("60")},
        as_of=bp.AS_OF,
    )

    assert changed.without_payroll < base.without_payroll
    assert changed.with_payroll != base.with_payroll
    assert references.item("drilling_conditions", "COND_GRANITE").payload == condition_before
    assert references.item("labor_rates", "LR_DRILLER").payload == rate_before
    assert params.crew_scale == D("1")


def test_what_if_material_price_moves_tooling_line() -> None:
    base, changed = ds.what_if(fx.snapshot(), fx.parameters(), fx.references(), {"BIT_PRICE": D("70000")})
    # Коронка: 13 953,49 м / 700 м × (70 000 − 35 000) ₽ на метр = 50 ₽/м.
    assert (changed.without_payroll - base.without_payroll).quantize(D("0.01")) == D("50.00")


def test_what_if_rejects_unknown_knob_and_broken_scale() -> None:
    references = bp._references()
    with pytest.raises(ds.WhatIfError, match="недоступна"):
        ds.what_if(fx.snapshot(), _payroll_params(), references, {"NO_SUCH": D("1")}, as_of=bp.AS_OF)
    with pytest.raises(ds.WhatIfError, match="Потолок должен быть выше нормы"):
        ds.what_if(fx.snapshot(), _payroll_params(), references, {"PREMIUM_CEILING": D("100")}, as_of=bp.AS_OF)
    with pytest.raises(ds.WhatIfError, match="не может быть ниже"):
        ds.what_if(fx.snapshot(), _payroll_params(), references, {"PREMIUM_RATE_CEILING": D("10")}, as_of=bp.AS_OF)
    with pytest.raises(ds.WhatIfError, match="больше нуля"):
        ds.what_if(fx.snapshot(), fx.parameters(), fx.references(), {"TECH_SPEED": D("0")})


def test_step_scale_exposes_tier_rates() -> None:
    tiers = [{"upto_per_shift": "100", "rate": "40"}, {"upto_per_shift": None, "rate": "60"}]
    rates = tuple(
        fx.item(item.code, item.name, {"position_code": "P_DRILLER", "fixed_monthly_rub": "27093", "scale_type": "STEP", "tiers": tiers})
        if item.code == "LR_DRILLER"
        else item
        for item in bp.LABOR_RATES
    )
    references = bp._references(labor_rates=rates)
    premium = ds.premium(_payroll_params(), references, fx.physical())

    assert premium is not None and premium.scale_type == "STEP"
    assert [(knob.code, knob.base) for knob in premium.knobs] == [
        ("PREMIUM_TIER_RATE_0", D("40")),
        ("PREMIUM_TIER_RATE_1", D("60")),
    ]
    _, _, changed = ds.apply_overrides(_payroll_params(), references, fx.physical(), {"PREMIUM_TIER_RATE_1": D("70")})
    assert changed.item("labor_rates", "LR_DRILLER").payload["tiers"][1]["rate"] == "70"
    assert references.item("labor_rates", "LR_DRILLER").payload["tiers"][1]["rate"] == "60"
