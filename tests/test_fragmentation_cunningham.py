"""Kuz-Ram по Каннингему (EFEE 2005): фактор породы, x50, n, подбор C(A)."""
import math
import unittest

from simulation.fragmentation import cunningham as kr


class SettingsTests(unittest.TestCase):
    def test_defaults_are_massive_rock(self):
        s = kr.KuzRamSettings()
        self.assertEqual(s.rock_factor_method, "rmd50")
        self.assertEqual(s.strength_exponent, "19/20")
        self.assertAlmostEqual(s.exponent, 0.95)
        self.assertEqual(s.q_max_kg_m3, 2.0)
        self.assertEqual(kr.MODEL_VERSION, "kuzram-cunningham-1.0")

    def test_out_of_range_value_has_russian_message(self):
        with self.assertRaisesRegex(ValueError, r"Поправка C\(A\) — от 0,1 до 10\."):
            kr.KuzRamSettings(rock_factor_correction=12)
        with self.assertRaisesRegex(ValueError, r"Верхняя граница перебора q, кг/м³ — от 0,5 до 5\."):
            kr.KuzRamSettings(q_max_kg_m3=0.2)

    def test_unknown_choice_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "JPA"):
            kr.KuzRamSettings(joint_angle=25)
        with self.assertRaisesRegex(ValueError, "JCF"):
            kr.KuzRamSettings(joint_condition=3)
        with self.assertRaisesRegex(ValueError, "19/20 или 19/30"):
            kr.KuzRamSettings(strength_exponent="1/2")
        with self.assertRaisesRegex(ValueError, "способ"):
            kr.KuzRamSettings(rock_factor_method="code")


class RockFactorTests(unittest.TestCase):
    ROCK = dict(ucs_mpa=168.0, density_t_m3=2.9, fissuring_per_m=2.2, burden_m=3.54, spacing_m=4.425)

    def test_massive_rock(self):
        a = kr.rock_factor(kr.KuzRamSettings(), **self.ROCK)
        self.assertAlmostEqual(a.rdi, 22.5)
        self.assertAlmostEqual(a.hf, 33.6)
        self.assertEqual(a.rmd, 50.0)
        self.assertAlmostEqual(a.value, 0.06 * (50 + 22.5 + 33.6))

    def test_friable_rock_and_correction(self):
        settings = kr.KuzRamSettings(rock_factor_method="rmd10", rock_factor_correction=1.5)
        a = kr.rock_factor(settings, **self.ROCK)
        self.assertAlmostEqual(a.base, 0.06 * (10 + 22.5 + 33.6))
        self.assertAlmostEqual(a.value, a.base * 1.5)

    def test_manual(self):
        settings = kr.KuzRamSettings(rock_factor_method="manual", rock_factor_manual=7.5)
        a = kr.rock_factor(settings, **self.ROCK)
        self.assertIsNone(a.rmd)
        self.assertAlmostEqual(a.value, 7.5)

    def test_joint_factor_uses_spacing_bands(self):
        settings = kr.KuzRamSettings(rock_factor_method="joint_factor", joint_condition=1.5, joint_angle=40)
        # P = √(3,54 · 4,425) ≈ 3,96 м; шаг трещин = 1 / трещиноватость
        for fissuring, jps in [(20.0, 10.0), (5.0, 20.0), (2.2, 80.0), (0.2, 50.0)]:
            with self.subTest(fissuring=fissuring):
                a = kr.rock_factor(settings, **{**self.ROCK, "fissuring_per_m": fissuring})
                self.assertEqual(a.jps, jps)
                self.assertAlmostEqual(a.rmd, 1.5 * jps + 40)
                self.assertAlmostEqual(a.joint_spacing_m, 1 / fissuring)
                self.assertAlmostEqual(a.reduced_pattern_m, math.sqrt(3.54 * 4.425))

    def test_joint_factor_without_fissuring_is_massive(self):
        settings = kr.KuzRamSettings(rock_factor_method="joint_factor")
        a = kr.rock_factor(settings, **{**self.ROCK, "fissuring_per_m": 0.0})
        self.assertEqual(a.rmd, 50.0)
        self.assertIsNone(a.jps)


class MeanFragmentTests(unittest.TestCase):
    def test_formula_and_exponent(self):
        re = 2.99 / 4.184
        x = kr.mean_fragment_mm(6.366, 1.0, 197.19, re, 19 / 20)
        self.assertAlmostEqual(x, 6.366 * 197.19 ** (1 / 6) * re ** (-19 / 20) * 10)
        older = kr.mean_fragment_mm(6.366, 1.0, 197.19, re, 19 / 30)
        self.assertLess(older, x)  # RE < 1: чем больше показатель, тем крупнее x50


class UniformityTests(unittest.TestCase):
    def test_diameter_in_millimetres(self):
        n = kr.uniformity_index(
            burden_m=3.54, hole_diameter_mm=159.6, spacing_to_burden=1.25,
            drill_deviation_m=0.0, charge_length_m=8.8, bench_height_m=10.0, correction=1.0,
        )
        expected = (2.2 - 14 * 3.54 / 159.6) * math.sqrt(2.25 / 2) * 1.1 ** 0.1 * 0.88
        self.assertAlmostEqual(n.raw, expected)
        self.assertAlmostEqual(n.value, expected)
        self.assertAlmostEqual(n.charge_to_bench, 0.88)
        self.assertGreater(n.value, 1.7)

    def test_charge_longer_than_bench_is_capped(self):
        n = kr.uniformity_index(
            burden_m=3.0, hole_diameter_mm=150.0, spacing_to_burden=1.0,
            drill_deviation_m=0.0, charge_length_m=12.0, bench_height_m=10.0, correction=1.0,
        )
        self.assertEqual(n.charge_to_bench, 1.0)

    def test_drill_deviation_and_floor(self):
        base = dict(burden_m=3.0, hole_diameter_mm=150.0, spacing_to_burden=1.25,
                    charge_length_m=8.0, bench_height_m=10.0, correction=1.0)
        without = kr.uniformity_index(drill_deviation_m=0.0, **base)
        with_dev = kr.uniformity_index(drill_deviation_m=0.3, **base)
        self.assertAlmostEqual(with_dev.raw, without.raw * 0.9)
        crushed = kr.uniformity_index(drill_deviation_m=3.0, **base)
        self.assertLessEqual(crushed.raw, 0.0)
        self.assertEqual(crushed.value, kr.MIN_UNIFORMITY_N)


class SolveCorrectionTests(unittest.TestCase):
    @staticmethod
    def _oversize_at(correction: float) -> float:
        # негабарит растёт с C(A): x50 пропорционален поправке
        return kr.oversize(176.0 * correction, 1.78, 400.0)[1]

    def test_round_trip(self):
        target = self._oversize_at(1.3)
        self.assertAlmostEqual(kr.solve_rock_factor_correction(self._oversize_at, target), 1.3, places=6)

    def test_outside_settings_bounds_returns_none(self):
        # при C(A) = 10 негабарит ≈ 95 %, при C(A) = 0,1 — около 6·10⁻⁷⁷ %
        self.assertIsNone(kr.solve_rock_factor_correction(self._oversize_at, 99.9))
        self.assertIsNone(kr.solve_rock_factor_correction(self._oversize_at, 1e-100))


if __name__ == "__main__":
    unittest.main()
