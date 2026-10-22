import math
import unittest

import pytest
import shapely

from Blast import ExplosiveProperties
from design.analysis import charge_per_delay, estimate_ppv, summary, timing_isolines, validate
from design.charging import apply_charge_rules
from design.models import BenchSurface, BlastDesign, BlockContour, Point3
from design.pattern import generate_pattern
from design.toe_line import floor_row_gaps
from design.timing import build_template_network, resolve_times

EXPLOSIVE = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)


def _design(pattern: str = "rectangular") -> tuple[BlastDesign, dict[str, float]]:
    contour = BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (20, 0), (20, 16), (0, 16)]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )
    params = {"pattern": pattern, "spacing_a_m": 4.0, "burden_b_m": 4.0, "offset_from_face_m": 0.0, "edge_margin_m": 0.0}
    holes = generate_pattern(contour, params)
    loads = apply_charge_rules(
        holes, {"stemming_m": 3.0, "decking": "continuous", "grid_a_m": 4.0, "grid_b_m": 4.0}, EXPLOSIVE
    )
    network = build_template_network(holes, "echelon", {"system": "nonel"})
    times, _warnings = resolve_times(network, holes)
    design = BlastDesign(
        design_id="test",
        contour=contour,
        holes=holes,
        loads=loads,
        network=network,
        pattern_params=params,
    )
    return design, times


class SummaryTests(unittest.TestCase):
    def test_summary_matches_hole_and_charge_totals(self):
        design, _times = _design()
        result = summary(design)
        self.assertEqual(result["hole_count"], len(design.holes))
        self.assertAlmostEqual(result["total_charge_kg"], sum(ld.total_charge_kg for ld in design.loads), places=2)
        self.assertIn("Гранулит-РП", result["explosive_breakdown_kg"])

    def test_summary_ignores_orphan_loads(self):
        design, _times = _design()
        orphan = design.loads[0]
        design.loads = [orphan]
        design.holes = design.holes[1:]
        result = summary(design)
        self.assertEqual(result["total_charge_kg"], 0.0)
        self.assertEqual(result["charged_hole_count"], 0)
        self.assertEqual(result["loads_by_hole_count"], 0)


class ChargePerDelayTests(unittest.TestCase):
    def test_mic_window_never_exceeds_total_charge(self):
        design, times = _design()
        result = charge_per_delay(times, design.loads, window_ms=8.0)
        total = sum(ld.total_charge_kg for ld in design.loads)
        self.assertGreater(result["mic_kg"], 0.0)
        self.assertLessEqual(result["mic_kg"], total)

    def test_wide_window_captures_more_charge_than_narrow(self):
        design, times = _design()
        narrow = charge_per_delay(times, design.loads, window_ms=1.0)
        wide = charge_per_delay(times, design.loads, window_ms=1000.0)
        self.assertLessEqual(narrow["mic_kg"], wide["mic_kg"])

    def test_empty_loads_return_zero(self):
        result = charge_per_delay({}, [], window_ms=8.0)
        self.assertEqual(result["mic_kg"], 0.0)
        self.assertEqual(result["hole_ids"], [])


class TimingIsolinesTests(unittest.TestCase):
    def test_isolines_cover_time_range(self):
        design, times = _design()
        isolines = timing_isolines(times, design.holes, step_ms=25.0)
        self.assertGreater(len(isolines), 0)
        levels = [iso["time_ms"] for iso in isolines]
        self.assertEqual(levels, sorted(levels))
        for iso in isolines:
            self.assertGreater(len(iso["segments"]), 0)
            for seg in iso["segments"]:
                self.assertEqual(len(seg), 2)

    def test_too_few_points_returns_empty(self):
        self.assertEqual(timing_isolines({"a": 0.0, "b": 1.0}, [], step_ms=10.0), [])


class ValidateTests(unittest.TestCase):
    def test_clean_design_has_no_warnings(self):
        design, _times = _design()
        warnings = validate(design)
        self.assertEqual(warnings, [])

    def test_hole_outside_contour_is_flagged(self):
        design, _times = _design()
        from dataclasses import replace

        bad = replace(design.holes[0], collar=replace(design.holes[0].collar, x=1000.0, y=1000.0))
        design.holes[0] = bad
        warnings = validate(design)
        self.assertTrue(any(w["code"] == "hole_outside_contour" for w in warnings))

    def test_short_stemming_is_flagged(self):
        design, _times = _design()
        loads = apply_charge_rules(
            design.holes, {"stemming_m": 0.1, "decking": "continuous", "grid_a_m": 4.0, "grid_b_m": 4.0}, EXPLOSIVE
        )
        design.loads = loads
        warnings = validate(design, min_stemming_m=0.5)
        self.assertTrue(any(w["code"] == "stemming_too_short" for w in warnings))


