"""API подбора q: /blast/optimize (Kuz-Ram и «до исправления») и /blast/kuzram/calibrate."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import blast
from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams
from simulation.fragmentation import cunningham as kr

GABBRO = {
    "rock": {"name": "Габбро-диабаз", "density_t_m3": 2.9, "ucs_mpa": 168, "fissuring_ff": 2.2},
    "explosive": {"name": "ЭВЕРСИН Э-100", "density_t_m3": 1.12, "power_mj_kg": 2.99},
    "target": {
        "lump_size_mm": 400, "bench_height_m": 10, "overdrill_m": 1,
        "hole_oversize_coeff": 1.05, "spacing_coeff_m": 1.25,
    },
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(blast.router, prefix="/api/v1")
    return TestClient(app)


def _optimize(**extra) -> dict:
    response = _client().post("/api/v1/blast/optimize", json={**GABBRO, **extra})
    assert response.status_code == 200, response.text
    return response.json()


class OptimizeEndpointTests(unittest.TestCase):
    def test_defaults_to_massive_rock_model(self):
        body = _optimize(crown_diameters_mm=[152])
        self.assertEqual(body["model_version"], "kuzram-cunningham-1.0")
        self.assertEqual(body["kuzram"]["rock_factor_method"], "rmd50")
        self.assertEqual(body["kuzram"]["q_max_kg_m3"], 2.0)
        variant = body["variants"][0]
        self.assertEqual(variant["specific_q_kg_m3"], 1.26)
        self.assertEqual(variant["grid_label"], "4.42 × 3.54")
        self.assertTrue(variant["reached"])
        self.assertEqual(variant["target_q_kg_m3"], 1.26)
        self.assertAlmostEqual(variant["details"]["rock_factor"]["value"], 6.366)
        self.assertAlmostEqual(variant["details"]["rock_factor"]["rdi"], 22.5)
        self.assertEqual(variant["details"]["strength_exponent"], "19/20")

    def test_legacy_block_matches_old_response(self):
        legacy = _optimize(crown_diameters_mm=[152])["variants"][0]["legacy"]
        self.assertEqual(legacy["specific_q_kg_m3"], 1.34)
        self.assertEqual(legacy["grid_label"], "4.29 × 3.43")
        self.assertEqual(legacy["x50_mm"], 64.2)
        self.assertEqual(legacy["oversize_pct"], 5.0)
        self.assertTrue(legacy["reached"])
        self.assertEqual(legacy["details"]["uniformity_n"], 0.8)
        self.assertIsNone(legacy["details"]["rock_factor"])

    def test_settings_change_the_result(self):
        body = _optimize(crown_diameters_mm=[152], kuzram={"rock_factor_method": "rmd10"})
        self.assertEqual(body["variants"][0]["specific_q_kg_m3"], 0.74)
        self.assertEqual(body["kuzram"]["rock_factor_method"], "rmd10")

    def test_not_reached_has_no_target_q(self):
        variant = _optimize(crown_diameters_mm=[250], kuzram={"q_max_kg_m3": 1.5})["variants"][0]
        self.assertFalse(variant["reached"])
        self.assertIsNone(variant["target_q_kg_m3"])
        self.assertEqual(variant["specific_q_kg_m3"], 1.5)

    def test_out_of_range_setting_is_422_with_russian_message(self):
        response = _client().post("/api/v1/blast/optimize", json={**GABBRO, "kuzram": {"rock_factor_correction": 50}})
        self.assertEqual(response.status_code, 422)
        messages = " ".join(error["msg"] for error in response.json()["detail"])
        self.assertIn("Поправка C(A) — от 0,1 до 10.", messages)

    def test_unknown_setting_is_rejected(self):
        response = _client().post("/api/v1/blast/optimize", json={**GABBRO, "kuzram": {"a_method": "code"}})
        self.assertEqual(response.status_code, 422)


class CalibrateEndpointTests(unittest.TestCase):
    def test_round_trip_and_skipped_rows(self):
        engine = BlastEngine(
            RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
            ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99),
            TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0),
        )
        truth = kr.KuzRamSettings(rock_factor_correction=1.2)
        facts = [
            {"crown_mm": crown, "q_kg_m3": q, "oversize_pct": engine.kuzram_point(crown, q, truth).oversize_pct}
            for crown, q in [(110, 1.0), (152, 1.1), (171, 1.2)]
        ]
        facts.append({"crown_mm": 152, "q_kg_m3": 1.1, "oversize_pct": 99.99})
        response = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": facts})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["used"], 3)
        self.assertEqual(body["skipped"], 1)
        self.assertAlmostEqual(body["rock_factor_correction"], 1.2, places=3)
        self.assertEqual(body["model_version"], "kuzram-cunningham-1.0")
        self.assertAlmostEqual(body["rows"][0]["rock_factor_correction"], 1.2, places=3)
        self.assertGreater(body["rows"][0]["legacy_oversize_pct"], 0)
        self.assertIsNone(body["rows"][3]["rock_factor_correction"])
        self.assertIn("C(A) от 0,1 до 10", body["rows"][3]["note"])

    def test_nothing_solved_gives_null(self):
        facts = [{"crown_mm": 152, "q_kg_m3": 1.1, "oversize_pct": 99.99}]
        body = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": facts}).json()
        self.assertIsNone(body["rock_factor_correction"])
        self.assertEqual(body["used"], 0)

    def test_facts_are_required(self):
        response = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": []})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
