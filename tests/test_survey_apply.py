"""Применение съёмки к проекту блока (TASK-014, PR 5а): устья, длины, вода, заряды, факт."""
from __future__ import annotations

import copy
import math

import pytest

from Blast import ExplosiveProperties
from design.charging import apply_charge_rules
from design.geometry import hole_from_collar, layout_axes
from design.lifecycle import classify_mutations, designed_payload, designed_sha256, execution_payload
from design.models import BlastDesign, Hole, ManualOffset, Point3, WaterInterval
from design.survey.apply import ChargeInputs, SurveyApplication, apply_survey, moved_offset
from design.survey.evaluate import VERDICT_CODES, SurveyTolerances, evaluate_survey
from design.survey.match import SurveyMatch
from design.survey.read import SurveyedPoint
from tests.front_rows_fixtures import GAP_PATTERN, design_with, grid_rows

EXPLOSIVE = ExplosiveProperties(name="Э-100", density_t_m3=1.2, power_mj_kg=3.8)
RULES = {"stemming_m": 3.0}
CHARGE = ChargeInputs(rules=RULES, explosive=EXPLOSIVE, explosives=[])
NOW = "2026-11-14T10:00:00Z"


def _design(*, loads: bool = False, tilt_deg: float = 0.0) -> BlastDesign:
    design = design_with(grid_rows(row_one_tilt_deg=tilt_deg), GAP_PATTERN)
    if loads:
        design.loads = apply_charge_rules(design.holes, RULES, EXPLOSIVE, contour=design.contour)
    return design


def _hole(design, hole_id: str) -> Hole:
    return next(hole for hole in design.holes if hole.id == hole_id)


def _point(hole: Hole, **changes) -> SurveyedPoint:
    dx, dy, dz, dl = (changes.pop(key, 0.0) for key in ("dx", "dy", "dz", "dl"))
    values = {
        "name": hole.id, "x": hole.collar.x + dx, "y": hole.collar.y + dy, "z": hole.collar.z + dz,
        "depth_m": hole.length_m + dl,
    }
    values.update(changes)
    return SurveyedPoint(**values)


def _matches(design, changed=None, only=None) -> list[SurveyMatch]:
    changed = changed or {}
    return [
        SurveyMatch(hole.id, changed.get(hole.id) or _point(hole), "name")
        for hole in design.holes
        if only is None or hole.id in only
    ]


def _apply(design, matches, charge=CHARGE):
    verdicts = evaluate_survey(design, matches, SurveyTolerances())
    return apply_survey(
        design, matches, verdicts, file_name="s66.csv", file_sha256="ab" * 32,
        survey_date="2026-11-13", actor="mark@mine", charge=charge, now=NOW,
    )


def _applied(design: BlastDesign, result) -> BlastDesign:
    """Проект после «Применить»: как его соберёт фронт (`APPLY_SURVEY`)."""

    out = copy.deepcopy(design)
    out.holes = result.holes
    if result.loads is not None:
        out.loads = result.loads
    out.as_drilled_holes = result.as_drilled_holes
    out.survey_applications = [*out.survey_applications, result.application]
    return out


def _by_id(holes) -> dict[str, Hole]:
    return {hole.id: hole for hole in holes}


def test_unchanged_survey_keeps_designed_sha256():
    design = _design(loads=True, tilt_deg=15.0)
    before = designed_sha256(design)
    result = _apply(design, _matches(design))
    assert result.changed_ids == []
    applied = _applied(design, result)
    assert designed_sha256(applied) == before
    assert [hole.to_dict() for hole in result.holes] == [hole.to_dict() for hole in design.holes]
    assert [load.to_dict() for load in result.loads] == [load.to_dict() for load in design.loads]
    assert sorted(item.design_hole_id for item in result.as_drilled_holes) == sorted(h.id for h in design.holes)


