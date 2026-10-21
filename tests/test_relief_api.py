"""Темп отбойки в ответе анализа тайминга."""
import unittest

from api.schemas.design import AnalyzeRequest, PatternGenerateRequest, TieGenerateRequest
from api.services import design_service


def _contour_payload(width: float = 20.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


def _analyze(height: float):
    holes = design_service.generate_pattern(
        PatternGenerateRequest(
            contour=_contour_payload(height=height),
            params={
                "pattern": "rectangular",
                "spacing_a_m": 4.0,
                "burden_b_m": 4.0,
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
            },
        )
    ).holes
    tie = design_service.generate_tie(
        TieGenerateRequest(
            holes=[h.model_dump() for h in holes],
            scheme="row",
            params={"system": "nonel", "surface_delay_ms": 25.0, "row_delay_ms": 42.0},
        )
    )
    return design_service.analyze_design(
        AnalyzeRequest(
            design={
                "design_id": "relief",
                "holes": [h.model_dump() for h in holes],
                "contour": _contour_payload(height=height),
                "network": tie.network.model_dump(),
                "loads": [],
            }
        )
    )


class ReliefApiTests(unittest.TestCase):
    def test_analyze_returns_burden_relief(self):
        relief = _analyze(16.0).relief
        self.assertIsNotNone(relief)
        self.assertGreater(relief.stats.triangles, 0)
        self.assertGreater(relief.stats.median_ms_m, 0)
        self.assertEqual(len(relief.triangles[0].points), 3)
        # округление: мс/м — 2 знака, координаты — 3
        value = relief.triangles[0].relief_ms_m
        self.assertEqual(value, round(value, 2))
        for x, y in relief.triangles[0].points:
            self.assertEqual(x, round(x, 3))
            self.assertEqual(y, round(y, 3))

    def test_analyze_without_triangles_returns_null_relief(self):
        # узкий блок — один ряд скважин на одной прямой
        self.assertIsNone(_analyze(3.0).relief)
