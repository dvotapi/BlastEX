"""Факт блока для документов проекта МВ (TASK-018, PR 5, §2 плана): графы Ф, итоги, расход, Г.1."""
from __future__ import annotations

import copy
import math

import pytest

from design.as_charged import as_charged_from_design_load
from design.as_drilled import as_drilled_from_design_hole
from design.lifecycle import designed_payload, execution_payload
from design.mass_blast_fact import block_fact, execution_sha256, fact_subdrill_m
from design.models import AsDrilledHole, DataProvenance, Point3
from tests.mass_blast_block66 import context66, design66
from tests.test_safety_design import MATERIALS

FACT_KEYS = ("depth", "subdrill", "lspp", "spacing", "burden", "stemming")


@pytest.fixture(scope="module")
def base():
    design = design66()
    table = context66(design)["blocks_v2"][0]["parameter_table"]
    return design, table


def _with_copies(design, *, drill=True, charge=True):
    design = copy.deepcopy(design)
    if drill:
        design.as_drilled_holes = [as_drilled_from_design_hole(hole) for hole in design.holes if hole.enabled]
    if charge:
        design.as_charged_holes = [as_charged_from_design_load(load) for load in design.loads]
    return design


def test_fact_equal_to_project_gives_equal_columns(base):
    design, table = base
    fact, issues = block_fact(_with_copies(design), table, MATERIALS)
    assert len(fact["rows"]) == len(table["rows"])
    for row in fact["rows"]:
        for key in FACT_KEYS:
            assert row[f"{key}_fact_m"] == row[f"{key}_m"], (row["hole_id"], key)
        assert row["charge_fact_exact_kg"] == pytest.approx(row["charge_exact_kg"], abs=0.01)
    totals = fact["totals"]
    assert totals["drilled_count"] == totals["charged_count"] == len(table["rows"])
    assert totals["depth_fact_m"] == pytest.approx(table["totals"]["depth_m"], abs=0.2)
    # Масса Ф — до 1 кг (В3), Р — кратно 5 кг: итоги близки, но не равны.
    assert totals["charge_fact_kg"] == pytest.approx(table["totals"]["charge_kg"], abs=len(table["rows"]) * 2.5)
    assert [item["code"] for item in issues] == ["fact_copied_from_design"]


def test_project_block_is_not_changed(base):
    design, table = base
    design = _with_copies(design)
    before = (designed_payload(design), execution_payload(design))
    block_fact(design, table, MATERIALS)
    assert (designed_payload(design), execution_payload(design)) == before


def test_moved_hole_changes_its_columns_and_neighbours(base):
    design, table = base
    design = _with_copies(design, charge=False)
    first = next(row for row in table["rows"] if row["first_row"])
    target = first["hole_id"]
    item = next(item for item in design.as_drilled_holes if item.design_hole_id == target)
    item.actual_collar = Point3(item.actual_collar.x + 1.0, item.actual_collar.y, item.actual_collar.z)
    item.actual_toe = Point3(item.actual_toe.x + 1.0, item.actual_toe.y, item.actual_toe.z - 0.6)
    item.actual_depth = 0.0
    item.provenance = DataProvenance(source="survey", method="gnss")
    fact, issues = block_fact(design, table, MATERIALS)
    rows = {row["hole_id"]: row for row in fact["rows"]}
    row = rows[target]
    assert row["depth_fact_m"] == pytest.approx(row["depth_m"] + 0.6, abs=0.06)
    assert row["subdrill_fact_m"] == pytest.approx(row["subdrill_m"] + 0.6, abs=0.06)
    assert row["spacing_fact_m"] != row["spacing_m"] or row["lspp_fact_m"] != row["lspp_m"]
    # Без факта заряжания масса и забойка Ф пустые, итог Ф массы — тоже.
    assert row["charge_fact_kg"] is None and fact["totals"]["charge_fact_kg"] is None
    assert "fact_charging_missing" in {issue["code"] for issue in issues}
    point = next(hole for hole in fact["holes"] if hole["hole_id"] == target)
    assert point["surveyed"] and point["offset_m"] == pytest.approx(1.0, abs=0.01)


