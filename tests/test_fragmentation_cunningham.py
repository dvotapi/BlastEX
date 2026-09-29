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


class PredictPointTests(unittest.TestCase):
    """predict_point — это те же четыре функции модуля в фиксированном порядке."""

    ARGS = dict(
        ucs_mpa=120.0,
        density_t_m3=2.9,
        fissuring_per_m=0.3,
        burden_m=3.5,
        spacing_m=4.375,
        hole_diameter_mm=159.6,
        powder_factor_kg_m3=1.26,
        charge_mass_kg=105.0,
        re_weight=0.9,
        charge_length_m=8.8,
        bench_height_m=10.0,
        lump_size_mm=800.0,
    )

    def test_matches_step_by_step_calls(self):
        settings = kr.KuzRamSettings()
        args = dict(self.ARGS)
        rock = kr.rock_factor(
            settings,
            ucs_mpa=args["ucs_mpa"],
            density_t_m3=args["density_t_m3"],
            fissuring_per_m=args["fissuring_per_m"],
            burden_m=args["burden_m"],
            spacing_m=args["spacing_m"],
        )
        x50 = kr.mean_fragment_mm(
            rock.value, args["powder_factor_kg_m3"], args["charge_mass_kg"],
            args["re_weight"], settings.exponent,
        )
        n = kr.uniformity_index(
            burden_m=args["burden_m"],
            hole_diameter_mm=args["hole_diameter_mm"],
            spacing_to_burden=args["spacing_m"] / args["burden_m"],
            drill_deviation_m=settings.drill_deviation_m,
            charge_length_m=args["charge_length_m"],
            bench_height_m=args["bench_height_m"],
            correction=settings.uniformity_correction,
        )
        xc, oversize_pct = kr.oversize(x50, n.value, args["lump_size_mm"])

        point = kr.predict_point(settings, **args)

        self.assertEqual(point.rock, rock)
        self.assertEqual(point.x50_mm, x50)
        self.assertEqual(point.uniformity, n)
        self.assertEqual(point.characteristic_size_mm, xc)
        self.assertEqual(point.oversize_pct, oversize_pct)
        self.assertEqual(point.warnings, ())

    def test_missing_charge_length_keeps_uniformity_and_warns(self):
        args = dict(self.ARGS, charge_length_m=0.0)

        point = kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertEqual(point.uniformity.charge_to_bench, 1.0)
        full = kr.predict_point(
            kr.KuzRamSettings(), **dict(self.ARGS, charge_length_m=self.ARGS["bench_height_m"])
        )
        self.assertEqual(point.uniformity.value, full.uniformity.value)
        self.assertEqual(len(point.warnings), 1)
        self.assertIn("L/H", point.warnings[0])

    def test_negative_or_nan_charge_length_falls_back_with_one_warning(self):
        for bad in (-2.0, float("nan"), float("inf")):
            with self.subTest(charge_length_m=bad):
                point = kr.predict_point(kr.KuzRamSettings(), **dict(self.ARGS, charge_length_m=bad))
                self.assertEqual(point.uniformity.charge_to_bench, 1.0)
                self.assertEqual(len(point.warnings), 1)
                self.assertIn("L/H", point.warnings[0])

    def test_both_length_and_height_zero_warn_once(self):
        args = dict(self.ARGS, charge_length_m=0.0, bench_height_m=0.0)

        point = kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertEqual(len(point.warnings), 1)

    def test_bad_inputs_are_rejected_with_russian_message(self):
        cases = [
            ("burden_m", -1.0, "ЛНС"),
            ("burden_m", float("nan"), "ЛНС"),
            ("burden_m", float("inf"), "ЛНС"),
            ("powder_factor_kg_m3", float("nan"), "Удельный расход"),
            ("charge_mass_kg", float("nan"), "Масса заряда"),
            ("re_weight", 0.0, "Относительная сила ВВ"),
            ("re_weight", -0.5, "Относительная сила ВВ"),
            ("re_weight", float("nan"), "Относительная сила ВВ"),
            ("spacing_m", 0.0, "Расстояние между скважинами"),
            ("spacing_m", -1.0, "Расстояние между скважинами"),
            ("spacing_m", float("nan"), "Расстояние между скважинами"),
        ]
        for name, value, text in cases:
            with self.subTest(name=name, value=value):
                with self.assertRaises(ValueError) as ctx:
                    kr.predict_point(kr.KuzRamSettings(), **dict(self.ARGS, **{name: value}))
                self.assertIn(text, str(ctx.exception))

    def test_missing_bench_height_keeps_uniformity_and_warns(self):
        args = dict(self.ARGS, bench_height_m=0.0)

        point = kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertEqual(point.uniformity.charge_to_bench, 1.0)
        self.assertEqual(len(point.warnings), 1)

    def test_charge_longer_than_bench_does_not_raise_uniformity(self):
        args = dict(self.ARGS, charge_length_m=15.0, bench_height_m=10.0)

        point = kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertEqual(point.uniformity.charge_to_bench, 1.0)
        self.assertEqual(point.warnings, ())

    def test_zero_burden_is_rejected(self):
        args = dict(self.ARGS, burden_m=0.0)

        with self.assertRaises(ValueError) as ctx:
            kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertIn("ЛНС", str(ctx.exception))

    def test_zero_powder_factor_is_rejected(self):
        args = dict(self.ARGS, powder_factor_kg_m3=0.0)

        with self.assertRaises(ValueError) as ctx:
            kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertIn("Удельный расход", str(ctx.exception))

    def test_zero_charge_mass_is_rejected(self):
        args = dict(self.ARGS, charge_mass_kg=0.0)

        with self.assertRaises(ValueError) as ctx:
            kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertIn("Масса заряда", str(ctx.exception))

    def test_diameter_in_metres_is_rejected(self):
        args = dict(self.ARGS, hole_diameter_mm=0.1596)

        with self.assertRaises(ValueError) as ctx:
            kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertIn("миллиметрах", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
