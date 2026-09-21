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

    def test_huge_joint_angle_is_rejected_without_overflow(self):
        # float(10**400) кидает OverflowError, который не ловится как
        # ValueError выше по стеку (KuzRamSettingsSchema._within_bounds).
        with self.assertRaisesRegex(ValueError, "JPA"):
            kr.KuzRamSettings(joint_angle=10**400)


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

    def test_non_positive_a_is_rejected_with_russian_message(self):
        # RDI = 25·1,4 − 50 = −15; HF = 20/5 = 4; A = 0,06·(10 − 15 + 4) = −0,06 ≤ 0.
        settings = kr.KuzRamSettings(rock_factor_method="rmd10")
        with self.assertRaisesRegex(ValueError, "Фактор породы A"):
            kr.rock_factor(settings, **{**self.ROCK, "ucs_mpa": 20.0, "density_t_m3": 1.4})


class MeanFragmentTests(unittest.TestCase):
    def test_formula_and_exponent(self):
        re = 2.99 / 4.184
        x = kr.mean_fragment_mm(6.366, 1.0, 197.19, re, 19 / 20)
        self.assertAlmostEqual(x, 6.366 * 197.19 ** (1 / 6) * re ** (-19 / 20) * 10)
        older = kr.mean_fragment_mm(6.366, 1.0, 197.19, re, 19 / 30)
        self.assertLess(older, x)  # RE < 1: чем больше показатель, тем крупнее x50


class UniformityTests(unittest.TestCase):
    # Сетка без отклонения бурения, скважина 11 м с зарядом 80 %: L/H = 0,88.
    PATTERN = dict(
        spacing_to_burden=1.25, drill_deviation_m=0.0, charge_length_m=8.8, bench_height_m=10.0, correction=1.0,
    )

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

    def test_deviation_larger_than_burden_does_not_flip_sign(self):
        # (2,2 − 14·4/20) = −0,6 — уже отрицательный первый множитель; без
        # max(0, ...) (1 − 6/4) = −0,5 даёт произведение двух минусов, и итог
        # получался бы ≈ +0,26 — выше нижней границы n, а не нулём.
        n = kr.uniformity_index(
            burden_m=4.0, hole_diameter_mm=20.0, spacing_to_burden=1.25,
            drill_deviation_m=6.0, charge_length_m=8.0, bench_height_m=10.0, correction=1.0,
        )
        self.assertEqual(n.raw, 0.0)
        self.assertEqual(n.value, kr.MIN_UNIFORMITY_N)

    def test_usual_patterns_stay_above_floor(self):
        # Перенесено из PR #82: при обычной сетке W = 25–35·d индекс n лежит
        # в привычной полосе Каннингема и не упирается в нижнюю границу.
        # От диаметра n зависит только через W/d, поэтому перебирается W/d.
        for burden_to_diameter in (25.0, 30.0, 35.0):
            with self.subTest(burden_to_diameter=burden_to_diameter):
                n = kr.uniformity_index(
                    burden_m=burden_to_diameter * 0.1596, hole_diameter_mm=159.6, **self.PATTERN
                )
                self.assertEqual(n.value, n.raw)
                self.assertGreater(n.raw, 1.5)
                self.assertLess(n.raw, 2.0)

    def test_large_burden_to_diameter_hits_floor(self):
        # W/d = 8 м / 45 мм: 14·W/d ≈ 2,49 > 2,2 — n отрицательный уже без
        # отклонения бурения, остаётся нижняя граница.
        n = kr.uniformity_index(burden_m=8.0, hole_diameter_mm=45.0, **self.PATTERN)
        self.assertLess(n.raw, 0.0)
        self.assertEqual(n.value, kr.MIN_UNIFORMITY_N)

    def test_implausible_diameter_is_rejected(self):
        # Формула сама по себе безразлична к единицам: диаметр 0,1596 (метры)
        # дал бы n ≈ −290 и молчаливый упор в нижнюю границу, как в PR #82;
        # 159 600 (миллиметры, пересчитанные ещё раз) — правдоподобный n ≈ 2,07.
        for diameter in (0.1596, 19.9, 2000.1, 159600.0):
            with self.subTest(diameter=diameter):
                with self.assertRaisesRegex(ValueError, r"в миллиметрах, от 20 до 2000 мм"):
                    kr.uniformity_index(burden_m=3.54, hole_diameter_mm=diameter, **self.PATTERN)

    def test_non_finite_diameter_is_rejected_in_russian(self):
        for diameter in (math.nan, math.inf, -math.inf):
            with self.subTest(diameter=diameter):
                with self.assertRaisesRegex(ValueError, "конечным числом") as caught:
                    kr.uniformity_index(burden_m=3.54, hole_diameter_mm=diameter, **self.PATTERN)
                self.assertNotIn("nan", str(caught.exception))
                self.assertNotIn("inf", str(caught.exception))

    def test_diameter_bounds_are_accepted(self):
        self.assertEqual((kr.MIN_HOLE_DIAMETER_MM, kr.MAX_HOLE_DIAMETER_MM), (20.0, 2000.0))
        for diameter, burden_m in ((kr.MIN_HOLE_DIAMETER_MM, 0.6), (kr.MAX_HOLE_DIAMETER_MM, 60.0)):
            with self.subTest(diameter=diameter):
                n = kr.uniformity_index(burden_m=burden_m, hole_diameter_mm=diameter, **self.PATTERN)
                self.assertGreater(n.value, kr.MIN_UNIFORMITY_N)


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

    def test_target_at_upper_bound_is_clamped(self):
        # Бисекция сходится к границе log(10); exp() обратно может дать
        # 10.000000000000002 — без зажима result не проходит валидацию
        # KuzRamSettings (0,1–10).
        target = self._oversize_at(10.0)
        result = kr.solve_rock_factor_correction(self._oversize_at, target)
        self.assertLessEqual(result, 10.0)
        self.assertAlmostEqual(result, 10.0, places=6)


if __name__ == "__main__":
    unittest.main()