def test_subdrill_formula_with_shorter_hole(base):
    design, _table = base
    hole = next(hole for hole in design.holes if hole.enabled)
    drilled = as_drilled_from_design_hole(hole)
    drilled.actual_toe = Point3(drilled.actual_toe.x, drilled.actual_toe.y, drilled.actual_toe.z + hole.subdrill_m + 0.4)
    drilled.actual_depth = 0.0
    # Забой выше проектной подошвы на 0,4 м — недобур, перебур отрицательный.
    assert fact_subdrill_m(hole, drilled) == pytest.approx(-0.4, abs=1e-6)


def test_depth_only_record_follows_design_axis(base):
    design, table = base
    design = copy.deepcopy(design)
    hole = next(hole for hole in design.holes if hole.enabled)
    design.as_drilled_holes = [
        AsDrilledHole(design_hole_id=hole.id, actual_collar=hole.collar, actual_toe=hole.collar,
                      actual_depth=hole.length_m - 1.0, actual_diameter=hole.diameter_mm)
    ]
    fact, issues = block_fact(design, table, MATERIALS)
    row = next(row for row in fact["rows"] if row["hole_id"] == hole.id)
    assert row["depth_fact_m"] == pytest.approx(round(hole.length_m - 1.0, 1))
    assert row["subdrill_fact_m"] == pytest.approx(round(hole.subdrill_m - 1.0, 1), abs=0.11)
    # Частичный факт: итог Ф глубины не печатается, остальные скважины — без Ф.
    assert fact["totals"]["depth_fact_m"] is None
    other = next(row for row in fact["rows"] if row["hole_id"] != hole.id)
    assert other["depth_fact_m"] is None and not other["drilled"]
    assert "fact_drilling_missing" in {issue["code"] for issue in issues}


def test_charge_fact_mass_and_consumption(base):
    design, table = base
    design = _with_copies(design, drill=False)
    for item in design.as_charged_holes:
        item.charge_mass_kg = round(item.charge_mass_kg + 3.4, 3)
    fact, _issues = block_fact(design, table, MATERIALS)
    row = fact["rows"][0]
    assert row["charge_fact_kg"] == round(row["charge_fact_exact_kg"])
    explosive = next(line for line in fact["consumption"] if line["kind"] == "explosive")
    assert explosive["quantity"] == pytest.approx(fact["totals"]["charge_fact_partial_kg"], abs=0.01)
    # Поверхностных и стартеров в факте нет — их вводят в наряде вручную (В9).
    assert {line["kind"] for line in fact["consumption"]} <= {"explosive", "primer", "nsi_downhole", "detonator_electronic"}


def test_execution_hash_changes_with_fact(base):
    design, _table = base
    plain = copy.deepcopy(design)
    with_fact = _with_copies(design, charge=False)
    assert execution_sha256(plain) != execution_sha256(with_fact)
    assert plain.designed_sha256 == with_fact.designed_sha256 or not plain.designed_sha256


def test_g1_points_use_fact_collars(base):
    design, table = base
    design = _with_copies(design, charge=False)
    design.as_drilled_holes = design.as_drilled_holes[1:]
    fact, _issues = block_fact(design, table, MATERIALS)
    surveyed = [point for point in fact["holes"] if point["surveyed"]]
    assert len(surveyed) == len(fact["holes"]) - 1
    missing = next(point for point in fact["holes"] if not point["surveyed"])
    assert missing["offset_m"] is None
    assert all(math.isfinite(point["x"]) for point in fact["holes"])


def test_depth_edited_after_copy_moves_the_toe_along_the_axis(base):
    """Копия проекта, затем правка глубины: забой — на записанной длине, перебур и подошва согласованы."""

    design, table = base
    design = _with_copies(design, charge=False)
    item = design.as_drilled_holes[0]
    hole = next(h for h in design.holes if h.id == item.design_hole_id)
    item.actual_depth = hole.length_m - 0.5
    fact, _issues = block_fact(design, table, MATERIALS)
    row = next(row for row in fact["rows"] if row["hole_id"] == hole.id)
    assert row["depth_fact_m"] == pytest.approx(round(hole.length_m - 0.5, 1))
    assert row["subdrill_fact_m"] == pytest.approx(round(hole.subdrill_m - 0.5, 1), abs=0.11)
    assert fact_subdrill_m(hole, item) == pytest.approx(hole.subdrill_m - 0.5, abs=1e-6)


