"""Формулы безопасных расстояний (`design/safety/`, safety-v1) на эталоне блока 66.

Эталон — форма ВМ.09.03 v0.11, пересчитанная LibreOffice
(`tests/fixtures/mass_blast/block66_form_v0.11.json`, 197 строк таблицы
параметров). Где реализация по ФНП 494 расходится с формой (решения
владельца В1–В5), тест проверяет ФНП, а расхождение печатает в отчёт
(`print` + `record_property`).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from design.safety import SafetyValue, ceil_to
from design.safety.airblast import (
    AirblastCharge,
    airblast_glazing,
    airblast_groups,
    airblast_on_buildings,
    delay_factor,
    kz_lookup,
    qe_external,
    rv_glazing,
)
from design.safety.flyrock import flyrock_r, flyrock_series, relief_factor
from design.safety.holes import SafetyHole
from design.safety.objects import ProtectedObject, assess_objects
from design.safety.params import KN_EXTERNAL, KZ_BY_FREE, KZ_BY_STEMMING
from design.safety.seismic import Charge, delay_groups, seismic_r, seismic_safety
from design.safety.zones import apply_manual, danger_zones

FIXTURE = Path(__file__).parent / "fixtures" / "mass_blast" / "block66_form_v0.11.json"
FORM = json.loads(FIXTURE.read_text(encoding="utf-8"))
INPUTS = FORM["inputs"]
TECH = FORM["technical_calculation"]


def _report(record_property, key: str, ours: object, form: object, note: str) -> None:
    line = f"{key}: BlastEX {ours} / форма v0.11 {form} — {note}"
    print(line)
    record_property(key, line)


def _form_holes() -> list[SafetyHole]:
    """Строки таблицы параметров как скважины: колонка до забойки, забойка на всю свободную часть."""

    holes = []
    for row in FORM["holes"]:
        length = float(row["depth_m"])
        stemming = float(row["stemming_m"])
        holes.append(
            SafetyHole(
                hole_id=str(row["n"]),
                length_m=length,
                diameter_m=row["d_mm"] / 1000.0,
                stemming_m=stemming,
                charge_length_m=length - stemming,
                free_length_m=stemming,
                charge_kg=float(row["charge_kg_form"]),
                spacing_m=float(row["a_m"]),
                # У первого ряда в графе «между рядами» стоит ЛСПП — это не расстояние между рядами.
                row_step_m=None if row["lspp_m"] is not None else float(row["b_m"]),
                primer_count=int(row["primers_pcs"]),
                primer_kg=float(row["primer_kg"]),
            )
        )
    return holes


# --- Разлёт, пп. 784–786 -------------------------------------------------------


def test_fixture_has_all_197_rows() -> None:
    assert len(FORM["holes"]) == 197
    assert FORM["totals"]["charge_kg_form"] == 32830


@pytest.mark.parametrize("row", FORM["holes"], ids=lambda row: f"скв{row['n']}")
def test_flyrock_per_hole_matches_form_column(row: dict) -> None:
    """Формула (1) по скважине совпадает с графой «r_разл» формы (±1 м); a — графа «между скважинами»."""

    length = float(row["depth_m"])
    eta_charge = (length - float(row["stemming_m"])) / length
    assert eta_charge == pytest.approx(row["eta_z"], abs=0.0006)
    r = flyrock_r(eta_charge, 1.0, INPUTS["hardness_f"], row["d_mm"] / 1000.0, float(row["a_m"]))
    assert r == pytest.approx(row["flyrock_r_m"], abs=1.0)


def test_flyrock_series_follows_fnp_rule(record_property) -> None:
    """Серия (п. 784, В2): a = 2,10 м, η_з = 0,819 — 709 м → 750 м; механизмы — 500 м."""

    result = flyrock_series(_form_holes(), hardness_f=INPUTS["hardness_f"], relief_height_m=0.0, slope_angle_deg=0.0)
    assert result.distance_m == pytest.approx(2.10)
    assert result.eta_charge == pytest.approx(0.819, abs=0.0005)
    assert result.eta_stemming == pytest.approx(1.0)
    assert result.series.value == pytest.approx(709, abs=0.5)
    assert "п. 784" in result.series.basis
    zones = danger_zones(
        flyrock_m=result.with_relief.value,
        people_min_m=INPUTS["people_min_m"],
        on_slope=False,
        k_mech=INPUTS["k_mech"],
        seismic_m=100.0,
        airblast_m=50.0,
    )
    assert zones.people.value == 750
    assert zones.people_factor == "разлёт"
    assert zones.mechanisms.value == 500
    assert zones.mechanisms.basis.startswith("принято проектом")
    _report(
        record_property,
        "flyrock_people_zone",
        f"{result.series.value:.0f} → {zones.people.value:.0f} м (серия: a = 2,10, η_з = 0,819)",
        f"{TECH['flyrock_max_m']} → {TECH['people_zone_m']} м (максимум по скважинам)",
        "правило серии п. 784 вместо максимума по скважинам (решение В2)",
    )
    _report(
        record_property,
        "mechanisms_zone",
        f"{zones.mechanisms.value:.0f} м (0,667·750 = 500,25 → 500 → 500)",
        f"{TECH['mech_zone_m']} м (0,667·700)",
        "доля до целого метра, затем вверх до 50 м; строго вверх от 500,25 было бы 550",
    )


def test_relief_factor_formulas() -> None:
    slope, issues = relief_factor(700.0, relief_height_m=None, slope_angle_deg=20.0)
    assert slope.value == pytest.approx(1 + math.tan(math.radians(20)))
    assert "формула (3)" in slope.basis and not issues
    height, _ = relief_factor(700.0, relief_height_m=40.0, slope_angle_deg=None)
    assert height.value == pytest.approx(0.5 * (1 + math.sqrt(1 + 4 * 40 / 700)))
    assert "формула (4)" in height.basis
    low, issues = relief_factor(700.0, relief_height_m=30.0, slope_angle_deg=None)
    assert low.value == 1.0 and not issues
    unknown, issues = relief_factor(700.0, relief_height_m=None, slope_angle_deg=None)
    assert unknown.value == 1.0
    assert [issue.code for issue in issues] == ["relief_unknown"]


def test_people_zone_minimum_and_slope() -> None:
    zones = danger_zones(flyrock_m=120.0, people_min_m=200.0, on_slope=False, k_mech=0.667, seismic_m=0, airblast_m=0)
    assert zones.people.value == 200 and zones.people_factor == "прил. 21"
    slope = danger_zones(flyrock_m=120.0, people_min_m=200.0, on_slope=True, k_mech=0.667, seismic_m=0, airblast_m=0)
    assert slope.people.value == 300


def test_rounding_up_to_50() -> None:
    assert ceil_to(700.0) == 700
    assert ceil_to(700.0000000001) == 700
    assert ceil_to(700.4) == 750
    assert ceil_to(45.5) == 50
    assert ceil_to(0.0) == 0


# --- УВВ, пп. 803–807 ----------------------------------------------------------


def test_kz_tables_take_the_nearest_lower_point() -> None:
    assert kz_lookup(2.5 / 0.144, KZ_BY_STEMMING) == 0.003  # 17,4 → точка 15
    for ratio, k in KZ_BY_STEMMING:
        assert kz_lookup(ratio, KZ_BY_STEMMING) == k
    assert kz_lookup(4.99, KZ_BY_STEMMING) == 1.0
    assert kz_lookup(25.0, KZ_BY_STEMMING) == 0.002
    assert kz_lookup(10.0, KZ_BY_FREE) == 0.07
    assert kz_lookup(19.9, KZ_BY_FREE) == 0.02
    assert kz_lookup(1.0, KN_EXTERNAL) == 0.5
    assert qe_external(100.0, 3.5, 1.0, KN_EXTERNAL) == pytest.approx(10.0)


def test_rv_ranges_by_fnp() -> None:
    """(14) 65·∛Q_э² до 2 кг, (13) 65·√Q_э от 2 до 1000, (12) 200·∛Q_э от 1000 (В3)."""

    assert rv_glazing(2.0)[2] == "(14)"
    assert rv_glazing(2.0)[0] == pytest.approx(65 * 2 ** (2 / 3))
    assert rv_glazing(2.0001)[2] == "(13)"
    assert rv_glazing(999.9)[0] == pytest.approx(65 * math.sqrt(999.9))
    assert rv_glazing(1000.0)[2] == "(12)"
    assert rv_glazing(1000.0)[0] == pytest.approx(2000.0)


def _form_charges(step_ms: float) -> list[AirblastCharge]:
    p = FORM["p_kg_m"]
    return [
        AirblastCharge(
            hole_id=str(row["n"]),
            time_ms=index * step_ms,
            capacity_kg_m=p,
            charge_length_m=row["depth_m"] - row["stemming_m"],
            diameter_m=row["d_mm"] / 1000.0,
            kz=kz_lookup(row["stemming_m"] / (row["d_mm"] / 1000.0), KZ_BY_STEMMING),
        )
        for index, row in enumerate(FORM["holes"])
    ]


def test_airblast_on_form_numbers(record_property) -> None:
    """Скважины через 25 мс: N = 1, Q_э = 0,095 кг, поправки 1,5·1,5·1,5 = 3,375, r_в 46 → 50."""

    groups = airblast_groups(_form_charges(25.0), 10.0)
    assert len(groups) == 197
    result = airblast_glazing(groups, rock_group_ix=True, rock_group_v_reduce=False, frost=True)
    assert result.group is not None and len(result.group.charges) == TECH["uvv_n"] == 1
    assert result.kz.value == TECH["uvv_kz"] == 0.003
    assert result.qe.value == pytest.approx(TECH["q_e_kg"], abs=0.0005)
    assert "формула (17)" in result.qe.basis
    assert result.factors.value == pytest.approx(TECH["uvv_k_product"])
    assert result.calculated.value == pytest.approx(65 * 0.0946 ** (2 / 3) * 3.375, abs=0.1)
    assert round(result.calculated.value) == 46
    assert result.accepted.value == TECH["r_v_accepted_m"] == 50
    _report(
        record_property,
        "airblast_rv",
        f"{result.calculated.value:.1f} м (65·Q_э^(2/3)·3,375) → {result.accepted.value:.0f}",
        f"{TECH['r_v_m']} м (63·Q_э^(2/3)·3,375) → {TECH['r_v_accepted_m']}",
        "коэффициент формулы (14) по ФНП — 65, в форме 63 (решение В3)",
    )


def test_airblast_delay_factor_by_smallest_gap() -> None:
    def groups(*times: float):
        return airblast_groups(
            [AirblastCharge(str(i), t, 18.24, 8.0, 0.144, 0.003) for i, t in enumerate(times)], 10.0
        )

    assert delay_factor(groups(0, 60, 120)) == (1.0, 60)
    assert delay_factor(groups(0, 30, 90))[0] == 1.2
    assert delay_factor(groups(0, 20, 90))[0] == 1.5
    assert delay_factor(groups(0, 10, 90))[0] == 2.0
    assert delay_factor(groups(0, 5, 9))[0] == 1.0  # одна группа: моменты ближе 10 мс
    one = groups(0, 5, 9)
    assert len(one) == 1 and len(one[0].charges) == 3


def test_airblast_takes_the_group_with_largest_qe() -> None:
    charges = [AirblastCharge("a", 0, 18.24, 8.0, 0.144, 0.003)] + [
        AirblastCharge(f"b{i}", 100 + i, 18.24, 8.0, 0.144, 0.003) for i in range(3)
    ]
    result = airblast_glazing(airblast_groups(charges, 10.0), rock_group_ix=False, rock_group_v_reduce=False, frost=False)
    assert len(result.group.charges) == 3
    assert result.factors.value == 1.0  # интервал 100 мс — без поправки


def test_rock_group_v_reduces_by_half() -> None:
    groups = airblast_groups([AirblastCharge("a", 0, 18.24, 8.0, 0.144, 0.003)], 10.0)
    reduced = airblast_glazing(groups, rock_group_ix=False, rock_group_v_reduce=True, frost=False)
    assert reduced.factors.value == 0.5


def test_airblast_on_buildings_formulas() -> None:
    small = airblast_on_buildings(500.0, coefficient=10.0, formula="11")
    assert small.value == pytest.approx(10 * math.sqrt(500))
    assert "формула (11)" in small.basis
    large = airblast_on_buildings(20000.0, coefficient=60.0, formula="10", barrier_behind_blast=True)
    assert large.value == pytest.approx(60 * 20000 ** (1 / 3) * 1.3)
    with pytest.raises(ValueError):
        airblast_on_buildings(1.0, coefficient=1.0, formula="12")


# --- Сейсмика, пп. 792–795 -----------------------------------------------------


def test_seismic_formula_8_on_form_numbers() -> None:
    """Проверка формулы (8), не группировки: Q = 33 029 кг, N = 197 → 86 м."""

    r = seismic_r(TECH["seis_q_kg"], TECH["seis_n"], INPUTS["k_g"], INPUTS["k_s"], INPUTS["alpha"])
    assert round(r) == TECH["r_c_m"] == 86
    assert ceil_to(r) == TECH["r_c_accepted_m"] == 100
    assert TECH["seis_q_kg"] == FORM["totals"]["charge_kg_form"] + FORM["totals"]["primer_kg"]  # Q = ВВ + ПД (В4)


def test_seismic_groups_by_20_ms() -> None:
    spaced = [Charge(str(i), i * 25.0, 150.0) for i in range(10)]
    assert len(delay_groups(spaced, 20.0)) == 10
    exactly = [Charge(str(i), i * 20.0, 150.0) for i in range(10)]
    assert len(delay_groups(exactly, 20.0)) == 10  # интервал 20 мс — уже не одна группа
    chain = [Charge(str(i), i * 15.0, 150.0) for i in range(10)]
    assert len(delay_groups(chain, 20.0)) == 1  # цепочка по 15 мс — одна группа
    result = seismic_safety(delay_groups(chain, 20.0), k_ground=5, k_structure=2, alpha=1)
    assert result.chosen.n == 1
    assert "формула (5)" in result.calculated.basis
    assert result.calculated.value == pytest.approx(10 * 1500 ** (1 / 3))


def test_seismic_small_charges_rule_takes_the_larger_distance() -> None:
    """п. 794: заряды в 3 раза и более меньше можно не учитывать — считаем оба варианта, берём больший."""

    charges = [Charge("big", 0.0, 300.0)] + [Charge(f"s{i}", 25.0 * (i + 1), 90.0) for i in range(20)]
    result = seismic_safety(delay_groups(charges, 20.0), k_ground=5, k_structure=2, alpha=1)
    rules = {variant.rule: variant for variant in result.variants}
    assert rules["all"].n == 21 and rules["small_dropped"].n == 1
    assert rules["small_dropped"].q_kg == 300.0
    assert result.chosen.r_m == max(rules["all"].r_m, rules["small_dropped"].r_m)


def test_seismic_damaged_buildings_double() -> None:
    groups = delay_groups([Charge("1", 0.0, 1000.0)], 20.0)
    plain = seismic_safety(groups, k_ground=5, k_structure=2, alpha=1)
    damaged = seismic_safety(groups, k_ground=5, k_structure=2, alpha=1, buildings_damaged=True)
    assert damaged.calculated.value == pytest.approx(2 * plain.calculated.value)
    assert "п. 795" in damaged.calculated.basis


# --- Объекты и ручной ввод -----------------------------------------------------


def test_protected_objects_of_the_form() -> None:
    """Объекты формы: ЛЭП 420 м — В ЗОНЕ (сооружения — механизмы 500), промплощадка 650 м — вне зоны."""

    kinds = {"здания": "buildings", "сооружения": "structures"}
    objects = [ProtectedObject(item["name"], kinds[item["factor"]], item["distance_m"]) for item in FORM["protected_objects"]]
    rows, issues = assess_objects(objects, people_m=750, mechanisms_m=500, seismic_m=100, airblast_m=50)
    assert not issues
    expected = {item["name"]: (item["safe_m"], item["position"]) for item in FORM["protected_objects_result"]}
    for row in rows:
        assert (row.required_m, row.position) == expected[row.name]


def test_expert_required_for_a_sensitive_object_in_the_zone() -> None:
    near = ProtectedObject("Детский сад", "buildings", 80.0, sensitive=True)
    far = ProtectedObject("Больница", "buildings", 900.0, sensitive=True)
    _, issues = assess_objects([near, far], people_m=750, mechanisms_m=500, seismic_m=100, airblast_m=50)
    assert [(issue.level, issue.code) for issue in issues] == [("error", "expert_required")]


def test_manual_zone_must_have_a_reason_and_not_be_smaller() -> None:
    calculated = SafetyValue(750.0, "м", basis="ФНП 494 п. 786")
    value, issues = apply_manual("people", calculated, (700.0, "по распоряжению"))
    assert value.value == 750 and [issue.code for issue in issues] == ["manual_below_calculated"]
    value, issues = apply_manual("people", calculated, (800.0, ""))
    assert value.value == 750 and [issue.code for issue in issues] == ["manual_reason_missing"]
    value, issues = apply_manual("people", calculated, (800.0, "ЛЭП на границе зоны"))
    assert value.value == 800 and value.source == "MANUAL_OVERRIDE" and not issues


def test_manual_buildings_zone_drives_object_assessment() -> None:
    """Ручная зона для зданий больше расчётной — по ней и «В ЗОНЕ», и `expert_required`."""

    plant = ProtectedObject("Промплощадка", "buildings", 200.0)
    school = ProtectedObject("Школа", "buildings", 250.0, sensitive=True)
    rows, issues = assess_objects([plant, school], people_m=750, mechanisms_m=500, seismic_m=100, airblast_m=50, buildings_m=300)
    assert [(row.required_m, row.factor, row.position) for row in rows] == [
        (300, "принято проектом", "В ЗОНЕ"),
        (300, "принято проектом", "В ЗОНЕ"),
    ]
    assert [issue.code for issue in issues] == ["expert_required"]


def test_kz_label_names_the_free_column_table() -> None:
    charge = AirblastCharge("1", 0.0, 18.24, 8.0, 0.144, 0.02, kz_by_free=True)
    result = airblast_glazing(airblast_groups([charge], 10.0), rock_group_ix=False, rock_group_v_reduce=False, frost=False)
    assert "l_св/d" in result.kz.formula


def test_people_zone_never_below_200_m() -> None:
    """Пол прил. 21 действует, даже если параметр минимума пришёл меньше 200 м."""

    zones = danger_zones(flyrock_m=40.0, people_min_m=1.0, on_slope=False, k_mech=0.667, seismic_m=0, airblast_m=0)
    assert zones.people.value == 200
