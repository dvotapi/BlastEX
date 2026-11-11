"""Проверки проекта МВ v2 (TASK-018, PR 2, §7 плана): каждый код на синтетическом блоке.

Блок — квадратная сетка 4 × 4 м, 3 ряда по 6 скважин, свободная
поверхность впереди первого ряда, сеть «каждая скважина через 25 мс».
"""
from __future__ import annotations

import pytest

from Blast import ExplosiveProperties
from design.charging import apply_charge_rules
from design.mass_blast import block_from_design
from design.mass_blast_context import BlockSource, ContextReferences, build_document_context_v2, validate_project_context_v2
from design.mass_blast_table import NOTE_REDUCE_CHARGE, parameter_table, round_to_step
from design.models import (
    BlastDesign,
    BlockContour,
    DownholeConnector,
    Hole,
    InitiationNetwork,
    Point3,
    Primer,
    Starter,
    SurfaceConnector,
)
from design.safety.holes import material_index
from tests.mass_blast_block66 import payload66

EXPLOSIVE = ExplosiveProperties("Порэмит", 1.12, 3.2)
PRIMER = "ПД 1000"
MATERIALS = [{"code": "PD", "name": PRIMER, "payload": {"nomenclature_role": "BOOSTER", "mass_kg": 1}}]
SAFETY = {"site_code": "ZHK", "relief_height_m": 0, "k_ground": 5, "k_structure": 2}


def grid_design(*, rows: int = 3, cols: int = 6, step: float = 4.0, bench: float = 10.0, front_gap: float = 3.0) -> BlastDesign:
    holes = []
    for r in range(rows):
        for c in range(cols):
            x, y = c * step, -r * step
            holes.append(
                Hole(
                    id=f"{c + 1}-{r + 1:02d}",
                    row=r + 1,
                    col=c,
                    collar=Point3(x, y, 100.0),
                    toe=Point3(x, y, 100.0 - bench - 1.0),
                    diameter_mm=144.0,
                    subdrill_m=1.0,
                )
            )
    width = (cols - 1) * step
    depth = (rows - 1) * step
    vertices = [(-2.0, front_gap), (width + 2.0, front_gap), (width + 2.0, -depth - 2.0), (-2.0, -depth - 2.0)]
    contour = BlockContour(vertices=[Point3(x, y, 100.0) for x, y in vertices], free_faces=[[0, 1]], name="Т1")
    loads = apply_charge_rules(holes, {"stemming_m": 3.0}, EXPLOSIVE)
    for load in loads:
        load.primer_items = [Primer(position_m=bench, product=PRIMER)]
        load.primers = [bench]
    ids = [hole.id for hole in holes]
    network = InitiationNetwork(
        system="nonel",
        starter_items=[Starter(id="st", hole_id=ids[0])],
        surface_connectors=[
            SurfaceConnector(id=f"s{i}", from_hole=a, to_hole=b, delay_ms=25.0, product="НСИ П-25")
            for i, (a, b) in enumerate(zip(ids, ids[1:]))
        ],
        downhole_connectors=[DownholeConnector(id=f"d{h}", hole_id=h, delay_ms=700.0, product="НСИ С-700") for h in ids],
    )
    design = BlastDesign(
        design_id="grid",
        name="Сетка",
        contour=contour,
        holes=holes,
        loads=loads,
        network=network,
        pattern_params={"pattern": "square", "spacing_a_m": step},
        explosive_key=EXPLOSIVE.name,
    )
    return design


def build(design: BlastDesign | None = None, *, site_safety=SAFETY, references: ContextReferences | None = None, **payload):
    design = design or grid_design()
    block = block_from_design(design, code="Т1", horizon="100")
    data = payload66(**payload)
    data["blocks"] = [{**block.to_dict(), "details": data.pop("details", {})}]
    source = BlockSource(design=design, site_safety=site_safety, rock={"hardness_f": 10}, materials=MATERIALS)
    context = build_document_context_v2(data, [block], [source], references or ContextReferences(has_situation_refs=True))
    return context, validate_project_context_v2(context)


def codes(issues, level: str | None = None) -> set[str]:
    return {issue.code for issue in issues if level is None or issue.level == level}


def test_grid_without_problems_is_releasable():
    context, issues = build()
    errors = [issue for issue in issues if issue.level == "error"]
    assert errors == [], errors
    table = context["blocks_v2"][0]["parameter_table"]
    assert table["totals"]["spacing_mean_m"] == pytest.approx(4.0)
    assert table["totals"]["burden_mean_m"] == pytest.approx(4.0)
    assert table["totals"]["first_row_count"] == 6


