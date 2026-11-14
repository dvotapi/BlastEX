"""Оценка скважин по съёмке (TASK-014, PR 5а): допуски паспорта, коды, смешанная сетка."""
from __future__ import annotations

import copy
import math

import pytest

from design.models import Hole
from design.survey.evaluate import (
    VERDICT_CODES,
    SurveyTolerances,
    evaluate_survey,
    surveyed_geometry,
    tolerances_from_payload,
)
from design.survey.match import SurveyMatch
from design.survey.read import SurveyedPoint
from tests.front_rows_fixtures import GAP_PATTERN, design_with, grid_rows

TOL = SurveyTolerances()


def _design(tilt_deg: float = 0.0):
    """Сетка 4 × 5 у откоса y = 0 (ряд 1 — y = 2), a = 4, b = 3,5; ряд 1 наклонён на `tilt_deg` к откосу."""
    return design_with(grid_rows(row_one_tilt_deg=tilt_deg), GAP_PATTERN)


def _hole(design, hole_id: str) -> Hole:
    return next(hole for hole in design.holes if hole.id == hole_id)


def _point(hole: Hole, **changes) -> SurveyedPoint:
    """Точка «как в проекте»: устье, отметка и длина; `dx`, `dy`, `dz`, `dl` — сдвиги."""

    dx, dy, dz, dl = (changes.pop(key, 0.0) for key in ("dx", "dy", "dz", "dl"))
    values = {
        "name": hole.id, "x": hole.collar.x + dx, "y": hole.collar.y + dy, "z": hole.collar.z + dz,
        "depth_m": hole.length_m + dl,
    }
    values.update(changes)
    return SurveyedPoint(**values)


def _matches(design, changed: dict[str, SurveyedPoint] | None = None, only=None) -> list[SurveyMatch]:
    changed = changed or {}
    return [
        SurveyMatch(hole.id, changed.get(hole.id) or _point(hole), "name")
        for hole in design.holes
        if only is None or hole.id in only
    ]


def _verdicts(design, matches, tol=TOL):
    return {verdict.hole_id: verdict for verdict in evaluate_survey(design, matches, tol)}


def test_all_ok_when_survey_equals_design():
    design = _design(tilt_deg=15.0)
    verdicts = _verdicts(design, _matches(design))
    assert len(verdicts) == len(design.holes)
    for verdict in verdicts.values():
        assert verdict.codes == ["ok"], verdict
        assert verdict.unchanged
        assert verdict.offset_m == pytest.approx(0.0)
        assert verdict.depth_delta_m == pytest.approx(0.0, abs=1e-9)


def test_plan_offset_only_counts_xy():
    design = _design()
    hole = _hole(design, "2-03")
    point = _point(hole, dz=0.4, dl=0.4)  # вертикальная: нужная длина длиннее ровно на 0,4
    verdict = _verdicts(design, _matches(design, {"2-03": point}))["2-03"]
    assert "offset" not in verdict.codes
    assert verdict.offset_m == pytest.approx(0.0)
    assert verdict.codes == ["ok"]
    assert not verdict.unchanged


def test_higher_collar_same_length_is_underdrill():
    design = _design(tilt_deg=15.0)
    hole = _hole(design, "1-02")
    verdict = _verdicts(design, _matches(design, {"1-02": _point(hole, dz=0.4)}))["1-02"]
    assert verdict.codes == ["underdrill"]
    cos_a = math.cos(math.radians(15.0))
    assert verdict.required_length_m == pytest.approx(hole.length_m + 0.4 / cos_a)
    assert verdict.depth_delta_m == pytest.approx(-0.4 / cos_a)


def test_short_by_0_6_is_underdrill_long_is_overdrill():
    design = _design()
    short = _point(_hole(design, "2-02"), dl=-0.6)
    long = _point(_hole(design, "2-04"), dl=0.6)
    within = _point(_hole(design, "3-03"), dl=0.25)
    verdicts = _verdicts(design, _matches(design, {"2-02": short, "2-04": long, "3-03": within}))
    assert verdicts["2-02"].codes == ["underdrill"]
    assert verdicts["2-02"].depth_delta_m == pytest.approx(-0.6)
    assert verdicts["2-04"].codes == ["overdrill"]
    assert verdicts["2-04"].depth_delta_m == pytest.approx(0.6)
    assert verdicts["3-03"].codes == ["ok"]


def test_offset_0_5_in_plan():
    design = _design()
    hole = _hole(design, "3-03")
    verdict = _verdicts(design, _matches(design, {"3-03": _point(hole, dx=0.3, dy=0.4)}))["3-03"]
    assert "offset" in verdict.codes and "ok" not in verdict.codes
    assert verdict.offset_m == pytest.approx(0.5)
    near = _point(_hole(design, "3-02"), dy=0.2)
    assert "offset" not in _verdicts(design, _matches(design, {"3-02": near}))["3-02"].codes


