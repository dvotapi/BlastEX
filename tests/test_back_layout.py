"""Шаблон раскладки «от тыла» (PR 2): тыл, решётка от тыла, конец эшелона."""
import math

import pytest

from design.back_layout import BACK_SPLIT_TURN_DEG, back_azimuth_deg, back_side
from design.models import BenchSurface, BlockContour, Point3

H = 10.0


def _contour(verts, free) -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=float(x), y=float(y), z=0.0) for x, y in verts],
        free_faces=[list(edge) for edge in free],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=75.0),
    )


def rect(width, height, free=([0, 1],)) -> BlockContour:
    """Прямоугольник против часовой; ребро [0, 1] — нижнее (y = 0)."""
    return _contour([(0, 0), (width, 0), (width, height), (0, height)], free)


def arc_back_block(width=40.0, side=20.0, sagitta=6.0, segments=12) -> BlockContour:
    """Бровка внизу, фланги по `side`, тыл — пологая дуга из `segments` рёбер.

    Излом внутри дуги ~5,5°, на стыке с флангами ~57°: дуга — одна сторона.
    """
    half = width / 2.0
    radius = (half * half + sagitta * sagitta) / (2.0 * sagitta)
    cy = side + sagitta - radius
    start = math.atan2(side - cy, half)
    end = math.pi - start
    arc = [
        (half + radius * math.cos(start + (end - start) * k / segments),
         cy + radius * math.sin(start + (end - start) * k / segments))
        for k in range(segments + 1)
    ]
    verts = [(0.0, 0.0), (width, 0.0)] + arc
    return _contour(verts, [[0, 1]])


def l_shaped_back() -> BlockContour:
    """Треугольник: бровка — гипотенуза, несвободная цепь 30 м и 12 м с изломом 90°."""
    return _contour([(0, 0), (30, 0), (30, 12)], [[2, 0]])


def test_split_turn_constant():
    assert BACK_SPLIT_TURN_DEG == 45.0


def test_back_of_rectangle_is_the_long_side_opposite_the_face():
    c = rect(40, 22, free=[[0, 1]])
    assert back_side(c) == [(40.0, 22.0), (0.0, 22.0)]
    assert back_azimuth_deg(c) == pytest.approx(90.0)


def test_arc_back_is_one_side():
    c = arc_back_block()
    side = back_side(c)
    assert len(side) == 13
    assert side[0] == pytest.approx((40.0, 20.0))
    assert side[-1] == pytest.approx((0.0, 20.0))
    assert back_azimuth_deg(c) == pytest.approx(90.0)


def test_sharp_corner_splits_sides_longest_wins():
    side = back_side(l_shaped_back())
    assert math.dist(side[0], side[-1]) == pytest.approx(30.0)
    assert back_azimuth_deg(l_shaped_back()) == pytest.approx(90.0)


def test_no_back_when_whole_contour_is_free():
    c = rect(40, 22, free=[[0, 1], [1, 2], [2, 3], [3, 0]])
    assert back_side(c) is None
    assert back_azimuth_deg(c) is None


def test_free_face_given_as_chain_of_indices():
    """Свободная поверхность цепью [0, 1, 2]: нижнее и правое рёбра; тыл — верхнее."""
    c = rect(40, 22, free=[[0, 1, 2]])
    assert back_side(c) == [(40.0, 22.0), (0.0, 22.0)]


def test_repeated_vertex_does_not_split_the_back():
    """Повтор вершины на тыле (чертёж) — вырожденное ребро, сторона не рвётся."""
    c = _contour([(0, 0), (40, 0), (40, 22), (20, 22), (20, 22), (0, 22)], [[0, 1]])
    side = back_side(c)
    assert side[0] == (40.0, 22.0) and side[-1] == (0.0, 22.0)


# --- Решётка от тыла (Task 2) ---------------------------------------------------

from design.back_layout import (  # noqa: E402
    BACK_OFFSET_DEFAULT_RATIO,
    BACK_OFFSET_RANGE,
    back_columns,
    back_offset_m,
)
from design.geometry import local_basis  # noqa: E402


def _ring(c):
    return c.points_xy


def _dist_to_back(c, xy):
    import shapely

    return shapely.distance(shapely.Point(xy), shapely.LineString(back_side(c)))


