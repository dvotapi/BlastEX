"""Подбор q в Blast.py: Kuz-Ram по Каннингему и расчёт «до исправления»."""
import json
import math
import unittest
from pathlib import Path

from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams, _legacy_uniformity_raw
from simulation.fragmentation import cunningham as kr
from simulation.fragmentation.kuzram import MIN_UNIFORMITY_N as LEGACY_MIN_UNIFORMITY_N
from simulation.fragmentation.kuzram import cunningham_uniformity_n

FIXTURES = Path(__file__).parent / "fixtures"


def _engine(case: dict) -> BlastEngine:
    rock, ex = case["rock"], case["explosive"]
    return BlastEngine(
        RockProperties("r", rock["density_t_m3"], rock["ucs_mpa"], rock["fissuring_ff"]),
        ExplosiveProperties("e", ex["density_t_m3"], ex["power_mj_kg"]),
        TargetParams(hole_diameter_mm=0, **case["target"]),
    )


def _gabbro() -> BlastEngine:
    return BlastEngine(
        RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
        ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99),
        TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0),
    )


class LegacyOptimizerTests(unittest.TestCase):
    def test_matches_blast_py_before_the_fix(self):
        data = json.loads((FIXTURES / "blast_legacy_golden.json").read_text(encoding="utf-8"))
        for case in data["cases"]:
            engine = _engine(case)
            for row in case["rows"]:
                with self.subTest(crown=row["crown_mm"], target=case["target"]):
                    result = engine.optimize_blast_legacy(row["crown_mm"], case["threshold"])
                    self.assertEqual(round(result.point.q_kg_m3, 2), row["q"])
                    self.assertEqual(round(result.point.burden_m, 2), row["burden_m"])
                    self.assertEqual(round(result.point.x50_mm, 1), row["x50_mm"])
                    self.assertEqual(round(result.point.oversize_pct, 2), row["oversize_pct"])
                    self.assertEqual(result.reached, row["reached"])

    def test_legacy_n_is_clamped_by_metre_diameter(self):
        result = _gabbro().optimize_blast_legacy(152, 5.0)
        self.assertEqual(result.point.uniformity_n, 0.8)
        self.assertLess(result.point.uniformity_n_raw, -300)
        self.assertEqual(round(result.point.q_kg_m3, 2), 1.34)
        self.assertIsNone(result.point.rock_factor)
        self.assertEqual(result.point.strength_exponent, "19/30")


class LegacyUniformityRawTests(unittest.TestCase):
    """R3: _legacy_uniformity_raw не должен разойтись с cunningham_uniformity_n."""

    def test_matches_kuzram_module_when_not_clamped(self):
        # burden/diameter и a/W подобраны так, чтобы (2,2 − 14·W/d) не
        # клэмпилось полом 0,8 в cunningham_uniformity_n — тогда обе функции
        # обязаны совпасть побитово (drill_deviation_m по умолчанию 0).
        cases = [
            (0.01, 0.16, 1.25),
            (0.005, 0.2, 1.0),
        ]
        for burden_m, diameter_m, spacing_to_burden in cases:
            with self.subTest(burden_m=burden_m, diameter_m=diameter_m, spacing_to_burden=spacing_to_burden):
                raw = _legacy_uniformity_raw(burden_m, diameter_m, spacing_to_burden)
                clamped = cunningham_uniformity_n(burden_m, diameter_m, spacing_to_burden)
                self.assertGreater(raw, LEGACY_MIN_UNIFORMITY_N)  # клэмп и правда не сработал
                self.assertEqual(raw, clamped)


