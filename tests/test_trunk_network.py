"""Построитель графа «магистраль + цепочки»: вруб у фланга, магистраль по головам
столбцов, цепочки назад по рядам, пара у откоса и прочие скважины."""
import math
import random
import unittest
from collections import Counter
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from design.models import BlockContour, Hole, Point3, face_pair_partner_id, logical_row
from design.pattern import generate_pattern
from design.spatial.cad.contour import ready_contour
from design.spatial.cad.reader import read_cad
from design.spatial.cad.roles import RoleParams, assign_roles
from design.spatial.cad.stitch import StitchedLine, stitch_lines
from design.spatial.cad.two_contours import bench_levels, two_contours
from design.timing import build_template_network, resolve_times
from design.trunk_network import (
    BURNING_FRONT_RADIUS_M,
    DOWNHOLE_LATE_WARNING,
    ELECTRONIC_MODE_IGNORED_WARNING,
    WALLS_AFTER_GRID_WARNING,
    _is_column_member,
    build_trunk_chains_network,
    pick_downhole_ms,
    plan_trunk_chains,
    row_axis,
)
from tests.front_rows_fixtures import (
    BASE,
    CONTOUR,
    _contour_of,
    _rect_contour,
    vertical_hole,
)

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


def _assert_fires_after_all_rows_ahead(case: unittest.TestCase, holes: list[Hole], plan, step_a: float) -> None:
    """Член столбца срабатывает позже каждой скважины столбцов в 0,75·a по оси
    ряда во всех рядах впереди."""
    (ax, ay), _ = row_axis(holes)
    members = [h for h in holes if _is_column_member(h)]
    for h in members:
        pos = h.collar.x * ax + h.collar.y * ay
        for y in members:
            ahead = logical_row(y.row) < logical_row(h.row)
            if ahead and abs(y.collar.x * ax + y.collar.y * ay - pos) <= 0.75 * step_a + 1e-6:
                case.assertGreater(plan.surface_ms[h.id], plan.surface_ms[y.id], msg=(y.id, h.id))


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

    def test_detcord_snaps_to_relay_steps(self):
        plan = plan_trunk_chains(self.holes, trunk_ms=17.0, chain_ms=67.0, system="detcord")
        self.assertEqual({ms for *_, ms in plan.ties}, {20.0, 42.0})
        self.assertTrue(any("реле ДШ" in w for w in plan.warnings))


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


class AfterRowsAheadTests(unittest.TestCase):
    """Каждая скважина позже всех скважин в 0,75·a по оси во всех рядах впереди:
    голова — только без скважин впереди, магистраль по всем головам не обгоняет ряды."""

    CONTOURS = {
        # Песочные часы: широкий фронт, узкая шейка, широкий тыл.
        "песочные часы": ([(0.0, 0.0), (24.0, 0.0), (16.0, 10.0), (24.0, 20.0), (0.0, 20.0), (8.0, 10.0)], ((0, 1),)),
        # Косой край: фронт уже тыла, левая сторона скошена наружу.
        "косой край": ([(10.0, 0.0), (28.0, 0.0), (28.0, 20.0), (0.0, 20.0)], ((0, 1),)),
        # Вырез в бровке шире 1,5·a: отдельный участок магистрали законен.
        "вырез": ([(0.0, 0.0), (8.0, 0.0), (12.0, 9.0), (16.0, 0.0), (28.0, 0.0), (28.0, 20.0), (0.0, 20.0)], ((0, 1), (3, 4))),
    }

    def test_every_hole_fires_after_all_rows_ahead(self):
        # Шахматка на этих контурах — неровные края рядов: предшественница
        # одного столбца бывала раньше соседки другого (замечание Codex к #123).
        for name, (vertices, faces) in self.CONTOURS.items():
            for pattern in ("rectangular", "staggered"):
                holes = generate_pattern(_contour_of(vertices, faces), RECT | {"pattern": pattern})
                self.assertGreater(len(holes), 10, msg=name)
                for flank in ("left", "right"):
                    with self.subTest(contour=name, pattern=pattern, flank=flank):
                        plan = plan_trunk_chains(holes, cut_flank=flank)
                        self.assertEqual(set(plan.surface_ms), {h.id for h in holes})
                        _assert_fires_after_all_rows_ahead(self, holes, plan, 4.0)


