"""Контрольный пример Kuz-Ram по Каннингему (TASK: проверка cunningham.py).

x50 [см] = A · q^−0,8 · Q^(1/6) · (115/RWS)^(19/20), RWS — массовая сила ВВ
относительно ANFO, %. Для эмульсии с теплотой взрыва 2990 кДж/кг при
Q_ANFO = 3800 кДж/кг RWS = 78,7 %.

Пример проходит через BlastEngine.kuzram_point — ту же цепочку, что и подбор
q на листе «Расчёт»: коронка 125 мм × 1,03 = 128,75 мм, H = 10 м без
перебура, L = 0,8·H = 8 м, ρВВ = 1,12 т/м³ → Q ≈ 116,65 кг; a/W = 1.
"""
import math
import unittest

from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams
from simulation.fragmentation import cunningham as kr

TOLERANCE = 0.005  # ±0,5 % от ожидаемого значения

ANFO_HEAT_MJ_KG = 3.8
HEAT_MJ_KG = 2.99
RWS_PCT = 100.0 * HEAT_MJ_KG / ANFO_HEAT_MJ_KG  # 78,7 %

A = 8.0
Q_KG_M3 = 1.30
EXPECTED_X50_MM = 205.6
EXPECTED_N = 1.514
EXPECTED_OVERSIZE_PCT = 15.0


def _engine() -> BlastEngine:
    # Порода не участвует: A задан вручную.
    rock = RockProperties("контрольный пример", 2.7, 150.0, 0.0)
    explosive = ExplosiveProperties("эмульсия 2990 кДж/кг", 1.12, HEAT_MJ_KG)
    target = TargetParams(
        lump_size_mm=400.0,
        hole_diameter_mm=0.0,
        overdrill_m=0.0,
        hole_oversize_coeff=1.03,
        spacing_coeff_m=1.0,
        bench_height_m=10.0,
    )
    return BlastEngine(rock, explosive, target)


SETTINGS = kr.KuzRamSettings(rock_factor_method="manual", rock_factor_manual=A)


class ControlExampleTests(unittest.TestCase):
    def setUp(self):
        self.point = _engine().kuzram_point(125.0, Q_KG_M3, SETTINGS)

    def assertWithin(self, actual: float, expected: float, label: str) -> None:
        self.assertLessEqual(
            abs(actual - expected) / expected,
            TOLERANCE,
            f"{label}: получено {actual:.4f}, ожидалось {expected} ± 0,5 %",
        )

    def test_input_geometry(self):
        self.assertWithin(self.point.hole_diameter_mm, 128.75, "d, мм")
        self.assertWithin(self.point.charge_length_m, 8.0, "L, м")
        self.assertWithin(self.point.charge_mass_kg, 116.65, "Q, кг")
        self.assertWithin(self.point.burden_m, 2.996, "W, м")
        self.assertWithin(self.point.spacing_m, 2.996, "a, м")

    def test_rws_of_emulsion(self):
        self.assertAlmostEqual(RWS_PCT, 78.7, places=1)

    def test_mean_fragment(self):
        self.assertWithin(self.point.x50_mm, EXPECTED_X50_MM, "x50, мм")

    def test_mean_fragment_matches_cunningham_formula(self):
        p = self.point
        x50_cm = A * Q_KG_M3 ** -0.8 * p.charge_mass_kg ** (1 / 6) * (115.0 / RWS_PCT) ** (19 / 20)
        self.assertWithin(p.x50_mm, x50_cm * 10.0, "x50 против формулы с 115/RWS, мм")

    def test_uniformity_index(self):
        self.assertWithin(self.point.uniformity_n, EXPECTED_N, "n")

    def test_oversize(self):
        self.assertWithin(self.point.oversize_pct, EXPECTED_OVERSIZE_PCT, "негабарит > 400 мм, %")

    def test_expected_numbers_are_self_consistent(self):
        # Ожидаемые x50 и n сами дают ожидаемый негабарит по Розину–Раммлеру.
        xc = EXPECTED_X50_MM / math.log(2) ** (1 / EXPECTED_N)
        oversize = 100.0 * math.exp(-((400.0 / xc) ** EXPECTED_N))
        self.assertWithin(oversize, EXPECTED_OVERSIZE_PCT, "негабарит из ожидаемых x50 и n, %")


if __name__ == "__main__":
    unittest.main()
