"""Ручные скважины в старых шаблонах коммутации (порядная, эшелон, V, трапеция).

Ручная скважина (`source = "manual"`, ряд −1000, номер `M-<n>`) — «прочая»,
как у «Магистраль + цепочки»: сетка строится без неё (её стартовые и времена
— те же, что без ручной), а сама ручная подключается связью от ближайшей уже
подключённой скважины ступенью — интервалом схемы (решение владельца
14.11.2026), не входит в общий шнур ДШ, и генерация предупреждает об этом.
С TASK-017 PR 5 добавление скважины само пересчитывает сеть шаблона, поэтому
ручная не должна становиться стартовой посреди блока.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from design.models import BenchSurface, BlockContour, Hole, Point3
from design.pattern import generate_pattern
from design.timing import (
    build_template_network,
    build_template_network_with_warnings,
    resolve_network,
)

OLD_SCHEMES = ("row", "echelon", "diagonal_v", "trapezoid")
SYSTEMS = ("nonel", "detcord", "electronic")
INTERVAL = {"nonel": 25.0, "detcord": 20.0, "electronic": 17.0}

PARAMS = {
    "pattern": "rectangular",
    "spacing_a_m": 5.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": 90.0,
    "angle_deg": 0.0,
    "subdrill_m": 1.0,
    "diameter_mm": 165.0,
}


def _grid() -> list[Hole]:
    contour = BlockContour(
        vertices=[Point3(0, 0, 0), Point3(40, 0, 0), Point3(40, 30, 0), Point3(0, 30, 0)],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=75.0),
    )
    return generate_pattern(contour, PARAMS)


def _manual(grid: list[Hole], hole_id: str, x: float, y: float) -> Hole:
    """Ручная скважина, как её ставит план: ряд −1000, столбец 0."""
    base = grid[0]
    return replace(
        base,
        id=hole_id,
        source="manual",
        row=-1000,
        col=0,
        collar=Point3(x, y, base.collar.z),
        toe=Point3(x, y, base.toe.z),
    )


def _between_rows(grid: list[Hole]) -> tuple[float, float]:
    """Точка между вторым и третьим рядами, рядом со вторым столбцом."""
    rows = sorted({hole.row for hole in grid})
    second = sorted((h for h in grid if h.row == rows[1]), key=lambda h: h.collar.x)[1]
    third = sorted((h for h in grid if h.row == rows[2]), key=lambda h: h.collar.x)[1]
    return second.collar.x + 1.0, (second.collar.y + third.collar.y) / 2.0


class ManualHoleInOldTemplatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.grid = _grid()
        x, y = _between_rows(self.grid)
        self.manual = _manual(self.grid, "M-1", x, y)
        self.holes = self.grid + [self.manual]

    def test_manual_is_not_starter_and_grid_times_unchanged(self) -> None:
        for system in SYSTEMS:
            for scheme in OLD_SCHEMES:
                with self.subTest(system=system, scheme=scheme):
                    params = {"system": system}
                    before = build_template_network(self.grid, scheme, params)
                    after = build_template_network(self.holes, scheme, params)
                    self.assertNotIn("M-1", after.starters)
                    self.assertEqual(after.starters, before.starters)
                    self.assertEqual([item.hole_id for item in after.starter_items], before.starters)
                    times_before = resolve_network(before, self.grid).times_ms
                    times_after = resolve_network(after, self.holes).times_ms
                    for hole_id, value in times_before.items():
                        self.assertAlmostEqual(times_after[hole_id], value, places=6, msg=hole_id)

    def test_manual_hangs_on_nearest_tied_hole_with_scheme_interval(self) -> None:
        for system in SYSTEMS:
            for scheme in OLD_SCHEMES:
                with self.subTest(system=system, scheme=scheme):
                    network = build_template_network(self.holes, scheme, {"system": system})
                    # Ручная — лист: из неё связей нет, входящая одна.
                    self.assertFalse([c for c in network.surface_connectors if c.from_hole == "M-1"])
                    incoming = [c for c in network.surface_connectors if c.to_hole == "M-1"]
                    self.assertEqual(len(incoming), 1)
                    self.assertEqual(incoming[0].delay_ms, INTERVAL[system])
                    nearest = min(
                        self.grid,
                        key=lambda h: (
                            (h.collar.x - self.manual.collar.x) ** 2 + (h.collar.y - self.manual.collar.y) ** 2,
                            h.id,
                        ),
                    )
                    self.assertEqual(incoming[0].from_hole, nearest.id)
                    times = resolve_network(network, self.holes).times_ms
                    self.assertAlmostEqual(times["M-1"], times[nearest.id] + INTERVAL[system], places=6)
                    # В общий шнур ДШ ручная не входит: время — только по своей связи.
                    for cord in network.detonating_cords:
                        self.assertNotIn("M-1", cord.hole_ids)

    def test_interval_from_params_is_the_step(self) -> None:
        network = build_template_network(self.holes, "echelon", {"system": "nonel", "interval_ms": 42})
        incoming = [c for c in network.surface_connectors if c.to_hole == "M-1"]
        self.assertEqual([c.delay_ms for c in incoming], [42.0])

    def test_close_manual_holes_hang_on_each_other(self) -> None:
        # Две ручные рядом: ближняя к сетке — от сетки, вторая — от неё (как Прим).
        x, y = self.manual.collar.x, self.manual.collar.y
        near = _manual(self.grid, "M-2", x + 0.3, y + 0.3)
        network = build_template_network(self.holes + [near], "row", {"system": "nonel"})
        incoming = {c.to_hole: c.from_hole for c in network.surface_connectors}
        self.assertTrue(incoming["M-1"] == "M-2" or incoming["M-2"] == "M-1")
        self.assertNotIn("M-1", network.starters)
        self.assertNotIn("M-2", network.starters)

    def test_disabled_manual_is_ignored(self) -> None:
        holes = self.grid + [replace(self.manual, enabled=False)]
        network, warnings = build_template_network_with_warnings(holes, "row", {"system": "nonel"})
        self.assertFalse([c for c in network.surface_connectors if "M-1" in (c.from_hole, c.to_hole)])
        self.assertEqual(warnings, [])

    def test_warning_names_manual_holes_and_step(self) -> None:
        _network, warnings = build_template_network_with_warnings(self.holes, "echelon", {"system": "nonel"})
        self.assertEqual(len(warnings), 1)
        self.assertIn("M-1", warnings[0])
        self.assertIn("25 мс", warnings[0])
        _network, warnings = build_template_network_with_warnings(self.grid, "echelon", {"system": "nonel"})
        self.assertEqual(warnings, [])

    def test_only_manual_holes_keep_previous_behaviour(self) -> None:
        # Сетки нет — привязать не к чему: ручные стартуют, как раньше.
        only = [self.manual, _manual(self.grid, "M-2", 10.0, 10.0)]
        network, warnings = build_template_network_with_warnings(only, "row", {"system": "nonel"})
        self.assertEqual(sorted(network.starters), ["M-1", "M-2"])
        self.assertEqual(warnings, [])

    def test_electronic_timing_mode_keeps_manual_with_first_wave(self) -> None:
        # Режим электронного тайминга программирует время сам (ручные — с первым
        # рядом); связи схемы в нём лишь рисунок, предупреждения нет.
        network, warnings = build_template_network_with_warnings(
            self.holes, "row", {"system": "electronic", "timing_mode": "row", "interval_ms": 17}
        )
        self.assertEqual(warnings, [])
        self.assertIn("M-1", network.electronic_times_ms)


if __name__ == "__main__":
    unittest.main()