def test_moved_grid_hole_gets_manual_xy_and_offset():
    design = _design()
    hole = _hole(design, "2-03")
    result = _apply(design, _matches(design, {"2-03": _point(hole, dx=0.3, dy=0.4)}))
    assert result.changed_ids == ["2-03"]
    moved = _by_id(result.holes)["2-03"]
    assert "xy" in moved.manual
    assert moved.source == "generated"
    assert (moved.collar.x, moved.collar.y) == pytest.approx((hole.collar.x + 0.3, hole.collar.y + 0.4))
    # Ряд — по азимуту 90° (вдоль x), «поперёк» — к откосу y = 0: +0,4 по y — от откоса.
    along, across = layout_axes(design.contour, 90.0)
    assert along == pytest.approx((1.0, 0.0)) and across == pytest.approx((0.0, -1.0))
    assert moved.manual_offset == ManualOffset(hole.collar.x, hole.collar.y, 0.3, -0.4)


def test_already_moved_hole_keeps_original_node():
    design = _design()
    hole = _hole(design, "3-02")
    node = (hole.collar.x - 0.2, hole.collar.y)
    hole.manual = ["xy"]
    hole.manual_offset = ManualOffset(node[0], node[1], 0.2, 0.0)
    result = _apply(design, _matches(design, {"3-02": _point(hole, dx=0.1)}))
    moved = _by_id(result.holes)["3-02"]
    assert moved.manual.count("xy") == 1
    assert moved.manual_offset.node_x == pytest.approx(node[0])
    assert moved.manual_offset.node_y == pytest.approx(node[1])
    assert moved.manual_offset.along == pytest.approx(0.3)
    assert moved.manual_offset.across == pytest.approx(0.0)


def test_moved_offset_back_to_node_and_rounding():
    before = Hole(
        id="1", row=0, col=0, collar=Point3(10.0, 2.0, 0.0), toe=Point3(10.0, 2.0, -11.0), diameter_mm=215.0,
        manual=["xy"], manual_offset=ManualOffset(9.0, 2.0, 1.0, 0.0),
    )
    axes = ((1.0, 0.0), (0.0, -1.0))
    assert moved_offset(before, 9.0003, 2.0002, *axes) is None
    offset = moved_offset(before, 9.12345678, 1.9, *axes)
    assert offset == ManualOffset(9.0, 2.0, 0.123457, 0.1)


def test_manual_hole_moves_without_marker():
    design = _design()
    hole = _hole(design, "3-04")
    hole.source = "manual"
    result = _apply(design, _matches(design, {"3-04": _point(hole, dx=0.5)}))
    moved = _by_id(result.holes)["3-04"]
    assert moved.collar.x == pytest.approx(hole.collar.x + 0.5)
    assert "xy" not in moved.manual
    assert moved.manual_offset is None


def test_depth_sets_manual_length_and_collar_z():
    design = _design(tilt_deg=15.0)
    hole = _hole(design, "1-02")
    point = _point(hole, dz=0.2, dl=-0.6, dx=0.1)
    result = _apply(design, _matches(design, {"1-02": point}))
    moved = _by_id(result.holes)["1-02"]
    assert moved.length_m == pytest.approx(point.depth_m)
    assert moved.collar == Point3(point.x, point.y, point.z)
    expected_toe = hole_from_collar(moved.collar, point.depth_m, hole.angle_deg, hole.azimuth_deg)
    assert (moved.toe.x, moved.toe.y, moved.toe.z) == pytest.approx((expected_toe.x, expected_toe.y, expected_toe.z))
    assert "collar_z" in moved.manual and "length" in moved.manual
    # Подошва — проектная: перебур — длина за ней по оси.
    floor_z = hole.collar.z - hole.bench_height_m
    assert moved.collar.z - moved.bench_height_m == pytest.approx(floor_z)


def test_no_depth_keeps_design_length_moves_collar_only():
    design = _design()
    hole = _hole(design, "2-02")
    point = _point(hole, dx=0.4, depth_m=None, z=None)
    result = _apply(design, _matches(design, {"2-02": point}))
    moved = _by_id(result.holes)["2-02"]
    assert moved.length_m == pytest.approx(hole.length_m)
    assert moved.collar.z == pytest.approx(hole.collar.z)
    assert "length" not in moved.manual and "collar_z" not in moved.manual
    assert "xy" in moved.manual


