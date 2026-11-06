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