def test_volume_mismatch_when_contour_and_grid_differ():
    # Свободная поверхность в 12 м перед первым рядом: контур втрое больше сетки.
    _, issues = build(grid_design(front_gap=12.0))
    assert "volume_mismatch" in codes(issues, "warning")
    _, issues = build()
    assert "volume_mismatch" not in codes(issues)


def test_q_deviation_without_justification_blocks_release():
    _, issues = build(explosives={"q_tp_kg_m3": 0.3, "initiation": "НСИ"})
    assert "q_deviation" in codes(issues, "warning")
    assert "q_just_missing" in codes(issues, "error")


def test_q_tp_missing_is_a_warning():
    _, issues = build(explosives={"initiation": "НСИ"})
    assert "q_tp_missing" in codes(issues, "warning")


def test_object_in_zone_without_measures():
    objects = [{"source": "MANUAL", "name": "Бытовка", "kind": "people", "distance_m": 150}]
    context, issues = build(protected_objects=objects)
    assert context["protected_objects"][0]["position"] == "В ЗОНЕ"
    assert "object_in_zone_no_measures" in codes(issues, "error")
    objects[0]["measures"] = "вывод людей на время взрыва"
    context, issues = build(protected_objects=objects)
    assert "object_in_zone_no_measures" not in codes(issues)
    point14 = next(item for item in context["schedule"]["points"] if item["point"] == "14")
    assert point14["value"] == "Бытовка: вывод людей на время взрыва"


def test_sensitive_object_requires_experts():
    objects = [{"source": "MANUAL", "name": "Детский сад", "kind": "buildings", "distance_m": 20, "sensitive": True, "measures": "—"}]
    _, issues = build(protected_objects=objects)
    assert "expert_required" in codes(issues, "error")


def test_no_guard_posts_and_no_station():
    _, issues = build(guard_posts=[], schedule={"station": ""})
    assert {"guard_posts", "blast_station_missing"} <= codes(issues, "error")


def test_relief_unknown_without_reference_values():
    _, issues = build(site_safety={"site_code": "ZHK"})
    assert "relief_unknown" in codes(issues, "warning")


def test_manual_zone_below_calculated_is_an_error():
    context, _ = build()
    calculated = context["zones"]["people"]["value"]
    _, issues = build(safety_plan={"manual_zones": {"people": {"value": calculated - 50, "reason": "так решили"}}})
    assert "manual_below_calculated" in codes(issues, "error")
    context, issues = build(safety_plan={"manual_zones": {"people": {"value": calculated + 100, "reason": "ветер"}}})
    assert "manual_below_calculated" not in codes(issues)
    assert context["zones"]["people"]["value"] == calculated + 100
    assert context["zones"]["people"]["source"] == "MANUAL_OVERRIDE"


def test_missing_time_and_personnel():
    _, issues = build(blast_time="", personnel=[])
    assert "blast_time_missing" in codes(issues, "error")
    assert "personnel_missing" in codes(issues, "warning")


def test_signer_without_authority_warns():
    requisites = {"customer_approver": {"position": "начальник участка", "name": "Петров П. П.", "is_head": False}}
    _, issues = build(requisites=requisites)
    assert "signer_no_authority" in codes(issues, "warning")
    requisites["customer_approver"]["authority"] = "приказ № 12 от 01.10.2026"
    _, issues = build(requisites=requisites)
    assert "signer_no_authority" not in codes(issues)


def test_situation_missing_warning():
    _, issues = build(references=ContextReferences(has_situation_refs=False))
    assert "situation_missing" in codes(issues, "warning")


def test_reduce_charge_note_when_burden_short():
    """ЛСПП у подошвы < 0,8·W: авто-примечание «снизить заряд» (решение В4); ручное — к нему."""

    design = grid_design(front_gap=0.5)
    table = parameter_table(design, material_index(MATERIALS), hole_notes={"1-01": "проверить устье"})
    first = [row for row in table.rows if row["first_row"]]
    assert first and all(row["note"].startswith(NOTE_REDUCE_CHARGE) for row in first)
    # Общее для ≥ 60 % скважин не выносится: первый ряд — треть блока.
    assert table.common_note == ""
    assert next(row for row in table.rows if row["hole_id"] == "1-01")["note"] == "снизить заряд; проверить устье"


