"""Автозаполнение блока покрывает весь контур, а не только полосу у бровки.

Контур «сапогом»: узкая полоса вдоль свободной поверхности, внизу карман, где
бровка поворачивает на 90° и выходит вперёд. Средняя точка бровки (начало
отсчёта рядов) оказывается внутри кармана, и узлы впереди неё раньше не
перебирались.
"""
import math
import unittest

from design.geometry import (
    distance_to_free_faces,
    ensure_ccw,
    local_basis,
    offset_polygon,
    pattern_origin,
    point_in_polygon,
)
from design.models import BenchSurface, BlastDomain, BlockContour, Point3
from design.pattern import generate_pattern

# Против часовой стрелки: тыл (x = 0) сверху вниз, наклонная сторона, низ
# кармана, бровка снизу вверх: карман → поворот на 90° → полоса.
BOOT = [
    (0.0, 140.0),
    (0.0, 55.0),
    (45.0, -5.0),
    (54.0, -5.0),
    (55.0, 5.0),
    (57.0, 25.0),
    (55.0, 33.0),
    (28.0, 35.0),
    (26.0, 40.0),
    (26.0, 138.0),
]
BOOT_FACE = [[4, 5, 6, 7, 8, 9]]

PARAMS = {
    "pattern": "square",
    "spacing_a_m": 5.0,
    "offset_from_face_m": 2.3,
    "edge_margin_m": 1.0,
    "row_azimuth_deg": 0.0,
    "depth_m": 10.0,
}


def _contour(points, free_faces=BOOT_FACE) -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in points],
        free_faces=free_faces,
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )


def _rotate(points, deg: float):
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def _production_xy(holes):
    return [(h.collar.x, h.collar.y) for h in holes if h.kind == "production"]


def _lattice_reference(
    contour: BlockContour,
    params: dict,
    margin_steps: int = 5,
    shift_ratio: float = 0.0,
    burden: float | None = None,
):
    """Узлы бесконечной сетки той же фазы, прошедшие фильтр по контуру.

    Фаза рядов — первый ряд на расстоянии offset_from_face от средней точки
    бровки; фаза вдоль ряда — от крайней проекции вершины. Перебор — по bbox
    контура в осях сетки с запасом margin_steps шагов. Узлы впереди первого
    ряда, кроме того, не ближе offset_from_face к бровке.
    """
    a = float(params["spacing_a_m"])
    b = a if burden is None else burden
    offset = float(params["offset_from_face_m"])
    margin = float(params["edge_margin_m"])
    verts = ensure_ccw(contour.points_xy)
    boundary = offset_polygon(verts, margin)
    row_dir, advance_dir = local_basis(float(params["row_azimuth_deg"]))
    origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)
    us = [(x - origin[0]) * row_dir[0] + (y - origin[1]) * row_dir[1] for x, y in verts]
    vs = [(x - origin[0]) * advance_dir[0] + (y - origin[1]) * advance_dir[1] for x, y in verts]
    u_phase = min(us)
    i_lo = math.floor((min(us) - u_phase) / a) - margin_steps
    i_hi = math.ceil((max(us) - u_phase) / a) + margin_steps
    k_lo = math.floor((min(vs) - offset) / b) - margin_steps
    k_hi = math.ceil((max(vs) - offset) / b) + margin_steps
    nodes = []
    for k in range(k_lo, k_hi + 1):
        v = offset + k * b
        for i in range(i_lo, i_hi + 1):
            u = u_phase + i * a + (shift_ratio * a if k % 2 else 0.0)
            x = origin[0] + row_dir[0] * u + advance_dir[0] * v
            y = origin[1] + row_dir[1] * u + advance_dir[1] * v
            if not point_in_polygon((x, y), boundary):
                continue
            if k < 0 and distance_to_free_faces((x, y), contour) < offset - 1e-9:
                continue
            nodes.append((x, y))
    return nodes


def _as_set(points, digits: int = 6):
    return {(round(x, digits), round(y, digits)) for x, y in points}