class EstimatePpvTests(unittest.TestCase):
    def test_ppv_increases_with_charge_and_decreases_with_distance(self):
        # В формуле V = K·(Q^(1/3)/R)^n показатель Q^(1/3)/R уже растёт при
        # приближении/увеличении заряда, поэтому n здесь положительный
        # (типичное значение ~1.6), в отличие от классической записи через
        # приведённое расстояние R/W^0.5 со отрицательным показателем.
        near = estimate_ppv(mic_kg=100.0, distance_m=50.0, k=200.0, n=1.6)
        far = estimate_ppv(mic_kg=100.0, distance_m=200.0, k=200.0, n=1.6)
        more_charge = estimate_ppv(mic_kg=400.0, distance_m=50.0, k=200.0, n=1.6)
        self.assertGreater(near, far)
        self.assertGreater(more_charge, near)

    def test_zero_inputs_return_zero(self):
        self.assertEqual(estimate_ppv(0.0, 50.0, 200.0, 1.6), 0.0)
        self.assertEqual(estimate_ppv(100.0, 0.0, 200.0, 1.6), 0.0)


def test_validate_warns_when_floor_burden_exceeds_w_plus_3_percent():
    from tests.test_toe_line import face_design

    warnings = validate(face_design())
    excess = [w for w in warnings if w["code"] == "floor_burden_excess"]
    assert [w["hole_id"] for w in excess] == ["1-01"]
    assert "ЛСП 6,4 м больше допустимого 3,8 м" in excess[0]["message"]
    assert "подошва по углу" in excess[0]["message"]


def test_validate_warns_when_hole_exits_into_slope():
    from design.models import BlastDesign
    from tests.front_rows_fixtures import PATTERN, inclined_hole, rect_contour

    out = inclined_hole("1-01", x=10, y=1.0, row=0, angle_deg=30, azimuth_deg=180)
    ok = inclined_hole("1-02", x=20, y=3.7, row=0, angle_deg=15, azimuth_deg=180)
    design = BlastDesign(design_id="t", contour=rect_contour(), holes=[out, ok], pattern_params=PATTERN)
    warnings = validate(design)
    beyond = [w for w in warnings if w["code"] == "floor_beyond_toe"]
    assert [w["hole_id"] for w in beyond] == ["1-01"]
    assert beyond[0]["message"] == "Скважина 1-01 выходит в откос: точка на подошве за нижней бровкой."
    # ЛСП вышедшей в откос скважины предупреждением о ЛСП не дублируется.
    assert not any(w["code"] == "floor_burden_excess" and w["hole_id"] == "1-01" for w in warnings)


def test_validate_warns_when_floor_burden_below_0_8_w():
    from design.models import BlastDesign
    from tests.front_rows_fixtures import PATTERN, rect_contour, vertical_hole

    hole = vertical_hole("1-01", x=10, y=0.2, row=0)  # ЛСП 2,88 < 0,8·3,7 = 2,96
    design = BlastDesign(design_id="t", contour=rect_contour(), holes=[hole], pattern_params=PATTERN)
    short = [w for w in validate(design) if w["code"] == "floor_burden_short"]
    assert [w["hole_id"] for w in short] == ["1-01"]
    assert short[0]["message"] == "ЛСП 2,9 м меньше допустимого 3,0 м (0,8·W, подошва по углу)."


def test_floor_burden_messages_show_two_decimals_when_rounding_hides_difference():
    from design.models import BlastDesign
    from tests.front_rows_fixtures import PATTERN, rect_contour, vertical_hole

    # Допуск 3,811; ЛСП 3,83 — обе «3,8» при одном знаке.
    over = vertical_hole("1-01", x=10, y=3.83 - 2.6795, row=0)
    # Нижняя граница 2,96; ЛСП 2,952 — обе «3,0» при одном знаке.
    under = vertical_hole("1-03", x=30, y=2.952 - 2.6795, row=0)
    design = BlastDesign(design_id="t", contour=rect_contour(), holes=[over, under], pattern_params=PATTERN)
    warnings = validate(design)
    excess = [w for w in warnings if w["code"] == "floor_burden_excess"]
    short = [w for w in warnings if w["code"] == "floor_burden_short"]
    assert excess[0]["message"] == "ЛСП 3,83 м больше допустимого 3,81 м (W + 3%, подошва по углу)."
    assert short[0]["message"] == "ЛСП 2,95 м меньше допустимого 2,96 м (0,8·W, подошва по углу)."