class SingleHoleRowsTests(unittest.TestCase):
    """Шаг ряда a не определяется (по скважине в ряду) — порог цепочки 0,75·b."""

    def test_chain_limit_falls_back_to_burden(self):
        # Ось ряда — по X (ковариация x и y нулевая), b = 4, порог 3 м.
        a = vertical_hole("A", 0.0, 0.0, row=0)
        b = vertical_hole("B", 24.0, 4.0, row=1)
        c = vertical_hole("C", 0.0, 8.0, row=2)
        plan = plan_trunk_chains([a, b, c])
        self.assertEqual(plan.starters, ["A"])
        # B смещена по оси на 24 м — не продолжение столбца A, а голова у переднего края.
        self.assertIn(("A", "B", 25.0), plan.ties)
        # C — продолжение столбца A через ряд без скважины в пределах порога.
        self.assertIn(("A", "C", 42.0), plan.ties)

    def test_no_limit_when_burden_unknown_too(self):
        # Один столбец поперёк бровки: ось ряда вдоль столбца, b не определяется.
        holes = [vertical_hole(f"H{i}", 0.0, 4.0 * i, row=i) for i in range(3)]
        plan = plan_trunk_chains(holes)
        self.assertEqual(len(plan.starters), 1)
        self.assertEqual(len(plan.ties), 2)
        self.assertEqual(set(plan.surface_ms), {h.id for h in holes})


class ElectronicStepsTests(unittest.TestCase):
    """Электронная система: ступени не привязываются к номиналам."""

    def setUp(self):
        self.holes = _rect_holes()

    def test_electronic_keeps_any_step_without_warning(self):
        plan = plan_trunk_chains(self.holes, trunk_ms=30.0, chain_ms=50.0, system="electronic")
        self.assertEqual({ms for *_, ms in plan.ties}, {30.0, 50.0})
        self.assertEqual(plan.warnings, [])
        network, warnings = build_trunk_chains_network(
            self.holes, {"system": "electronic", "trunk_ms": 30.0, "chain_ms": 50.0}
        )
        self.assertEqual(network.timing_params["trunk_ms"], 30.0)
        self.assertEqual(network.timing_params["chain_ms"], 50.0)
        self.assertEqual(warnings, [])

    def test_electronic_step_below_one_ms_is_raised_to_one(self):
        plan = plan_trunk_chains(self.holes, trunk_ms=0.0, chain_ms=42.0, system="electronic")
        self.assertEqual(plan.trunk_ms, 1.0)
        self.assertTrue(any("1 мс" in w for w in plan.warnings))

    def test_electronic_shared_predecessor_gets_a_later_step(self):
        holes = generate_pattern(_rect_contour(20.0, 16.0), RECT | {"pattern": "staggered"})
        plan = plan_trunk_chains(holes, trunk_ms=30.0, chain_ms=50.0, system="electronic")
        steps = set(ms for *_, ms in plan.ties)
        self.assertTrue(steps <= {30.0, 50.0, 67.0}, steps)
        self.assertIn(67.0, steps)


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
    # Размеры блока (ширина × глубина) и фланги вруба, на которых край ряда
    # шахматки ловил обгон скважины впереди.
    SIZES = ((20.0, 16.0), (22.0, 16.0), (18.0, 20.0), (40.0, 30.0), (60.0, 40.0))
    FLANKS = ("left", "right")

    def _cases(self):
        for width, depth in self.SIZES:
            holes = generate_pattern(_rect_contour(width, depth), RECT | {"pattern": "staggered"})
            for flank in self.FLANKS:
                yield (width, depth, flank), holes, plan_trunk_chains(holes, cut_flank=flank)

    def test_staggered_every_hole_timed_once(self):
        for case, holes, plan in self._cases():
            with self.subTest(case=case):
                self.assertGreater(len({round(h.collar.x % 4.0, 3) for h in holes}), 1)
                self.assertEqual(set(plan.surface_ms), {h.id for h in holes})
                # Занятый предшественник — следующая ступень НСИ после 42 мс.
                self.assertTrue(all(ms in (25.0, 42.0, 67.0) for _, _, ms in plan.ties))
                incoming = Counter(to for _, to, _ in plan.ties)
                self.assertTrue(all(incoming[h.id] == 1 for h in holes if h.id not in plan.starters))
                self.assertTrue(all(incoming[s] == 0 for s in plan.starters))
                by_id = {h.id: h for h in holes}
                # Цепочка — только от ближайшего ряда впереди, ряд не пропускается.
                for frm, to, ms in plan.ties:
                    if ms != 25.0:
                        self.assertEqual(logical_row(by_id[to].row) - logical_row(by_id[frm].row), 1)

    def test_staggered_hole_fires_after_nearest_row_ahead(self):
        for case, holes, plan in self._cases():
            with self.subTest(case=case):
                rows: dict[int, list[Hole]] = {}
                for h in holes:
                    rows.setdefault(logical_row(h.row), []).append(h)
                t = plan.surface_ms
                for row, items in rows.items():
                    ahead = [r for r in rows if r < row]
                    if not ahead:
                        continue
                    for h in items:
                        near = [y for y in rows[max(ahead)] if abs(y.collar.x - h.collar.x) <= 0.75 * 4.0 + 1e-9]
                        for y in near:
                            self.assertGreater(t[h.id], t[y.id], msg=(case, y.id, h.id))

    def test_staggered_neighbours_in_row_never_fire_together(self):
        for case, holes, plan in self._cases():
            with self.subTest(case=case):
                rows: dict[int, list[Hole]] = {}
                for h in holes:
                    rows.setdefault(logical_row(h.row), []).append(h)
                for row, items in rows.items():
                    items.sort(key=lambda h: h.collar.x)
                    for a, b in pairwise(items):
                        if _dist(a, b) <= 1.1 * 4.0:
                            self.assertNotEqual(plan.surface_ms[a.id], plan.surface_ms[b.id], msg=(case, row, a.id, b.id))

    def test_detcord_shared_predecessor_takes_next_relay(self):
        holes = generate_pattern(_rect_contour(20.0, 16.0), RECT | {"pattern": "staggered"})
        plan = plan_trunk_chains(holes, chain_ms=25.0, system="detcord")
        steps = Counter(ms for _, _, ms in plan.ties)
        # 25 мс — и магистраль, и цепочка; занятый предшественник — реле 35 мс.
        self.assertGreater(steps[35.0], 0)
        self.assertEqual(set(steps), {25.0, 35.0})


