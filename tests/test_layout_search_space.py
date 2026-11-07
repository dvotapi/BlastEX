"""Пространство вариантов перебора раскладки."""
import unittest

from design.back_layout import back_azimuth_deg
from design.geometry import crest_azimuth_deg
from design.layout_search.space import (
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
        # Шаблон «от тыла»: сдвиг вдоль ряда четвертями a, поворот ±5° шагом
        # 2,5° около азимута тыла, оба фланга. Отступ от тыла на вкладке пуст —
        # перебор пробует 20·d·k (ключа нет, его берёт генератор) и 0,5–0,8·b
        # (решение владельца 07.11.2026).
        contour = _contour([[0, 1]])
        ref = back_azimuth_deg(contour)
        cands = stage1(RECT, contour)
        back = _back(cands)
        self.assertEqual(len(back), len(BACK_TURNS_DEG) * 4 * 5 * 2)
        self.assertEqual(len(back), 200)
        self.assertEqual(len(cands), 288 + len(back))
        self.assertEqual({c.params.get("back_offset_m") for c in back}, {None, 2.5, 3.0, 3.5, 4.0})
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
        # Опора базы не важна: перебор пробует оба шаблона.
        base = {**RECT, "layout_anchor": "back"}
        cands = stage1(base, _contour([[0, 1]]))
        self.assertEqual([c.key() for c in cands], [c.key() for c in stage1(RECT, _contour([[0, 1]]))])

    def test_back_offset_from_base_is_kept(self):
        # Отступ от тыла с вкладки «Сетка» — у всех вариантов «от тыла» как есть,
        # в том числе вне прежних 0,5–0,8·b (решение владельца 07.11.2026); у
        # вариантов от бровки ключа нет.
        contour = _contour([[0, 1]])
        for own in (2.2, 3.045, 4.6):
            cands = stage1({**RECT, "layout_anchor": "back", "back_offset_m": own}, contour)
            self.assertEqual({c.params["back_offset_m"] for c in _back(cands)}, {own})
            self.assertTrue(all("back_offset_m" not in c.params for c in _crest(cands)))
            seed = _back(cands)[0]
            self.assertEqual({c.params["back_offset_m"] for c in stage3([seed], RECT, contour)}, {own})
        # Неверное значение — как пустое поле: 20·d·k (без ключа) и доли b.
        for bad in (0, -1, None, "", "x"):
            back = _back(stage1({**RECT, "back_offset_m": bad}, contour))
            self.assertEqual({c.params.get("back_offset_m") for c in back}, {None, 2.5, 3.0, 3.5, 4.0})

    def test_stage3_back_seed(self):
        contour = _contour([[0, 1]])
        ref = back_azimuth_deg(contour)
        # Семя в середине диапазонов: поворот 0, сдвиг a/4.
        seed = next(
            c for c in _back(stage1(RECT, contour))
            if abs(_turn(c.params["row_azimuth_deg"], ref)) < 1e-9 and c.params.get("grid_shift_along_m") == 1.0
        )
        out = stage3([seed], RECT, contour)
        # Геометрия 3 × 3 и шаги a × b при геометрии семени (3 × 3 − 1).
        self.assertEqual(len(out), 9 + 8)
        for c in out:
            self.assertEqual(c.params["layout_anchor"], "back")
            self.assertEqual(c.cut_flank, seed.cut_flank)
            self.assertNotIn("offset_from_face_m", c.params)
            self.assertNotIn("front_rows_mode", c.params)
            self.assertNotIn("back_offset_m", c.params)
            self.assertIn(c.params["spacing_a_m"], (3.88, 4.0, 4.12))
            self.assertIn(c.params["burden_b_m"], (4.85, 5.0, 5.15))
            if c.params["spacing_a_m"] != 4.0 or c.params["burden_b_m"] != 5.0:
                # Шаги подстраиваются при геометрии семени.
                self.assertEqual(c.params["row_azimuth_deg"], seed.params["row_azimuth_deg"])
                self.assertEqual(c.params.get("grid_shift_along_m"), seed.params.get("grid_shift_along_m"))
        self.assertEqual({c.params.get("grid_shift_along_m", 0.0) for c in out}, {0.5, 1.0, 1.5})
        self.assertEqual({round(_turn(c.params["row_azimuth_deg"], ref), 6) for c in out}, {-1.25, 0.0, 1.25})
        # Квадратная: шаг один — геометрия 9 и a × {0,97; 1,03}; b не пишется.
        square_seed = next(
            c for c in _back(stage1(SQUARE, contour)) if abs(_turn(c.params["row_azimuth_deg"], ref)) < 1e-9
        )
        square = stage3([square_seed], SQUARE, contour)
        self.assertEqual(len(square), 9 + 2)
        self.assertTrue(all("burden_b_m" not in c.params for c in square))

    def test_stage3_back_limits(self):
        # Подстройка не выводит поворот за ±5° от тыла.
        contour = _contour([[0, 1]])
        ref = back_azimuth_deg(contour)
        edge = next(
            c for c in _back(stage1(RECT, contour)) if abs(_turn(c.params["row_azimuth_deg"], ref) - 5.0) < 1e-9
        )
        out = stage3([edge], RECT, contour)
        for c in out:
            self.assertLessEqual(abs(_turn(c.params["row_azimuth_deg"], ref)), 5.0 + 1e-6)
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