def test_angle_1_5_deg():
    design = _design(tilt_deg=15.0)
    vertical = _hole(design, "3-03")
    inclined = _hole(design, "1-03")
    points = {
        # Вертикальная: угол по съёмке 1,5° — ось отклонилась на 1,5°.
        "3-03": _point(vertical, angle_deg=1.5, azimuth_deg=0.0),
        # Наклонная 15°: азимут на 6° в сторону — ось отклонилась на ~1,55°.
        "1-03": _point(inclined, angle_deg=15.0, azimuth_deg=inclined.azimuth_deg + 6.0),
        # Угол в пределах допуска.
        "3-04": _point(_hole(design, "3-04"), angle_deg=0.5),
    }
    verdicts = _verdicts(design, _matches(design, points))
    assert "angle" in verdicts["3-03"].codes
    assert verdicts["3-03"].angle_delta_deg == pytest.approx(1.5)
    assert "angle" in verdicts["1-03"].codes
    assert verdicts["1-03"].angle_delta_deg == pytest.approx(1.552, abs=0.01)
    assert "angle" not in verdicts["3-04"].codes
    assert not verdicts["3-04"].unchanged
    # Азимут вертикальной ничего не значит; угла и азимута нет — угол не замерен.
    plain = _verdicts(design, _matches(design, {"3-02": _point(_hole(design, "3-02"), azimuth_deg=123.0)}))
    assert plain["3-02"].codes == ["ok"] and plain["3-02"].unchanged
    assert _verdicts(design, _matches(design))["3-03"].angle_delta_deg is None


def test_first_row_burden_over_5_pct():
    design = _design()
    hole = _hole(design, "1-03")
    verdicts = _verdicts(design, _matches(design, {"1-03": _point(hole, dy=-0.6)}))
    assert "burden" in verdicts["1-03"].codes
    # ЛСПП ряда 1 — 2 + 2,68 = 4,68 м; на 0,6 м ближе к откосу — −12,8 %.
    assert verdicts["1-03"].burden_delta_pct == pytest.approx(-0.6 / (2.0 + 2.6795) * 100, abs=0.05)
    assert [hid for hid, verdict in verdicts.items() if "burden" in verdict.codes] == ["1-03"]
    assert verdicts["2-03"].burden_delta_pct is None  # не первый ряд — ЛСПП нет


def test_spacing_over_5_pct_mixed_grid():
    design = _design()
    moved = _point(_hole(design, "2-03"), dx=0.4)
    # Точка только у 2-03 и 2-04: соседи без съёмки стоят по проекту.
    verdicts = _verdicts(design, _matches(design, {"2-03": moved}, only={"2-03", "2-04"}))
    assert set(verdicts) == {"2-03", "2-04"}
    assert "spacing" in verdicts["2-03"].codes
    assert verdicts["2-03"].spacing_delta_pct == pytest.approx(-10.0)
    # У 2-04 своя точка по проекту, но сосед 2-03 съехал к ней: 3,6 м вместо 4.
    assert verdicts["2-04"].codes == ["spacing"]
    small = _point(_hole(design, "2-03"), dx=0.15)
    assert "spacing" not in _verdicts(design, _matches(design, {"2-03": small}))["2-03"].codes


def test_no_depth_code_and_depth_checks_skipped():
    design = _design()
    hole = _hole(design, "2-02")
    verdict = _verdicts(design, _matches(design, {"2-02": _point(hole, dz=0.6, depth_m=None)}))["2-02"]
    assert verdict.codes == ["no_depth"]
    assert verdict.depth_delta_m is None
    assert verdict.required_length_m == pytest.approx(hole.length_m + 0.6)
    offset = _point(hole, dy=0.5, depth_m=None)
    assert _verdicts(design, _matches(design, {"2-02": offset}))["2-02"].codes == ["offset", "no_depth"]


def test_unchanged_thresholds():
    design = _design()
    hole = _hole(design, "2-02")
    close = _point(hole, dx=0.0009 / math.sqrt(2), dy=0.0009 / math.sqrt(2), dz=0.0009, dl=0.009)
    assert _verdicts(design, _matches(design, {"2-02": close}))["2-02"].unchanged
    for changes in ({"dx": 0.0011}, {"dz": -0.0011}, {"dl": 0.011}):
        verdict = _verdicts(design, _matches(design, {"2-02": _point(hole, **changes)}))["2-02"]
        assert not verdict.unchanged, changes
    no_z = _point(hole, z=None, depth_m=None)
    assert _verdicts(design, _matches(design, {"2-02": no_z}))["2-02"].unchanged


