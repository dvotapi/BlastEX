"""Задержки по типу коммутации поверхности: согласованные значения по умолчанию.

nonel — шаг снапится к ступеням НСИ (17, 25, 42, 67, 109 мс), по умолчанию 25;
ДШ — шаг снапится к ступеням реле (10, 20, 25, 35, 42 мс), по умолчанию 20; плюс
время пробега по шнуру длина ÷ 7000 м/с; электронная — свободный шаг, по умолчанию 17.
"""
import unittest

from design.models import Hole, Point3
from design.timing import DEFAULT_INTERVAL_MS, build_template_network


def _row(hid: str, x: float, row: int) -> Hole:
    p = Point3(x=x, y=row * 5.0, z=0.0)
    return Hole(id=hid, row=row, col=0, collar=p, toe=p, diameter_mm=152.0)


class ConnectionDelayDefaultsTest(unittest.TestCase):
    def test_defaults_match_agreed_values(self):
        self.assertEqual(DEFAULT_INTERVAL_MS, {"nonel": 25.0, "electronic": 17.0, "detcord": 20.0})

    def test_nonel_interval_snaps_to_surface_nsi_ladder(self):
        holes = [_row("a", 0.0, 0), _row("b", 0.0, 1)]
        net = build_template_network(holes, "row", {"system": "nonel", "interval_ms": 20.0})
        self.assertEqual(net.timing_params["interval_ms"], 17.0)
        net = build_template_network(holes, "row", {"system": "nonel", "interval_ms": 30.0})
        self.assertEqual(net.timing_params["interval_ms"], 25.0)

    def test_detcord_interval_snaps_to_relay_ladder(self):
        holes = [_row("a", 0.0, 0), _row("b", 0.0, 1)]
        net = build_template_network(holes, "row", {"system": "detcord", "interval_ms": 22.0})
        self.assertEqual(net.timing_params["interval_ms"], 20.0)

    def test_electronic_interval_is_free(self):
        holes = [_row("a", 0.0, 0), _row("b", 0.0, 1)]
        net = build_template_network(holes, "row", {"system": "electronic", "interval_ms": 33.3})
        self.assertEqual(net.timing_params["interval_ms"], 33.3)


if __name__ == "__main__":
    unittest.main()


class PresplitLeadLadderTest(unittest.TestCase):
    def test_presplit_lead_on_nonel_is_the_largest_ladder_step_below_lead(self):
        from design.models import Hole, Point3

        def h(hid, x, row, kind="production"):
            p = Point3(x=x, y=row * 5.0, z=0.0)
            return Hole(id=hid, row=row, col=0, collar=p, toe=p, diameter_mm=152.0, kind=kind)

        holes = [h("P0", 0.0, 0), h("P1", 0.0, 1), h("PS", 0.0, -1, "presplit")]
        net = build_template_network(holes, "row", {"system": "nonel", "interval_ms": 25.0})
        delays = {(c.from_hole, c.to_hole): c.delay_ms for c in net.connectors}
        # 150 мс не входит в ступени НСИ: ближайшая не выше — 109 мс.
        self.assertEqual(delays[("PS", "P0")], 109.0)
        self.assertEqual(delays[("P0", "P1")], 25.0)