class BootContourFillTests(unittest.TestCase):
    def test_holes_match_full_lattice_inside_contour(self):
        contour = _contour(BOOT)
        holes = generate_pattern(contour, PARAMS)
        expected = _lattice_reference(contour, PARAMS)
        self.assertEqual(_as_set(_production_xy(holes)), _as_set(expected))

    def test_pocket_in_front_of_face_reference_is_filled(self):
        holes = generate_pattern(_contour(BOOT), PARAMS)
        pocket = [(x, y) for x, y in _production_xy(holes) if x > 42.0 and y < 32.0]
        self.assertGreaterEqual(len(pocket), 9)

    def test_rows_in_front_keep_first_row_burden_to_face(self):
        contour = _contour(BOOT)
        row_dir, advance_dir = local_basis(0.0)
        origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)
        offset = float(PARAMS["offset_from_face_m"])
        front = [
            (x, y)
            for x, y in _production_xy(generate_pattern(contour, PARAMS))
            if (x - origin[0]) * advance_dir[0] + (y - origin[1]) * advance_dir[1] < offset - 1e-6
        ]
        self.assertGreater(len(front), 0)
        for x, y in front:
            self.assertGreaterEqual(distance_to_free_faces((x, y), contour), offset - 1e-9)

    def test_row_numbers_are_dense_and_ids_unique(self):
        holes = [h for h in generate_pattern(_contour(BOOT), PARAMS) if h.kind == "production"]
        rows = sorted({h.row for h in holes})
        self.assertEqual(rows, list(range(len(rows))))
        self.assertEqual(len({h.id for h in holes}), len(holes))

    def test_staggered_matches_lattice_parity(self):
        # Нечётные ряды решётки (по счёту от первого ряда у бровки) сдвинуты
        # на половину шага — и впереди первого ряда тоже.
        params = {**PARAMS, "pattern": "staggered", "burden_b_m": 5.0, "row_shift_ratio": 0.5}
        contour = _contour(BOOT)
        holes = generate_pattern(contour, params)
        expected = _lattice_reference(contour, params, shift_ratio=0.5)
        self.assertEqual(_as_set(_production_xy(holes)), _as_set(expected))


    def test_variable_burden_steps_front_rows_by_their_own_burden(self):
        # Общий burden_b 5 м, но у строки row_params — 12 м: ряды впереди
        # первого тоже идут через 12 м, а не через общие 5.
        params = {**PARAMS, "pattern": "variable", "burden_b_m": 5.0, "row_params": [{"burden_b_m": 12.0}]}
        contour = _contour(BOOT)
        holes = generate_pattern(contour, params)
        expected = _lattice_reference(contour, params, burden=12.0)
        self.assertEqual(_as_set(_production_xy(holes)), _as_set(expected))

    def test_domain_burden_steps_front_rows_by_domain_burden(self):
        domain = BlastDomain(id="d", name="d", spacing_a_m=5.0, burden_b_m=12.0)
        params = {**PARAMS, "pattern": "domain_dependent", "burden_b_m": 5.0}
        contour = _contour(BOOT)
        holes = generate_pattern(contour, params, domains=[domain])
        expected = _lattice_reference(contour, params, burden=12.0)
        # Вдоль ряда домен идёт своим обходом, поэтому сверяем только ряды:
        # ряды лежат вдоль оси Y, продвижение — по X.
        self.assertEqual(
            {round(x, 6) for x, _ in _production_xy(holes)}, {round(x, 6) for x, _ in expected}
        )

    def test_pocket_domain_steps_front_rows_by_its_burden(self):
        # Домен только в кармане: середина ряда по bbox лежит вне него и вне
        # контура, но принятые узлы ряда — внутри домена.
        pocket = [Point3(x=x, y=y, z=0.0) for x, y in ((38.0, -10.0), (70.0, -10.0), (70.0, 34.0), (38.0, 34.0))]
        domain = BlastDomain(id="d", name="d", polygon=pocket, spacing_a_m=5.0, burden_b_m=12.0)
        params = {**PARAMS, "pattern": "domain_dependent", "burden_b_m": 5.0}
        contour = _contour(BOOT)
        row_dir, advance_dir = local_basis(0.0)
        origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)
        offset = float(PARAMS["offset_from_face_m"])
        holes = generate_pattern(contour, params, domains=[domain])
        vs = sorted(
            {
                round((x - origin[0]) * advance_dir[0] + (y - origin[1]) * advance_dir[1], 6)
                for x, y in _production_xy(holes)
            }
        )
        front = [v for v in vs if v < offset - 1e-6]
        self.assertGreaterEqual(len(front), 1)
        self.assertAlmostEqual(front[-1], offset - 12.0, places=5)
        for lower, upper in zip(front, front[1:]):
            self.assertAlmostEqual(upper - lower, 12.0, places=5)