def test_two_numbers_adds_digits_until_numbers_differ():
    from design.analysis import _two_numbers

    assert _two_numbers(6.38, 3.81) == ("6,4", "3,8")
    assert _two_numbers(3.83, 3.811) == ("3,83", "3,81")
    assert _two_numbers(3.8114, 3.811) == ("3,811", "3,811")


# --- Разрыв между рядами у подошвы и устье у кромки (часть 3b) ---------------


def _codes(warnings, code):
    return [w for w in warnings if w["code"] == code]


def _validate(contour, params):
    holes = generate_pattern(contour, params)
    return validate(BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params))


def test_validate_warns_about_gap_between_rows_at_floor():
    from tests.front_rows_fixtures import GAP_PATTERN, design_with, grid_rows

    gaps = _codes(validate(design_with(grid_rows(15.0), pattern_params=GAP_PATTERN)), "floor_row_gap_excess")
    assert sorted(w["hole_id"] for w in gaps) == [f"2-{c:02d}" for c in range(1, 6)]
    assert gaps[0]["message"] == "Между рядами у подошвы 6,2 м — больше допустимого 3,6 м (b + 3%)."


def test_validate_gap_along_row_names_step_a():
    from tests.front_rows_fixtures import ACROSS_PATTERN, design_with, rows_across_face

    front = tuple(f"{r}-01" for r in range(1, 6))
    gaps = _codes(validate(design_with(rows_across_face(front), pattern_params=ACROSS_PATTERN)), "floor_row_gap_excess")
    assert sorted(w["hole_id"] for w in gaps) == [f"{r}-02" for r in range(1, 6)]
    assert gaps[0]["message"] == "Между рядами у подошвы 7,7 м — больше допустимого 5,2 м (a + 3%)."


def test_validate_gap_against_projected_lattice_names_grid_step():
    # 3-01 наклонена на 25°, соседи наискосок 2-01 и 4-01 — на 15°: у 3-02
    # наименьшее отношение — у соседа другого ряда, чей допуск — проекция
    # решётки на коридор (5 м при b = 3,5): подпись «шаг сетки», а не a или b.
    from design.models import Hole
    from tests.front_rows_fixtures import ACROSS_PATTERN, design_with, inclined_hole, rows_across_face

    holes = [
        Hole(**{**inclined_hole("3-01", h.collar.x, h.collar.y, h.row, 25, 180).__dict__, "col": h.col})
        if h.id == "3-01"
        else h
        for h in rows_across_face(("2-01", "4-01"))
    ]
    gaps = floor_row_gaps(design_with(holes, pattern_params=ACROSS_PATTERN))
    assert gaps["3-02"].step == "grid" and gaps["3-02"].excess
    found = [w for w in _codes(validate(design_with(holes, pattern_params=ACROSS_PATTERN)), "floor_row_gap_excess")]
    message = next(w["message"] for w in found if w["hole_id"] == "3-02")
    assert message == "Между рядами у подошвы 7,7 м — больше допустимого 5,2 м (шаг сетки + 3%)."


def test_gap_two_rows_apart_names_two_b():
    from tests.front_rows_fixtures import GAP_PATTERN, design_with, grid_rows

    gaps = floor_row_gaps(design_with(grid_rows(15.0, rows=3, tilted_row=2), pattern_params=GAP_PATTERN))
    assert {gaps[f"3-{c:02d}"].step for c in range(1, 6)} == {"2b"}


