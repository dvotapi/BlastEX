"""Общая база «Проектирования» и лист «Расчёт» — одна функция прогноза.

Критерий успеха спеки: при одинаковых входных величинах и настройках числа
совпадают. Тест строит входные величины региона из точки листа «Расчёт» и
сравнивает прогноз до 1e-9.
"""
import unittest
from dataclasses import asdict, replace

from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams
from simulation.fragmentation.base import (
    base_parameters,
    calibration_warnings,
    charged_diameter_mm,
    predictive_settings,
    region_point,
    settings_source_label,
)
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.models import Calibration, FragmentationInputs
from tests.test_fragmentation_kuzram import _inputs

ROCKS = (
    RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
    RockProperties("Гранит", 2.65, 150, 2.0),
    RockProperties("Известняк трещиноватый", 2.4, 60, 4.0),
)
SETTINGS = (
    KuzRamSettings(),
    KuzRamSettings(rock_factor_method="joint_factor", joint_condition=1.5, joint_angle=30),
    KuzRamSettings(rock_factor_method="rmd10", strength_exponent="19/30", drill_deviation_m=0.3, uniformity_correction=1.2),
    KuzRamSettings(rock_factor_method="manual", rock_factor_manual=8.0, rock_factor_correction=1.4),
)
CROWNS_MM = (110, 152, 250)
Q_KG_M3 = (0.6, 1.26)
SPACING_COEFFS = (1.0, 1.25)


def _inputs_from_point(engine: BlastEngine, crown_mm: float, point) -> FragmentationInputs:
    """Входные величины региона, равные тем, что лист «Расчёт» подал в predict_point."""
    return FragmentationInputs(
        burden_m=point.burden_m,
        spacing_m=point.spacing_m,
        bench_height_m=engine.target.bench_height_m,
        diameter_mm=crown_mm,
        charge_mass_kg=point.charge_mass_kg,
        powder_factor_kg_m3=point.q_kg_m3,
        stemming_m=0.0,
        explosive_name=engine.explosive.name,
        explosive_density_t_m3=engine.explosive.density_t_m3,
        explosive_energy_mj_kg=engine.explosive.power_mj_kg,
        rock_name=engine.rock.name,
        rock_density_t_m3=engine.rock.density_t_m3,
        rock_ucs_mpa=engine.rock.ucs_mpa,
        rock_fissuring=engine.rock.fissuring_ff,
        lump_size_mm=engine.target.lump_size_mm,
        hole_oversize_coeff=engine.target.hole_oversize_coeff,
        charge_length_m=point.charge_length_m,
        hole_length_m=engine.target.bench_height_m + engine.target.overdrill_m,
    )


class CalcSheetParityTests(unittest.TestCase):
    def test_region_point_matches_kuzram_point(self):
        explosive = ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99)
        for rock in ROCKS:
            for spacing_coeff in SPACING_COEFFS:
                target = TargetParams(
                    lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0, spacing_coeff_m=spacing_coeff
                )
                engine = BlastEngine(rock, explosive, target)
                for settings in SETTINGS:
                    for crown_mm in CROWNS_MM:
                        for q in Q_KG_M3:
                            with self.subTest(rock=rock.name, a_w=spacing_coeff, settings=settings, crown=crown_mm, q=q):
                                sheet = engine.kuzram_point(crown_mm, q, settings)
                                point = region_point(_inputs_from_point(engine, crown_mm, sheet), settings)
                                self.assertAlmostEqual(point.x50_mm, sheet.x50_mm, places=9)
                                self.assertAlmostEqual(point.uniformity.value, sheet.uniformity_n, places=9)
                                self.assertAlmostEqual(point.uniformity.raw, sheet.uniformity_n_raw, places=9)
                                self.assertAlmostEqual(point.oversize_pct, sheet.oversize_pct, places=9)
                                self.assertAlmostEqual(point.rock.value, sheet.rock_factor_a, places=9)
                                self.assertEqual(point.warnings, ())

    def test_charged_diameter_is_computed_like_calc_sheet(self):
        inputs = _inputs(diameter_mm=152.0, hole_oversize_coeff=1.05)
        # Blast.py::_charge: d_m = коронка / 1000 · коэффициент, затем d_m · 1000.
        self.assertEqual(charged_diameter_mm(inputs), 152.0 / 1000 * 1.05 * 1000)