def test_angle_azimuth_from_survey_else_design():
    design = _design(tilt_deg=15.0)
    inclined = _hole(design, "1-03")
    vertical = _hole(design, "3-03")
    points = {
        "1-03": _point(inclined, angle_deg=None, azimuth_deg=None, dl=0.2),
        "3-03": _point(vertical, angle_deg=3.0, azimuth_deg=45.0),
    }
    holes = _by_id(_apply(design, _matches(design, points)).holes)
    assert holes["1-03"].angle_deg == pytest.approx(inclined.angle_deg)
    assert holes["1-03"].azimuth_deg == pytest.approx(inclined.azimuth_deg)
    assert holes["3-03"].angle_deg == pytest.approx(3.0)
    assert holes["3-03"].azimuth_deg == pytest.approx(45.0)


def test_water_replaces_designed_intervals():
    design = _design()
    hole = _hole(design, "2-04")
    hole.water_intervals = [
        WaterInterval(from_m=1.0, to_m=2.0, condition="moist"),
        WaterInterval(from_m=5.0, to_m=6.0, condition="wet", role="measured"),
    ]
    dry = _hole(design, "3-04")
    dry.water_intervals = [WaterInterval(from_m=0.0, to_m=dry.length_m)]
    keep = _hole(design, "4-04")
    keep.water_intervals = [WaterInterval(from_m=3.0, to_m=keep.length_m)]
    points = {
        "2-04": _point(hole, wet=True, water_depth_m=4.0),
        "3-04": _point(dry, wet=False),
        "4-04": _point(keep, dx=0.5),
    }
    result = _apply(design, _matches(design, points))
    holes = _by_id(result.holes)
    designed = [iv for iv in holes["2-04"].water_intervals if iv.role == "designed"]
    assert len(designed) == 1
    assert designed[0].from_m == pytest.approx(4.0)
    assert designed[0].to_m == pytest.approx(holes["2-04"].length_m)
    assert designed[0].condition == "wet"
    assert designed[0].provenance.method == "survey_import"
    assert designed[0].provenance.source == "s66.csv"
    # Измеренная вода съёмкой не трогается.
    assert [iv.role for iv in holes["2-04"].water_intervals].count("measured") == 1
    assert holes["3-04"].water_intervals == []
    assert [iv.to_dict() for iv in holes["4-04"].water_intervals] == [iv.to_dict() for iv in keep.water_intervals]
    # Вода без изменения геометрии — тоже изменение скважины (заряд пересчитывается).
    assert set(result.changed_ids) == {"2-04", "3-04", "4-04"}


def test_loads_recomputed_only_for_changed_holes():
    design = _design(loads=True)
    edited = next(load for load in design.loads if load.hole_id == "4-05")
    edited.total_charge_kg = 999.0  # правлено руками
    hole = _hole(design, "2-03")
    result = _apply(design, _matches(design, {"2-03": _point(hole, dl=-0.6)}))
    assert result.changed_ids == ["2-03"]
    fresh = {
        load.hole_id: load
        for load in apply_charge_rules(result.holes, RULES, EXPLOSIVE, contour=design.contour)
    }
    before = {load.hole_id: load for load in design.loads}
    after = {load.hole_id: load for load in result.loads}
    assert [load.hole_id for load in result.loads] == [load.hole_id for load in design.loads]
    assert after["2-03"].to_dict() == fresh["2-03"].to_dict()
    assert after["2-03"].to_dict() != before["2-03"].to_dict()
    for hole_id, load in before.items():
        if hole_id != "2-03":
            assert after[hole_id].to_dict() == load.to_dict()
    assert after["4-05"].total_charge_kg == 999.0


def test_no_loads_in_design_returns_none():
    design = _design()
    hole = _hole(design, "2-03")
    result = _apply(design, _matches(design, {"2-03": _point(hole, dl=-0.6)}))
    assert result.loads is None


def test_loads_without_charge_inputs_are_kept_with_warning():
    design = _design(loads=True)
    hole = _hole(design, "2-03")
    result = _apply(design, _matches(design, {"2-03": _point(hole, dl=-0.6)}), charge=None)
    assert result.loads is None
    assert any("Заряды" in warning for warning in result.warnings)


