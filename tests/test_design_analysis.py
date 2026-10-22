import unittest

from Blast import ExplosiveProperties
from design.analysis import charge_per_delay, estimate_ppv, summary, timing_isolines, validate
from design.charging import apply_charge_rules
from design.models import BenchSurface, BlastDesign, BlockContour, Point3
from design.pattern import generate_pattern
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
    from tests.test_toe_line import PATTERN, inclined_hole, rect_contour

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
    from tests.test_toe_line import PATTERN, rect_contour, vertical_hole

    hole = vertical_hole("1-01", x=10, y=0.2, row=0)  # ЛСП 2,88 < 0,8·3,7 = 2,96
    design = BlastDesign(design_id="t", contour=rect_contour(), holes=[hole], pattern_params=PATTERN)
    short = [w for w in validate(design) if w["code"] == "floor_burden_short"]
    assert [w["hole_id"] for w in short] == ["1-01"]
    assert short[0]["message"] == "ЛСП 2,9 м меньше допустимого 3,0 м (0,8·W, подошва по углу)."


def test_floor_burden_messages_show_two_decimals_when_rounding_hides_difference():
    from design.models import BlastDesign
    from tests.test_toe_line import PATTERN, rect_contour, vertical_hole

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


if __name__ == "__main__":
    unittest.main()
