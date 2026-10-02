"""Миграция 20261002_0011: C(A) объектов работ переводится под силу ВВ к ANFO.

Главное свойство — прогноз объекта с подобранной C(A) не меняется: старая
формула (RE^−e к тротилу) со старой C(A) даёт тот же x50 и негабарит, что
новая формула ((115/RWS)^e к ANFO) с пересчитанной C(A).
"""
from __future__ import annotations

import importlib.util
import json
import math
import unittest
from pathlib import Path
from typing import Any

from simulation.fragmentation import cunningham as kr
from tests.pg_public import public_db, requires_pg  # noqa: F401 — фикстура
from simulation.fragmentation.units import anfo_weight_strength_pct, relative_weight_strength

MIGRATION = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "20261002_0011_kuzram_strength_rws.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("kuzram_strength_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()

# Точка габбро-диабаза, коронка 152 мм: геометрия как у листа «Расчёт».
POINT = dict(
    ucs_mpa=168.0,
    density_t_m3=2.9,
    fissuring_per_m=2.2,
    burden_m=3.44,
    spacing_m=4.3,
    hole_diameter_mm=159.6,
    powder_factor_kg_m3=1.3,
    charge_mass_kg=176.3,
    charge_length_m=8.8,
    bench_height_m=10.0,
    lump_size_mm=400.0,
)


def _old_prediction(settings: kr.KuzRamSettings, energy_mj_kg: float) -> tuple[float, float]:
    """x50 и негабарит по формуле до PR #106: сила ВВ RE^−e, RE = Q/4,184."""
    rock = kr.rock_factor(
        settings,
        ucs_mpa=POINT["ucs_mpa"],
        density_t_m3=POINT["density_t_m3"],
        fissuring_per_m=POINT["fissuring_per_m"],
        burden_m=POINT["burden_m"],
        spacing_m=POINT["spacing_m"],
    )
    x50_cm = (
        rock.value
        * POINT["powder_factor_kg_m3"] ** -0.8
        * POINT["charge_mass_kg"] ** (1 / 6)
        * relative_weight_strength(energy_mj_kg) ** (-settings.exponent)
    )
    x50_mm = x50_cm * 10
    n = kr.uniformity_index(
        burden_m=POINT["burden_m"],
        hole_diameter_mm=POINT["hole_diameter_mm"],
        spacing_to_burden=POINT["spacing_m"] / POINT["burden_m"],
        drill_deviation_m=settings.drill_deviation_m,
        charge_length_m=POINT["charge_length_m"],
        bench_height_m=POINT["bench_height_m"],
        correction=settings.uniformity_correction,
    ).value
    return x50_mm, kr.oversize(x50_mm, n, POINT["lump_size_mm"])[1]


def _new_prediction(settings: kr.KuzRamSettings, energy_mj_kg: float) -> tuple[float, float]:
    point = kr.predict_point(settings, rws_anfo_pct=anfo_weight_strength_pct(energy_mj_kg), **POINT)
    return point.x50_mm, point.oversize_pct


class StrengthRatioTests(unittest.TestCase):
    def test_ratio_is_the_same_for_any_explosive(self):
        # Отношение множителей не зависит от теплоты взрыва — на этом стоит миграция.
        for exponent, e in (("19/20", 19 / 20), ("19/30", 19 / 30)):
            ratio = migration.strength_ratio(exponent)
            for energy in (2.5, 2.99, 3.76, 4.184, 5.2):
                with self.subTest(exponent=exponent, energy=energy):
                    new_term = (115 / anfo_weight_strength_pct(energy)) ** e
                    old_term = relative_weight_strength(energy) ** (-e)
                    self.assertAlmostEqual(new_term / old_term, ratio, places=12)

    def test_frozen_constants_match_the_model(self):
        self.assertEqual(migration.STRENGTH_EXPONENTS, kr.STRENGTH_EXPONENTS)
        low, high, _label = kr.NUMERIC_BOUNDS["rock_factor_correction"]
        self.assertEqual((migration.CORRECTION_MIN, migration.CORRECTION_MAX), (low, high))

    def test_help_example_value(self):
        # Справка: по трём фактическим взрывам старая модель подбирала 1,127, новая — 1,081.
        block = migration.convert_block({"rock_factor_correction": 1.127, "strength_exponent": "19/20"})
        self.assertAlmostEqual(block["rock_factor_correction"], 1.0814, places=4)