class FollowFaceFillTests(unittest.TestCase):
    PARAMS = {**PARAMS, "first_row_follow_face": True}

    def test_pocket_is_filled_without_touching_the_face_row(self):
        contour = _contour(BOOT)
        holes = [h for h in generate_pattern(contour, self.PARAMS) if h.kind == "production"]
        face_row = [h for h in holes if h.row == 0]
        grid = [h for h in holes if h.row >= 1]
        self.assertGreater(len(face_row), 0)
        row_dir, advance_dir = local_basis(0.0)
        origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)
        offset = float(self.PARAMS["offset_from_face_m"])
        step = float(self.PARAMS["spacing_a_m"])
        front = [
            h
            for h in grid
            if (h.collar.x - origin[0]) * advance_dir[0] + (h.collar.y - origin[1]) * advance_dir[1]
            < offset + step - 1e-6
        ]
        # В кармане, впереди начала отсчёта, раньше сетки не было совсем.
        self.assertGreaterEqual(len([h for h in front if h.collar.x > 42.0 and h.collar.y < 32.0]), 4)
        for hole in front:
            self.assertGreaterEqual(
                distance_to_free_faces((hole.collar.x, hole.collar.y), contour), offset + step - 1e-9
            )
        # Ряд вдоль бровки и ряды впереди первого не накладываются.
        for g in front:
            for f in face_row:
                self.assertGreaterEqual(
                    math.hypot(g.collar.x - f.collar.x, g.collar.y - f.collar.y), step - 1e-6
                )
        self.assertEqual(len({h.id for h in holes}), len(holes))


class RotationInvarianceTests(unittest.TestCase):
    def test_rotated_block_gives_same_holes_relative_to_contour(self):
        base = _as_set(_production_xy(generate_pattern(_contour(BOOT), PARAMS)), digits=4)
        for deg in (0.0, 30.0, 90.0, 180.0):
            with self.subTest(deg=deg):
                rotated = _contour(_rotate(BOOT, deg))
                # Азимут считается по часовой от севера, поворот — против.
                params = {**PARAMS, "row_azimuth_deg": -deg % 360.0}
                holes = generate_pattern(rotated, params)
                back = _rotate(_production_xy(holes), -deg)
                self.assertEqual(len(back), len(base))
                self.assertEqual(_as_set(back, digits=4), base)


class RectangleUnchangedTests(unittest.TestCase):
    def test_rectangle_with_face_keeps_previous_layout(self):
        # Бровка — южная сторона, ряды вдоль X, продвижение на север.
        contour = _contour([(0.0, 0.0), (40.0, 0.0), (40.0, 22.0), (0.0, 22.0)], [[0, 1]])
        params = {
            "pattern": "square",
            "spacing_a_m": 5.0,
            "offset_from_face_m": 2.5,
            "edge_margin_m": 1.0,
            "row_azimuth_deg": 90.0,
            "depth_m": 10.0,
        }
        holes = [h for h in generate_pattern(contour, params) if h.kind == "production"]
        # u отсчитывается от середины бровки (x = 20) с фазой min(u) − a.
        expected = []
        for row, y in enumerate((2.5, 7.5, 12.5, 17.5)):
            for col, x in enumerate((5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0)):
                expected.append((f"{row + 1}-{col + 1:02d}", row, col, x, y))
        got = [(h.id, h.row, h.col, round(h.collar.x, 6), round(h.collar.y, 6)) for h in holes]
        self.assertEqual(got, expected)

    def test_first_row_burden_larger_than_burden_adds_no_row_in_front(self):
        params = {
            "pattern": "rectangular",
            "spacing_a_m": 5.0,
            "burden_b_m": 4.0,
            "first_row_burden_m": 6.0,
            "edge_margin_m": 0.5,
            "row_azimuth_deg": 90.0,
            "depth_m": 10.0,
        }
        rect = [(0.0, 0.0), (40.0, 0.0), (40.0, 22.0), (0.0, 22.0)]
        with_face = generate_pattern(_contour(rect, [[0, 1]]), params)
        self.assertEqual(sorted({round(y, 6) for _, y in _production_xy(with_face)}), [6.0, 10.0, 14.0, 18.0])
        # Без свободной поверхности ряды идут от северного края на юг.
        no_face = generate_pattern(_contour(rect, []), params)
        self.assertEqual(sorted({round(y, 6) for _, y in _production_xy(no_face)}), [4.0, 8.0, 12.0, 16.0])


if __name__ == "__main__":
    unittest.main()