def test_as_drilled_for_every_matched_hole():
    design = _design()
    hole = _hole(design, "2-03")
    old = _apply(design, _matches(design, only={"2-03"}))
    design.as_drilled_holes = old.as_drilled_holes
    design.as_drilled_holes[0].provenance.method = "manual"
    point = _point(hole, dx=0.2, dl=-0.3)
    matches = _matches(design, {"2-03": point})
    matches.append(SurveyMatch(None, SurveyedPoint("Rp1", 0.0, 0.0), "", "unmatched_point"))
    result = _apply(design, matches)
    records = {item.design_hole_id: item for item in result.as_drilled_holes}
    assert len(result.as_drilled_holes) == len(design.holes)  # запись по скважине одна
    for item in result.as_drilled_holes:
        assert item.provenance.method == "survey_import"
        assert item.provenance.source == "s66.csv"
        assert item.provenance.timestamp == "2026-11-13"
        assert item.role == "executed"
    record = records["2-03"]
    assert (record.actual_collar.x, record.actual_collar.y) == pytest.approx((point.x, point.y))
    assert record.actual_depth == pytest.approx(point.depth_m)
    assert record.actual_diameter == pytest.approx(hole.diameter_mm)


def test_application_counts():
    design = _design()
    points = {
        "2-02": _point(_hole(design, "2-02"), dl=-0.6),
        "2-03": _point(_hole(design, "2-03"), dx=0.5),
        "3-03": _point(_hole(design, "3-03"), depth_m=None),
    }
    matches = _matches(design, points, only={"2-02", "2-03", "3-03", "4-01"})
    matches += [
        SurveyMatch(None, SurveyedPoint("Rp1", 0.0, 0.0), "", "unmatched_point"),
        SurveyMatch("4-02", None, "", "missing_point"),
        SurveyMatch("4-03", None, "", "missing_point"),
        SurveyMatch("4-04", SurveyedPoint("4-04", 0.0, 0.0), "name", "duplicate_point"),
    ]
    result = _apply(design, matches)
    application = result.application
    assert isinstance(application, SurveyApplication)
    assert set(application.counts) == {*VERDICT_CODES, "changed", "unmatched_point", "missing_point"}
    assert application.counts["underdrill"] == 1
    assert application.counts["offset"] == 1
    assert application.counts["no_depth"] == 1
    assert application.counts["ok"] == 1  # 4-01
    assert application.counts["changed"] == 2  # 2-02, 2-03; 3-03 без замера — без изменения
    assert application.counts["unmatched_point"] == 1
    assert application.counts["missing_point"] == 2
    assert (application.applied_at, application.survey_date, application.file_name, application.actor) == (
        NOW, "2026-11-13", "s66.csv", "mark@mine",
    )
    assert application.file_sha256 == "ab" * 32
    # Дубликат и отсутствующие не применяются.
    assert {item.design_hole_id for item in result.as_drilled_holes} == {"2-02", "2-03", "3-03", "4-01"}
    assert SurveyApplication.from_dict(application.to_dict()) == application


def test_survey_applications_is_execution_key():
    design = _design(loads=True)
    assert "survey_applications" not in design.to_dict()
    assert "survey_applications" not in execution_payload(design)
    applied = _applied(design, _apply(design, _matches(design)))
    assert classify_mutations(design, applied) == ["execution"]
    data = applied.to_dict()
    assert data["survey_applications"] == [applied.survey_applications[0].to_dict()]
    assert BlastDesign.from_dict(data).survey_applications == applied.survey_applications


def test_input_design_not_mutated():
    design = _design(loads=True, tilt_deg=15.0)
    _hole(design, "2-04").water_intervals = [WaterInterval(from_m=1.0, to_m=2.0)]
    snapshot = copy.deepcopy(design.to_dict())
    points = {
        "2-04": _point(_hole(design, "2-04"), dx=0.4, dl=-0.5, wet=True, water_depth_m=3.0),
        "1-02": _point(_hole(design, "1-02"), dz=0.3, angle_deg=12.0),
    }
    result = _apply(design, _matches(design, points))
    assert design.to_dict() == snapshot
    assert all(a is not b for a, b in zip(result.holes, design.holes))
    assert math.isfinite(_by_id(result.holes)["1-02"].subdrill_m)


def _max_deck_depth(load) -> float:
    return max((deck.to_m for deck in load.decks), default=0.0)


