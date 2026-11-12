"""Контекст проекта МВ v2 на блоке 66 против эталона формы ВМ.09.03 v0.11 (TASK-018, PR 2).

Значения, не зависящие от разбивки на ряды (её в выгрузке SHOTPlus нет — см.
§10 плана PR 1), сверяются с формой; расхождения печатаются в отчёт теста и
не подгоняются: 196 скважин против 197, масса по декам против MROUND формы,
контур паспорта на бурение (вогнутая оболочка + 2 м) против маркшейдерского.
"""
from __future__ import annotations

import copy

import pytest

from design.mass_blast import build_document_context, block_from_design, content_sha256
from tests.mass_blast_block66 import context66, design66, payload66
from tests.test_safety_design import FORM, TECH

INPUTS = FORM["inputs"]


def _report(record_property, key: str, line: str) -> None:
    print(f"{key}: {line}")
    record_property(key, line)


@pytest.fixture(scope="module")
def context():
    return context66()


def _section(context, number: str) -> dict:
    return next(item for item in context["blocks_v2"][0]["technical_calculation"] if item["number"] == number)


def _item(section: dict, label_start: str) -> dict:
    return next(item for item in section["items"] if item.get("label", "").startswith(label_start))


def test_context_is_a_superset_of_v1(context):
    design = design66()
    block = block_from_design(design, code="66", horizon="410")
    v1 = build_document_context({**payload66(), "blocks": [block.to_dict()]}, [block])
    for key in v1:
        if key in ("document_context_version", "formula_version", "safety_plan"):
            continue
        assert context[key] == v1[key], key
    assert context["document_context_version"] == 2
    assert context["formula_version"] == "mass-blast-v2"
    assert context["safety_formula_version"] == "safety-v1"
    # Опасная зона в v2 — расчётная зона для людей, не ручной ввод.
    assert context["safety_plan"]["danger_zone_radius_m"] == context["zones"]["people"]["value"]


def test_section4_against_form(context, record_property):
    section = _section(context, "4")
    p = _item(section, "Вместимость 1 м")
    assert p["value"] == pytest.approx(FORM["p_kg_m"], abs=0.01)
    assert p["formula"] == "P = π·d²/4·Δ"
    assert "π·0,144²/4·1\u00a0120" in p["substitution"]
    typical = _item(section, "Заряд типовой скважины")
    # Форма: 18,24·(11,6 − 2,5) по 197 скважинам = 166; BlastEX — по 196.
    assert typical["value"] == pytest.approx(TECH["typical_charge_kg"], abs=2)
    assert _item(section, "Скважин").get("value") == "196 шт / 2\u00a0280,5 п. м"
    table = context["blocks_v2"][0]["parameter_table"]["totals"]
    _report(record_property, "typical_charge", f"BlastEX {typical['value']} кг, форма {TECH['typical_charge_kg']} кг")
    _report(
        record_property,
        "explosive_mass",
        f"по таблице (кратно 5 кг) {table['charge_kg']:.0f} кг на 196 скв.; форма {TECH['consumption'][0]['qty']} кг на 197 скв.",
    )
    # Масса по таблице кратно 5 кг совпадает с формой без скважины № 197 (§10 плана PR 1).
    assert table["charge_kg"] == pytest.approx(32675)


def test_q_deviation_and_justification(context, record_property):
    section = _section(context, "4")
    q = _item(section, "Удельный расход ВМ расчётный")
    _report(record_property, "q_calc", f"BlastEX {q['value']} кг/м³ (объём контура паспорта), форма {TECH['q_calc_kg_m3']}")
    codes = {issue["code"] for issue in context["issues"]}
    assert "q_deviation" in codes  # 1,27 против ТП 1,10
    assert "q_just_missing" not in codes  # обоснование задано в проекте
    assert any(item.get("text", "").startswith("Обоснование удельного расхода") for item in section["items"])


def test_safety_sections_against_form(context, record_property):
    airblast = _section(context, "14")
    assert _item(airblast, "Безопасное расстояние по остеклению")["value"] == TECH["r_v_accepted_m"]
    seismic = _section(context, "15")
    assert _item(seismic, "Сейсмически безопасное")["value"] == TECH["r_c_accepted_m"]
    flyrock = _section(context, "13")
    people = _item(flyrock, "Опасная зона для людей")["value"]
    _report(
        record_property,
        "people_zone",
        f"BlastEX {people:.0f} м (ряды SHOTPlus не заданы: a = 1,41 м), форма {TECH['people_zone_m']} м; "
        "по 197 строкам формы с правилом серии — 750 м (PR 1)",
    )
    assert people >= 750


