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
from design.models import BenchSurface, BlockContour, Point3
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
    contour: BlockContour, params: dict, margin_steps: int = 5, shift_ratio: float = 0.0
):
    """Узлы бесконечной сетки той же фазы, прошедшие фильтр по контуру.

    Фаза рядов — первый ряд на расстоянии offset_from_face от средней точки
    бровки; фаза вдоль ряда — от крайней проекции вершины. Перебор — по bbox
    контура в осях сетки с запасом margin_steps шагов. Узлы впереди первого
    ряда, кроме того, не ближе offset_from_face к бровке.
    """
    a = float(params["spacing_a_m"])
    b = a
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