class SparseStaggeredTests(unittest.TestCase):
    """Шахматка с пропусками: скважина, привязанная к одной предшественнице,
    не срабатывает раньше другой скважины впереди в 0,75·a по оси."""

    SEEDS = range(12)
    SIZES = ((20.0, 16.0), (28.0, 24.0), (40.0, 30.0))

    def _cases(self):
        for width, depth in self.SIZES:
            full = generate_pattern(_rect_contour(width, depth), RECT | {"pattern": "staggered"})
            for seed in self.SEEDS:
                rng = random.Random(seed)
                holes = [h for h in full if rng.random() > 0.25]
                for flank in ("left", "right"):
                    yield (width, depth, seed, flank), holes, flank

    def test_every_hole_fires_after_all_rows_ahead(self):
        for case, holes, flank in self._cases():
            for system, chain in (("nonel", 42.0), ("detcord", 42.0), ("detcord", 25.0), ("electronic", 50.0)):
                with self.subTest(case=case, system=system, chain=chain):
                    plan = plan_trunk_chains(holes, cut_flank=flank, system=system, chain_ms=chain)
                    self.assertEqual(set(plan.surface_ms), {h.id for h in holes})
                    incoming = Counter(to for _, to, _ in plan.ties)
                    self.assertTrue(all(incoming[h.id] == 1 for h in holes if h.id not in plan.starters))
                    _assert_fires_after_all_rows_ahead(self, holes, plan, 4.0)


class DetcordExhaustedStepTests(unittest.TestCase):
    """ДШ, цепочка 42 мс: реле выше нет — вторая скважина с общей предшественницей
    привязывается к соседке по ряду, уже взявшей её, наименьшим реле (10 мс)."""

    def test_row_neighbours_never_fire_together(self):
        fallback_seen = False
        for width, depth in StaggeredTests.SIZES:
            holes = generate_pattern(_rect_contour(width, depth), RECT | {"pattern": "staggered"})
            by_id = {h.id: h for h in holes}
            for flank in ("left", "right"):
                with self.subTest(size=(width, depth), flank=flank):
                    plan = plan_trunk_chains(holes, cut_flank=flank, chain_ms=42.0, system="detcord")
                    steps = {ms for *_, ms in plan.ties}
                    fallback_seen |= 10.0 in steps
                    self.assertTrue(steps <= {25.0, 42.0, 10.0}, steps)
                    # Связь 10 мс — от соседки по тому же ряду.
                    for frm, to, ms in plan.ties:
                        if ms == 10.0:
                            self.assertEqual(logical_row(by_id[frm].row), logical_row(by_id[to].row))
                    rows: dict[int, list[Hole]] = {}
                    for h in holes:
                        rows.setdefault(logical_row(h.row), []).append(h)
                    for items in rows.values():
                        times = [plan.surface_ms[h.id] for h in items]
                        self.assertEqual(len(times), len(set(times)), msg=sorted(times))
                    _assert_fires_after_all_rows_ahead(self, holes, plan, 4.0)
        self.assertTrue(fallback_seen)

    def test_nonel_top_step_falls_back_to_smallest_nsi(self):
        holes = generate_pattern(_rect_contour(20.0, 16.0), RECT | {"pattern": "staggered"})
        plan = plan_trunk_chains(holes, chain_ms=109.0)
        self.assertIn(17.0, {ms for *_, ms in plan.ties})
        _assert_fires_after_all_rows_ahead(self, holes, plan, 4.0)


