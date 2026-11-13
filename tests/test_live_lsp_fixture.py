"""Фикстура живой проверки ЛСП на плане (TASK-017, PR 1).

Фронт при перетаскивании скважин считает ЛСП сам, без запроса к серверу
(`frontend/src/pages/design/liveChecks.ts`), по линии подошвы, которую уже
получил от пересчёта скважин. Чтобы правило не разошлось с сервером, общий
пример лежит во фронте (`frontend/src/pages/design/testing/liveLspFixture.json`):
этот тест проверяет, что записанные в нём ЛСП и превышения — те, что сейчас
даёт `design/toe_line.py::floor_burdens`, а тест фронта — что клиент
получает то же самое по той же линии подошвы.

Перезаписать фикстуру после намеренной смены правила:
`BLASTEX_WRITE_FIXTURES=1 pytest tests/test_live_lsp_fixture.py`.
"""
from __future__ import annotations

import json
import math
import os
import unittest
from dataclasses import replace
from pathlib import Path

from api.services.design_service import _toe_line_schema
from design.models import BenchSurface, BlastDesign, BlockContour, Hole, Point3
from design.pattern import generate_pattern
from design.toe_line import allowed_floor_burden_m, floor_burdens

FIXTURE = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "design" / "testing" / "liveLspFixture.json"
)

# Повёрнутая раскладка: бровка и ряды — по азимуту 30°, блок 40 × 25 м,
# уступ 10 м, подошва по углу 75°.
ROW_AZIMUTH_DEG = 30.0
BASE_PARAMS = {
    "pattern": "rectangular",
    "spacing_a_m": 5.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": ROW_AZIMUTH_DEG,
    "angle_deg": 0.0,
    "subdrill_m": 1.0,
    "diameter_mm": 165.0,
    "min_crest_offset_m": 0.3,
}
PAIR_PARAMS = {**BASE_PARAMS, "front_rows_mode": "pair", "front_rows_tilt_deg": 15.0}
PLAIN_PARAMS = {**BASE_PARAMS, "offset_from_face_m": 1.0}


def _contour() -> BlockContour:
    along = (math.sin(math.radians(ROW_AZIMUTH_DEG)), math.cos(math.radians(ROW_AZIMUTH_DEG)))
    inward = (along[1], -along[0])
    v0 = (0.0, 0.0)
    v1 = (40 * along[0], 40 * along[1])
    v2 = (v1[0] + 25 * inward[0], v1[1] + 25 * inward[1])
    v3 = (25 * inward[0], 25 * inward[1])
    return BlockContour(
        vertices=[Point3(round(x, 3), round(y, 3), 0.0) for x, y in (v0, v1, v2, v3)],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=75.0),
    )


def _moved(holes: list[Hole], hole_id: str, deep_m: float) -> list[Hole]:
    """Скважина `hole_id` и её ось — на `deep_m` вглубь блока (от откоса)."""
    az = math.radians(ROW_AZIMUTH_DEG)
    dx, dy = deep_m * math.cos(az), -deep_m * math.sin(az)
    out = []
    for hole in holes:
        if hole.id == hole_id:
            hole = replace(
                hole,
                collar=Point3(round(hole.collar.x + dx, 3), round(hole.collar.y + dy, 3), hole.collar.z),
                toe=Point3(round(hole.toe.x + dx, 3), round(hole.toe.y + dy, 3), hole.toe.z),
            )
        out.append(hole)
    return out


def _round_hole(hole: Hole) -> Hole:
    # Координаты — как их хранит паспорт (миллиметры), чтобы клиент и сервер
    # считали по одним и тем же числам.
    return replace(
        hole,
        collar=Point3(round(hole.collar.x, 3), round(hole.collar.y, 3), round(hole.collar.z, 3)),
        toe=Point3(round(hole.toe.x, 3), round(hole.toe.y, 3), round(hole.toe.z, 3)),
    )


def _case(name: str, contour: BlockContour, holes: list[Hole], params: dict) -> dict:
    design = BlastDesign(design_id="fixture", contour=contour, holes=holes, pattern_params=params)
    burdens = floor_burdens(design)
    toe_line = _toe_line_schema(contour)
    assert toe_line is not None
    return {
        "name": name,
        "pattern_params": params,
        "holes": [hole.to_dict() for hole in holes],
        "toe_line": toe_line.model_dump(),
        "allowed_m": allowed_floor_burden_m(params),
        "expected": {
            hole_id: {"value_m": round(item.value_m, 6), "excess": item.excess}
            for hole_id, item in sorted(burdens.items())
        },
    }


def build_fixture() -> dict:
    contour = _contour()
    pair = [_round_hole(h) for h in generate_pattern(contour, PAIR_PARAMS)]
    plain = [_round_hole(h) for h in generate_pattern(contour, PLAIN_PARAMS)]
    return {
        "contour": contour.to_dict(),
        "cases": [
            _case("pair", contour, pair, PAIR_PARAMS),
            _case("pair_moved", contour, _moved(pair, "5-01T", 1.5), PAIR_PARAMS),
            _case("plain", contour, plain, PLAIN_PARAMS),
            # На 1 м вглубь — соседи по ряду впереди меньше чем на 0,4·min(a, b):
            # скважина остаётся первым рядом, ЛСП больше W + 3 %.
            _case("plain_moved", contour, _moved(plain, "5-01", 1.0), PLAIN_PARAMS),
            # На 2 м — соседи по ряду уже впереди и закрывают её: ЛСП у неё нет.
            _case("plain_moved_closed", contour, _moved(plain, "5-01", 2.0), PLAIN_PARAMS),
        ],
    }


class LiveLspFixtureTest(unittest.TestCase):
    def test_fixture_matches_server(self) -> None:
        fixture = build_fixture()
        if os.environ.get("BLASTEX_WRITE_FIXTURES") == "1":
            FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE.write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        saved = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(saved, json.loads(json.dumps(fixture)), "фикстура разошлась с сервером — перезапишите её")

    def test_cases_cover_both_sides_of_the_limit(self) -> None:
        # В примере есть и ЛСП в допуске, и превышение, а до порога W + 3 %
        # далеко: клиентская линия подошвы округлена до миллиметра и решать
        # «на волоске» не должна.
        for case in build_fixture()["cases"]:
            allowed = case["allowed_m"]
            for item in case["expected"].values():
                self.assertGreater(abs(item["value_m"] - allowed), 0.01)
        cases = {case["name"]: case["expected"] for case in build_fixture()["cases"]}
        excess = {name: [item["excess"] for item in expected.values()] for name, expected in cases.items()}
        self.assertTrue(any(excess["pair_moved"]) and not all(excess["pair_moved"]))
        self.assertTrue(any(excess["plain_moved"]) and not all(excess["plain_moved"]))
        self.assertFalse(any(excess["plain"]))
        self.assertNotIn("5-01", cases["plain_moved_closed"])


if __name__ == "__main__":
    unittest.main()