def _gap_cases():
    from tests.front_rows_fixtures import BASE, SLANT, STEP, STEP_FACE, _arc_contour, _contour_of, _poly_contour, _rect_contour

    contours = {
        "rect": _rect_contour(60.0, 40.0),
        "arc": _arc_contour(55.0),
        "poly": _poly_contour(55.0),
        "slant": _contour_of(SLANT, ((0, 1),), 55.0),
        "step": _contour_of(STEP, STEP_FACE, 55.0),
    }
    patterns = {
        "rect": {},
        "staggered": {"pattern": "staggered"},
        "across": {"row_azimuth_deg": 0.0},
        "oblique": {"row_azimuth_deg": 60.0},
        "variable": {"pattern": "variable", "row_params": [{}, {"burden_b_m": 4.5}, {}]},
        "square": {"pattern": "square"},
    }
    modes = {"plain": {}, "pair": {"front_rows_mode": "pair", "offset_from_face_m": 3.5}}
    cases = [
        pytest.param(contour, BASE | pattern | mode, True, id=f"{cn}-{pn}-{mn}")
        for cn, contour in contours.items()
        for pn, pattern in patterns.items()
        for mn, mode in modes.items()
    ]
    # Плавный переход у прямой, косой и ступенчатой бровки при рядах вдоль неё:
    # у подошвы — решётка, разрывов нет. На шахматке переход не применяется:
    # сетка как без ключей, и устья у кромки генератор не убирает — отступ там
    # не проверяется в этом тесте.
    for cn in ("rect", "slant", "step"):
        for pn in ("rect", "staggered", "variable", "square"):
            for count in (1, 2):
                params = BASE | patterns[pn] | {"front_rows_tilt_count": count}
                cases.append(pytest.param(contours[cn], params, pn != "staggered", id=f"{cn}-{pn}-taper{count}"))
    cases.append(pytest.param(contours["rect"], {k: v for k, v in BASE.items() if k != "spacing_a_m"} | {"pattern": "square", "burden_b_m": 3.0, "row_azimuth_deg": 0.0}, True, id="square-no-a"))
    return cases


@pytest.mark.parametrize("contour, params, check_crest", _gap_cases())
def test_regular_layouts_have_no_gap_or_crest_warnings(contour, params, check_crest):
    warnings = _validate(contour, params)
    assert not _codes(warnings, "floor_row_gap_excess")
    if check_crest:
        assert not _codes(warnings, "collar_too_close_to_crest")


@pytest.mark.parametrize("shape", ["arc", "poly"])
@pytest.mark.parametrize("count", [1, 2])
def test_taper_on_curved_crest_reports_only_row_breaks(shape, count):
    # Плавный переход даёт каждому участку ряда свой угол; на дуге и ломаной
    # бровке ряды ломаются там, где меняется угол (спецификация это
    # допускает), а коридор к подошве идёт вдоль ряда. Разрыв там настоящий,
    # но не больше разницы сдвигов соседних столбцов у подошвы: H·tg α = 2,68 м.
    from tests.front_rows_fixtures import BASE, _arc_contour, _poly_contour

    contour = (_arc_contour if shape == "arc" else _poly_contour)(55.0)
    params = BASE | {"front_rows_tilt_count": count}
    holes = generate_pattern(contour, params)
    gaps = floor_row_gaps(BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params))
    excess = [g for g in gaps.values() if g.excess]
    assert len(excess) <= 8
    assert all(g.value_m - g.allowed_m <= 10.0 * math.tan(math.radians(15.0)) for g in excess)


def test_variable_row_step_is_not_a_gap():
    from tests.front_rows_fixtures import BASE, _rect_contour

    params = BASE | {"pattern": "variable", "row_params": [{}, {"burden_b_m": 4.5}, {}]}
    assert not _codes(_validate(_rect_contour(60.0, 40.0), params), "floor_row_gap_excess")


def test_validate_warns_when_collar_is_too_close_to_crest():
    from tests.front_rows_fixtures import PATTERN, rect_contour, vertical_hole

    near = vertical_hole("1-01", x=10, y=0.6, row=0)
    ok = vertical_hole("1-03", x=30, y=1.3, row=0)

    def close(params):
        design = BlastDesign(design_id="t", contour=rect_contour(), holes=[near, ok], pattern_params=params)
        return _codes(validate(design), "collar_too_close_to_crest")

    found = close(PATTERN | {"min_crest_offset_m": 1})
    assert [w["hole_id"] for w in found] == ["1-01"]
    assert found[0]["message"] == "Устье 1-01 ближе 1 м к кромке уступа."
    found = close(PATTERN | {"min_crest_offset_m": 1.25})
    assert [w["message"] for w in found] == ["Устье 1-01 ближе 1,25 м к кромке уступа."]
    assert not close(PATTERN | {"min_crest_offset_m": 0.5})
    # Схема первого ряда задана — отступ по умолчанию 1 м.
    assert [w["hole_id"] for w in close(PATTERN | {"front_rows_mode": "pair"})] == ["1-01"]
    # Старый паспорт без ключей — не проверяется.
    assert not close(PATTERN)
    # Шахматка: переход генератор не применяет — его ключи проверку не включают.
    staggered = PATTERN | {"pattern": "staggered"}
    assert not close(staggered | {"front_rows_mode": "taper", "front_rows_tilt_count": 1})
    assert not close(staggered | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 15})
    assert [w["hole_id"] for w in close(staggered | {"front_rows_tilt_count": 1, "min_crest_offset_m": 1})] == ["1-01"]
    assert [w["hole_id"] for w in close(staggered | {"front_rows_mode": "pair"})] == ["1-01"]