class KuzRamOptimizerTests(unittest.TestCase):
    FIELDS = [
        ("burden_m", "burden_m"),
        ("x50_mm", "x50_mm"),
        ("uniformity_n", "n"),
        ("oversize_pct", "oversize_pct"),
        ("rock_factor_a", "rock_factor_a"),
    ]

    def test_matches_reference_implementation(self):
        data = json.loads((FIXTURES / "kuzram_cunningham_golden.json").read_text(encoding="utf-8"))
        for case in data["cases"]:
            engine = _engine(case)
            settings = kr.KuzRamSettings(**case["settings"])
            for row in case["rows"]:
                with self.subTest(crown=row["crown_mm"], settings=case["settings"]):
                    result = engine.optimize_blast(row["crown_mm"], case["threshold"], settings)
                    self.assertAlmostEqual(result.point.q_kg_m3, row["q"], places=9)
                    self.assertEqual(result.reached, row["reached"])
                    for field, key in self.FIELDS:
                        self.assertTrue(
                            math.isclose(getattr(result.point, field), row[key], rel_tol=1e-9, abs_tol=1e-12),
                            f"{field}: {getattr(result.point, field)} != {row[key]}",
                        )

    def test_gabbro_example(self):
        result = _gabbro().optimize_blast(152, 5.0)
        point = result.point
        self.assertTrue(result.reached)
        self.assertEqual(round(point.q_kg_m3, 2), 1.26)
        self.assertEqual(round(point.burden_m, 2), 3.54)
        self.assertAlmostEqual(point.rock_factor_a, 6.366)
        self.assertEqual(point.rock_factor.method, "rmd50")
        self.assertEqual(point.strength_exponent, "19/20")
        self.assertAlmostEqual(point.charge_to_bench, 0.88)
        self.assertAlmostEqual(point.hole_diameter_mm, 159.6)
        self.assertAlmostEqual(point.burden_to_diameter, point.burden_m / 0.1596)

    def test_q_can_go_below_old_floor(self):
        soft = BlastEngine(
            RockProperties("Песчаник", 2.4, 100, 1.8),
            ExplosiveProperties("Гранулит-РП", 0.85, 3.76),
            TargetParams(lump_size_mm=800, hole_diameter_mm=0, bench_height_m=10.0),
        )
        result = soft.optimize_blast(110, 10.0, kr.KuzRamSettings(rock_factor_method="rmd10"))
        self.assertTrue(result.reached)
        self.assertAlmostEqual(result.point.q_kg_m3, 0.12)

    def test_not_reached_returns_upper_bound(self):
        result = _gabbro().optimize_blast(250, 5.0, kr.KuzRamSettings(q_max_kg_m3=1.5))
        self.assertFalse(result.reached)
        self.assertEqual(result.point.q_kg_m3, 1.5)
        self.assertAlmostEqual(result.point.oversize_pct, 5.40, places=2)

    def test_calibration_round_trip(self):
        engine = _gabbro()
        truth = kr.KuzRamSettings(rock_factor_correction=1.3)
        oversize = engine.kuzram_point(152, 1.1, truth).oversize_pct
        found = engine.calibrate_rock_factor(152, 1.1, oversize, kr.KuzRamSettings())
        self.assertAlmostEqual(found, 1.3, places=6)

    def test_calibration_outside_bounds(self):
        self.assertIsNone(_gabbro().calibrate_rock_factor(152, 1.1, 99.99, kr.KuzRamSettings()))

    def test_calibration_at_upper_bound_does_not_raise(self):
        # oversize_at(C(A)=10) — без зажима в solve_rock_factor_correction
        # replace(settings, rock_factor_correction=10.000000000000002) падает
        # с «Поправка C(A) — от 0,1 до 10.».
        engine = _gabbro()
        target = engine.kuzram_point(152, 1.1, kr.KuzRamSettings(rock_factor_correction=10.0)).oversize_pct
        found = engine.calibrate_rock_factor(152, 1.1, target, kr.KuzRamSettings())
        self.assertIsNotNone(found)
        self.assertLessEqual(found, 10.0)

    def test_upper_bound_is_floored_not_rounded(self):
        # round(1.527 * 100) = 153 → 1.53 кг/м³; порог впервые достигается
        # только на 1.53, значит на floor-границе 1.52 «не достигнут».
        result = _gabbro().optimize_blast(250, 5.0, kr.KuzRamSettings(q_max_kg_m3=1.527))
        self.assertFalse(result.reached)
        self.assertEqual(result.point.q_kg_m3, 1.52)


if __name__ == "__main__":
    unittest.main()
