"""Построитель графа «магистраль + цепочки»: вруб у фланга, магистраль по головам
столбцов, цепочки назад по рядам, пара у откоса и прочие скважины."""
import math
import unittest
from collections import Counter

from design.models import Hole, face_pair_partner_id, logical_row
from design.pattern import generate_pattern
from design.trunk_network import plan_trunk_chains, row_axis
from tests.front_rows_fixtures import BASE, CONTOUR, _contour_of, _rect_contour, vertical_hole

# Прямоугольник 20×16, a = b = 4, бровка снизу: ряд 0 на y = 0, вглубь — по +Y.
RECT = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": 90.0,
    "offset_from_face_m": 0.0,
    "edge_margin_m": 0.0,
}


def _rect_holes(pattern: str = "rectangular") -> list[Hole]:
    return generate_pattern(_rect_contour(20.0, 16.0), RECT | {"pattern": pattern})


def _dist(a: Hole, b: Hole) -> float:
    return math.hypot(a.collar.x - b.collar.x, a.collar.y - b.collar.y)


class RectangularGridTests(unittest.TestCase):
    def setUp(self):
        self.holes = _rect_holes()
        self.by_id = {h.id: h for h in self.holes}
        self.min_row = min(logical_row(h.row) for h in self.holes)
        self.first_row = [h for h in self.holes if logical_row(h.row) == self.min_row]

    def test_row_axis_along_face_and_deep_into_block(self):
        axis, deep = row_axis(self.holes)
        self.assertAlmostEqual(axis[0], 1.0, places=6)
        self.assertAlmostEqual(axis[1], 0.0, places=6)
        self.assertAlmostEqual(deep[0], 0.0, places=6)
        self.assertAlmostEqual(deep[1], 1.0, places=6)

    def test_rectangular_grid_trunk_and_chains(self):
        plan = plan_trunk_chains(self.holes, cut_flank="left")
        self.assertEqual(len(plan.starters), 1)
        starter = self.by_id[plan.starters[0]]
        self.assertEqual(logical_row(starter.row), self.min_row)
        self.assertEqual(starter.collar.x, min(h.collar.x for h in self.first_row))
        incoming = Counter(to for _, to, _ in plan.ties)
        self.assertTrue(all(incoming[h.id] == 1 for h in self.holes if h.id not in plan.starters))
        self.assertEqual(incoming[starter.id], 0)
        for h in self.holes:
            col_rank = round(h.collar.x / 4.0)
            row_rank = logical_row(h.row) - self.min_row
            self.assertAlmostEqual(plan.surface_ms[h.id], 25 * col_rank + 42 * row_rank, msg=h.id)

    def test_right_flank_mirrors(self):
        plan = plan_trunk_chains(self.holes, cut_flank="right")
        self.assertEqual(self.by_id[plan.starters[0]].collar.x, max(h.collar.x for h in self.first_row))
        for h in self.holes:
            col_rank = round((20.0 - h.collar.x) / 4.0)
            row_rank = logical_row(h.row) - self.min_row
            self.assertAlmostEqual(plan.surface_ms[h.id], 25 * col_rank + 42 * row_rank, msg=h.id)

    def test_unknown_flank_falls_back_to_left(self):
        plan = plan_trunk_chains(self.holes, cut_flank="middle")
        self.assertEqual(self.by_id[plan.starters[0]].collar.x, min(h.collar.x for h in self.first_row))

    def test_only_nsi_delays(self):
        plan = plan_trunk_chains(self.holes, trunk_ms=24.0, chain_ms=40.0)
        self.assertEqual({ms for *_, ms in plan.ties}, {25.0, 42.0})


class SteppedFrontTests(unittest.TestCase):
    def test_stepped_front_trunk_follows_column_heads(self):
        holes = _rect_holes()
        # Ступень бровки: в левой половине нет ряда 0.
        stepped = [h for h in holes if not (logical_row(h.row) == 0 and h.collar.x < 10.0)]
        heads: dict[int, Hole] = {}
        for h in stepped:
            col = round(h.collar.x / 4.0)
            if col not in heads or logical_row(h.row) < logical_row(heads[col].row):
                heads[col] = h
        column_heads = {h.id for h in heads.values()}
        self.assertGreater(len({logical_row(h.row) for h in heads.values()}), 1)
        plan = plan_trunk_chains(stepped, cut_flank="left")
        trunk_targets = {to for _, to, ms in plan.ties if ms == 25.0}
        self.assertEqual(trunk_targets | set(plan.starters), column_heads)
        self.assertEqual(set(plan.surface_ms), {h.id for h in stepped})