class MainKindTests(unittest.TestCase):
    """Основная сетка стеночного вида (`main_kind`) — члены столбцов; отдельный
    стеночный ряд того же вида (свой номер ряда < 0) — «прочие»."""

    def setUp(self):
        self.grid = generate_pattern(_rect_contour(20.0, 16.0), RECT | {"default_kind": "contour"})
        self.assertTrue(all(h.kind == "contour" for h in self.grid))
        self.assertTrue(all(h.row >= 0 for h in self.grid))
        self.wall = [vertical_hole(f"K{i}", 4.0 * i, -3.0, row=-1, kind="contour") for i in range(6)]
        self.holes = self.grid + self.wall

    def test_main_grid_gets_trunk_and_wall_row_is_other(self):
        plan = plan_trunk_chains(self.holes, main_kind="contour")
        min_row = min(logical_row(h.row) for h in self.grid)
        for h in self.grid:
            col_rank = round(h.collar.x / 4.0)
            row_rank = logical_row(h.row) - min_row
            self.assertAlmostEqual(plan.surface_ms[h.id], 25 * col_rank + 42 * row_rank, msg=h.id)
        grid_ids = {h.id for h in self.grid}
        self.assertTrue(set(plan.starters) <= grid_ids)
        for wall in self.wall:
            frm, ms = next((f, m) for f, t, m in plan.ties if t == wall.id)
            self.assertEqual(ms, 42.0)
            self.assertIn(wall.id, plan.surface_ms)

    def test_network_includes_contour_grid_without_include_contour(self):
        network, warnings = build_trunk_chains_network(self.holes, {"system": "nonel", "main_kind": "contour"})
        # Основная сетка — не стенки: предупреждения о стенках нет.
        self.assertNotIn(WALLS_AFTER_GRID_WARNING, warnings)
        times, _ = resolve_times(network, self.holes)
        self.assertTrue({h.id for h in self.grid} <= set(times))
        self.assertTrue(any(c.delay_ms == 25.0 for c in network.surface_connectors))
        # Отдельный контурный ряд без include_contour в сеть не входит.
        self.assertFalse({h.id for h in self.wall} & set(times))
        with_walls, _ = build_trunk_chains_network(
            self.holes, {"system": "nonel", "main_kind": "contour", "include_contour": True}
        )
        times, _ = resolve_times(with_walls, self.holes)
        self.assertEqual(set(times), {h.id for h in self.holes})

    def test_contour_lattice_is_member_without_main_kind(self):
        # Член столбцов — скважина ряда решётки при любом виде: `main_kind`
        # нужен лишь стабилизации и сателлитам.
        plan = plan_trunk_chains(self.grid)
        self.assertIn(25.0, {ms for *_, ms in plan.ties})
        self.assertEqual(plan.surface_ms, plan_trunk_chains(self.grid, main_kind="contour").surface_ms)

    def test_variable_wall_kind_row_is_member(self):
        # Сетка variable: ряд решётки, которому `row_params` дал вид contour, —
        # член столбцов, времена — как у рядовой сетки.
        rows = [{"kind": "contour"}, {"kind": "production"}]
        holes = generate_pattern(_rect_contour(20.0, 16.0), RECT | {"pattern": "variable", "row_params": rows})
        self.assertTrue(any(h.kind == "contour" and h.row >= 0 for h in holes))
        plain = generate_pattern(_rect_contour(20.0, 16.0), RECT | {"pattern": "variable"})
        xy = lambda hs, t: sorted((round(h.collar.x, 6), round(h.collar.y, 6), t[h.id]) for h in hs)
        self.assertEqual(xy(holes, plan_trunk_chains(holes).surface_ms), xy(plain, plan_trunk_chains(plain).surface_ms))


