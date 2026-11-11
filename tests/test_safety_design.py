"""`safety_for_design` на проекте блока 66 (TASK-018, PR 1).

Скважины — выгрузка SHOTPlus `tests/fixtures/drill_passport/block66_shotplus.xlsx`
(196 скважин: у № 197 формы нет координат — решение владельца В8),
диаметр 144 мм (долото 140 × 1,03), заряжание — `apply_charge_rules`
(Порэмит 1А 1120 кг/м³, забойка 2,5 м), ПД — по графе формы. Ряды — как в
тестах паспорта на бурение: первый ряд (перебур 1,5 м) и остальные.

Сеть — цепочка по номерам скважин через 25 мс, в скважине 700 мс: все
заряды разнесены не меньше 20 мс, поэтому N групп = числу скважин и r_с
совпадает с формой (§3.5 TASK-018). Масса ВВ BlastEX по декам с «формулой
формы» не сравнивается в утверждениях — только в отчёте теста.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from Blast import ExplosiveProperties
from design.charging import apply_charge_rules
from design.mass_blast import block_from_design
from design.models import (
    BlastDesign,
    DownholeConnector,
    Hole,
    InitiationNetwork,
    Point3,
    Primer,
    Starter,
    SurfaceConnector,
)
from design.safety.design import safety_for_design
from design.safety.params import safety_params

ROOT = Path(__file__).parent / "fixtures"
SHOTPLUS = ROOT / "drill_passport" / "block66_shotplus.xlsx"
FORM = json.loads((ROOT / "mass_blast" / "block66_form_v0.11.json").read_text(encoding="utf-8"))
TECH = FORM["technical_calculation"]
EXPLOSIVE = ExplosiveProperties("ЭВВ Порэмит 1А", 1.12, 3.2)
PRIMER = "ПД Сферит-ДП 1000 г"
MATERIALS = [
    {"code": "MAT_PD_1000", "name": PRIMER, "payload": {"nomenclature_role": "BOOSTER", "mass_kg": 1}},
]
# Коэффициенты формы v0.11 (лист «Реквизиты»), как запись справочника объекта.
SITE_SAFETY = {
    "site_code": "ZHK",
    "k_ground": FORM["inputs"]["k_g"],
    "k_structure": FORM["inputs"]["k_s"],
    "alpha_blast": FORM["inputs"]["alpha"],
    "people_min_m": FORM["inputs"]["people_min_m"],
    "k_mech": FORM["inputs"]["k_mech"],
    "rock_group_ix": FORM["inputs"]["rock_group_ix_or_higher"],
    "frost": FORM["inputs"]["frost"],
    "relief_height_m": 0,
}


def _report(record_property, key: str, line: str) -> None:
    print(f"{key}: {line}")
    record_property(key, line)


def _rows() -> list[tuple]:
    openpyxl = pytest.importorskip("openpyxl")
    sheet = openpyxl.load_workbook(SHOTPLUS, read_only=True).worksheets[0]
    return [
        row[:6]
        for row in sheet.iter_rows(values_only=True)
        if row and isinstance(row[0], (int, float)) and isinstance(row[4], (int, float))
    ]


def _network(hole_ids: list[str], *, surface_ms: float) -> InitiationNetwork:
    return InitiationNetwork(
        system="nonel",
        starter_items=[Starter(id="st-1", hole_id=hole_ids[0])],
        surface_connectors=[
            SurfaceConnector(id=f"sc-{a}", from_hole=a, to_hole=b, delay_ms=surface_ms, product="НСИ ИСКРА-П-25-5")
            for a, b in zip(hole_ids, hole_ids[1:])
        ],
        downhole_connectors=[
            DownholeConnector(id=f"dh-{h}", hole_id=h, delay_ms=700.0, product="НСИ ИСКРА-С-700-12") for h in hole_ids
        ],
    )


def block66_design(*, surface_ms: float = 25.0) -> BlastDesign:
    holes = [
        Hole(
            id=str(hole_id),
            row=0 if math.isclose(float(subdrill), 1.5) else 1,
            col=index,
            collar=Point3(float(x), float(y), float(z)),
            toe=Point3(float(x), float(y), float(z) - float(length)),
            diameter_mm=144.0,
            subdrill_m=float(subdrill),
        )
        for index, (hole_id, x, y, z, length, subdrill) in enumerate(_rows())
    ]
    loads = apply_charge_rules(holes, {"stemming_m": 2.5}, EXPLOSIVE)
    primers = {str(row["n"]): int(row["primers_pcs"]) for row in FORM["holes"]}
    by_id = {hole.id: hole for hole in holes}
    for load in loads:
        length = by_id[load.hole_id].length_m
        positions = [length - FORM["inputs"]["primer_from_bottom_m"], 2.5 + 1.0][: primers[load.hole_id]]
        load.primer_items = [Primer(position_m=pos, product=PRIMER) for pos in positions]
        load.primers = positions
    ids = [hole.id for hole in sorted(holes, key=lambda hole: int(hole.id))]
    return BlastDesign(
        design_id="block-66",
        name="Блок 66",
        holes=holes,
        loads=loads,
        network=_network(ids, surface_ms=surface_ms),
        rock_name="Габбро",
        explosive_key=EXPLOSIVE.name,
    )


@pytest.fixture(scope="module")
def design() -> BlastDesign:
    return block66_design()


@pytest.fixture(scope="module")
def params():
    return safety_params(SITE_SAFETY, {"hardness_f": FORM["inputs"]["hardness_f"]})


def test_196_holes_without_hole_197(design: BlastDesign) -> None:
    assert len(design.holes) == 196 == len(FORM["holes"]) - 1


def test_spaced_network_gives_one_group_per_hole(design, params, record_property) -> None:
    """Все заряды разнесены ≥ 20 мс: N = числу скважин, r_с совпадает с формой (§3.5 TASK-018)."""

    result = safety_for_design(design, params, materials=MATERIALS)
    seismic = result.seismic
    assert len(seismic.groups) == 196
    assert seismic.chosen.n == 196
    assert seismic.chosen.rule == "all"
    assert "формула (8)" in seismic.calculated.basis
    assert seismic.calculated.value == pytest.approx(TECH["r_c_m"], abs=1.0)
    assert seismic.accepted.value == TECH["r_c_accepted_m"] == 100
    _report(
        record_property,
        "seismic_block66",
        f"BlastEX Q = {seismic.chosen.q_kg:.0f} кг, N = {seismic.chosen.n}, r_с = {seismic.calculated.value:.1f} → "
        f"{seismic.accepted.value:.0f} м / форма Q = {TECH['seis_q_kg']} кг, N = {TECH['seis_n']}, r_с = "
        f"{TECH['r_c_m']} → {TECH['r_c_accepted_m']} м (196 скважин против 197 — В8; масса по декам)",
    )


def test_airblast_and_zones_on_block66(design, params, record_property) -> None:
    result = safety_for_design(design, params, materials=MATERIALS)
    airblast = result.airblast
    assert airblast.kz.value == 0.003
    assert len(airblast.group.charges) == 1
    assert airblast.factors.value == pytest.approx(3.375)  # 25 мс ×1,5, IX ×1,5, мороз ×1,5
    assert airblast.accepted.value == 50
    assert result.zones.buildings.value == 100 and result.zones.buildings_factor == "сейсмика"
    assert not result.errors
    _report(
        record_property,
        "zones_block66",
        f"BlastEX: разлёт {result.flyrock.series.value:.0f} м (a = {result.flyrock.distance_m:.2f}, "
        f"η_з = {result.flyrock.eta_charge:.3f}), люди {result.zones.people.value:.0f}, механизмы "
        f"{result.zones.mechanisms.value:.0f}, r_в {airblast.calculated.value:.1f} → {airblast.accepted.value:.0f} м / "
        f"форма: люди {TECH['people_zone_m']}, механизмы {TECH['mech_zone_m']}, r_в {TECH['r_v_m']} → "
        f"{TECH['r_v_accepted_m']} м",
    )


def test_timing_change_changes_groups_and_seismic_distance(params) -> None:
    """§7 TASK-018: изменение тайминга меняет число групп и r_с."""

    spaced = safety_for_design(block66_design(surface_ms=25.0), params, materials=MATERIALS)
    chained = safety_for_design(block66_design(surface_ms=15.0), params, materials=MATERIALS)
    simultaneous = safety_for_design(block66_design(surface_ms=0.0), params, materials=MATERIALS)
    assert len(spaced.seismic.groups) == 196
    assert len(chained.seismic.groups) == 1  # цепочка по 15 мс — одна группа
    assert len(simultaneous.seismic.groups) == 1
    assert "формула (5)" in simultaneous.seismic.calculated.basis
    assert chained.seismic.calculated.value > spaced.seismic.calculated.value
    # УВВ: по 15 мс — группы отдельные, поправка ×2; одновременно — одна группа на 196 зарядов.
    assert chained.airblast.factors.value == pytest.approx(2.0 * 1.5 * 1.5)
    assert len(simultaneous.airblast.group.charges) == 196
    assert simultaneous.airblast.accepted.value > spaced.airblast.accepted.value


def test_explosive_mass_by_decks_against_form_formula(design, params, record_property) -> None:
    """Масса ВВ: расчёт BlastEX по декам против «формулы формы» — только отчёт, без подгонки."""

    result = safety_for_design(design, params, materials=MATERIALS)
    form_total = FORM["totals"]["charge_kg_form"]
    form_196 = form_total - FORM["holes"][-1]["charge_kg_form"]
    _report(
        record_property,
        "explosive_mass",
        f"BlastEX по декам {result.explosive_kg:.1f} кг (196 скв., P·l_зар без округления) / форма {form_total} кг "
        f"(197 скв., MROUND((L − l_заб)·P; 5)); без № 197 — {form_196} кг; разница {result.explosive_kg - form_196:+.1f} кг",
    )
    assert result.explosive_kg > 0
    assert result.primer_kg == sum(row["primer_kg"] for row in FORM["holes"][:196])


def test_design_is_not_changed(params) -> None:
    """Расчёт только читает проект: сеть разрешается на копии, снимок v1 и хэш прежние."""

    design = block66_design()
    before = copy.deepcopy(design.to_dict())
    block_before = block_from_design(copy.deepcopy(design))
    safety_for_design(design, params, materials=MATERIALS)
    assert design.to_dict() == before
    assert block_from_design(copy.deepcopy(design)).design_sha256 == block_before.design_sha256


def test_untimed_holes_form_one_group_with_warning(params) -> None:
    design = block66_design()
    design.network.surface_connectors = design.network.surface_connectors[:100]
    result = safety_for_design(design, params, materials=MATERIALS)
    codes = {issue.code for issue in result.issues}
    assert "delay_groups_unknown" in codes
    untimed = [group for group in result.seismic.groups if group.start_ms is None]
    assert len(untimed) == 1 and len(untimed[0].charges) == 95
    assert result.airblast.factors.value == pytest.approx(2.0 * 1.5 * 1.5)  # интервал неизвестен — ×2


def test_missing_reference_and_hardness_fall_back_to_form(design) -> None:
    params = safety_params(None, None)
    codes = {issue.code for issue in params.issues}
    assert codes == {"safety_reference_missing", "hardness_unknown"}
    assert params.hardness_f == 14 and params.rock_group_ix and params.frost
    result = safety_for_design(design, params, materials=MATERIALS)
    assert {"safety_reference_missing", "hardness_unknown"} <= {issue.code for issue in result.issues}


def test_stemming_between_decks_is_not_top_stemming(params) -> None:
    """l_заб — только над верхним зарядом: промежуточная забойка K_з не уменьшает."""

    from design.models import Deck, HoleLoad
    from design.safety.holes import material_index, safety_holes

    design = block66_design()
    hole = design.holes[0]
    length = hole.length_m
    design.loads = [
        HoleLoad(
            hole_id=hole.id,
            decks=[
                Deck("stemming", 0.0, 2.5),
                Deck("charge", 2.5, 5.0, explosive_key=EXPLOSIVE.name, mass_kg=45.0),
                Deck("stemming", 5.0, 6.5),
                Deck("charge", 6.5, length, explosive_key=EXPLOSIVE.name, mass_kg=75.0),
            ],
        )
    ]
    holes, _, _ = safety_holes(design, material_index(None))
    assert holes[0].stemming_m == pytest.approx(2.5)
    result = safety_for_design(design, params, materials=MATERIALS)
    assert result.airblast.kz.value == 0.003  # 2,5/0,144 = 17,4, а не 4,0/0,144 = 27,8 → 0,002


def test_invalid_manual_values_fall_back_with_a_warning() -> None:
    params = safety_params(SITE_SAFETY, {"hardness_f": 14}, overrides={"hardness_f": "abc", "k_ground": 0, "frost": False})
    assert params.hardness_f == 14 and params.source("hardness_f") == "REFERENCE"
    assert params.k_ground == 5 and params.frost is False
    warnings = [issue for issue in params.issues if issue.code == "manual_value_invalid"]
    assert len(warnings) == 2
    assert all("hardness_f" not in issue.message and "k_ground" not in issue.message for issue in warnings)
