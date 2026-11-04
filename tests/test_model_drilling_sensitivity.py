"""Что двигает цену метра бурения: ручки, чувствительность и «что если».

Фикстура — блок `tests/model_fixtures.py` (12 м/ч, смена 11 ч, станок 40
смен); экипаж на методике — `tests/test_model_block_payroll.py` (машинист на
кривой X: норма 115,3846, потолок 184,6154, 45 / 168,66 ₽).
"""
from __future__ import annotations

from dataclasses import replace
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
    """Без услуг и персонала участка: без ФОТ — `drilling_rub_per_m`; с ФОТ — плюс ФОТ экипажа на метр."""

    result = compute_block_economics(fx.snapshot(), fx.parameters(), fx.references())
    prices = ds.prices(result, fx.parameters())

    assert abs(prices.without_payroll - result.natural.values["drilling_rub_per_m"]) < D("0.000001")
    driller = next(line for line in result.lines if line.cost_item_code == "LABOR_POS_DRILLER")
    assert abs(prices.with_payroll - prices.without_payroll - driller.amount_rub / result.natural.values["drilling_m"]) < D("0.000001")
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
    # Множителя численности экипажа среди ручек нет: это не параметр блока.
    assert "CREW_SCALE" not in knobs
    # Обсадки среди ручек нет: в списке только коронка, ППУ и штанги.
    assert "CASING_LIFE" not in knobs


def test_sensitivity_is_sorted_by_absolute_effect_on_price_with_payroll() -> None:
    result = ds.compute(fx.snapshot(), fx.parameters(), fx.references())

    deltas = [abs(row.delta) for row in result.rows]
    assert deltas == sorted(deltas, reverse=True)
    assert {row.knob.code for row in result.rows} >= {"TECH_SPEED", "DIESEL_PRICE", "BIT_LIFE"}
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


def test_premium_marked_inactive_when_methodology_falls_back_to_rates() -> None:
    """Режим «Методика ФОТ» выбран, но без «Параметров ФОТ» года экипаж считается по ставкам."""

    references = bp._references(payroll_params=())
    result = ds.compute(fx.snapshot(), _payroll_params(), references, as_of=bp.AS_OF)

    assert result.base.payroll_source == "PAYROLL" and not result.base.payroll_applied
    assert result.premium is not None and not result.premium.applies
    assert "не применилась" in result.premium.note
    assert all(row.delta == 0 for row in result.premium_rows)


def test_zero_unproductive_time_is_allowed() -> None:
    base, changed = ds.what_if(fx.snapshot(), fx.parameters(), fx.references(), {"UNPRODUCTIVE_H": D("0")})
    assert changed.without_payroll < base.without_payroll
    with pytest.raises(ds.WhatIfError, match="не меньше нуля"):
        ds.what_if(fx.snapshot(), fx.parameters(), fx.references(), {"UNPRODUCTIVE_H": D("-1")})


def test_premium_probes_stay_within_scale_rules() -> None:
    """Расценка на норме равна расценке на потолке: плечо +10 % упирается в границу, а не ломает шкалу."""

    rates = tuple(
        fx.item(item.code, item.name, {**item.payload, "rate_norm": "168.66"}) if item.code == "LR_DRILLER" else item
        for item in bp.LABOR_RATES
    )
    references = bp._references(labor_rates=rates)
    result = ds.compute(fx.snapshot(), _payroll_params(), references, as_of=bp.AS_OF)

    assert result.base.payroll_applied
    rate_norm = next(row for row in result.premium_rows if row.knob.code == "PREMIUM_RATE_NORM")
    assert rate_norm.price_plus == result.base.with_payroll
    assert rate_norm.price_minus < result.base.with_payroll
    rate_ceiling = next(row for row in result.premium_rows if row.knob.code == "PREMIUM_RATE_CEILING")
    assert rate_ceiling.price_minus == result.base.with_payroll
    assert rate_ceiling.price_plus >= result.base.with_payroll