@pytest.mark.parametrize("mode", [{"front_rows_mode": "pair"}, {"front_rows_tilt_count": 1}, {"front_rows_tilt_count": 2}])
def test_front_row_schemes_skip_collars_near_crest(mode):
    from design.toe_line import crest_geometry
    from tests.front_rows_fixtures import BASE, CONTOUR

    params = BASE | {"offset_from_face_m": 0.5} | mode
    crest = crest_geometry(CONTOUR)
    plain = generate_pattern(CONTOUR, BASE | {"offset_from_face_m": 0.5})
    assert any(shapely.Point(h.collar.x, h.collar.y).distance(crest) < 1.0 for h in plain)
    holes = generate_pattern(CONTOUR, params)
    grid = [h for h in holes if h.kind in ("production", "face_toe")]
    assert grid and all(shapely.Point(h.collar.x, h.collar.y).distance(crest) >= 1.0 - 1e-9 for h in grid)
    assert not _codes(_validate(CONTOUR, params), "collar_too_close_to_crest")


@pytest.mark.parametrize(
    "mode",
    [
        {"front_rows_mode": "pair"},
        {"front_rows_mode": "pair", "offset_from_face_m": 3.5},
        {"front_rows_tilt_count": 1},
        {"front_rows_tilt_count": 2},
        {"front_rows_tilt_count": 1, "front_rows_tilt_deg": 30},
        {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 30},
    ],
    ids=["pair", "pair-3.5", "taper1", "taper2", "taper1-30", "taper2-30"],
)
def test_front_row_schemes_pass_legacy_spacing_and_burden_checks(mode):
    """Пара у откоса и плавный переход не противоречат старым проверкам.

    Пара стоит в 1 м от своей вертикальной — не шаг сетки; у перехода решётка
    держится у подошвы (устья рангов сближены намеренно); ЛНС «забой — бровка»
    наклонной скважины у откоса заменена ЛСП и разрывом у подошвы.
    """
    from tests.front_rows_fixtures import BASE, CONTOUR

    warnings = _validate(CONTOUR, BASE | mode)
    assert not _codes(warnings, "hole_spacing")
    assert not _codes(warnings, "burden_too_small")


def test_vertical_hole_close_to_crest_still_warns_burden_too_small():
    from tests.front_rows_fixtures import GAP_PATTERN, design_with, vertical_hole

    holes = [vertical_hole("1-01", 10.0, 0.5, 0), vertical_hole("2-01", 10.0, 4.0, 1)]
    found = _codes(validate(design_with(holes, pattern_params=GAP_PATTERN)), "burden_too_small")
    assert [w["hole_id"] for w in found] == ["1-01"]


def test_shadowed_tilted_hole_keeps_burden_too_small():
    """Наклонная скважина без ЛСП (закрыта впереди стоящей) и не из перехода — ЛНС проверяется по-старому."""
    from design.toe_line import floor_checks
    from tests.front_rows_fixtures import GAP_PATTERN, design_with, inclined_hole, vertical_hole

    front = vertical_hole("1-01", 10.0, 0.2, 0)
    tilted = inclined_hole("2-01", 10.0, 5.3, 1, 20.0, 180, subdrill=3.0)
    design = design_with([front, tilted], pattern_params=GAP_PATTERN)
    assert "2-01" not in floor_checks(design)[0]
    found = [w["hole_id"] for w in _codes(validate(design), "burden_too_small")]
    assert "2-01" in found


def test_tilted_hole_with_floor_burden_skips_burden_too_small():
    from tests.front_rows_fixtures import GAP_PATTERN, design_with, inclined_hole

    tilted = inclined_hole("1-01", 10.0, 3.0, 0, 20.0, 180, subdrill=3.0)
    assert not _codes(validate(design_with([tilted], pattern_params=GAP_PATTERN)), "burden_too_small")


if __name__ == "__main__":
    unittest.main()