def test_back_offset_constants_and_key():
    assert BACK_OFFSET_DEFAULT_RATIO == 0.65
    assert BACK_OFFSET_RANGE == (0.5, 0.8)
    assert back_offset_m({}, 4.0) == pytest.approx(2.6)
    assert back_offset_m({"back_offset_m": 3}, 4.0) == 3.0
    assert back_offset_m({"back_offset_m": ""}, 4.0) == pytest.approx(2.6)
    assert back_offset_m({"back_offset_m": "x"}, 4.0) == pytest.approx(2.6)
    assert back_offset_m({"back_offset_m": -1}, 4.0) == pytest.approx(2.6)


def test_straight_back_first_row_at_offset():
    c = rect(40, 30)
    columns = back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 0.0)
    assert len(columns) >= 7
    for column in columns:
        x, y = column.nodes[0]
        assert y == pytest.approx(30.0 - 2.6)
        assert column.rows[0] == 0


def test_columns_are_parallel_and_step_b():
    c = rect(40, 30)
    columns = back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 0.0)
    row_dir, _ = local_basis(90.0)
    xs = []
    for column in columns:
        for (x0, y0), (x1, y1), r0, r1 in zip(column.nodes, column.nodes[1:], column.rows, column.rows[1:]):
            assert math.hypot(x1 - x0, y1 - y0) == pytest.approx(4.0)
            assert (x1 - x0) * row_dir[0] + (y1 - y0) * row_dir[1] == pytest.approx(0.0, abs=1e-9)
            assert y1 < y0  # к бровке (y = 0)
            assert r1 == r0 + 1
        xs.append(column.nodes[0][0])
    steps = [b - a for a, b in zip(xs, xs[1:])]
    assert all(s == pytest.approx(5.0) for s in steps)


def test_nodes_inside_boundary_only():
    from design.geometry import point_in_polygon

    c = rect(40, 30)
    for column in back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 0.0):
        assert all(point_in_polygon(xy, _ring(c)) for xy in column.nodes)


def test_shift_along_moves_columns_by_phase():
    c = rect(40, 30)
    base = back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 0.0)
    moved = back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 1.5)
    bx = sorted(col.nodes[0][0] for col in base)
    mx = sorted(col.nodes[0][0] for col in moved)
    assert {round((m - bx[0]) % 5.0, 6) for m in mx} == {1.5}


def test_arc_back_first_row_is_a_staircase():
    """Дуга: первый узел каждого эшелона — узел решётки в 0,5–0,8·b от тыла, а
    если такого нет — ближайший к диапазону; первые узлы не на одной прямой."""
    from design.geometry import point_in_polygon

    b = 4.0
    c = arc_back_block()
    # Сдвиг 1 м: эшелоны не на флангах (узел на ребре контура — пограничный случай).
    columns = back_columns(c, _ring(c), 90.0, 4.0, b, 0.65 * b, 1.0)
    assert len(columns) >= 8
    firsts = [col.nodes[0] for col in columns]
    assert len({round(y, 6) for _, y in firsts}) > 1  # лесенка
    in_range = 0
    for col in columns:  # в диапазоне — не все: решётка одна, шаг b больше ширины диапазона
        d = _dist_to_back(c, col.nodes[0])
        gap = max(0.5 * b - d, d - 0.8 * b, 0.0)
        in_range += gap == 0.0
        # Ни один другой узел решётки этого эшелона внутри блока не ближе к диапазону.
        x0, y0 = col.nodes[0]
        for j in range(-6, 7):
            xy = (x0, y0 - j * b)
            if j == 0 or not point_in_polygon(xy, _ring(c)):
                continue
            dj = _dist_to_back(c, xy)
            assert max(0.5 * b - dj, dj - 0.8 * b, 0.0) >= gap - 1e-9
        assert 0.15 * b - 1e-9 <= d <= 1.15 * b + 1e-9
    assert in_range >= 1
    # Ряд решётки — один на всю сетку: у узлов на одной высоте один номер ряда.
    rows_by_y = {}
    for col in columns:
        for (x, y), r in zip(col.nodes, col.rows):
            rows_by_y.setdefault(round(y, 6), set()).add(r)
    assert all(len(rs) == 1 for rs in rows_by_y.values())
    assert min(r for col in columns for r in col.rows) == 0
