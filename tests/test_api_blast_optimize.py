"""API подбора q: /blast/optimize (Kuz-Ram и «до исправления») и /blast/kuzram/calibrate."""
import asyncio
import json
import unittest

from annotated_types import Ge, Le
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import pydantic_validation_handler, request_validation_handler, value_error_handler
from api.routers import blast
from api.schemas.blast import (
    CROWN_MM_MAX,
    CROWN_MM_MIN,
    BlastOptimizeRequest,
    KuzRamFactSchema,
    KuzRamSettingsSchema,
    TargetParamsSchema,
)
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


def _client_with_app_handlers() -> TestClient:
    """Клиент с обработчиками ошибок из api/main.py (не умолчаниями FastAPI).

    ``_client()`` использует голый ``FastAPI()`` со стандартным обработчиком
    ``RequestValidationError`` — он маскирует баг сериализации, из-за
    которого в реальном приложении та же ошибка настроек даёт 500.
    """
    app = FastAPI()
    app.include_router(blast.router, prefix="/api/v1")
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(ValueError, value_error_handler)
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
        self.assertIn("burden_to_diameter", variant["details"])

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
        for error in response.json()["detail"]:
            self.assertFalse(error["msg"].startswith("Value error"), error["msg"])

    def test_unknown_setting_is_rejected(self):
        response = _client().post("/api/v1/blast/optimize", json={**GABBRO, "kuzram": {"a_method": "code"}})
        self.assertEqual(response.status_code, 422)

    def test_out_of_range_setting_is_422_with_real_app_handlers(self):
        # С голым FastAPI() (_client()) обработчик по умолчанию сериализует
        # ошибку без проблем; в реальном приложении (api/main.py) тот же
        # ValueError в ctx падал с TypeError → 500. Проверяем через
        # настоящие обработчики.
        response = _client_with_app_handlers().post(
            "/api/v1/blast/optimize", json={**GABBRO, "kuzram": {"rock_factor_correction": 50}}
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error_type"], "validation_error")
        messages = [error["msg"] for error in body["details"]]
        self.assertIn("Поправка C(A) — от 0,1 до 10.", messages)

    def test_rock_factor_non_positive_is_400_with_real_app_handlers(self):
        response = _client_with_app_handlers().post(
            "/api/v1/blast/optimize",
            json={
                **GABBRO,
                "rock": {"name": "Уголь", "density_t_m3": 1.4, "ucs_mpa": 20, "fissuring_ff": 1},
                "kuzram": {"rock_factor_method": "rmd10"},
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Фактор породы A", response.json()["detail"])

    def test_crown_out_of_bounds_is_422_with_russian_message(self):
        # 0,152 (метры вместо миллиметров), 15 и 5000 мм — вне 20–1000 мм.
        # Ошибка называет коронку и её место в списке, а не диаметр скважины.
        for crowns, index in (([0.152], 0), ([152, 15], 1), ([5000], 0)):
            with self.subTest(crowns=crowns):
                response = _client_with_app_handlers().post(
                    "/api/v1/blast/optimize", json={**GABBRO, "crown_diameters_mm": crowns}
                )
                self.assertEqual(response.status_code, 422)
                errors = response.json()["details"]
                self.assertEqual([error["msg"] for error in errors], ["Диаметр коронки — от 20 до 1000 мм."])
                self.assertEqual(errors[0]["loc"], ["body", "crown_diameters_mm", index])

    def test_non_finite_input_is_422_with_russian_message(self):
        # json.loads принимает NaN, а в деталях 422 pydantic повторяет ввод:
        # без замены JSONResponse падал на NaN, и вместо 422 уходил 400
        # «Out of range float values are not JSON compliant».
        cases = (
            ({"crown_diameters_mm": [float("nan")]}, "Диаметр коронки — от 20 до 1000 мм."),
            ({"kuzram": {"rock_factor_correction": float("inf")}}, "Поправка C(A) — от 0,1 до 10."),
        )
        for extra, message in cases:
            with self.subTest(extra=extra):
                response = _client_with_app_handlers().post(
                    "/api/v1/blast/optimize",
                    content=json.dumps({**GABBRO, **extra}),
                    headers={"content-type": "application/json"},
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn(message, [error["msg"] for error in response.json()["details"]])

    def test_crown_bounds_fit_formula_bounds(self):
        # Коэффициент разбуривания — в границах TargetParamsSchema: любая
        # коронка, которую пропускает схема, даёт скважину в границах формулы n.
        metadata = TargetParamsSchema.model_fields["hole_oversize_coeff"].metadata
        coeff_min = next(item.ge for item in metadata if isinstance(item, Ge))
        coeff_max = next(item.le for item in metadata if isinstance(item, Le))
        self.assertGreaterEqual(CROWN_MM_MIN * coeff_min, kr.MIN_HOLE_DIAMETER_MM)
        self.assertLessEqual(CROWN_MM_MAX * coeff_max, kr.MAX_HOLE_DIAMETER_MM)

    def test_crown_bounds_are_published_in_json_schema(self):
        # Границы коронки проверяет AfterValidator (ради русского текста) — в
        # схеме OpenAPI их нужно объявить явно, иначе клиенты видят просто число.
        fact = KuzRamFactSchema.model_json_schema()["properties"]["crown_mm"]
        crowns = BlastOptimizeRequest.model_json_schema()["properties"]["crown_diameters_mm"]["items"]
        for schema in (fact, crowns):
            with self.subTest(schema=schema):
                self.assertEqual((schema["minimum"], schema["maximum"]), (CROWN_MM_MIN, CROWN_MM_MAX))

    def test_empty_crowns_is_422(self):
        # Пустой список отсекает схема (min_length=1), сервис его не проверяет.
        response = _client().post("/api/v1/blast/optimize", json={**GABBRO, "crown_diameters_mm": []})
        self.assertEqual(response.status_code, 422)

    def test_crown_diameters_over_fifty_is_422(self):
        response = _client().post(
            "/api/v1/blast/optimize", json={**GABBRO, "crown_diameters_mm": [110.0 + i for i in range(51)]}
        )
        self.assertEqual(response.status_code, 422)

    def test_absurd_lump_size_is_422_not_500(self):
        # Без верхней границы n не клэмпится, и math.pow(lump/xc, n) в
        # rosin_rammler_oversize_pct кидает OverflowError → 500.
        response = _client().post(
            "/api/v1/blast/optimize",
            json={**GABBRO, "crown_diameters_mm": [152], "target": {**GABBRO["target"], "lump_size_mm": 1e305}},
        )
        self.assertEqual(response.status_code, 422)

    def test_absurd_spacing_coeff_is_422_not_500(self):
        # Огромное a/W тоже даёт переполнение через n (при полном наборе
        # коронок по умолчанию — см. cr-fix-brief.md R1).
        response = _client().post(
            "/api/v1/blast/optimize",
            json={**GABBRO, "target": {**GABBRO["target"], "spacing_coeff_m": 1e6}},
        )
        self.assertEqual(response.status_code, 422)

    def test_huge_joint_angle_is_422_with_jpa_message(self):
        # 10**400 не помещается в float → float(joint_angle) в
        # KuzRamSettings.__post_init__ кидал OverflowError. Тело собираем
        # через json.dumps: Python-int неограничен, а TestClient(json=...)
        # не должен превращать его во float на пути к серверу.
        body = json.dumps({**GABBRO, "crown_diameters_mm": [152], "kuzram": {"joint_angle": 10**400}})
        response = _client().post(
            "/api/v1/blast/optimize", content=body, headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.status_code, 422)
        messages = [error["msg"] for error in response.json()["detail"]]
        self.assertTrue(any("JPA" in msg for msg in messages), messages)


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
        # GABBRO не задаёт "kuzram" → запрос считает по умолчаниям
        # KuzRamSettings() (F10.3), значит и разобранная строка тоже.
        self.assertEqual(
            body["rows"][0]["model_oversize_pct"],
            round(engine.kuzram_point(110, 1.0, kr.KuzRamSettings()).oversize_pct, 2),
        )

    def test_nothing_solved_gives_null(self):
        facts = [{"crown_mm": 152, "q_kg_m3": 1.1, "oversize_pct": 99.99}]
        body = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": facts}).json()
        self.assertIsNone(body["rock_factor_correction"])
        self.assertEqual(body["used"], 0)

    def test_facts_are_required(self):
        response = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": []})
        self.assertEqual(response.status_code, 422)

    def test_kuzram_none_uses_defaults(self):
        facts = [{"crown_mm": 152, "q_kg_m3": 1.1, "oversize_pct": 5.0}]
        response = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "kuzram": None, "facts": facts})
        self.assertEqual(response.status_code, 200, response.text)

    def test_fact_crown_out_of_bounds_is_422(self):
        facts = [
            {"crown_mm": 152, "q_kg_m3": 1.1, "oversize_pct": 5.0},
            {"crown_mm": 15, "q_kg_m3": 1.1, "oversize_pct": 5.0},
        ]
        response = _client_with_app_handlers().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": facts})
        self.assertEqual(response.status_code, 422)
        errors = response.json()["details"]
        self.assertEqual([error["msg"] for error in errors], ["Диаметр коронки — от 20 до 1000 мм."])
        self.assertEqual(errors[0]["loc"], ["body", "facts", 1, "crown_mm"])

    def test_fact_q_over_ten_is_422(self):
        facts = [{"crown_mm": 152, "q_kg_m3": 11, "oversize_pct": 5.0}]
        response = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": facts})
        self.assertEqual(response.status_code, 422)

    def test_out_of_range_kuzram_is_422_with_real_app_handlers(self):
        facts = [{"crown_mm": 152, "q_kg_m3": 1.1, "oversize_pct": 5.0}]
        response = _client_with_app_handlers().post(
            "/api/v1/blast/kuzram/calibrate",
            json={**GABBRO, "kuzram": {"rock_factor_correction": 50}, "facts": facts},
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error_type"], "validation_error")
        messages = [error["msg"] for error in body["details"]]
        self.assertIn("Поправка C(A) — от 0,1 до 10.", messages)


class SettingsSchemaParityTests(unittest.TestCase):
    """F7: умолчания и выбор значений не должны расходиться между схемой и датаклассом."""

    def test_schema_defaults_round_trip_to_dataclass_defaults(self):
        self.assertEqual(KuzRamSettingsSchema().to_settings(), kr.KuzRamSettings())

    def test_from_settings_round_trip_matches_schema_defaults(self):
        self.assertEqual(
            KuzRamSettingsSchema.from_settings(kr.KuzRamSettings()).model_dump(),
            KuzRamSettingsSchema().model_dump(),
        )



class ErrorHandlerTests(unittest.TestCase):
    def test_response_validation_error_with_nan_input_is_422(self):
        # ValidationError, поднятый внутри маршрута, повторяет ввод в деталях;
        # NaN там ронял JSONResponse, и вместо 422 уходил 400.
        with self.assertRaises(ValidationError) as caught:
            KuzRamSettingsSchema(rock_factor_correction=float("nan"))
        response = asyncio.run(pydantic_validation_handler(None, caught.exception))
        self.assertEqual(response.status_code, 422)
        messages = [error["msg"] for error in json.loads(response.body)["details"]]
        self.assertIn("Поправка C(A) — от 0,1 до 10.", messages)


if __name__ == "__main__":
    unittest.main()