def test_record_mass_with_massless_decks_is_consumed(base):
    design, table = base
    design = _with_copies(design, drill=False)
    for item in design.as_charged_holes:
        for deck in item.decks:
            deck.mass_kg = 0.0
        item.charge_mass_kg = 100.0
    fact, _issues = block_fact(design, table, MATERIALS)
    explosive = next(line for line in fact["consumption"] if line["kind"] == "explosive")
    assert explosive["quantity"] == pytest.approx(100.0 * len(design.as_charged_holes))


def test_fired_detonator_replaces_the_planned_one(base):
    from design.as_fired import as_fired_from_design_hole

    design, table = base
    design = _with_copies(design, drill=False)
    hole = next(h for h in design.holes if h.enabled)
    fired = as_fired_from_design_hole(design, hole)
    fired.detonator.product = "Электронный ДЭ-1"
    fired.detonator.kind = "electronic"
    design.as_fired_holes = [fired]
    fact, _issues = block_fact(design, table, MATERIALS)
    kinds = {line["kind"]: line for line in fact["consumption"]}
    assert kinds["detonator_electronic"]["quantity"] >= 1
    assert kinds["nsi_downhole"]["quantity"] == 198 - kinds["detonator_electronic"]["quantity"]


def test_fact_mass_total_is_the_exact_sum(base):
    design, table = base
    design = _with_copies(design, drill=False)
    for item in design.as_charged_holes:
        item.charge_mass_kg = 100.49
    fact, _issues = block_fact(design, table, MATERIALS)
    assert fact["rows"][0]["charge_fact_kg"] == 100
    assert fact["totals"]["charge_fact_kg"] == pytest.approx(100.49 * len(design.as_charged_holes))


def test_edited_product_and_stemming_of_a_copied_charge(base):
    design, table = base
    design = _with_copies(design, drill=False)
    item = design.as_charged_holes[0]
    item.explosive_product = "ACTUAL_NEW_PRODUCT"
    item.stemming_length_m = 4.2
    fact, _issues = block_fact(design, table, MATERIALS)
    row = next(row for row in fact["rows"] if row["hole_id"] == item.design_hole_id)
    assert row["stemming_fact_m"] == 4.2
    names = {line["name"]: line["quantity"] for line in fact["consumption"] if line["kind"] == "explosive"}
    assert names["ACTUAL_NEW_PRODUCT"] == pytest.approx(item.charge_mass_kg)


def test_surveyed_curved_toe_is_kept():
    from design.mass_blast_fact import _actual_toe
    from design.models import Hole, SurveyPoint

    hole = Hole(id="1", row=0, col=0, collar=Point3(0, 0, 100), toe=Point3(0, 0, 90), diameter_mm=144)
    drilled = AsDrilledHole(design_hole_id="1", actual_collar=Point3(0, 0, 100), actual_toe=Point3(3, 0, 92),
                            actual_depth=9.243, survey_points=[SurveyPoint(depth_m=9.243, x=3, y=0, z=92)])
    toe = _actual_toe(hole, drilled)
    assert (toe.x, toe.y, toe.z) == (3, 0, 92)


def test_primer_scoped_fired_detonator_replaces_only_its_primer(base):
    from design.as_fired import as_fired_from_design_hole
    from design.mass_blast_fact import _overlay_fired_detonators
    from design.models import Detonator

    design, _table = base
    design = copy.deepcopy(design)
    hole = next(h for h in design.holes if h.enabled)
    design.network.detonators = [d for d in design.network.detonators if d.hole_id != hole.id] + [
        Detonator(id="a", hole_id=hole.id, product="A", kind="electronic", primer_index=0),
        Detonator(id="b", hole_id=hole.id, product="B", kind="electronic", primer_index=1),
    ]
    fired = as_fired_from_design_hole(design, hole)
    fired.detonator = Detonator(id="a", hole_id=hole.id, product="A2", kind="electronic", primer_index=0)
    design.as_fired_holes = [fired]
    _overlay_fired_detonators(design, {hole.id: hole})
    products = {d.product for d in design.network.detonators if d.hole_id == hole.id}
    connectors = [(c.product, c.primer_index) for c in design.network.downhole_connectors if c.hole_id == hole.id]
    assert "B" in products and "A" not in products and ("A2", 0) in connectors