class ConvertBlockTests(unittest.TestCase):
    def test_converted_correction_keeps_the_calibrated_prediction(self):
        cases: list[dict[str, Any]] = [
            {"rock_factor_correction": 1.3},
            {"rock_factor_correction": 0.62, "strength_exponent": "19/30"},
            {"rock_factor_correction": 2.4, "rock_factor_method": "rmd10", "drill_deviation_m": 0.2},
            {"rock_factor_correction": 1.15, "rock_factor_method": "joint_factor", "joint_angle": 40},
        ]
        for stored in cases:
            for energy in (2.99, 3.76):
                with self.subTest(stored=stored, energy=energy):
                    converted = migration.convert_block(stored)
                    old_x50, old_oversize = _old_prediction(kr.KuzRamSettings(**stored), energy)
                    new_x50, new_oversize = _new_prediction(kr.KuzRamSettings(**converted), energy)
                    self.assertTrue(math.isclose(old_x50, new_x50, rel_tol=1e-12))
                    self.assertTrue(math.isclose(old_oversize, new_oversize, rel_tol=1e-9))

    def test_other_fields_and_facts_are_kept(self):
        stored = {
            "rock_factor_correction": 1.3,
            "rock_factor_method": "rmd10",
            "q_max_kg_m3": 3.0,
            "facts": [{"crown_mm": 152, "q_kg_m3": 1.3, "oversize_pct": 8.0}],
        }
        converted = migration.convert_block(stored)
        self.assertEqual({k: v for k, v in converted.items() if k != "rock_factor_correction"},
                         {k: v for k, v in stored.items() if k != "rock_factor_correction"})
        self.assertEqual(stored["rock_factor_correction"], 1.3)  # исходный блок не изменён

    def test_nothing_to_change(self):
        for kuzram in (None, [], "rmd50", {}, {"rock_factor_method": "rmd10"},
                       {"rock_factor_correction": 1.0}, {"rock_factor_correction": 1},
                       {"rock_factor_correction": "1,3"}, {"rock_factor_correction": True},
                       {"rock_factor_correction": float("nan")}, {"rock_factor_correction": 0}):
            with self.subTest(kuzram=kuzram):
                self.assertIsNone(migration.convert_block(kuzram))

    def test_result_stays_within_bounds(self):
        self.assertEqual(migration.convert_block({"rock_factor_correction": 0.1})["rock_factor_correction"], 0.1)
        back = migration.convert_block({"rock_factor_correction": 10.0}, reverse=True)
        self.assertEqual(back["rock_factor_correction"], 10.0)

    def test_unknown_exponent_falls_back_to_default(self):
        block = migration.convert_block({"rock_factor_correction": 1.3, "strength_exponent": "1/2"})
        self.assertAlmostEqual(block["rock_factor_correction"], 1.3 / migration.strength_ratio("19/20"))

    def test_downgrade_restores_value(self):
        for exponent in ("19/20", "19/30"):
            stored = {"rock_factor_correction": 1.3, "strength_exponent": exponent}
            back = migration.convert_block(migration.convert_block(stored), reverse=True)
            self.assertAlmostEqual(back["rock_factor_correction"], 1.3, places=12)

    def test_converted_block_is_json_and_valid_settings(self):
        converted = migration.convert_block({"rock_factor_correction": 1.3})
        json.dumps(converted)
        kr.KuzRamSettings(**converted)


@requires_pg
def test_migration_rewrites_stored_corrections(public_db) -> None:  # noqa: F811 — фикстура
    import os
    import subprocess
    import sys

    from sqlalchemy import text

    from tests.pg_public import _REPO_ROOT, TEST_DATABASE_URL

    def alembic(*args: str) -> None:
        env = {**os.environ, "BLASTEX_DATABASE_URL": TEST_DATABASE_URL}
        subprocess.run([sys.executable, "-m", "alembic", *args], cwd=_REPO_ROOT, env=env, check=True)

    def corrections() -> dict[str, Any]:
        with public_db.connect() as connection:
            rows = connection.execute(
                text("SELECT work_object_name, inputs FROM blastex.calc_object_inputs ORDER BY work_object_name")
            ).all()
        return {name: (inputs.get("kuzram") or {}).get("rock_factor_correction") for name, inputs in rows}

    alembic("downgrade", "20261001_0010")
    stored = {
        "Подобран": {"kuzram": {"rock_factor_correction": 1.3, "strength_exponent": "19/30", "facts": []}},
        "Без подгонки": {"kuzram": {"rock_factor_correction": 1.0}},
        "Без блока": {"diameter_mm": 152},
    }
    with public_db.begin() as connection:
        for name, inputs in stored.items():
            connection.execute(
                text(
                    "INSERT INTO blastex.calc_object_inputs "
                    "(organization_id, work_object_name, inputs, updated_at, updated_by) "
                    "VALUES ('org', :name, CAST(:inputs AS JSONB), '2026-10-01T00:00:00Z', 'user@example.com')"
                ),
                {"name": name, "inputs": json.dumps(stored[name])},
            )

    alembic("upgrade", "20261002_0011")
    after = corrections()
    assert math.isclose(after["Подобран"], 1.3 / migration.strength_ratio("19/30"), rel_tol=1e-12)
    assert after["Без подгонки"] == 1.0
    assert after["Без блока"] is None
    with public_db.connect() as connection:
        updated_by = connection.execute(
            text("SELECT DISTINCT updated_by FROM blastex.calc_object_inputs")
        ).scalars().all()
    assert updated_by == ["user@example.com"]

    alembic("downgrade", "20261001_0010")
    assert math.isclose(corrections()["Подобран"], 1.3, rel_tol=1e-12)
    alembic("upgrade", "head")


if __name__ == "__main__":
    unittest.main()