class StabMainKindTests(unittest.TestCase):
    """Основная сетка вида stab/satellite (`main_kind`) — члены столбцов;
    отдельно сгенерированные вставки этих видов при рядовой сетке — «прочие»."""

    def test_stab_main_grid_gets_trunk(self):
        for kind in ("stab", "satellite"):
            grid = generate_pattern(_rect_contour(20.0, 16.0), RECT | {"default_kind": kind})
            self.assertTrue(grid and all(h.kind == kind for h in grid))
            plan = plan_trunk_chains(grid, main_kind=kind)
            min_row = min(logical_row(h.row) for h in grid)
            for h in grid:
                col_rank = round(h.collar.x / 4.0)
                row_rank = logical_row(h.row) - min_row
                self.assertAlmostEqual(plan.surface_ms[h.id], 25 * col_rank + 42 * row_rank, msg=(kind, h.id))
            network, _ = build_trunk_chains_network(grid, {"system": "nonel", "main_kind": kind})
            self.assertTrue(any(c.delay_ms == 25.0 for c in network.surface_connectors))

    def test_inserts_are_others(self):
        holes = generate_pattern(_rect_contour(20.0, 16.0), RECT | {"stab_row": True, "satellite_holes": True})
        inserts = [h for h in holes if h.kind in ("stab", "satellite")]
        self.assertEqual({h.kind for h in inserts}, {"stab", "satellite"})
        plan = plan_trunk_chains(holes, main_kind="production")
        self.assertTrue(set(plan.starters).isdisjoint(h.id for h in inserts))
        for h in inserts:
            self.assertFalse(_is_column_member(h, "production"))
            self.assertEqual(next(m for _, t, m in plan.ties if t == h.id), 42.0)


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