class GapAndWideningTests(unittest.TestCase):
    def _assert_columns_fire_front_to_back(self, holes, plan):
        for h in holes:
            for front in holes:
                same_column = abs(front.collar.x - h.collar.x) < 1e-6
                if same_column and logical_row(front.row) < logical_row(h.row):
                    self.assertGreater(plan.surface_ms[h.id], plan.surface_ms[front.id], msg=(front.id, h.id))

    def test_gap_in_column_does_not_make_a_head(self):
        holes = _rect_holes()
        gap = next(h for h in holes if logical_row(h.row) == 1 and abs(h.collar.x - 8.0) < 1e-6)
        behind = next(h for h in holes if logical_row(h.row) == 2 and abs(h.collar.x - 8.0) < 1e-6)
        front = next(h for h in holes if logical_row(h.row) == 0 and abs(h.collar.x - 8.0) < 1e-6)
        holes = [h for h in holes if h.id != gap.id]
        plan = plan_trunk_chains(holes)
        self.assertIn((front.id, behind.id, 42.0), plan.ties)
        self.assertEqual(set(plan.surface_ms), {h.id for h in holes})
        self._assert_columns_fire_front_to_back(holes, plan)

    def test_widening_contour_keeps_cut_in_front_row(self):
        # Трапеция: фронт x 8…20 у бровки y = 0, тыл x 0…20 — контур расширяется вглубь.
        contour = _contour_of([(8.0, 0.0), (20.0, 0.0), (20.0, 16.0), (0.0, 16.0)], ((0, 1),))
        holes = generate_pattern(contour, RECT)
        by_id = {h.id: h for h in holes}
        min_row = min(logical_row(h.row) for h in holes)
        first_row = [h for h in holes if logical_row(h.row) == min_row]
        self.assertLess(min(h.collar.x for h in holes), min(h.collar.x for h in first_row))
        plan = plan_trunk_chains(holes, cut_flank="left")
        starter = by_id[plan.starters[0]]
        self.assertEqual(logical_row(starter.row), min_row)
        self.assertEqual(starter.collar.x, min(h.collar.x for h in first_row))
        self.assertEqual(set(plan.surface_ms), {h.id for h in holes})
        self.assertTrue(all(ms in (25.0, 42.0) for _, _, ms in plan.ties))
        self._assert_columns_fire_front_to_back(holes, plan)


class FacePairTests(unittest.TestCase):
    def test_face_pair_fires_with_vertical(self):
        holes = generate_pattern(CONTOUR, BASE | {"front_rows_mode": "pair"})
        toes = [h for h in holes if h.kind == "face_toe"]
        self.assertTrue(toes)
        plan = plan_trunk_chains(holes)
        for toe in toes:
            partner = face_pair_partner_id(toe)
            self.assertEqual(plan.surface_ms[toe.id], plan.surface_ms[partner])
            if partner in plan.starters:
                self.assertIn(toe.id, plan.starters)
            else:
                into_toe = [(f, ms) for f, t, ms in plan.ties if t == toe.id]
                into_partner = [(f, ms) for f, t, ms in plan.ties if t == partner]
                self.assertEqual(into_toe, into_partner)
        self.assertFalse(any(ms == 0.0 for _, _, ms in plan.ties))
        self.assertEqual(set(plan.surface_ms), {h.id for h in holes})


class StaggeredTests(unittest.TestCase):
    def test_staggered_every_hole_timed_once(self):
        staggered = _rect_holes("staggered")
        self.assertGreater(len({round(h.collar.x % 4.0, 3) for h in staggered}), 1)
        plan = plan_trunk_chains(staggered)
        self.assertEqual(set(plan.surface_ms), {h.id for h in staggered})
        self.assertTrue(all(ms in (25.0, 42.0) for _, _, ms in plan.ties))
        incoming = Counter(to for _, to, _ in plan.ties)
        self.assertTrue(all(incoming[h.id] == 1 for h in staggered if h.id not in plan.starters))
        by_id = {h.id: h for h in staggered}
        # Цепочка 42 мс — всегда к скважине предыдущего ряда.
        for frm, to, ms in plan.ties:
            if ms == 42.0:
                self.assertEqual(logical_row(by_id[frm].row) + 1, logical_row(by_id[to].row))


class StrayTests(unittest.TestCase):
    def test_strays_tie_to_nearest(self):
        grid = _rect_holes()
        strays = [
            vertical_hole("S1", 9.0, 17.5, row=4, kind="stab"),
            vertical_hole("K1", -2.0, 5.0, row=-1, kind="contour"),
            vertical_hole("K2", 22.0, 13.0, row=-1, kind="contour"),
        ]
        holes_with_strays = grid + strays

        def nearest_timed_neighbour_id(stray: Hole) -> str:
            return min(grid, key=lambda h: _dist(h, stray)).id

        plan = plan_trunk_chains(holes_with_strays)
        for stray in strays:
            frm, ms = next((f, m) for f, t, m in plan.ties if t == stray.id)
            self.assertEqual(frm, nearest_timed_neighbour_id(stray))
            self.assertEqual(ms, 42.0)
            self.assertIn(stray.id, plan.surface_ms)
        self.assertEqual(len(plan.starters), 1)


class DegenerateTests(unittest.TestCase):
    def test_degenerate_layouts(self):
        single = vertical_hole("1-01", 5.0, 5.0, row=0)
        plan = plan_trunk_chains([single])
        self.assertEqual(plan.starters, [single.id])
        self.assertEqual(plan.ties, [])
        self.assertEqual(plan.surface_ms, {single.id: 0.0})
        row_of_five = [vertical_hole(f"1-0{i + 1}", 4.0 * i, 0.0, row=0) for i in range(5)]
        one_row = plan_trunk_chains(row_of_five)
        self.assertEqual(len(one_row.ties), 4)
        self.assertEqual(sorted(one_row.surface_ms.values()), [0.0, 25.0, 50.0, 75.0, 100.0])
        self.assertEqual(plan_trunk_chains([]).starters, [])


if __name__ == "__main__":
    unittest.main()
