"""Цена метра и доля экипажа в марже блока (TASK-010 PR 3a, решения §2.1–§2.2).

Фикстура — та же, что у строк ФОТ блока (`tests/test_model_block_payroll.py`):
машинист и помощник на кривой X, ОХР и рентабельность 10 % + 10 %. Блок
считается на строке матрицы f 17 / Ø 250 (m_план = 236,16, M_блока / п.м. =
1,968): ориентир спеки 726,96 ₽/м получен при k = 1 и здесь пересчитан.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from cost.model import block_margin, block_payroll, drilling, markup
from cost.model.engine import compute_block_economics
from cost.model.inputs import ModelContext, ServiceCharge
from cost.model.payroll import margin_check
from cost.v2.models import CostLayer
from tests import model_fixtures as fx
from tests import payroll_fixtures as pfx
from tests.test_model_block_payroll import AS_OF, COND_F17, CREW, _references

D = Decimal
F17_REFERENCES = dict(site={"rock_code": "ROCK_F17"}, drilling_conditions=(COND_F17,))


def _economics(references=None, **params):
    return compute_block_economics(
        fx.snapshot(),
        fx.parameters(**{"crew": CREW, "payroll_source": "PAYROLL", **params}),
        references or _references(**F17_REFERENCES),
        as_of=AS_OF,
    )


def _norms(references=None, **params):
    context = ModelContext(
        references or _references(**F17_REFERENCES),
        fx.parameters(**{"crew": CREW, "payroll_source": "PAYROLL", **params}),
        fx.physical(),
        as_of=AS_OF,
    )
    return drilling.compute(context), context.value("drilling_m")


def _crew_rub(economics) -> Decimal:
    return sum(
        (line.amount_rub for line in economics.lines if line.price_origin == "PAYROLL"), D("0")
    )


# --- Цена метра (§2.1) ----------------------------------------------------------


def test_price_m_matches_section_2_1_formula() -> None:
    economics = _economics()
    norms, drilling_m = _norms()
    crew_rub_per_m = _crew_rub(economics) / drilling_m

    expected = (norms.cost_rub_per_m + crew_rub_per_m) * D("1.1") * D("1.1")
    payroll = economics.payroll
    assert payroll is not None
    assert payroll["price_rub_per_m"] == pytest.approx(float(expected), rel=1e-12)
    # Зафиксировано первым прогоном (f 17 / Ø 250): метр бурения 408,93 ₽
    # (переменные 296,20 + постоянные 112,73), ФОТ экипажа 657,51 ₽/м
    # (постоянная и переменная части двух человек), надбавки 10 % + 10 %.
    assert round(norms.cost_rub_per_m, 2) == D("408.93")
    assert round(float(crew_rub_per_m), 2) == 657.51
    assert round(payroll["price_rub_per_m"], 2) == 1290.40


def test_markup_rates_are_shared_by_price_ladder_and_price_of_metre() -> None:
    context = ModelContext(
        _references(), fx.parameters(overhead_rate=D("0.15"), vat_rate=D("0.22")), fx.physical(), as_of=AS_OF
    )
    assert markup.rates(context) == (D("0.15"), D("0.10"), D("0.22"))
    _, values = markup.apply(context, markup.layer_totals(()))
    assert (values["overhead_rate"], values["target_margin_rate"], values["vat_rate"]) == markup.rates(context)


def test_var_m_excludes_depreciation_insurance_maintenance() -> None:
    economics = _economics()
    drilling_lines = [line for line in economics.lines if line.operation_code == "PRODUCTION_DRILLING"]
    codes = {line.cost_item_code: line for line in drilling_lines}
    # Амортизация, страхование и ТО станка — строки бурения, но не переменные.
    for code in ("DRILL_DEPRECIATION", "DRILL_INSURANCE", "DRILL_MAINTENANCE"):
        assert codes[code].layer is not CostLayer.VARIABLE
    drilling_m = economics.natural.values["drilling_m"]

    variable = sum((line.amount_rub for line in drilling_lines if line.layer is CostLayer.VARIABLE), D("0"))
    everything = sum((line.amount_rub for line in drilling_lines), D("0"))
    var_m = economics.payroll["variable_rub_per_m"]
    assert var_m == pytest.approx(float(variable / drilling_m), rel=1e-12)
    assert var_m < float(everything / drilling_m)
    assert round(var_m, 2) == 289.07


# --- Доля в марже (§2.2) --------------------------------------------------------


def test_share_checked_at_plan_and_ceiling_with_warning_on_ceiling() -> None:
    economics = _economics()
    margin = economics.payroll["margin"]

    assert margin["status"] == "CHECKED"
    assert margin["threshold"] == pytest.approx(0.70)
    assert margin["margin_rub_per_m"] == pytest.approx(
        economics.payroll["price_rub_per_m"] - economics.payroll["variable_rub_per_m"]
    )
    plan, ceiling = margin["plan"], margin["ceiling"]
    assert plan["pace"] == pytest.approx(120 * 1.968)
    assert ceiling["pace"] == pytest.approx(184.6154, abs=1e-4)
    # Темп строки выше потолка: цена последнего метра там та же — r(потолок).
    assert plan["crew_share"] == pytest.approx(ceiling["crew_share"])
    # Экипаж из двух на кривой X: 2 × 168,66 × 1,572827 × 1,968 / маржа.
    margin_m = margin["margin_rub_per_m"]
    assert ceiling["crew_share"] == pytest.approx(2 * 168.66 * 1.572827209 * 1.968 / margin_m, rel=1e-6)
    assert ceiling["main_share"] == pytest.approx(168.66 * 1.968 / margin_m, rel=1e-6)
    # Зафиксировано первым прогоном: маржа 1 290,40 − 289,07 = 1 001,33 ₽/м.
    assert round(margin_m, 2) == 1001.33
    assert round(ceiling["crew_share"], 4) == 1.0427
    assert round(ceiling["main_share"], 4) == 0.3315
    assert [flag["code"] for flag in margin["flags"]] == ["MARGIN_SHARE_ABOVE_WARN"]
    assert "на потолке" in margin["flags"][0]["message"]
    # Флаг виден и в предупреждениях модели — ровно один раз.
    assert sum("на потолке" in warning for warning in economics.warnings) == 1


def test_share_under_threshold_gives_no_share_warning() -> None:
    """Рентабельность 100 %: маржа метра растёт, доля на потолке ниже порога — ни флага, ни предупреждения."""

    economics = _economics(_references(), target_margin_rate=D("1"))
    margin = economics.payroll["margin"]
    assert margin["status"] == "CHECKED"
    assert margin["ceiling"]["crew_share"] < margin["threshold"]
    assert margin["flags"] == []
    assert not any("маржи метра" in warning for warning in economics.warnings)


def test_time_pay_crew_share_not_applicable_warns_once() -> None:
    """Экипаж из повременщиков: доля в марже не применима — одно предупреждение."""

    references = _references(
        **F17_REFERENCES,
        positions=tuple(
            fx.item(item.code, item.name, {**item.payload, "pay_system": "TIME_BONUS"})
            if item.code in ("P_DRILLER", "P_ASSISTANT")
            else item
            for item in _references().sections["positions"]
        ),
    )
    economics = _economics(references)
    margin = economics.payroll["margin"]
    assert margin["status"] == "NOT_APPLICABLE"
    assert margin["plan"] is None and margin["ceiling"] is None
    assert sum("Доля в марже не проверена" in warning for warning in economics.warnings) == 1


def test_base_row_share_at_plan_is_below_ceiling() -> None:
    """Базовая строка (m_план = 120 — около нормы кривой): на плане доля ниже порога, флаг — по потолку."""

    economics = _economics(_references())
    margin = economics.payroll["margin"]
    assert margin["status"] == "CHECKED"
    assert margin["plan"]["pace"] == pytest.approx(120)
    assert margin["plan"]["crew_share"] < margin["ceiling"]["crew_share"]
    # Зафиксировано первым прогоном: метр бурения 458,93 ₽ (ориентир спеки), ФОТ
    # экипажа 256,93 ₽/м с постоянной частью, а не только 2 × 70,93.
    assert round(economics.payroll["price_rub_per_m"], 2) == 866.18
    assert round(margin["plan"]["crew_share"], 4) == 0.2998
    assert margin["plan"]["crew_share"] < margin["threshold"]
    assert round(margin["ceiling"]["crew_share"], 4) == 1.0065
    assert [flag["code"] for flag in margin["flags"]] == ["MARGIN_SHARE_ABOVE_WARN"]


def test_margin_not_positive_gives_null_and_warning() -> None:
    economics = _economics(target_margin_rate=D("-0.9"))
    margin = economics.payroll["margin"]

    assert margin["status"] == "NO_MARGIN"
    assert margin["margin_rub_per_m"] <= 0
    assert margin["plan"] is None and margin["ceiling"] is None
    assert margin["flags"] == []
    assert any("не положительна" in warning for warning in economics.warnings)


def test_subcontract_margin_check_is_none() -> None:
    economics = _economics(drilling_executor="SUBCONTRACTOR")
    assert economics.payroll is None
    assert economics.to_dict()["payroll"] is None

    context = ModelContext(
        _references(), fx.parameters(crew=CREW, payroll_source="PAYROLL", drilling_executor="SUBCONTRACTOR"),
        fx.physical(), as_of=AS_OF,
    )
    assert block_margin.margin(context, None, None, ()) is None


def test_rates_mode_payroll_block_is_none() -> None:
    economics = _economics(payroll_source="RATES")
    assert economics.payroll is None
    assert economics.to_dict()["payroll"] is None


def test_payroll_block_shape() -> None:
    payroll = _economics().to_dict()["payroll"]

    assert set(payroll) == {
        "pace",
        "normalized_meters",
        "effective_shifts",
        "positions",
        "main_position_code",
        "scale",
        "series",
        "price_rub_per_m",
        "variable_rub_per_m",
        "margin",
        "lineage",
    }
    assert payroll["pace"] == {
        "m_plan": pytest.approx(236.16),
        "k_hardness": pytest.approx(1.2),
        "k_diameter": pytest.approx(1.64),
        "diameter_mm": 250.0,
        "condition_code": "COND_F17",
    }
    assert payroll["effective_shifts"] == 13.0
    assert [row["position_code"] for row in payroll["positions"]] == ["P_DRILLER", "P_ASSISTANT"]
    driller = payroll["positions"][0]
    assert set(driller) == {"position_code", "position_name", "headcount", "c_var", "fixed_rub", "variable_rub", "amount_rub"}
    assert driller["c_var"] == pytest.approx(137.82, abs=0.01)
    assert driller["amount_rub"] == pytest.approx(driller["fixed_rub"] + driller["variable_rub"])
    assert set(payroll["margin"]) == {
        "status", "margin_rub_per_m", "plan", "ceiling", "threshold", "flags", "lineage",
    }
    assert {"price_rub_per_m", "variable_rub_per_m", "margin", "share"} <= set(payroll["margin"]["lineage"])
    assert {"normalized_meters", "effective_shifts", "planned_pace"} <= set(payroll["lineage"])


# --- Документирующий тест ----------------------------------------------------------


def test_documenting_price_includes_crew_payroll() -> None:
    """ФОТ экипажа входит и в цену, и в долю: доля растёт с ФОТ медленнее, чем при договорной цене.

    Цена метра строится по себестоимости с надбавками (§2.1), а не по договору:
    удвоенный экипаж удваивает стоимость последнего метра, но поднимает и цену,
    поэтому доля растёт меньше чем вдвое. При неизменной (договорной) цене та же
    стоимость удвоила бы долю ровно.
    """

    one, two = _economics(), _economics(crew_scale=D("2"))
    norms, drilling_m = _norms()
    # ФОТ экипажа — в цене: цена минус цена метра бурения без ФОТ — ФОТ с надбавками.
    crew_in_price = one.payroll["price_rub_per_m"] - float(norms.cost_rub_per_m * D("1.21"))
    assert crew_in_price == pytest.approx(float(_crew_rub(one) / drilling_m * D("1.21")), rel=1e-9)
    assert crew_in_price > 0

    share_one = one.payroll["margin"]["ceiling"]["crew_share"]
    share_two = two.payroll["margin"]["ceiling"]["crew_share"]
    assert share_one < share_two < 2 * share_one

    # Договорная цена — та же цена метра первого прогона, экипаж удвоен: доля × 2 ровно.
    context = ModelContext(
        _references(**F17_REFERENCES),
        fx.parameters(crew=CREW, payroll_source="PAYROLL", crew_scale=D("2")),
        fx.physical(),
        as_of=AS_OF,
    )
    norms_two = drilling.compute(context)
    result = block_payroll.compute(context, norms_two)
    contract = margin_check(
        main_scale=result.main_scale,
        crew=result.crew,
        pace=result.pace.pace,
        meters_factor=result.normalized_meters / context.value("drilling_m"),
        price=D(str(one.payroll["price_rub_per_m"])),
        variable=D(str(one.payroll["variable_rub_per_m"])),
        threshold=result.threshold,
    )
    assert float(contract.ceiling.crew_share) == pytest.approx(2 * share_one, rel=1e-9)


# --- Переменные бурения вне drilling.compute ------------------------------------


_EXTRA_RATE = D("15")
_EXTRA_RULE = fx.item(
    "RULE_DRILL_EXTRA",
    "Буровой раствор",
    {
        "operation_code": "PRODUCTION_DRILLING",
        "cost_item_code": "DRILL_FLUID",
        "behavior_type": "VARIABLE",
        "cost_layer": "variable",
        "driver": "drilling_m",
        "rate_rub": str(_EXTRA_RATE),
        "estimate_section": "DRILLING",
    },
)
_SERVICE_PER_SHIFT = D("1200")


def _with_extra(**kwargs):
    references = _references(**F17_REFERENCES, cost_rules=(*fx.COST_RULES, _EXTRA_RULE))
    return _economics(
        references,
        services=(
            ServiceCharge(
                "Геофизика скважин", _SERVICE_PER_SHIFT, layer="variable", operation_code="PRODUCTION_DRILLING", per_shift=True
            ),
        ),
        **kwargs,
    )


def test_variable_drilling_lines_outside_drilling_module_enter_price_once() -> None:
    """Правило затрат и услуга на бурении: цена растёт на X × 1,21, переменные — на X, маржа — на X × 0,21."""

    base, extra = _economics(), _with_extra()
    drilling_m = extra.natural.values["drilling_m"]
    codes = {line.cost_item_code for line in extra.lines if line.operation_code == "PRODUCTION_DRILLING"}
    assert "DRILL_FLUID" in codes
    service = [
        line for line in extra.lines if line.operation_code == "PRODUCTION_DRILLING" and line.layer is CostLayer.VARIABLE
        and line.cost_item_code not in {l.cost_item_code for l in base.lines}
    ]
    assert len(service) == 2, [line.cost_item_code for line in service]
    x = float(sum((line.amount_rub for line in service), D("0")) / drilling_m)
    rig_shifts = float(extra.natural.values["rig_shifts"])
    assert x == pytest.approx(float(_EXTRA_RATE) + float(_SERVICE_PER_SHIFT) * rig_shifts / float(drilling_m))

    b, e = base.payroll, extra.payroll
    assert e["price_rub_per_m"] - b["price_rub_per_m"] == pytest.approx(x * 1.21, rel=1e-9)
    assert e["variable_rub_per_m"] - b["variable_rub_per_m"] == pytest.approx(x, rel=1e-9)
    assert e["margin"]["margin_rub_per_m"] - b["margin"]["margin_rub_per_m"] == pytest.approx(x * 0.21, rel=1e-9)


def test_own_drilling_lines_found_by_identity_not_by_position() -> None:
    """Строки бурения узнаются по самим объектам `norms.lines`: порядок строк и чужая строка впереди цену не меняют."""

    context = ModelContext(
        _references(**F17_REFERENCES), fx.parameters(crew=CREW, payroll_source="PAYROLL"), fx.physical(), as_of=AS_OF
    )
    norms = drilling.compute(context)
    payroll = block_payroll.compute(context, norms)
    assert norms.lines and all(any(line is own for own in context.lines) for line in norms.lines)
    lines = list(context.lines)
    base = block_margin.margin(context, norms, payroll, lines)

    unrelated = replace(lines[-1], operation_code="BLAST_EXECUTION", cost_item_code="OTHER")
    moved = block_margin.margin(context, norms, payroll, [unrelated, *reversed(lines)])
    assert (moved.price, moved.variable) == (base.price, base.variable)

    # Копия своей строки — уже не строка `drilling.compute`: она входит в цену как добавка.
    own_variable = next(line for line in norms.lines if line.layer is CostLayer.VARIABLE)
    copy = replace(own_variable)
    extra = block_margin.margin(context, norms, payroll, [copy, *lines])
    drilling_m = context.value("drilling_m")
    assert extra.variable - base.variable == copy.amount_rub / drilling_m
    assert extra.price - base.price == copy.amount_rub / drilling_m * D("1.1") * D("1.1")


# --- Пороги методики из «Параметров ФОТ» -------------------------------------------


def _year_params(**fields):
    record = pfx.PAYROLL_SECTIONS["payroll_params"][0]
    return (fx.item(record.code, record.name, {**record.payload, **fields}),)


def test_write_off_and_pace_thresholds_do_not_touch_block_economics() -> None:
    """Флаги списаний и темпа — только в превью: экономика блока от их порогов не зависит."""

    base = _economics()
    loose = _economics(
        _references(
            **F17_REFERENCES,
            payroll_params=_year_params(write_off_flag_share="0.9", pace_flag_ratio="3"),
        )
    )
    assert loose.lines == base.lines
    assert loose.payroll == base.payroll
    assert loose.warnings == base.warnings


def test_margin_share_threshold_comes_from_the_year_record() -> None:
    economics = _economics(_references(**F17_REFERENCES, payroll_params=_year_params(margin_share_warn="1.2")))
    margin = economics.payroll["margin"]
    # Доля на потолке 104,27 % ниже порога 120 %: флага нет ни в блоке, ни в предупреждениях.
    assert round(margin["ceiling"]["crew_share"], 4) == 1.0427
    assert margin["threshold"] == pytest.approx(1.2)
    assert margin["flags"] == []
    assert not any("на потолке" in warning for warning in economics.warnings)


# --- Шкала и ряды графика (PR 3b) ---------------------------------------------


def test_payroll_block_has_scale_and_series_for_curve_scale() -> None:
    economics = _economics()
    payroll = economics.to_dict()["payroll"]
    scale = payroll["scale"]

    assert scale["scale_type"] == "CURVE_POWER"
    assert scale["norm_per_shift"] == pytest.approx(115.3846)
    assert scale["ceiling_per_shift"] == pytest.approx(184.6154)
    assert scale["rate_norm"] == pytest.approx(45)
    assert scale["rate_ceiling"] == pytest.approx(168.66)
    assert scale["gamma"] is not None

    series = payroll["series"]
    paces = [point["pace"] for point in series]
    assert paces == sorted(paces)
    assert len(series) >= 2
    for node in (scale["norm_per_shift"], scale["ceiling_per_shift"], payroll["pace"]["m_plan"]):
        assert any(pace == pytest.approx(node) for pace in paces)
    curve = pfx.CURVE_X
    for point in series:
        assert point["rate"] == pytest.approx(float(curve.rate_at(D(str(point["pace"])))), rel=1e-6)
        assert point["per_shift"] == pytest.approx(float(curve.per_shift(D(str(point["pace"])))), rel=1e-6)


def test_positions_carry_names_from_reference() -> None:
    references = _references(**F17_REFERENCES)
    names = {item.code: item.name for item in references.sections["positions"]}
    payroll = _economics(references).to_dict()["payroll"]

    for row in payroll["positions"]:
        assert row["position_name"] == names[row["position_code"]]
        assert row["position_name"] != row["position_code"]
    assert payroll["main_position_code"] in {row["position_code"] for row in payroll["positions"]}


def test_series_empty_when_main_has_no_scale() -> None:
    references = _references(
        **F17_REFERENCES,
        positions=tuple(
            fx.item(item.code, item.name, {**item.payload, "pay_system": "TIME_BONUS"})
            if item.code in ("P_DRILLER", "P_ASSISTANT")
            else item
            for item in _references().sections["positions"]
        ),
    )
    payroll = _economics(references).to_dict()["payroll"]
    assert payroll["scale"] is None
    assert payroll["series"] == []
    assert payroll["main_position_code"] is None


def test_drilling_operation_constant_is_shared() -> None:
    assert block_margin.DRILLING_OPERATION is drilling.DRILLING_OPERATION