class ManualHoleTests(unittest.TestCase):
    """Ручная скважина (row −1000, как в design/editing.py) — прочая, не член столбца."""

    def setUp(self):
        self.grid = _rect_holes()
        self.manual = Hole(
            id="M-1",
            row=-1000,
            col=1,
            collar=Point3(8.0, 14.0, 0.0),
            toe=Point3(8.0, 14.0, -11.0),
            diameter_mm=152.0,
            kind="production",
            source="manual",
        )
        self.holes = self.grid + [self.manual]
        self.min_row = min(logical_row(h.row) for h in self.grid)

    def test_manual_hole_is_not_a_column_member(self):
        self.assertFalse(_is_column_member(self.manual))
        self.assertEqual(row_axis(self.holes), row_axis(self.grid))

    def test_manual_hole_near_back_edge_keeps_grid_order(self):
        plan = plan_trunk_chains(self.holes, cut_flank="left")
        by_id = {h.id: h for h in self.holes}
        starter = by_id[plan.starters[0]]
        first_row = [h for h in self.grid if logical_row(h.row) == self.min_row]
        self.assertEqual(starter.collar.x, min(h.collar.x for h in first_row))
        # Ручная — от ближайшей привязанной скважины сетки, 42 мс.
        nearest = min(self.grid, key=lambda h: (_dist(h, self.manual), h.id))
        self.assertIn((nearest.id, self.manual.id, 42.0), plan.ties)
        # От ручной никого не цепляют.
        self.assertFalse([t for f, t, _ in plan.ties if f == self.manual.id])
        # Сетка — те же времена, что без ручной: столбцы спереди назад.
        without = plan_trunk_chains(self.grid, cut_flank="left")
        for h in self.grid:
            self.assertEqual(plan.surface_ms[h.id], without.surface_ms[h.id], msg=h.id)
        for h in self.grid:
            for front in self.grid:
                if abs(front.collar.x - h.collar.x) < 1e-6 and logical_row(front.row) < logical_row(h.row):
                    self.assertGreater(plan.surface_ms[h.id], plan.surface_ms[front.id], msg=(front.id, h.id))


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

    @staticmethod
    def _pair(gap_m: float, late_ms: float) -> tuple[list[Hole], dict[str, float]]:
        """Две скважины в gap_m по устьям: вторая срабатывает на late_ms позже."""
        holes = [vertical_hole("1-01", 0.0, 0.0, row=0), vertical_hole("1-02", gap_m, 0.0, row=0)]
        return holes, {"1-01": 0.0, "1-02": late_ms}

    def test_pick_downhole_smallest_safe_by_local_lag(self):
        """Запас L — наибольшая разница времён соседей в радиусе R; D строго больше L."""
        self.assertEqual(BURNING_FRONT_RADIUS_M, 30.0)
        self.assertEqual(pick_downhole_ms(*self._pair(10.0, 320.0)), (500.0, []))
        self.assertEqual(pick_downhole_ms(*self._pair(10.0, 500.0)), (700.0, []))  # строго больше
        self.assertEqual(pick_downhole_ms(*self._pair(10.0, 600.0)), (700.0, []))
        self.assertEqual(pick_downhole_ms(*self._pair(10.0, 999.0)), (1000.0, []))
        ms, warnings = pick_downhole_ms(*self._pair(10.0, 1000.0))
        self.assertEqual(ms, 1000.0)
        self.assertEqual(warnings, [DOWNHOLE_LATE_WARNING])
        self.assertIn("в радиусе 30 м", DOWNHOLE_LATE_WARNING)
        # Порядок пары не важен: запас — по модулю разницы.
        holes, surface = self._pair(10.0, 600.0)
        self.assertEqual(pick_downhole_ms(holes, {"1-01": 600.0, "1-02": 0.0}), (700.0, []))
        self.assertEqual(pick_downhole_ms(holes, surface, 12.0), (700.0, []))

    def test_pick_downhole_ignores_pairs_beyond_radius(self):
        """Соседи дальше R не связаны: импульс к ним может идти и после взрыва."""
        self.assertEqual(pick_downhole_ms(*self._pair(30.0, 600.0)), (700.0, []))  # ровно R — входит
        self.assertEqual(pick_downhole_ms(*self._pair(30.5, 1500.0)), (500.0, []))
        holes, surface = self._pair(40.0, 800.0)
        self.assertEqual(pick_downhole_ms(holes, surface, 50.0), (1000.0, []))
        self.assertEqual(pick_downhole_ms(holes, surface, 39.0), (500.0, []))
        # Пар нет вовсе — запас 0.
        self.assertEqual(pick_downhole_ms([], {}), (500.0, []))
        self.assertEqual(pick_downhole_ms(holes[:1], {"1-01": 0.0}), (500.0, []))

    def test_pick_downhole_skips_holes_without_surface_time(self):
        holes, _ = self._pair(5.0, 0.0)
        self.assertEqual(pick_downhole_ms(holes, {"1-01": 900.0}), (500.0, []))

    def test_late_warning_names_radius(self):
        holes, surface = self._pair(10.0, 1200.0)
        ms, warnings = pick_downhole_ms(holes, surface, 12.5)
        self.assertEqual(ms, 1000.0)
        self.assertEqual(
            warnings,
            ["Фронт инициирования отстаёт: в радиусе 12,5 м импульс не успевает до взрыва скважины — возможен подбой."],
        )

    def test_network_resolves_to_plan_times(self):
        network, _warnings = build_trunk_chains_network(self.holes, {"system": "nonel"})
        times, _resolve_warnings = resolve_times(network, self.holes)
        plan = plan_trunk_chains(self.holes)
        for h in self.holes:
            self.assertAlmostEqual(times[h.id], plan.surface_ms[h.id] + 500.0)
        self.assertEqual(network.timing_params["scheme"], "trunk_chains")

    def test_detcord_network_keeps_relay_delays(self):
        """У ДШ времена задают реле связей: общего шнура через все скважины нет."""
        holes = _rect_holes()
        network, _warnings = build_trunk_chains_network(holes, {"system": "detcord"})
        self.assertEqual(network.detonating_cords, [])
        times, _resolve_warnings = resolve_times(network, holes)
        plan = plan_trunk_chains(holes, system="detcord")
        downhole = network.timing_params["downhole_delay_ms"]
        for h in holes:
            self.assertAlmostEqual(times[h.id], plan.surface_ms[h.id] + downhole)
        # Соседи по ряду из разных столбцов не срабатывают почти разом.
        by_row: dict[int, list[Hole]] = {}
        for h in holes:
            by_row.setdefault(logical_row(h.row), []).append(h)
        for items in by_row.values():
            items.sort(key=lambda h: h.collar.x)
            for a, b in pairwise(items):
                self.assertGreater(abs(times[a.id] - times[b.id]), 1.0, msg=(a.id, b.id))

    def test_template_entry_point(self):
        network = build_template_network(self.holes, "trunk_chains", {"system": "nonel", "cut_flank": "right"})
        self.assertEqual(network.timing_params["cut_flank"], "right")

    def test_timing_params_store_snapped_steps_and_normalized_flank(self):
        network, _warnings = build_trunk_chains_network(
            self.holes, {"system": "nonel", "trunk_ms": 24.0, "chain_ms": 40.0, "cut_flank": "middle"}
        )
        self.assertEqual(network.timing_params["trunk_ms"], 25.0)
        self.assertEqual(network.timing_params["chain_ms"], 42.0)
        self.assertEqual(network.timing_params["cut_flank"], "left")
        detcord, _ = build_trunk_chains_network(self.holes, {"system": "detcord", "trunk_ms": 17.0})
        self.assertEqual(detcord.timing_params["trunk_ms"], 20.0)
        self.assertEqual({c.delay_ms for c in detcord.connectors}, {20.0, 42.0})

    def test_walls_in_network_warn_they_fire_after_grid(self):
        _, plain = build_trunk_chains_network(self.holes, {"system": "nonel"})
        self.assertNotIn(WALLS_AFTER_GRID_WARNING, plain)
        for kind in ("contour", "presplit", "trim"):
            wall = vertical_hole("W1", 10.0, -3.0, row=-1, kind=kind)
            _, warnings = build_trunk_chains_network(
                self.holes + [wall], {"system": "nonel", "include_contour": True}
            )
            self.assertIn(WALLS_AFTER_GRID_WARNING, warnings, msg=kind)
        # Контур без include_contour в сеть не входит — и предупреждения нет.
        contour = vertical_hole("W1", 10.0, -3.0, row=-1, kind="contour")
        _, warnings = build_trunk_chains_network(self.holes + [contour], {"system": "nonel"})
        self.assertNotIn(WALLS_AFTER_GRID_WARNING, warnings)

    def test_electronic_timing_mode_is_ignored_with_warning(self):
        network, warnings = build_trunk_chains_network(
            self.holes, {"system": "electronic", "timing_mode": "direction"}
        )
        self.assertIn(ELECTRONIC_MODE_IGNORED_WARNING, warnings)
        self.assertEqual(network.timing_params["scheme"], "trunk_chains")
        self.assertEqual({c.delay_ms for c in network.connectors}, {25.0, 42.0})
        _, no_mode = build_trunk_chains_network(self.holes, {"system": "electronic", "timing_mode": ""})
        self.assertNotIn(ELECTRONIC_MODE_IGNORED_WARNING, no_mode)
        _, nonel = build_trunk_chains_network(self.holes, {"system": "nonel", "timing_mode": "direction"})
        self.assertNotIn(ELECTRONIC_MODE_IGNORED_WARNING, nonel)

    def test_non_nonel_system_keeps_default_downhole(self):
        network, warnings = build_trunk_chains_network(self.holes, {"system": "electronic"})
        self.assertEqual(network.downhole_connectors, [])
        self.assertEqual(warnings, [])

    def test_non_nonel_system_takes_downhole_from_params(self):
        for system in ("detcord", "electronic"):
            with self.subTest(system=system):
                network, _ = build_trunk_chains_network(self.holes, {"system": system, "downhole_delay_ms": 300.0})
                self.assertEqual(network.timing_params["downhole_delay_ms"], 300.0)
                self.assertEqual(set(network.downhole_delay_ms.values()), {300.0})
        # У СИНВ замедление по-прежнему подбирается, поле параметров не действует.
        nonel, _ = build_trunk_chains_network(self.holes, {"system": "nonel", "downhole_delay_ms": 300.0})
        self.assertEqual(nonel.timing_params["downhole_delay_ms"], 500.0)

    def test_plan_times_match_resolved_network(self):
        """Времена плана (`_times_from_starters`) совпадают с `resolve_times` сети."""
        grid = _rect_holes()
        strays = [
            vertical_hole("S1", 9.0, 17.5, row=4, kind="stab"),
            vertical_hole("P1", 10.0, -3.0, row=-1, kind="presplit"),
        ]
        cases = {
            "прямоугольная": grid,
            "шахматка": generate_pattern(_rect_contour(22.0, 16.0), RECT | {"pattern": "staggered"}),
            "пара у откоса": generate_pattern(CONTOUR, BASE | {"front_rows_mode": "pair"}),
            "прочие": grid + strays,
        }
        for name, holes in cases.items():
            for flank in ("left", "right"):
                with self.subTest(case=name, flank=flank):
                    network, _ = build_trunk_chains_network(holes, {"system": "nonel", "cut_flank": flank})
                    times, _ = resolve_times(network, holes)
                    plan = plan_trunk_chains(holes, cut_flank=flank)
                    downhole = network.timing_params["downhole_delay_ms"]
                    self.assertEqual(set(times), set(plan.surface_ms))
                    for hole_id, ms in plan.surface_ms.items():
                        self.assertAlmostEqual(times[hole_id], ms + downhole, msg=hole_id)

    def test_long_block_keeps_500_by_local_criterion(self):
        """40 столбцов × 12 рядов: сеть длиннее 1000 мс, но в радиусе 30 м запас
        меньше 500 мс — замедление 500 без предупреждения."""
        holes = _long_block_holes()
        network, warnings = build_trunk_chains_network(holes, {"system": "nonel"})
        plan = plan_trunk_chains(holes)
        self.assertEqual(max(plan.surface_ms.values()), 1437.0)
        self.assertEqual(network.timing_params["downhole_delay_ms"], 500.0)
        self.assertFalse(any("Фронт инициирования отстаёт" in w for w in warnings))
        self.assertNotIn("burning_front_m", network.timing_params)

    def test_burning_front_radius_from_params(self):
        holes = _long_block_holes()
        wide, warnings = build_trunk_chains_network(holes, {"system": "nonel", "burning_front_m": 500.0})
        self.assertEqual(wide.timing_params["downhole_delay_ms"], 1000.0)
        self.assertTrue(any("в радиусе 500 м" in w for w in warnings))
        middle, warnings = build_trunk_chains_network(holes, {"system": "nonel", "burning_front_m": 60.0})
        self.assertEqual(middle.timing_params["downhole_delay_ms"], 1000.0)
        self.assertEqual(warnings, [])
        # Не число или не больше нуля — радиус по умолчанию.
        for bad in (0.0, -5.0, "много", None):
            with self.subTest(bad=bad):
                net, _ = build_trunk_chains_network(holes, {"system": "nonel", "burning_front_m": bad})
                self.assertEqual(net.timing_params["downhole_delay_ms"], 500.0)