def test_unchanged_angle_boundary_is_file_rounding():
    # Угол в файле — до 0,1°: проект 15°, в файле 15,05 → ровно половина шага — ещё «без изменения».
    design = _design(tilt_deg=15.0)
    hole = _hole(design, "1-02")
    at_boundary = _verdicts(design, _matches(design, {"1-02": _point(hole, angle_deg=15.05)}))["1-02"]
    assert at_boundary.angle_delta_deg == pytest.approx(0.05)
    assert at_boundary.unchanged
    beyond = _verdicts(design, _matches(design, {"1-02": _point(hole, angle_deg=15.06)}))["1-02"]
    assert not beyond.unchanged


def test_tolerances_from_payload_defaults_and_values():
    assert tolerances_from_payload(None, source="passport") == SurveyTolerances(source="default")
    defaults = tolerances_from_payload({"tol_depth_m": 0.3, "tol_collar_m": 0.3}, source="parent_passport")
    assert defaults == SurveyTolerances(source="parent_passport")
    values = tolerances_from_payload(
        {"tol_depth_m": 0.2, "tol_collar_m": 0.5, "tol_angle_deg": 1.5, "tol_burden_pct": 7,
         "tol_spacing_pct": 10.0},
        source="passport",
    )
    assert values == SurveyTolerances(
        depth_m=0.2, collar_m=0.5, angle_deg=1.5, burden_pct=7.0, spacing_pct=10.0, source="passport"
    )
    broken = tolerances_from_payload(
        {"tol_depth_m": None, "tol_collar_m": "x", "tol_angle_deg": 0, "tol_burden_pct": -1, "tol_spacing_pct": True},
        source="passport",
    )
    assert broken == SurveyTolerances(source="passport")


def test_tolerances_change_codes():
    design = _design()
    point = _point(_hole(design, "2-02"), dy=0.4)
    assert _verdicts(design, _matches(design, {"2-02": point}))["2-02"].codes == ["offset"]
    loose = SurveyTolerances(collar_m=0.5, source="passport")
    assert _verdicts(design, _matches(design, {"2-02": point}), loose)["2-02"].codes == ["ok"]


def test_only_clean_matches_are_evaluated():
    design = _design()
    holes = design.holes
    matches = [
        SurveyMatch(holes[0].id, _point(holes[0]), "name"),
        SurveyMatch(holes[1].id, None, "", "missing_point"),
        SurveyMatch(None, SurveyedPoint(name="RP", x=0, y=0), "", "unmatched_point"),
        SurveyMatch(holes[2].id, _point(holes[2]), "", "duplicate_point"),
        SurveyMatch("нет такой", SurveyedPoint(name="X", x=0, y=0), "manual"),
    ]
    assert [verdict.hole_id for verdict in evaluate_survey(design, matches, TOL)] == [holes[0].id]


def test_codes_are_known():
    design = _design()
    points = {"1-03": _point(_hole(design, "1-03"), dy=-0.6, dl=-1.0, angle_deg=3.0, azimuth_deg=180.0)}
    verdict = _verdicts(design, _matches(design, points))["1-03"]
    assert verdict.codes == ["underdrill", "offset", "angle", "burden"]
    assert set(verdict.codes) <= set(VERDICT_CODES)


def test_surveyed_geometry_is_a_copy_with_survey():
    design = _design(tilt_deg=15.0)
    before = copy.deepcopy(design.to_dict())
    hole = _hole(design, "1-03")
    point = _point(hole, dx=0.5, dz=0.2, depth_m=12.0, angle_deg=10.0, azimuth_deg=170.0)
    result = surveyed_geometry(design, _matches(design, {"1-03": point}, only={"1-03"}))
    assert design.to_dict() == before
    assert result is not design
    moved = _hole(result, "1-03")
    assert (moved.collar.x, moved.collar.y, moved.collar.z) == pytest.approx((hole.collar.x + 0.5, hole.collar.y, 0.2))
    assert moved.length_m == pytest.approx(12.0)
    assert moved.angle_deg == pytest.approx(10.0)
    assert moved.azimuth_deg == pytest.approx(170.0)
    # Подошва у копии — проектная: ось на уровне подошвы на той же отметке.
    floor_z = hole.collar.z - hole.bench_height_m
    assert moved.collar.z - moved.bench_height_m == pytest.approx(floor_z)
    # Скважина без точки — по проекту.
    assert _hole(result, "1-02").to_dict() == hole_dict(design, "1-02")


def hole_dict(design, hole_id):
    return _hole(design, hole_id).to_dict()