def test_premium_bounds_follow_neighbours() -> None:
    knobs = ds.premium(_payroll_params(), bp._references(), fx.physical()).knobs
    bounds = ds.premium_bounds(knobs)
    assert bounds["PREMIUM_NORM"] == (None, D("184.6154") - 1)
    assert bounds["PREMIUM_CEILING"] == (D("115.3846") + 1, None)
    assert bounds["PREMIUM_RATE_NORM"] == (None, D("168.66"))
    assert bounds["PREMIUM_RATE_CEILING"] == (D("45"), None)


def test_premium_skips_time_paid_position_with_a_scale() -> None:
    """Повременщик со шкалой в ставке идёт в экипаже первым — премию получает сдельщик за ним."""

    positions = tuple(
        fx.item(item.code, item.name, {**item.payload, "pay_system": "TIME_BONUS"}) if item.code == "P_ASSISTANT" else item
        for item in bp.CREW_POSITIONS
    )
    references = bp._references(positions=(*fx.POSITIONS, *positions))
    crew = (bp.CREW[1], bp.CREW[0], *bp.CREW[2:])
    premium = ds.premium(fx.parameters(crew=crew, payroll_source="PAYROLL"), references, fx.physical())

    assert premium is not None and premium.position_code == "P_DRILLER"


def test_prices_components_add_up_and_follow_overrides() -> None:
    """Слагаемые кольца складываются в цену с ФОТ; кривая премии строится по шкале с подменами."""

    references = bp._references()
    base, changed = ds.what_if(fx.snapshot(), _payroll_params(), references, {"PREMIUM_RATE_NORM": D("60")}, as_of=bp.AS_OF)

    assert [c.code for c in base.components][-1] == "CREW_PAYROLL"
    assert abs(sum((c.rub_per_m for c in base.components), D("0")) - base.with_payroll) < D("0.000001")
    assert base.premium_curve is not None and base.premium_curve.scale["rate_norm"] == 45.0
    assert changed.premium_curve is not None and changed.premium_curve.scale["rate_norm"] == 60.0
    assert base.premium_curve.pace == D("120") and len(base.premium_curve.series) > 2
    # ФОТ экипажа разложен по строкам: должности без префикса «ФОТ: », сумма — сам ФОТ.
    crew = base.components[-1]
    assert len(crew.parts) > 1
    assert abs(sum((p.rub_per_m for p in crew.parts), D("0")) - crew.rub_per_m) < D("0.000001")
    assert all(p.code.startswith("LABOR_") and not p.label.startswith("ФОТ: ") for p in crew.parts)
    assert len({p.code for p in crew.parts}) == len(crew.parts)
    assert crew.to_dict()["parts"][0]["label"] == crew.parts[0].label
    # На ставках шкалы в кривой нет (у бурильщика фикстуры её нет), слагаемые — есть.
    plain = ds.compute(fx.snapshot(), fx.parameters(), fx.references()).base
    assert plain.premium_curve is None and plain.components


