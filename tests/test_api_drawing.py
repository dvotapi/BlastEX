"""Сканирование чертежа и сборка уступа из выбранных вручную бровок."""
from __future__ import annotations

import io
import os
import unittest

import ezdxf

from api.exceptions import InvalidSurveyError
from api.schemas.design import BenchFromPolylinesRequest
from api.services import design_service


def _drawing_bytes() -> bytes:
    doc = ezdxf.new("R2010")
    doc.layers.add("BROVKA_TOP")
    doc.layers.add("BROVKA_BOTTOM")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (40, 0), (40, 30), (0, 30)],
        close=True,
        dxfattribs={"layer": "BROVKA_TOP", "elevation": 120.0},
    )
    msp.add_polyline3d(
        [(5, 5, 108.0), (35, 5, 108.0), (35, 25, 108.0), (5, 25, 108.0)],
        dxfattribs={"layer": "BROVKA_BOTTOM"},
    )
    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode("utf-8")


def _points(polyline) -> list[dict]:
    return [{"x": p.x, "y": p.y, "z": p.z} for p in polyline.points]


class DrawingScanApiTests(unittest.TestCase):
    def test_scan_returns_polylines_with_measurements(self):
        scan = design_service.scan_drawing(_drawing_bytes(), "block.dxf")

        self.assertEqual(scan.source_name, "block.dxf")
        self.assertEqual(scan.converted_from, "")
        self.assertFalse(scan.truncated)
        layers = {item.layer for item in scan.polylines}
        self.assertEqual(layers, {"BROVKA_TOP", "BROVKA_BOTTOM"})

        crest = next(item for item in scan.polylines if item.layer == "BROVKA_TOP")
        self.assertTrue(crest.closed)
        self.assertAlmostEqual(crest.z_min, 120.0)
        self.assertAlmostEqual(crest.area_m2, 1200.0)
        self.assertEqual(len(crest.points), 4)

    def test_scan_rejects_a_drawing_without_polylines(self):
        doc = ezdxf.new("R2010")
        doc.modelspace().add_text("подпись")
        buffer = io.StringIO()
        doc.write(buffer)
        with self.assertRaises(InvalidSurveyError):
            design_service.scan_drawing(buffer.getvalue().encode("utf-8"), "block.dxf")


class BenchFromPolylinesApiTests(unittest.TestCase):
    def _scan(self):
        return design_service.scan_drawing(_drawing_bytes(), "block.dxf")

    def test_builds_bench_from_the_chosen_polylines(self):
        scan = self._scan()
        crest = next(item for item in scan.polylines if item.layer == "BROVKA_TOP")
        toe = next(item for item in scan.polylines if item.layer == "BROVKA_BOTTOM")

        result = design_service.bench_from_polylines(BenchFromPolylinesRequest(
            crest=_points(crest), toe=_points(toe),
            crest_layer=crest.layer, toe_layer=toe.layer, filename="block.dxf",
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
        scan = self._scan()
        crest = next(item for item in scan.polylines if item.layer == "BROVKA_TOP")
        toe = next(item for item in scan.polylines if item.layer == "BROVKA_BOTTOM")

        with self.assertRaises(InvalidSurveyError) as ctx:
            design_service.bench_from_polylines(BenchFromPolylinesRequest(
                crest=_points(toe), toe=_points(crest),
            ))
        self.assertIn("выше", str(ctx.exception))

    def test_degenerate_selection_is_rejected(self):
        with self.assertRaises(InvalidSurveyError):
            design_service.bench_from_polylines(BenchFromPolylinesRequest(
                crest=[{"x": 0, "y": 0, "z": 10}],
                toe=[{"x": 0, "y": 1, "z": 0}, {"x": 1, "y": 1, "z": 0}],
            ))


class DrawingUploadRouteTests(unittest.TestCase):
    """HTTP-путь загрузки: multipart, лимит размера, понятная ошибка."""

    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.routers import design as design_router

        os.environ["BLASTEX_API_KEY"] = "test-api-key"
        os.environ["BLASTEX_SESSION_SECRET"] = "test-session-secret"
        app = FastAPI()
        app.include_router(design_router.router, prefix="/api/v1")
        self.client = TestClient(app, headers={"X-API-Key": "test-api-key"})

    def test_upload_returns_polylines(self):
        response = self.client.post(
            "/api/v1/design/drawing/polylines",
            files={"file": ("block.dxf", _drawing_bytes(), "application/dxf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual({item["layer"] for item in payload["polylines"]}, {"BROVKA_TOP", "BROVKA_BOTTOM"})
        self.assertEqual(payload["source_name"], "block.dxf")

    def test_oversized_upload_is_refused(self):
        from api.routers.design import MAX_DRAWING_BYTES

        response = self.client.post(
            "/api/v1/design/drawing/polylines",
            files={"file": ("huge.dxf", b"0" * (MAX_DRAWING_BYTES + 1), "application/dxf")},
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("МБ", response.json()["detail"])

    def test_bench_from_polylines_route(self):
        scan = self.client.post(
            "/api/v1/design/drawing/polylines",
            files={"file": ("block.dxf", _drawing_bytes(), "application/dxf")},
        ).json()
        crest = next(item for item in scan["polylines"] if item["layer"] == "BROVKA_TOP")
        toe = next(item for item in scan["polylines"] if item["layer"] == "BROVKA_BOTTOM")

        response = self.client.post("/api/v1/design/contour/from-polylines", json={
            "crest": crest["points"], "toe": toe["points"],
            "crest_layer": crest["layer"], "toe_layer": toe["layer"], "filename": "block.dxf",
        })
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertAlmostEqual(payload["crest_z_m"], 120.0)
        self.assertAlmostEqual(payload["toe_z_m"], 108.0)


if __name__ == "__main__":
    unittest.main()