def test_underdrilled_hole_keeps_design_floor_and_round_trips():
    from api.schemas.design import BlastDesignSchema
    from design.charge_templates import example_wet_dry_bottom_templates

    design = _design(loads=True)
    hole = _hole(design, "2-03")  # вертикальная, перебур 1 м
    point = _point(hole, dl=-1.6, wet=True, water_depth_m=5.0)
    result = _apply(design, _matches(design, {"2-03": point}))
    under = _by_id(result.holes)["2-03"]
    # Недобур ниже проектного перебура: перебур отрицательный, подошва — проектная.
    assert under.subdrill_m == pytest.approx(-0.6)
    assert under.collar.z - under.bench_height_m == pytest.approx(hole.collar.z - hole.bench_height_m)

    applied = _applied(design, result)
    schema = BlastDesignSchema.model_validate(applied.to_dict())
    back = BlastDesign.from_dict(schema.model_dump())
    assert _by_id(back.holes)["2-03"].subdrill_m == pytest.approx(-0.6)
    # Сравнение значений, а не хэша: заготовка контура с целыми координатами схема делает float.
    assert designed_payload(back) == designed_payload(applied)

    # Заряд — в пределах фактической длины скважины: и правилами, и шаблонами.
    load = next(item for item in result.loads if item.hole_id == "2-03")
    assert 0 < _max_deck_depth(load) <= under.length_m + 1e-9
    catalog = [
        ExplosiveProperties(name="Эмульсия плотная", density_t_m3=1.25, power_mj_kg=3.2),
        ExplosiveProperties(name="Эмульсия водоустойчивая", density_t_m3=1.2, power_mj_kg=3.0),
    ]
    templated = apply_charge_rules(
        back.holes, {"stemming_m": 3.0}, EXPLOSIVE, contour=back.contour,
        explosives=catalog, templates=example_wet_dry_bottom_templates(),
    )
    by_hole = {item.hole_id: item for item in templated}
    assert 0 < _max_deck_depth(by_hole["2-03"]) <= under.length_m + 1e-9
    assert by_hole["2-03"].total_charge_kg > 0


def test_water_level_without_wet_flag_and_wet_without_level():
    design = _design()
    level = _hole(design, "2-02")
    whole = _hole(design, "2-04")
    below = _hole(design, "3-02")
    below.water_intervals = [WaterInterval(from_m=6.0, to_m=below.length_m)]
    points = {
        "2-02": _point(level, wet=None, water_depth_m=7.5),
        "2-04": _point(whole, wet=True, water_depth_m=None),
        "3-02": _point(below, wet=None, water_depth_m=below.length_m + 1.0),
    }
    result = _apply(design, _matches(design, points))
    holes = _by_id(result.holes)
    [wet_level] = holes["2-02"].water_intervals
    assert (wet_level.from_m, wet_level.to_m, wet_level.condition) == pytest.approx((7.5, level.length_m, "wet"))
    [wet_whole] = holes["2-04"].water_intervals
    assert (wet_whole.from_m, wet_whole.to_m) == pytest.approx((0.0, whole.length_m))
    assert holes["3-02"].water_intervals == []
    assert any("3-02" in warning and "ниже забоя" in warning for warning in result.warnings)


def test_missing_fresh_load_is_warned(monkeypatch):
    import design.survey.apply as apply_module

    design = _design(loads=True)
    real = apply_module.apply_charge_rules

    def without(holes, *args, **kwargs):
        return [load for load in real(holes, *args, **kwargs) if load.hole_id != "2-03"]

    monkeypatch.setattr(apply_module, "apply_charge_rules", without)
    result = _apply(design, _matches(design, {"2-03": _point(_hole(design, "2-03"), dl=-0.6)}))
    assert any("2-03" in warning for warning in result.warnings)


def test_empty_survey_applications_not_in_execution_payload():
    data = _design().to_dict()
    data["survey_applications"] = []
    assert "survey_applications" not in execution_payload(data)