@lru_cache(maxsize=1)
def _long_block_holes_cached() -> tuple[Hole, ...]:
    return tuple(generate_pattern(_rect_contour(156.0, 44.0), RECT))


def _long_block_holes() -> list[Hole]:
    """Длинный блок 156×44 м, a = b = 4: 40 столбцов × 12 рядов, сеть 1437 мс."""
    return list(_long_block_holes_cached())


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
def _block66_contour() -> BlockContour:
    """Контур №66: готовый контур (handle 769), откосы и отметки — как в импорте чертежа."""
    drawing = read_cad(BLOCK66.read_bytes(), "block66.dxf")
    assign_roles(drawing.entities, {}, RoleParams())
    entities = drawing.entities
    draft = ready_contour({item.handle: item for item in entities}["769"])
    tops, _ = stitch_lines([e for e in entities if e.role == "crest_top" and e.geometry_type == "line"])
    bottoms, _ = stitch_lines([e for e in entities if e.role == "crest_bottom" and e.geometry_type == "line"])
    face_lines = [StitchedLine(points=[(x, y, 0.0) for x, y in draft.crest_line])] if draft.crest_line else None
    two = two_contours(draft.ring, tops, bottoms, face_lines=face_lines)
    levels = bench_levels(draft.ring, two.free_faces, tops, bottoms, 410.0)
    return BlockContour.from_dict(
        {
            "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in draft.ring],
            "free_faces": [list(edge) for edge in two.free_faces],
            "bench": {"crest_z_m": levels.crest_z_m, "toe_z_m": levels.toe_z_m},
        }
    )


@lru_cache(maxsize=1)
def _block66_holes() -> tuple[Hole, ...]:
    """Сетка паспорта №66 на его контуре."""
    return tuple(generate_pattern(_block66_contour(), BLOCK66_PARAMS))


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
                # Сеть 918 / 793 мс, но в радиусе 30 м запас меньше 500 мс.
                self.assertEqual(network.timing_params["downhole_delay_ms"], 500.0)

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
        for flank in ("left", "right"):
            with self.subTest(flank=flank, check="after_rows_ahead"):
                _assert_fires_after_all_rows_ahead(self, self.holes, plan_trunk_chains(self.holes, cut_flank=flank), 4.41)
        # Левый фланг мыса — и крайний столбец всего блока.
        left = plan_trunk_chains(self.holes, cut_flank="left").starters[0]
        self.assertEqual(left, min(members, key=along).id)


if __name__ == "__main__":
    unittest.main()
