"""Пространство вариантов перебора раскладки."""
import unittest

from design.back_layout import back_azimuth_deg
from design.geometry import crest_azimuth_deg
from design.layout_search.space import (
    BACK_OFFSET_RATIOS,
    BACK_TURNS_DEG,
    Candidate,
    interleave_templates,
    is_back,
    stage1,
    stage2,
    stage3,
)
from design.models import BenchSurface, BlockContour, Point3


def _contour(free_faces):
    verts = [(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
        free_faces=free_faces,
    )


RECT = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 5.0, "row_azimuth_deg": 33.0,
        "first_row_burden_m": 3.0, "min_crest_offset_m": 1.5}
SQUARE = {"pattern": "square", "spacing_a_m": 4.0, "min_crest_offset_m": 1.5}


def _crest(cands):
    """Варианты шаблона от бровки."""
    return [c for c in cands if not is_back(c.params)]


def _back(cands):
    """Варианты шаблона «от тыла»."""
    return [c for c in cands if is_back(c.params)]


def _turn(azimuth: float, ref: float | None) -> float:
    assert ref is not None
    return (azimuth - ref + 180.0) % 360.0 - 180.0


class SpaceTests(unittest.TestCase):
    def test_stage1_size(self):
        contour = _contour([[0, 1]])
        ref = crest_azimuth_deg(contour)
        cands = _crest(stage1(RECT, contour))
        self.assertEqual(len(cands), 9 * 4 * 4 * 2)
        for c in cands:
            self.assertNotIn("first_row_burden_m", c.params)
            self.assertNotIn("front_rows_mode", c.params)
            self.assertNotIn("layout_anchor", c.params)
            self.assertNotIn("back_offset_m", c.params)
            self.assertGreaterEqual(c.params["offset_from_face_m"], 1.5)
            self.assertLessEqual(abs(_turn(c.params["row_azimuth_deg"], ref)), 10.0 + 1e-6)
        self.assertEqual({c.cut_flank for c in cands}, {"left", "right"})
        self.assertTrue(any("grid_shift_along_m" not in c.params for c in cands))

    def test_stage1_back_variants(self):
        # Шаблон «от тыла»: отступ от тыла 0,5–0,8·b, сдвиг вдоль ряда
        # четвертями a, поворот ±5° шагом 2,5° около азимута тыла, оба фланга.
        contour = _contour([[0, 1]])
        ref = back_azimuth_deg(contour)
        cands = stage1(RECT, contour)
        back = _back(cands)
        self.assertEqual(len(back), len(BACK_TURNS_DEG) * len(BACK_OFFSET_RATIOS) * 4 * 2)
        self.assertEqual(len(back), 5 * 4 * 4 * 2)
        self.assertEqual(len(cands), 288 + len(back))
        self.assertEqual({c.params["back_offset_m"] for c in back}, {2.5, 3.0, 3.5, 4.0})
        self.assertEqual({c.cut_flank for c in back}, {"left", "right"})
        self.assertEqual({c.params.get("grid_shift_along_m", 0.0) for c in back}, {0.0, 1.0, 2.0, 3.0})
        self.assertEqual(
            {round(_turn(c.params["row_azimuth_deg"], ref), 6) for c in back}, {-5.0, -2.5, 0.0, 2.5, 5.0}
        )
        for c in back:
            self.assertEqual(c.params["layout_anchor"], "back")
            for key in ("front_rows_mode", "front_rows_tilt_count", "front_rows_tilt_deg",
                        "first_row_burden_m", "offset_from_face_m"):
                self.assertNotIn(key, c.params)
            self.assertEqual(c.params["min_crest_offset_m"], 1.5)
            self.assertEqual(c.params["spacing_a_m"], 4.0)
            self.assertEqual(c.params["burden_b_m"], 5.0)

    def test_back_keeps_base_tilt_limit(self):
        # У «от тыла» `front_rows_tilt_deg` — предел наклона конца эшелона
        # (0 — без наклона): перебор берёт его из базы, а не умолчание.
        contour = _contour([[0, 1]])
        back = _back(stage1({**RECT, "front_rows_tilt_deg": 0}, contour))
        self.assertTrue(back)
        self.assertTrue(all(c.params["front_rows_tilt_deg"] == 0 for c in back))
        self.assertTrue(all("front_rows_tilt_deg" not in c.params for c in _back(stage1(RECT, contour))))
        # Варианты от бровки угол схемы первого ряда выбирают сами (этап 2).
        self.assertTrue(all("front_rows_tilt_deg" not in c.params for c in _crest(stage1({**RECT, "front_rows_tilt_deg": 0}, contour))))

    def test_stage1_ignores_base_anchor(self):
        # Опора базы не важна: перебор пробует оба шаблона, отступ от тыла —
        # свой, а не базы.
        base = {**RECT, "layout_anchor": "back", "back_offset_m": 2.0}
        cands = stage1(base, _contour([[0, 1]]))
        self.assertEqual([c.key() for c in cands], [c.key() for c in stage1(RECT, _contour([[0, 1]]))])

    def test_back_only_for_square_and_rectangular_with_back_and_face(self):
        contour = _contour([[0, 1]])
        self.assertTrue(_back(stage1(SQUARE, contour)))
        # Нет ключа вида — квадратная, как у генератора.
        self.assertTrue(_back(stage1({k: v for k, v in SQUARE.items() if k != "pattern"}, contour)))
        for pattern in ("staggered", "variable", "domain_dependent"):
            with self.subTest(pattern=pattern):
                self.assertFalse(_back(stage1({**RECT, "pattern": pattern}, contour)))
        # Все стороны свободные — тыла нет; свободной поверхности нет — эшелонам не к чему идти.
        self.assertFalse(_back(stage1(RECT, _contour([[0, 1], [1, 2], [2, 3], [3, 0]]))))
        self.assertFalse(_back(stage1(RECT, _contour([]))))

    def test_interleave_templates(self):
        crest = [Candidate({"k": i}, "left") for i in range(3)]
        back = [Candidate({"k": 10 + i, "layout_anchor": "back"}, "left") for i in range(5)]
        out = interleave_templates(crest + back)
        self.assertEqual([c.params["k"] for c in out], [0, 10, 1, 11, 2, 12, 13, 14])
        self.assertEqual(interleave_templates(crest), crest)
        self.assertEqual(interleave_templates(back), back)

    def test_crest_azimuth_min_concentration(self):
        # Один откос — направление чёткое при любом пороге.
        self.assertAlmostEqual(crest_azimuth_deg(_contour([[0, 1]]), min_concentration=0.5), 90.0)
        # Откосы 40 и 30 м под прямым углом: сосредоточенность (40 − 30)/70 ≈ 0,14.
        corner = _contour([[0, 1], [1, 2]])
        self.assertIsNotNone(crest_azimuth_deg(corner))
        self.assertIsNone(crest_azimuth_deg(corner, min_concentration=0.5))
        self.assertIsNotNone(crest_azimuth_deg(corner, min_concentration=0.1))

    def test_stage1_without_face_uses_base_azimuth(self):
        cands = stage1(RECT, _contour([]))
        azs = {c.params["row_azimuth_deg"] for c in cands}
        self.assertIn(33.0, azs)
        self.assertEqual(min(azs), 23.0)
        self.assertEqual(max(azs), 43.0)

    def test_azimuth_wraps_near_zero(self):
        # Опорный азимут у самого 360°: 360 не появляется, 0 и 357,5 — да.
        cands = stage1({**RECT, "row_azimuth_deg": 359.99999}, _contour([]))
        azs = {c.params["row_azimuth_deg"] for c in cands}
        self.assertTrue(all(0.0 <= az < 360.0 for az in azs), azs)
        self.assertIn(0.0, azs)
        self.assertIn(357.5, azs)
        self.assertEqual(len(azs), 9)
        # Подстройка ±1,25° вокруг семени с азимутом 0 / 358,75.
        seed = next(c for c in cands if c.params["row_azimuth_deg"] == 0.0)
        fine = {c.params["row_azimuth_deg"] for c in stage3([seed], RECT)}
        self.assertEqual(fine, {358.75, 0.0, 1.25})
        seed = Candidate({**seed.params, "row_azimuth_deg": 358.75}, seed.cut_flank)
        fine = {c.params["row_azimuth_deg"] for c in stage3([seed], RECT)}
        self.assertEqual(fine, {357.5, 358.75, 0.0})

    def test_stage2_variants_per_seed(self):
        seed = _crest(stage1(RECT, _contour([[0, 1]])))[0]
        out = stage2([seed], RECT)
        # Пара одна: угол генератор подбирает сам (наименьший до ЛСП ≈ W).
        self.assertEqual(len(out), 6)
        self.assertEqual(sum(c.params.get("front_rows_mode") == "pair" for c in out), 1)
        self.assertEqual(sum(c.params.get("front_rows_mode") == "taper" for c in out), 4)
        self.assertTrue(all(c.cut_flank == seed.cut_flank for c in out))

    def test_stage2_back_seed_unchanged(self):
        # Схемы первого ряда к шаблону «от тыла» не применяются.
        seed = _back(stage1(RECT, _contour([[0, 1]])))[0]
        self.assertEqual(stage2([seed], RECT), [seed])

    def test_staggered_skips_taper(self):
        base = {**RECT, "pattern": "staggered"}
        seed = stage1(base, _contour([[0, 1]]))[0]
        out = stage2([seed], base)
        self.assertEqual(len(out), 2)
        self.assertFalse(any(c.params.get("front_rows_mode") == "taper" for c in out))

    def test_stage3_steps_within_3_percent(self):
        seed = stage2([_crest(stage1(RECT, _contour([[0, 1]])))[5]], RECT)[1]
        out = stage3([seed], RECT)
        self.assertEqual(len(out), 243)
        for c in out:
            self.assertGreaterEqual(c.params["spacing_a_m"], 4.0 * 0.97 - 1e-6)
            self.assertLessEqual(c.params["spacing_a_m"], 4.0 * 1.03 + 1e-6)
            self.assertGreaterEqual(c.params["burden_b_m"], 5.0 * 0.97 - 1e-6)
            self.assertLessEqual(c.params["burden_b_m"], 5.0 * 1.03 + 1e-6)
            self.assertGreaterEqual(c.params["offset_from_face_m"], 1.5)
            for k in ("front_rows_mode", "front_rows_tilt_count", "front_rows_tilt_deg"):
                self.assertEqual(c.params.get(k), seed.params.get(k))
            self.assertEqual(c.cut_flank, seed.cut_flank)
            self.assertNotIn("layout_anchor", c.params)

    def test_stage3_back_seed(self):
        contour = _contour([[0, 1]])
        ref = back_azimuth_deg(contour)
        # Семя в середине диапазонов: отступ 0,6·b, поворот 0, сдвиг a/4.
        seed = next(
            c for c in _back(stage1(RECT, contour))
            if c.params["back_offset_m"] == 3.0 and abs(_turn(c.params["row_azimuth_deg"], ref)) < 1e-9
            and c.params.get("grid_shift_along_m") == 1.0
        )
        out = stage3([seed], RECT, contour)
        # Геометрия 3 × 3 × 3 и шаги a × b при геометрии семени (3 × 3 − 1).
        self.assertEqual(len(out), 27 + 8)
        for c in out:
            self.assertEqual(c.params["layout_anchor"], "back")
            self.assertEqual(c.cut_flank, seed.cut_flank)
            self.assertNotIn("offset_from_face_m", c.params)
            self.assertNotIn("front_rows_mode", c.params)
            self.assertIn(c.params["spacing_a_m"], (3.88, 4.0, 4.12))
            self.assertIn(c.params["burden_b_m"], (4.85, 5.0, 5.15))
            if c.params["spacing_a_m"] != 4.0 or c.params["burden_b_m"] != 5.0:
                # Шаги подстраиваются при геометрии семени.
                self.assertEqual(c.params["row_azimuth_deg"], seed.params["row_azimuth_deg"])
                self.assertEqual(c.params["back_offset_m"], seed.params["back_offset_m"])
                self.assertEqual(c.params.get("grid_shift_along_m"), seed.params.get("grid_shift_along_m"))
        self.assertEqual({c.params["back_offset_m"] for c in out}, {2.75, 3.0, 3.25})
        self.assertEqual({c.params.get("grid_shift_along_m", 0.0) for c in out}, {0.5, 1.0, 1.5})
        self.assertEqual({round(_turn(c.params["row_azimuth_deg"], ref), 6) for c in out}, {-1.25, 0.0, 1.25})
        # Квадратная: шаг один — геометрия 27 и a × {0,97; 1,03}; b не пишется.
        square_seed = next(
            c for c in _back(stage1(SQUARE, contour))
            if c.params["back_offset_m"] == 2.4 and abs(_turn(c.params["row_azimuth_deg"], ref)) < 1e-9
        )
        square = stage3([square_seed], SQUARE, contour)
        self.assertEqual(len(square), 27 + 2)
        self.assertTrue(all("burden_b_m" not in c.params for c in square))

    def test_stage3_back_limits(self):
        # Подстройка не выводит поворот за ±5° от тыла и отступ за 0,5–0,8·b.
        contour = _contour([[0, 1]])
        ref = back_azimuth_deg(contour)
        edge = next(
            c for c in _back(stage1(RECT, contour))
            if c.params["back_offset_m"] == 4.0 and abs(_turn(c.params["row_azimuth_deg"], ref) - 5.0) < 1e-9
        )
        out = stage3([edge], RECT, contour)
        for c in out:
            self.assertLessEqual(abs(_turn(c.params["row_azimuth_deg"], ref)), 5.0 + 1e-6)
            self.assertLessEqual(c.params["back_offset_m"], 4.0 + 1e-9)
        self.assertEqual({c.params["back_offset_m"] for c in out}, {3.75, 4.0})
        self.assertEqual({round(_turn(c.params["row_azimuth_deg"], ref), 6) for c in out}, {3.75, 5.0})

    def test_square_single_multiplier(self):
        # Семя с отступом выше o0: срез по o0 не схлопывает варианты.
        seed = _crest(stage1(SQUARE, _contour([[0, 1]])))[-1]
        out = stage3([seed], SQUARE)
        self.assertEqual(len(out), 81)
        self.assertEqual({c.params["spacing_a_m"] for c in out}, {3.88, 4.0, 4.12})
        for c in out:
            self.assertNotIn("burden_b_m", c.params)
        # У семени на нижней границе отступа часть вариантов совпадает после среза.
        low = _crest(stage1(SQUARE, _contour([[0, 1]])))[0]
        self.assertLessEqual(len(stage3([low], SQUARE)), 81)

    def test_variable_and_domain_steps_not_searched(self):
        # Переменная сетка и сетка по доменам берут шаги из строк и доменов:
        # множители общих a и b на них не действуют, этап 3 их не перебирает.
        for pattern in ("variable", "domain_dependent"):
            with self.subTest(pattern=pattern):
                base = {**RECT, "pattern": pattern}
                seed = stage1(base, _contour([[0, 1]]))[-1]
                out = stage3([seed], base)
                self.assertEqual(len(out), 27)
                self.assertEqual({c.params["spacing_a_m"] for c in out}, {4.0})
                self.assertEqual({c.params["burden_b_m"] for c in out}, {5.0})

    def test_zero_shift_key_absent(self):
        contour = _contour([[0, 1]])
        for seed in (_crest(stage1(RECT, contour))[0], _back(stage1(RECT, contour))[0]):
            for c in stage3([seed], RECT, contour):
                if "grid_shift_along_m" in c.params:
                    self.assertGreater(abs(c.params["grid_shift_along_m"]), 1e-9)

    def test_dedup(self):
        seed = _crest(stage1(RECT, _contour([[0, 1]])))[0]
        twin = Candidate(dict(seed.params, row_azimuth_deg=seed.params["row_azimuth_deg"] + 0.001), seed.cut_flank)
        self.assertEqual(seed.key(), twin.key())
        self.assertEqual(len(stage2([seed, twin], RECT)), 6)
        keys = [c.key() for c in stage1(RECT, _contour([[0, 1]]))]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