class RegionPointTests(unittest.TestCase):
    def test_missing_charge_length_warns(self):
        point = region_point(_inputs(charge_length_m=0.0))

        self.assertEqual(point.uniformity.charge_to_bench, 1.0)
        self.assertEqual(len(point.warnings), 1)
        self.assertIn("L/H", point.warnings[0])

    def test_zero_explosive_energy_is_russian_error(self):
        with self.assertRaises(ValueError) as ctx:
            region_point(_inputs(explosive_energy_mj_kg=0.0, charge_length_m=7.0))

        self.assertIn("сила ВВ", str(ctx.exception))

    def test_base_parameters_are_unrounded(self):
        inputs = _inputs(charge_length_m=7.0)
        point = region_point(inputs)

        parameters = base_parameters(point, inputs)

        self.assertEqual(parameters["x50_mm"], point.x50_mm)
        self.assertEqual(parameters["rock_factor_A"], point.rock.value)
        self.assertEqual(parameters["uniformity_n_cunningham"], point.uniformity.value)
        self.assertEqual(parameters["rock_factor"]["method"], "rmd50")
        self.assertEqual(parameters["hole_diameter_mm"], charged_diameter_mm(inputs))

    def test_calibration_warnings_name_ignored_overrides(self):
        self.assertEqual(calibration_warnings(Calibration(uniformity_n=1.5, swebrec_b=2.0, xmax_mm=900.0)), [])

        warnings = calibration_warnings(Calibration(rock_factor_A=7.0, drill_deviation_m=0.2))

        self.assertEqual(len(warnings), 1)
        self.assertIn("фактор породы A", warnings[0])
        self.assertIn("отклонение бурения σ", warnings[0])


class SettingsSourceLabelTests(unittest.TestCase):
    def test_labels(self):
        def snap(source: str, name: str = "", warnings: list[str] | None = None) -> dict:
            return {"source": source, "work_object_name": name, "values": {}, "warnings": warnings or []}

        cases = (
            ("kuzram", "2.0.0", snap("work_object", "Карьер-1"), "Настройки модели: объект работ «Карьер-1»"),
            ("kuzram", "2.0.0", snap("request"), "Настройки модели: заданы в запросе"),
            ("kuzram", "2.0.0", snap("defaults"), "Настройки модели: умолчания"),
            (
                "kuzram",
                "2.0.0",
                snap("defaults", "Карьер-2"),
                "Настройки модели: умолчания — у объекта «Карьер-2» они не сохранены",
            ),
            (
                "kuzram",
                "2.0.0",
                snap("defaults", "Карьер-3", ["x"]),
                "Настройки модели: умолчания — настройки объекта «Карьер-3» не прочитаны",
            ),
            ("kuzram_legacy", "1.0.0", snap("work_object", "Карьер-1"), "Старая модель: настройки объекта не применяются"),
            ("kuzram_legacy", "1.0.0", None, "Старая модель: настройки объекта не применяются"),
            # Прогноз, сохранённый до PR 2, — тоже старая модель.
            ("kuzram", "1.0.0", None, "Старая модель: настройки объекта не применяются"),
            ("kuzram", "", {}, "Старая модель: настройки объекта не применяются"),
            # Новый прогноз без снимка строки не получает.
            ("kuzram", "2.0.0", {}, ""),
            ("kuzram", "2.0.0", None, ""),
        )
        for model, version, snapshot, label in cases:
            with self.subTest(model=model, version=version, snapshot=snapshot):
                self.assertEqual(settings_source_label(model, version, snapshot), label)


class PredictiveSettingsTests(unittest.TestCase):
    """Для сравнения прогнозов важны только настройки, которые их меняют."""

    def _values(self, **changes):
        return asdict(replace(KuzRamSettings(), **changes))

    def test_q_max_does_not_affect_prediction(self):
        self.assertEqual(
            predictive_settings(self._values(q_max_kg_m3=0.5), "kuzram"),
            predictive_settings(self._values(q_max_kg_m3=5.0), "kuzram"),
        )

    def test_inactive_method_fields_are_ignored(self):
        self.assertEqual(
            predictive_settings(self._values(rock_factor_manual=9.0, joint_angle=40), "kuzram"),
            predictive_settings(self._values(), "kuzram"),
        )
        manual = self._values(rock_factor_method="manual", rock_factor_manual=9.0)
        self.assertNotEqual(
            predictive_settings(manual, "kuzram"),
            predictive_settings(dict(manual, rock_factor_manual=7.0), "kuzram"),
        )

    def test_uniformity_fields_matter_only_for_kuzram(self):
        tuned = self._values(drill_deviation_m=0.5, uniformity_correction=1.2)
        self.assertNotEqual(predictive_settings(tuned, "kuzram"), predictive_settings(self._values(), "kuzram"))
        for model in ("kuznetsov", "swebrec"):
            with self.subTest(model=model):
                self.assertEqual(predictive_settings(tuned, model), predictive_settings(self._values(), model))

    def test_correction_and_exponent_always_matter(self):
        for changes in ({"rock_factor_correction": 1.3}, {"strength_exponent": "19/30"}):
            with self.subTest(changes=changes):
                self.assertNotEqual(
                    predictive_settings(self._values(**changes), "swebrec"),
                    predictive_settings(self._values(), "swebrec"),
                )


if __name__ == "__main__":
    unittest.main()