def test_consumption_section_has_item_numbers(context):
    rows = _section(context, "10–12")["consumption"]
    assert [row["item"] for row in rows][:3] == ["10", "11", "12"]
    assert rows[0]["quantity"] == pytest.approx(32659.3, abs=0.5)


def test_parameter_table_rows(context):
    table = context["blocks_v2"][0]["parameter_table"]
    rows = table["rows"]
    assert len(rows) == 196
    assert all(row["charge_kg"] % 5 == 0 for row in rows)
    assert table["totals"]["charge_kg"] == sum(row["charge_kg"] for row in rows)
    assert table["totals"]["primers_pcs"] == 198
    assert all(row[key] is None for row in rows for key in ("depth_fact_m", "charge_fact_kg", "stemming_fact_m"))
    first = [row for row in rows if row["first_row"]]
    assert len(first) == 44 and all(row["lspp_m"] is not None for row in first)
    assert all(row["lspp_m"] is None for row in rows if not row["first_row"])
    assert {row["stemming_m"] for row in rows} == {2.5}
    assert table["charge_round_kg"] == 5


def test_schedule_times_and_zones(context):
    schedule = context["schedule"]
    times = {row["point"]: row["time"] for row in schedule["signals"]["rows"]}
    assert times == {"29.1": "12:00", "29.2": "", "29.3": "", "30": "13:00", "31": "13:15", "32": "", "33": "13:30"}
    points = {item["point"]: item for item in schedule["points"]}
    zones = context["zones"]
    assert points["12"]["value"] == f"{zones['people']['value']:.0f} / {zones['mechanisms']['value']:.0f} / 100 м"
    assert points["4"]["value"]["blast_day_until"] == "12:00"
    assert points["13"]["value"] == "отсутствуют"
    assert len(schedule["posts"]["rows"]) == 5
    assert len(schedule["familiarization"]["rows"]) == 9
    names = [row["name"] for row in schedule["familiarization"]["rows"] if row["name"]]
    assert len(names) == len(set(names))  # ФИО не повторяются


def test_schedule_prints_exit_route_and_siren():
    """«Куда удаляются люди» и «Средство подачи сигналов» — в строках ответственных пп. 21 и 27."""

    from design.mass_blast_schedule import build_schedule

    def duties(schedule_payload: dict) -> dict[str, str]:
        result, _ = build_schedule(
            project={"blast_date": "2026-11-20", "blast_time": "13:00"},
            schedule=schedule_payload,
            people={},
            zones={},
            objects=[],
            blocks=[],
            totals={},
            guard_posts=[],
            texts={},
        )
        return {row["points"]: row["duty"] for row in result["responsibilities"]["rows"]}

    filled = duties({"station": "у поста 1", "exit_route": "на гор. 420 м", "siren": "сирена СС-1"})
    assert filled["21"] == "Вывод людей из запретной и опасной зон — на гор. 420 м"
    assert filled["27"] == "Подача звуковых сигналов — сирена СС-1"
    empty = duties({"station": "у поста 1"})
    assert empty["21"] == "Вывод людей из запретной и опасной зон"
    assert empty["27"] == "Подача звуковых сигналов"


def test_timing_change_changes_groups_and_seismic():
    spaced = context66(design66(surface_ms=25.0))
    together = context66(design66(surface_ms=5.0))
    n_spaced = spaced["blocks_v2"][0]["safety"]["seismic"]["group_count"]
    n_together = together["blocks_v2"][0]["safety"]["seismic"]["group_count"]
    assert n_spaced == 196 and n_together < n_spaced
    r_spaced = spaced["blocks_v2"][0]["safety"]["seismic"]["calculated"]["value"]
    r_together = together["blocks_v2"][0]["safety"]["seismic"]["calculated"]["value"]
    assert r_together > r_spaced


def test_design_is_not_changed():
    """Расчёт v2 проект блока не меняет (снимок v1 `block_from_design` пишет моменты сети сам — он до копии)."""

    design = design66()
    block = block_from_design(design, code="66", horizon="410")
    before = copy.deepcopy(design.to_dict())
    context66(design, {**payload66(), "blocks": [block.to_dict()]})
    assert design.to_dict() == before


def test_context_is_reproducible():
    assert content_sha256(context66()) == content_sha256(context66())
