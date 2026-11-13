"""Фикстура клиентских времён срабатывания (TASK-017, PR 4).

После правки связей на плане фронт сам пересчитывает времена и «без сигнала»
(`frontend/src/pages/design/networkTimes.ts`, порт `design/timing.py::
resolve_network`), без запроса к серверу. Общий пример лежит во фронте
(`frontend/src/pages/design/testing/networkTimesFixture.json`): этот тест
проверяет, что записанные в нём времена — те, что сейчас даёт
`resolve_network`, а тест фронта — что клиент получает то же самое.

Перезаписать фикстуру после намеренной смены правила:
`BLASTEX_WRITE_FIXTURES=1 pytest tests/test_network_times_fixture.py`.
"""
from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from pathlib import Path

from design.models import BenchSurface, BlockContour, DownholeConnector, Hole, InitiationNetwork, Point3
from design.pattern import generate_pattern
from design.timing import build_template_network, resolve_network
from design.trunk_network import build_trunk_chains_network

FIXTURE = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "design" / "testing" / "networkTimesFixture.json"
)

PARAMS = {
    "pattern": "rectangular",
    "spacing_a_m": 5.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": 90.0,
    "angle_deg": 0.0,
    "subdrill_m": 1.0,
    "diameter_mm": 165.0,
}


def _holes() -> list[Hole]:
    contour = BlockContour(
        vertices=[Point3(0, 0, 0), Point3(40, 0, 0), Point3(40, 30, 0), Point3(0, 30, 0)],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=75.0),
    )
    holes = generate_pattern(contour, PARAMS)
    # Координаты — как их хранит паспорт (миллиметры): клиент и сервер считают
    # по одним и тем же числам.
    return [
        replace(
            hole,
            collar=Point3(round(hole.collar.x, 3), round(hole.collar.y, 3), round(hole.collar.z, 3)),
            toe=Point3(round(hole.toe.x, 3), round(hole.toe.y, 3), round(hole.toe.z, 3)),
        )
        for hole in holes
    ]


def _trunk(holes: list[Hole], system: str) -> InitiationNetwork:
    network, _warnings = build_trunk_chains_network(
        holes, {"system": system, "trunk_ms": 25, "chain_ms": 42, "cut_flank": "left"}
    )
    return network


def _edited(holes: list[Hole]) -> tuple[list[Hole], InitiationNetwork]:
    """Правленая сеть СИНВ: снята связь в середине цепочки (за ней — без сигнала),
    стартовая с задержкой, своё замедление в одной скважине, связь к исключённой
    скважине."""
    network = _trunk(holes, "nonel")
    outgoing = {item.from_hole for item in network.surface_connectors}
    cut = next(item for item in network.surface_connectors if item.to_hole in outgoing)
    network.surface_connectors = [item for item in network.surface_connectors if item.id != cut.id]
    network.starter_items = [replace(item, delay_ms=5.0) for item in network.starter_items]
    target = network.surface_connectors[-1].to_hole
    network.downhole_connectors = [
        replace(item, delay_ms=700.0) if item.hole_id == target else item for item in network.downhole_connectors
    ]
    if not any(item.hole_id == target for item in network.downhole_connectors):
        network.downhole_connectors.append(DownholeConnector(id=f"dh-{target}", hole_id=target, delay_ms=700.0))
    disabled = network.surface_connectors[0].to_hole
    holes = [replace(hole, enabled=False) if hole.id == disabled else hole for hole in holes]
    network.sync_legacy_from_v2()
    return holes, network


def _case(name: str, holes: list[Hole], network: InitiationNetwork) -> dict:
    result = resolve_network(network, holes)
    enabled = {hole.id for hole in holes if hole.enabled}
    payload = network.to_dict()
    payload["firing_events"] = []
    return {
        "name": name,
        "holes": [
            {"id": hole.id, "collar": {"x": hole.collar.x, "y": hole.collar.y, "z": hole.collar.z}, "enabled": hole.enabled}
            for hole in holes
        ],
        "network": payload,
        "times": {hole_id: round(value, 6) for hole_id, value in sorted(result.times_ms.items())},
        "unsignaled": sorted(enabled - set(result.times_ms)),
    }


def build_fixture() -> dict:
    holes = _holes()
    edited_holes, edited = _edited(holes)
    electronic = build_template_network(
        holes, "row", {"system": "electronic", "timing_mode": "row", "interval_ms": 17, "base_ms": 0}
    )
    return {
        "cases": [
            _case("trunk_nonel", holes, _trunk(holes, "nonel")),
            _case("trunk_detcord", holes, _trunk(holes, "detcord")),
            _case("trunk_nonel_edited", edited_holes, edited),
            # Порядная ДШ: общий шнур — отрезки «расстояние / скорость + реле» в обе стороны.
            _case("row_detcord_cord", holes, build_template_network(holes, "row", {"system": "detcord"})),
            _case("row_electronic", holes, electronic),
        ],
    }


class NetworkTimesFixtureTest(unittest.TestCase):
    def test_fixture_matches_server(self) -> None:
        fixture = build_fixture()
        if os.environ.get("BLASTEX_WRITE_FIXTURES") == "1":
            FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE.write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        saved = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(saved, json.loads(json.dumps(fixture)), "фикстура разошлась с сервером — перезапишите её")

    def test_cases_cover_the_rules(self) -> None:
        cases = {case["name"]: case for case in build_fixture()["cases"]}
        # Связи-реле у «Магистраль + цепочки» ДШ без шнура, у порядной — шнур.
        self.assertEqual(cases["trunk_detcord"]["network"]["detonating_cords"], [])
        self.assertTrue(cases["row_detcord_cord"]["network"]["detonating_cords"])
        # Правленая сеть: есть скважины без сигнала, исключённая в них не входит.
        edited = cases["trunk_nonel_edited"]
        disabled = {hole["id"] for hole in edited["holes"] if not hole["enabled"]}
        self.assertTrue(edited["unsignaled"])
        self.assertTrue(disabled)
        self.assertFalse(disabled & set(edited["unsignaled"]))
        self.assertFalse(disabled & set(edited["times"]))
        self.assertFalse(cases["trunk_nonel"]["unsignaled"])
        # Электронная — времена каналов, а не связей.
        self.assertTrue(cases["row_electronic"]["network"]["electronic_times_ms"] or cases["row_electronic"]["network"]["electronic_channels"])


if __name__ == "__main__":
    unittest.main()
