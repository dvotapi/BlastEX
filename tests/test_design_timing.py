import unittest

from design.models import BenchSurface, BlockContour, Point3
from design.pattern import generate_pattern
from design.timing import build_template_network, resolve_times


def _grid_contour(width: float = 20.0, height: float = 16.0) -> BlockContour:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )


def _grid_holes():
    contour = _grid_contour()
    return generate_pattern(
        contour,
        {
            "pattern": "rectangular",
            "spacing_a_m": 4.0,
            "burden_b_m": 4.0,
            "offset_from_face_m": 0.0,
            "edge_margin_m": 0.0,
        },
    )


class RowSchemeTests(unittest.TestCase):
    def test_row_scheme_times_are_monotonic_by_row(self):
        holes = _grid_holes()
        network = build_template_network(holes, "row", {"system": "nonel"})
        times, warnings = resolve_times(network, holes)
        self.assertEqual(warnings, [])
        by_row: dict[int, set[float]] = {}
        for h in holes:
            by_row.setdefault(h.row, set()).add(times[h.id])
        # В пределах ряда все скважины срабатывают одновременно.
        for row, row_times in by_row.items():
            self.assertEqual(len(row_times), 1, f"row {row} has mixed times: {row_times}")
        # Времена рядов строго возрастают по порядку.
        row_time = {row: next(iter(vals)) for row, vals in by_row.items()}
        ordered_rows = sorted(row_time)
        ordered_times = [row_time[r] for r in ordered_rows]
        self.assertEqual(ordered_times, sorted(ordered_times))
        self.assertTrue(all(b > a for a, b in zip(ordered_times, ordered_times[1:])))


class EarliestArrivalTests(unittest.TestCase):
    def test_shortest_path_wins_over_longer_alternative(self):
        holes = _grid_holes()
        holes_by_id = {h.id: h for h in holes}
        network = build_template_network(holes, "echelon", {"system": "electronic", "interval_ms": 10.0})
        # Добавляем более длинный альтернативный путь к дальней скважине — он не должен победить.
        far_hole_id = holes[-1].id
        from design.models import Connector

        network.connectors.append(Connector(from_hole=network.starters[0], to_hole=far_hole_id, delay_ms=10000.0))
        times, warnings = resolve_times(network, holes)
        self.assertEqual(warnings, [])
        # Время дальней скважины должно определяться графом, а не длинным альтернативным путём.
        self.assertLess(times[far_hole_id], 10000.0)
        self.assertIn(far_hole_id, holes_by_id)


class DisconnectedHoleTests(unittest.TestCase):
    def test_hole_missing_from_network_is_reported(self):
        holes = _grid_holes()
        network = build_template_network(holes, "row", {"system": "nonel", "include_contour": False})
        # Убираем все коннекторы, ведущие к последней скважине — делаем её недостижимой.
        last_id = holes[-1].id
        network.connectors = [c for c in network.connectors if c.to_hole != last_id]
        network.surface_connectors = [c for c in network.surface_connectors if c.to_hole != last_id]
        network.starters = [s for s in network.starters if s != last_id]
        network.starter_items = [s for s in network.starter_items if s.hole_id != last_id]
        times, warnings = resolve_times(network, holes)
        self.assertNotIn(last_id, times)
        self.assertTrue(any(last_id in w for w in warnings))


class SchemeVarietyTests(unittest.TestCase):
    def test_all_schemes_produce_full_coverage_without_warnings(self):
        holes = _grid_holes()
        for scheme in ("row", "echelon", "diagonal_v", "trapezoid"):
            network = build_template_network(holes, scheme, {"system": "nonel"})
            times, warnings = resolve_times(network, holes)
            self.assertEqual(warnings, [], msg=f"scheme={scheme}")
            self.assertEqual(len(times), len(holes), msg=f"scheme={scheme}")

    def test_diagonal_v_and_trapezoid_pick_different_starters(self):
        holes = _grid_holes()
        v_network = build_template_network(holes, "diagonal_v", {"system": "nonel"})
        trapezoid_network = build_template_network(holes, "trapezoid", {"system": "nonel"})
        self.assertNotEqual(set(v_network.starters), set(trapezoid_network.starters))


class NonelSnappingTests(unittest.TestCase):
    def test_interval_snaps_to_nearest_nominal(self):
        holes = _grid_holes()
        network = build_template_network(holes, "row", {"system": "nonel", "interval_ms": 30.0})
        # 30 мс ближе всего к номиналу 25 или 42 — проверяем, что реальные
        # задержки коннекторов кратны одному из принятых номиналов НСИ.
        from design.timing import SURFACE_NSI_MS_OPTIONS

        deltas = {round(c.delay_ms, 1) for c in network.connectors if c.delay_ms > 0}
        for delta in deltas:
            self.assertTrue(
                any(abs(delta - k * option) < 1e-6 for option in SURFACE_NSI_MS_OPTIONS for k in range(1, 4)),
                msg=f"delay {delta} is not a multiple of any nominal",
            )


if __name__ == "__main__":
    unittest.main()
