"""Kuznetsov median size matches the historical BlastEX centimetre formula."""
import unittest

from simulation.fragmentation.kuznetsov import kuznetsov_x50_mm, rock_factor_A
from simulation.fragmentation.units import relative_weight_strength


class KuznetsovTests(unittest.TestCase):
    def test_rock_factor_matches_legacy_lilly_form(self):
        # A = 0.12 * (UCS/20 + density_t_m3*2.5 + 7)
        expected = 0.12 * (168 / 20 + 2.9 * 2.5 + 7)
        self.assertAlmostEqual(rock_factor_A(168, 2.9), expected)

    def test_x50_converts_cm_to_mm(self):
        A = rock_factor_A(168, 2.9)
        re_weight = relative_weight_strength(2.99)
        q = 0.8
        Q = 120.0
        x50_cm = A * q ** (-0.8) * Q ** (1 / 6) * re_weight ** (-19 / 30)
        self.assertAlmostEqual(kuznetsov_x50_mm(A, q, Q, re_weight), x50_cm * 10)

    def test_stronger_explosive_reduces_x50(self):
        A = rock_factor_A(150, 2.65)
        weak = kuznetsov_x50_mm(A, 0.7, 80.0, relative_weight_strength(2.5))
        strong = kuznetsov_x50_mm(A, 0.7, 80.0, relative_weight_strength(3.8))
        self.assertLess(strong, weak)

    def test_higher_powder_factor_reduces_x50(self):
        A = rock_factor_A(150, 2.65)
        re_weight = relative_weight_strength(3.8)
        coarse = kuznetsov_x50_mm(A, 0.5, 80.0, re_weight)
        fine = kuznetsov_x50_mm(A, 1.0, 80.0, re_weight)
        self.assertLess(fine, coarse)

    def test_rejects_non_positive_inputs(self):
        A = rock_factor_A(150, 2.65)
        with self.assertRaises(ValueError):
            kuznetsov_x50_mm(A, 0.0, 80.0, 1.0)
        with self.assertRaises(ValueError):
            kuznetsov_x50_mm(A, 0.7, 0.0, 1.0)

    def test_does_not_treat_kg_m3_as_t_m3(self):
        # 2700 kg/m³ passed in as if it were t/m³ would inflate A dramatically.
        a_si_mistake = rock_factor_A(150, 2700)
        a_correct = rock_factor_A(150, 2.7)
        self.assertGreater(a_si_mistake / a_correct, 100)


if __name__ == "__main__":
    unittest.main()