def test_resurvey_after_redrilling_is_ok():
    """Δ=1: недобур 0,5 → «Применить» → добурили до проекта → пересъёмка — ОК, а не ПЕРЕБУР."""

    design = _design()
    hole = _hole(design, "2-02")
    design_subdrill = hole.subdrill_m
    assert design_subdrill > 0.4
    short = _point(hole, dl=-0.5)
    first_matches = _matches(design, {"2-02": short}, only={"2-02"})
    (verdict,) = evaluate_survey(design, first_matches, SurveyTolerances())
    assert "underdrill" in verdict.codes
    after = _applied(design, _apply(design, first_matches))
    moved = _hole(after, "2-02")
    assert moved.subdrill_m == pytest.approx(design_subdrill - 0.5)
    assert moved.design_subdrill_m == pytest.approx(design_subdrill)
    assert moved.to_dict()["design_subdrill_m"] == pytest.approx(design_subdrill)

    redrilled = _point(moved, dl=0.5)
    second_matches = _matches(after, {"2-02": redrilled}, only={"2-02"})
    (again,) = evaluate_survey(after, second_matches, SurveyTolerances())
    assert again.codes == ["ok"]
    assert again.required_length_m == pytest.approx(hole.length_m)
    final = _applied(after, _apply(after, second_matches))
    # Перебур вернулся к проекту, проектный — тот же (не фактический 0,5).
    assert _hole(final, "2-02").subdrill_m == pytest.approx(design_subdrill)
    assert _hole(final, "2-02").design_subdrill_m == pytest.approx(design_subdrill)


def test_design_subdrill_not_written_when_subdrill_unchanged():
    design = _design()
    hole = _hole(design, "2-02")
    result = _apply(design, _matches(design, {"2-02": _point(hole, dx=0.4)}, only={"2-02"}))
    moved = _by_id(result.holes)["2-02"]
    assert moved.design_subdrill_m is None
    assert "design_subdrill_m" not in moved.to_dict()


def test_fact_without_depth_is_marked():
    """Глубина не замерена — запись факта помечена: в графы Ф глубина не идёт."""

    design = _design()
    measured, unmeasured = _hole(design, "2-02"), _hole(design, "2-03")
    points = {"2-02": _point(measured, dl=-0.3), "2-03": _point(unmeasured, dx=0.2, depth_m=None)}
    result = _apply(design, _matches(design, points, only=set(points)))
    methods = {item.design_hole_id: item.provenance.method for item in result.as_drilled_holes}
    assert methods == {"2-02": "survey_import", "2-03": "survey_import_no_depth"}


def test_unmeasured_depth_is_not_a_measurement_in_compare_and_report():
    """Факт без замера глубины: в сравнении с проектом и в погонаже факта — «нет замера»."""

    from design.as_drilled import compare_design
    from design.reporting.engine import _collect_executed

    design = _design()
    measured, unmeasured = _hole(design, "2-02"), _hole(design, "2-03")
    points = {"2-02": _point(measured, dl=-0.3), "2-03": _point(unmeasured, dx=0.2, depth_m=None)}
    applied = _applied(design, _apply(design, _matches(design, points, only=set(points))))
    rows = {row["design_hole_id"]: row for row in compare_design(applied)["deviations"]}
    assert rows["2-03"]["depth_deviation_m"] is None and rows["2-03"]["actual_depth_m"] is None
    assert rows["2-03"]["designed_depth_m"] == pytest.approx(unmeasured.length_m, abs=1e-3)
    # Применённая съёмка — и проект, и факт: замеренная глубина — число, не «нет замера».
    assert rows["2-02"]["depth_deviation_m"] == 0.0
    assert rows["2-02"]["actual_depth_m"] == pytest.approx(measured.length_m - 0.3, abs=1e-3)
    # Погонаж факта — только когда глубина замерена у всех пробуренных.
    assert _collect_executed(applied).drilling_metres is None
    only_measured = _applied(design, _apply(design, _matches(design, {"2-02": points["2-02"]}, only={"2-02"})))
    assert _collect_executed(only_measured).drilling_metres == pytest.approx(measured.length_m - 0.3, abs=1e-3)


def test_deviation_schema_accepts_unmeasured_depth():
    from api.schemas.design import HoleDeviationSchema

    row = HoleDeviationSchema(
        design_hole_id="2-03", collar_offset_m=0.2, toe_offset_m=0.2, depth_deviation_m=None,
        angle_deviation_deg=0.0, azimuth_deviation_deg=0.0, actual_depth_m=None, designed_depth_m=12.0,
    )
    assert row.depth_deviation_m is None and row.actual_depth_m is None
