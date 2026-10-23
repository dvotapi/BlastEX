"""Пространство вариантов перебора раскладки."""
import unittest

from design.geometry import crest_azimuth_deg
from design.layout_search.space import Candidate, stage1, stage2, stage3
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


class SpaceTests(unittest.TestCase):
    def test_stage1_size(self):
        contour = _contour([[0, 1]])
        ref = crest_azimuth_deg(contour)
        cands = stage1(RECT, contour)
        self.assertEqual(len(cands), 9 * 4 * 4 * 2)
        for c in cands:
            self.assertNotIn("first_row_burden_m", c.params)
            self.assertNotIn("front_rows_mode", c.params)
            self.assertGreaterEqual(c.params["offset_from_face_m"], 1.5)
            diff = (c.params["row_azimuth_deg"] - ref + 180) % 360 - 180
            self.assertLessEqual(abs(diff), 10.0 + 1e-6)
        self.assertEqual({c.cut_flank for c in cands}, {"left", "right"})
        self.assertTrue(any("grid_shift_along_m" not in c.params for c in cands))

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
        seed = stage1(RECT, _contour([[0, 1]]))[0]
        out = stage2([seed], RECT)
        self.assertEqual(len(out), 9)
        self.assertEqual(sum(c.params.get("front_rows_mode") == "pair" for c in out), 4)
        self.assertEqual(sum(c.params.get("front_rows_mode") == "taper" for c in out), 4)
        self.assertTrue(all(c.cut_flank == seed.cut_flank for c in out))

    def test_staggered_skips_taper(self):
        base = {**RECT, "pattern": "staggered"}
        seed = stage1(base, _contour([[0, 1]]))[0]
        out = stage2([seed], base)
        self.assertEqual(len(out), 5)
        self.assertFalse(any(c.params.get("front_rows_mode") == "taper" for c in out))

    def test_stage3_steps_within_3_percent(self):
        seed = stage2([stage1(RECT, _contour([[0, 1]]))[5]], RECT)[1]
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

    def test_square_single_multiplier(self):
        # Семя с отступом выше o0: срез по o0 не схлопывает варианты.
        seed = stage1(SQUARE, _contour([[0, 1]]))[-1]
        out = stage3([seed], SQUARE)
        self.assertEqual(len(out), 81)
        self.assertEqual({c.params["spacing_a_m"] for c in out}, {3.88, 4.0, 4.12})
        for c in out:
            self.assertNotIn("burden_b_m", c.params)
        # У семени на нижней границе отступа часть вариантов совпадает после среза.
        low = stage1(SQUARE, _contour([[0, 1]]))[0]
        self.assertLessEqual(len(stage3([low], SQUARE)), 81)

    def test_zero_shift_key_absent(self):
        seed = stage1(RECT, _contour([[0, 1]]))[0]
        for c in stage3([seed], RECT):
            if "grid_shift_along_m" in c.params:
                self.assertGreater(abs(c.params["grid_shift_along_m"]), 1e-9)

    def test_dedup(self):
        seed = stage1(RECT, _contour([[0, 1]]))[0]
        twin = Candidate(dict(seed.params, row_azimuth_deg=seed.params["row_azimuth_deg"] + 0.001), seed.cut_flank)
        self.assertEqual(seed.key(), twin.key())
        self.assertEqual(len(stage2([seed, twin], RECT)), 9)
        keys = [c.key() for c in stage1(RECT, _contour([[0, 1]]))]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