def test_rules_and_services_of_drilling_go_to_services_not_to_the_rig() -> None:
    """Трал и выпуск/медосмотр — услуги; правило со статьёй станка (доп. оснастка) — своя группа.

    Станок в кольце — только строки самой модели бурения; цена с ФОТ — все
    строки операций бурения, как цена метра листа «Расчёт».
    """

    rules = [
        fx.item(
            "RULE_TOOLING_EXTRA",
            "Доп. оснастка",
            {
                "operation_code": "PRODUCTION_DRILLING",
                "cost_item_code": "DRILL_TOOLING",
                "behavior_type": "VARIABLE",
                "cost_layer": "variable",
                "driver": "drilling_m",
                "rate_rub": "10",
                "estimate_section": "DRILLING",
            },
        ),
        fx.item(
            "RULE_TRAWL",
            "Услуги трала",
            {
                "operation_code": "PRODUCTION_DRILLING",
                "cost_item_code": "VM_DELIVERY",
                "behavior_type": "FIXED",
                "cost_layer": "project_direct",
                "fixed_rub": "70000",
                "estimate_section": "DRILLING",
            },
        ),
    ]
    references = fx.references(cost_rules=(*fx.COST_RULES, *rules))
    result = compute_block_economics(fx.snapshot(), fx.parameters(), references)
    plain = ds.prices(result, fx.parameters())
    drilling_m = result.natural.values["drilling_m"]

    rig = sum((c.rub_per_m for c in plain.components if c.code.startswith("DRILL_")), D("0"))
    inspection = next(line for line in result.drilling_lines if line.cost_item_code == "DRILL_INSPECTION")
    # Станок без выпуска и медосмотра — строки модели бурения.
    assert abs(rig + inspection.amount_rub / drilling_m - result.natural.values["drilling_rub_per_m"]) < D("0.000001")
    services = next(c for c in plain.components if c.code == "SERVICES")
    assert abs(services.rub_per_m - (inspection.amount_rub + D("70000")) / drilling_m) < D("0.000001")
    assert "Услуги трала" in {part.label for part in services.parts}
    assert len({part.code for part in services.parts}) == len(services.parts)
    # Доп. оснастка по правилу — затрата станка, не услуга подрядчика.
    rig_rules = next(c for c in plain.components if c.code == "RIG_RULES")
    assert [part.label for part in rig_rules.parts] == ["Доп. оснастка"]
    assert rig_rules.rub_per_m == D("10")
    total = sum((line.amount_rub for line in result.lines if line.operation_code == "PRODUCTION_DRILLING"), D("0"))
    assert abs(plain.with_payroll - total / drilling_m) < D("0.000001")
    assert abs(sum((c.rub_per_m for c in plain.components), D("0")) - plain.with_payroll) < D("0.000001")


def test_site_staff_bound_to_drilling_is_payroll_of_the_meter() -> None:
    """Механик, мастер, слесарь — постоянные затраты юнита с операцией бурения: своя группа ФОТ."""

    costs = tuple(
        fx.item(item.code, item.name, {**item.payload, "operation_code": "PRODUCTION_DRILLING"}) if item.code == "UFC_WH_HEAD" else item
        for item in fx.UNIT_FIXED_COSTS
    )
    references = fx.references(unit_fixed_costs=costs)
    result = compute_block_economics(fx.snapshot(), fx.parameters(), references)
    plain = ds.prices(result, fx.parameters())
    drilling_m = result.natural.values["drilling_m"]

    staff_line = next(line for line in result.lines if line.cost_item_code == "UNIT_UFC_WH_HEAD")
    staff = next(c for c in plain.components if c.code == "SITE_STAFF")
    assert staff.rub_per_m == staff_line.amount_rub / drilling_m
    # Подстрока — название записи без префикса категории.
    assert [part.label for part in staff.parts] == ["Заведующий складом"]
    # ФОТ персонала участка в «без ФОТ» не входит; содержание базы без операции — не в метре.
    crew = next(c for c in plain.components if c.code == "CREW_PAYROLL")
    assert abs(plain.with_payroll - plain.without_payroll - crew.rub_per_m - staff.rub_per_m) < D("0.000001")
    assert not any(c.code == "UNIT_FIXED" for c in plain.components)


def _site_references():
    """Трал правилом, механик с операцией бурения, проживание и питание на вахте, выпуск и медосмотр станка."""

    costs = tuple(
        fx.item(item.code, item.name, {**item.payload, "operation_code": "PRODUCTION_DRILLING"}) if item.code == "UFC_WH_HEAD" else item
        for item in fx.UNIT_FIXED_COSTS
    )
    trawl = fx.item(
        "RULE_TRAWL",
        "Услуги трала",
        {
            "operation_code": "PRODUCTION_DRILLING",
            "cost_item_code": "VM_DELIVERY",
            "behavior_type": "FIXED",
            "cost_layer": "project_direct",
            "fixed_rub": "70000",
            "estimate_section": "DRILLING",
        },
    )
    rates = fx.item("ORG_RATES_DEFAULT", "Ставки организации", {"per_diem_rub": "700", "lodging_rub": "1500", "meals_rub": "600"})
    return fx.references(unit_fixed_costs=costs, cost_rules=(*fx.COST_RULES, trawl), organization_rates=(rates,))


