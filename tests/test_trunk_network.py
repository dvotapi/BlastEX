"""Построитель графа «магистраль + цепочки»: вруб у фланга, магистраль по головам
столбцов, цепочки назад по рядам, пара у откоса и прочие скважины."""
import math
import unittest
from collections import Counter
from functools import lru_cache
from pathlib import Path

from design.models import BlockContour, Hole, face_pair_partner_id, logical_row
from design.pattern import generate_pattern
from design.spatial.cad.contour import ready_contour
from design.spatial.cad.reader import read_cad
from design.spatial.cad.roles import RoleParams, assign_roles
from design.spatial.cad.stitch import StitchedLine, stitch_lines
from design.spatial.cad.two_contours import bench_levels, two_contours
from design.timing import build_template_network, resolve_times
from design.trunk_network import (
    _is_column_member,
    build_trunk_chains_network,
    pick_downhole_ms,
    plan_trunk_chains,
    row_axis,
)
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


class DownholeAndNetworkTests(unittest.TestCase):
    def setUp(self):
        self.holes = _rect_holes()

    def test_pick_downhole_smallest_safe(self):
        self.assertEqual(pick_downhole_ms(320.0), (500.0, []))
        self.assertEqual(pick_downhole_ms(500.0), (700.0, []))  # строго больше
        self.assertEqual(pick_downhole_ms(999.0)[0], 1000.0)
        ms, warnings = pick_downhole_ms(1000.0)
        self.assertEqual(ms, 1000.0)
        self.assertIn("Фронт инициирования отстаёт", warnings[0])

    def test_network_resolves_to_plan_times(self):
        network, _warnings = build_trunk_chains_network(self.holes, {"system": "nonel"})
        times, _resolve_warnings = resolve_times(network, self.holes)
        plan = plan_trunk_chains(self.holes)
        for h in self.holes:
            self.assertAlmostEqual(times[h.id], plan.surface_ms[h.id] + 500.0)
        self.assertEqual(network.timing_params["scheme"], "trunk_chains")

    def test_template_entry_point(self):
        network = build_template_network(self.holes, "trunk_chains", {"system": "nonel", "cut_flank": "right"})
        self.assertEqual(network.timing_params["cut_flank"], "right")

    def test_non_nonel_system_keeps_default_downhole(self):
        network, warnings = build_trunk_chains_network(self.holes, {"system": "electronic"})
        self.assertEqual(network.downhole_connectors, [])
        self.assertEqual(warnings, [])

    def test_long_block_gets_1000_and_warning(self):
        holes = generate_pattern(
            _rect_contour(160.0, 48.0),
            RECT | {"burden_b_m": 4.0, "spacing_a_m": 4.0},
        )
        network, warnings = build_trunk_chains_network(holes, {"system": "nonel"})
        self.assertEqual(network.timing_params["downhole_delay_ms"], 1000.0)
        self.assertTrue(any("Фронт инициирования отстаёт" in w for w in warnings))


BLOCK66 = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"
# Сетка паспорта №66, как в проверках темпа отбойки и первого ряда.
BLOCK66_PARAMS = {
    "pattern": "rectangular",
    "spacing_a_m": 4.41,
    "burden_b_m": 3.53,
    "row_azimuth_deg": 0,
    "offset_from_face_m": 2,
    "first_row_burden_m": 2,
    "first_row_follow_face": False,
    "edge_margin_m": 1,
    "diameter_mm": 152,
    "subdrill_m": 1,
    "angle_deg": 0,
    "azimuth_deg": 0,
    "default_kind": "production",
}


@lru_cache(maxsize=1)
def _block66_holes() -> tuple[Hole, ...]:
    """Сетка на контуре №66: готовый контур (handle 769), откосы и отметки — как в импорте чертежа."""
    drawing = read_cad(BLOCK66.read_bytes(), "block66.dxf")
    assign_roles(drawing.entities, {}, RoleParams())
    entities = drawing.entities
    draft = ready_contour({item.handle: item for item in entities}["769"])
    tops, _ = stitch_lines([e for e in entities if e.role == "crest_top" and e.geometry_type == "line"])
    bottoms, _ = stitch_lines([e for e in entities if e.role == "crest_bottom" and e.geometry_type == "line"])
    face_lines = [StitchedLine(points=[(x, y, 0.0) for x, y in draft.crest_line])] if draft.crest_line else None
    two = two_contours(draft.ring, tops, bottoms, face_lines=face_lines)
    levels = bench_levels(draft.ring, two.free_faces, tops, bottoms, 410.0)
    contour = BlockContour.from_dict(
        {
            "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in draft.ring],
            "free_faces": [list(edge) for edge in two.free_faces],
            "bench": {"crest_z_m": levels.crest_z_m, "toe_z_m": levels.toe_z_m},
        }
    )
    return tuple(generate_pattern(contour, BLOCK66_PARAMS))


class Block66Tests(unittest.TestCase):
    """Блок №66: мыс впереди основного фронта, бровка ступенчатая."""

    def setUp(self):
        self.holes = list(_block66_holes())
        self.assertGreater(len(self.holes), 100)

    def test_every_hole_timed_and_only_trunk_or_chain_ties(self):
        for flank in ("left", "right"):
            with self.subTest(flank=flank):
                network, warnings = build_trunk_chains_network(self.holes, {"system": "nonel", "cut_flank": flank})
                times, _ = resolve_times(network, self.holes)
                self.assertEqual(set(times), {h.id for h in self.holes if h.enabled})
                self.assertEqual({c.delay_ms for c in network.surface_connectors}, {25.0, 42.0})
                self.assertEqual(warnings, [])

    def test_cut_is_flank_head_of_front(self):
        (ax, ay), (dx, dy) = row_axis(self.holes)
        members = [h for h in self.holes if _is_column_member(h)]

        def along(h: Hole) -> float:
            return h.collar.x * ax + h.collar.y * ay

        def depth(h: Hole) -> float:
            return h.collar.x * dx + h.collar.y * dy

        front = [h for h in members if depth(h) <= min(depth(m) for m in members) + 1.5 * 3.53 + 1e-6]
        for flank, pick in (("left", min), ("right", max)):
            with self.subTest(flank=flank):
                plan = plan_trunk_chains(self.holes, cut_flank=flank)
                self.assertEqual(len(plan.starters), 1)
                cut = plan.starters[0]
                self.assertNotIn(cut, {to for _, to, _ in plan.ties})
                self.assertEqual(cut, pick(front, key=along).id)
        # Левый фланг мыса — и крайний столбец всего блока.
        left = plan_trunk_chains(self.holes, cut_flank="left").starters[0]
        self.assertEqual(left, min(members, key=along).id)


if __name__ == "__main__":
    unittest.main()
