"""Сборка уступа из двух выбранных бровок (построение «по-старому» до PR 2 TASK-013).

Скан чертежа старого диалога («Бровки из чертежа») удалён: чертёж читает
импорт `/design/cad`, а кнопка «Построить блок» пока строит полосу между
верхней и нижней бровкой через `/design/contour/from-polylines`.
"""
from __future__ import annotations

import os
import unittest

from api.exceptions import InvalidSurveyError
from api.schemas.design import BenchFromPolylinesRequest
from api.services import design_service

CREST = [{"x": x, "y": y, "z": 120.0} for x, y in ((0, 0), (40, 0), (40, 30), (0, 30))]
TOE = [{"x": x, "y": y, "z": 108.0} for x, y in ((5, 5), (35, 5), (35, 25), (5, 25))]


class BenchFromPolylinesApiTests(unittest.TestCase):
    def test_builds_bench_from_the_chosen_polylines(self):
        result = design_service.bench_from_polylines(BenchFromPolylinesRequest(
            crest=CREST, toe=TOE, crest_layer="BROVKA_TOP", toe_layer="BROVKA_BOTTOM", filename="block.dxf",
        ))

        self.assertAlmostEqual(result.crest_z_m, 120.0)
        self.assertAlmostEqual(result.toe_z_m, 108.0)
        self.assertEqual(result.crest_layer, "BROVKA_TOP")
        self.assertGreaterEqual(result.vertex_count, 3)
        self.assertIsNotNone(result.surfaces.top)
        self.assertIsNotNone(result.surfaces.floor)
        self.assertIsNotNone(result.surfaces.face)
        self.assertAlmostEqual(result.contour.bench.crest_z_m, 120.0)

    def test_swapped_crest_and_toe_are_rejected(self):
        with self.assertRaises(InvalidSurveyError) as ctx:
            design_service.bench_from_polylines(BenchFromPolylinesRequest(crest=TOE, toe=CREST))
        self.assertIn("выше", str(ctx.exception))

    def test_degenerate_selection_is_rejected(self):
        with self.assertRaises(InvalidSurveyError):
            design_service.bench_from_polylines(BenchFromPolylinesRequest(
                crest=[{"x": 0, "y": 0, "z": 10}],
                toe=[{"x": 0, "y": 1, "z": 0}, {"x": 1, "y": 1, "z": 0}],
            ))


class DrawingRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.routers import design as design_router

        os.environ["BLASTEX_API_KEY"] = "test-api-key"
        os.environ["BLASTEX_SESSION_SECRET"] = "test-session-secret"
        app = FastAPI()
        app.include_router(design_router.router, prefix="/api/v1")
        self.client = TestClient(app, headers={"X-API-Key": "test-api-key"})

    def test_old_drawing_scan_route_is_gone(self):
        response = self.client.post(
            "/api/v1/design/drawing/polylines",
            files={"file": ("block.dxf", b"0\nSECTION\n0\nEOF\n", "application/dxf")},
        )
        self.assertEqual(response.status_code, 404)

    def test_bench_from_polylines_route(self):
        response = self.client.post("/api/v1/design/contour/from-polylines", json={
            "crest": CREST, "toe": TOE, "crest_layer": "BROVKA_TOP", "toe_layer": "BROVKA_BOTTOM",
            "filename": "block.dxf",
        })
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertAlmostEqual(payload["crest_z_m"], 120.0)
        self.assertAlmostEqual(payload["toe_z_m"], 108.0)


if __name__ == "__main__":
    unittest.main()