def test_site_knobs_cover_services_staff_salaries_and_camp() -> None:
    references = _site_references()
    params = fx.parameters()
    knobs = {knob.code: knob for knob in ds.knobs(params, references, fx.physical())}

    site = {code for code, knob in knobs.items() if knob.group == ds.SITE_GROUP}
    assert {"RULE:RULE_TRAWL", "STAFF:LR_WH_HEAD", "LODGING", "MEALS"} <= site
    assert knobs["RULE:RULE_TRAWL"].base == D("70000") and knobs["RULE:RULE_TRAWL"].unit == "₽ на блок"
    assert knobs["STAFF:LR_WH_HEAD"].base == D("40000") and knobs["STAFF:LR_WH_HEAD"].label == "Оклад: Заведующий складом"
    assert knobs["MEALS"].base == D("600")
    # Ручки станка в группе участка не числятся.
    assert knobs["TECH_SPEED"].group == "cost"


def test_site_knobs_move_the_meter_price() -> None:
    references = _site_references()
    base, changed = ds.what_if(
        fx.snapshot(), fx.parameters(), references, {"RULE:RULE_TRAWL": D("140000"), "STAFF:LR_WH_HEAD": D("80000"), "MEALS": D("1200")}
    )
    drilling_m = base.drilling_m

    def group(prices, code):
        return next(c.rub_per_m for c in prices.components if c.code == code)

    # Трал вдвое дороже — +70 000 ₽ на блок в услугах.
    assert abs(group(changed, "SERVICES") - group(base, "SERVICES") - D("70000") / drilling_m) < D("0.000001")
    # Оклад механика вдвое — вдвое больше и его доля в метре.
    assert abs(group(changed, "SITE_STAFF") - 2 * group(base, "SITE_STAFF")) < D("0.000001")
    # Питание дороже — растёт группа проживания и питания, ФОТ экипажа не меняется.
    assert group(changed, "CAMP") > group(base, "CAMP")
    assert group(changed, "CREW_PAYROLL") == group(base, "CREW_PAYROLL")
    # Проживание и питание — не ФОТ: «без ФОТ» их содержит.
    camp = group(base, "CAMP")
    assert abs(base.with_payroll - base.without_payroll - group(base, "CREW_PAYROLL") - group(base, "SITE_STAFF")) < D("0.000001")
    assert camp > 0


def test_manual_drilling_service_has_a_knob() -> None:
    from cost.model.inputs import ServiceCharge

    from cost.model.services import service_code

    params = replace(
        fx.parameters(),
        services=(
            ServiceCharge("Охрана площадки", D("20000"), operation_code="BLAST_EXECUTION"),
            ServiceCharge("Медосмотр подрядчика", D("50000"), operation_code="PRODUCTION_DRILLING"),
        ),
    )
    code = f"SERVICE:{service_code('Медосмотр подрядчика')}"
    knob = next(knob for knob in ds.knobs(params, fx.references(), fx.physical()) if knob.code == code)
    assert knob.group == ds.SITE_GROUP and knob.base == D("50000")
    # Код — по названию, не по номеру: услуга взрывных работ перед ней ручку не сдвигает,
    # а сама она ручки не получает (операция не бурения).
    assert not any(k.label == "Охрана площадки" for k in ds.knobs(params, fx.references(), fx.physical()))
    _, changed = ds.what_if(fx.snapshot(), params, fx.references(), {code: D("100000")})
    base, _ = ds.what_if(fx.snapshot(), params, fx.references(), {})
    assert abs(changed.with_payroll - base.with_payroll - D("50000") / base.drilling_m) < D("0.000001")