def test_common_note_goes_to_header():
    design = grid_design()
    notes = {hole.id: "забойка шламом" for hole in design.holes}
    table = parameter_table(design, material_index(MATERIALS), hole_notes=notes)
    assert table.common_note == "забойка шламом"
    assert all(row["note"] == "" for row in table.rows)


def test_charge_rounding_to_step():
    assert round_to_step(152.4, 5) == 150
    assert round_to_step(152.5, 5) == 155
    assert round_to_step(149.571, 5) == 150
    assert round_to_step(152.4, 10) == 150


def test_profile_rounding_step_is_used():
    context, _ = build(references=ContextReferences(has_situation_refs=True, profile={"charge_round_kg": 10}))
    rows = context["blocks_v2"][0]["parameter_table"]["rows"]
    assert all(row["charge_kg"] % 10 == 0 for row in rows)


def test_profile_texts_and_signals_replace_form_defaults():
    profile = {
        "signal_warning": "сирена 1 мин",
        "schedule_texts": [{"point": "16", "title": "", "value": "не менее 25 м"}, {"point": "3", "title": "Время взрыва"}],
    }
    context, _ = build(references=ContextReferences(has_situation_refs=True, profile=profile))
    points = {item["point"]: item for item in context["schedule"]["points"]}
    assert points["16"]["value"] == "не менее 25 м"
    assert points["3"]["title"] == "Время взрыва"
    assert points["3"]["value"] == "13:00"  # значение проекта текстом профиля не заменяется
    assert context["schedule"]["signals"]["rows"][0]["signal"] == "предупредительный: сирена 1 мин"


def test_multi_block_warning_and_project_zones():
    first, second = grid_design(), grid_design(step=3.0)
    blocks = [block_from_design(first, code="Т1", horizon="100"), block_from_design(second, code="Т2", horizon="100")]
    data = payload66()
    data["blocks"] = [block.to_dict() for block in blocks]
    sources = [BlockSource(design=d, site_safety=SAFETY, rock={"hardness_f": 10}, materials=MATERIALS) for d in (first, second)]
    context = build_document_context_v2(data, blocks, sources, ContextReferences(has_situation_refs=True))
    assert "multi_block_timing" in {issue["code"] for issue in context["issues"]}
    people = [block["safety"]["zones"]["people"]["value"] for block in context["blocks_v2"]]
    assert context["zones"]["people"]["value"] == max(people)
    assert len(context["blocks_v2"]) == 2


def test_manual_zone_that_is_not_an_object_is_an_issue():
    _, issues = build(safety_plan={"manual_zones": {"people": 800}})
    assert "manual_value_invalid" in codes(issues, "error")


def test_first_row_guess_is_reported():
    design = grid_design()
    design.contour.free_faces = []
    _, issues = build(design)
    assert "first_row_guessed" in codes(issues, "warning")


def test_uncharged_hole_has_no_stemming():
    design = grid_design()
    design.loads = [load for load in design.loads if load.hole_id != "1-01"]
    context, _ = build(design)
    table = context["blocks_v2"][0]["parameter_table"]
    row = next(item for item in table["rows"] if item["hole_id"] == "1-01")
    assert row["stemming_m"] is None and row["charge_kg"] == 0
    assert table["totals"]["stemming_min_m"] == 3.0


def test_inclined_hole_bench_height_is_vertical():
    design = grid_design()
    hole = design.holes[0]
    hole.toe = type(hole.toe)(hole.toe.x + 8.0, hole.toe.y, hole.toe.z)
    table = parameter_table(design, material_index(MATERIALS))
    row = next(item for item in table.rows if item["hole_id"] == hole.id)
    assert row["bench_height_m"] == pytest.approx(round(hole.bench_height_m, 1))
    assert row["bench_height_m"] < round(hole.length_m - hole.subdrill_m, 1)


def test_construction_charge_length_excludes_gaps():
    from design.models import Deck

    design = grid_design()
    for load in design.loads:
        load.decks = [
            Deck("stemming", 0.0, 3.0),
            Deck("bulk_explosive", 3.0, 6.0, mass_kg=50.0, product="Порэмит"),
            Deck("air", 6.0, 8.0),
            Deck("bulk_explosive", 8.0, 11.0, mass_kg=50.0, product="Порэмит"),
        ]
    context, _ = build(design)
    section = next(item for item in context["blocks_v2"][0]["technical_calculation"] if item["number"] == "7")
    assert section["constructions"][0]["charge_length_mean_m"] == 6.0
