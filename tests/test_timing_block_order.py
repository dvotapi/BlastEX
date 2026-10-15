"""Порядок взрыва по группам рядов: пресплит — до блока, буфер и контур — после сетки.

Пресплит стартует presplit_lead_ms (по умолчанию 150) до первого основного ряда;
буфер и контур — через wall_after_ms (по умолчанию — один интервал) после
последнего основного ряда. Сетка идёт по логическим номерам, как раньше.
"""
import unittest

from design.models import Hole, Point3
from design.timing import apply_electronic_timing, build_template_network


def _hole(hid: str, row: int, col: int, kind: str) -> Hole:
    point = Point3(x=float(col) * 5.0, y=float(row) * 5.0, z=0.0)
    return Hole(id=hid, row=row, col=col, collar=point, toe=point, diameter_mm=152.0, kind=kind)


def _block():
    grid = [_hole(f"P{r}-{c}", r, c, "production") for r in (0, 1, 2) for c in (0, 1)]
    presplit = [_hole("PS-1", -1, 0, "presplit")]
    buffer = [_hole("B-1", -10, 0, "buffer")]
    contour = [_hole("K-1", -1, 0, "contour")]
    return grid + presplit + buffer + contour


PARAMS = {"interval_ms": 50.0, "base_ms": 0.0}


class BlockOrderElectronicTest(unittest.TestCase):
    def test_presplit_fires_lead_before_first_block_row(self):
        network = apply_electronic_timing(_block(), "row", PARAMS)
        times = network.electronic_times_ms
        first_block = min(times[h.id] for h in _block() if h.kind == "production")
        self.assertAlmostEqual(first_block - times["PS-1"], 150.0)

    def test_buffer_and_contour_fire_after_last_block_row(self):
        network = apply_electronic_timing(_block(), "row", PARAMS)
        times = network.electronic_times_ms
        last_block = max(times[h.id] for h in _block() if h.kind == "production")
        self.assertAlmostEqual(times["B-1"] - last_block, 50.0)
        self.assertAlmostEqual(times["K-1"] - last_block, 50.0)

    def test_walls_no_longer_share_time_with_front_row(self):
        holes = [
            _hole("F1-0", -1001, 0, "production"),
            _hole("P0-0", 0, 0, "production"),
            _hole("K-1", -1, 0, "contour"),
        ]
        times = apply_electronic_timing(holes, "row", PARAMS).electronic_times_ms
        self.assertNotAlmostEqual(times["K-1"], times["F1-0"])

    def test_without_walls_timing_is_unchanged(self):
        holes = [_hole(f"P{r}-0", r, 0, "production") for r in (0, 1, 2)]
        times = apply_electronic_timing(holes, "row", PARAMS).electronic_times_ms
        self.assertEqual([times[f"P{r}-0"] for r in (0, 1, 2)], [0.0, 50.0, 100.0])


class BlockOrderWaveTest(unittest.TestCase):
    def test_presplit_is_starter_and_contour_is_not(self):
        network = build_template_network(
            _block(), "row", {"system": "electronic", "interval_ms": 50.0, "include_contour": True}
        )
        self.assertIn("PS-1", network.starters)
        self.assertNotIn("K-1", network.starters)
        self.assertNotIn("B-1", network.starters)


if __name__ == "__main__":
    unittest.main()
