"""Кольцо контура блока: нормализация и проверки (TASK-013, PR 2)."""
from __future__ import annotations

import shapely


def test_shapely_2_is_installed():
    major = int(shapely.__version__.split(".")[0])
    assert major >= 2
    for name in ("offset_curve", "polygonize", "is_valid_reason", "unary_union"):
        assert hasattr(shapely, name), name


import pytest

from design.spatial.cad.rings import (
    LocalFrame,
    check_ring,
    normalize_ring,
    ring_area,
    ring_perimeter,
)

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _codes(issues):
    return [issue.code for issue in issues]


def test_duplicates_and_repeated_first_point_are_removed():
    ring = normalize_ring([(0, 0), (10, 0), (10.004, 0.003), (10, 10), (0, 10), (0, 0)])
    assert ring == [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_collinear_vertex_within_a_centimetre_is_removed():
    ring = normalize_ring([(0, 0), (5, 0.008), (10, 0), (10, 10), (0, 10)])
    assert ring == [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_vertex_further_than_a_centimetre_is_kept():
    ring = normalize_ring([(0, 0), (5, 0.02), (10, 0), (10, 10), (0, 10)])
    assert (5, 0.02) in ring


def test_spike_back_along_the_edge_is_not_silently_removed():
    # B лежит на прямой A–C, но за пределами отрезка: это вырожденный «шип», а не лишняя вершина.
    ring = normalize_ring([(0, 0), (12, 0), (10, 0), (10, 10), (0, 10)])
    assert (12, 0) in ring


def test_clockwise_ring_becomes_counter_clockwise():
    ring = normalize_ring(list(reversed(SQUARE)))
    signed = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:] + ring[:1])) / 2
    assert signed > 0
    assert ring_area(ring) == pytest.approx(100.0)
    assert ring_perimeter(ring) == pytest.approx(40.0)


def test_valid_square_has_no_issues():
    assert check_ring(SQUARE) == []


def test_figure_eight_reports_self_intersection_with_its_point():
    issues = check_ring([(0, 0), (10, 10), (10, 0), (0, 10)])
    assert _codes(issues) == ["self_intersection"]
    assert issues[0].point == pytest.approx((5.0, 5.0), abs=0.01)
    assert "пересекает сам себя" in issues[0].message
    assert "5,00" in issues[0].message


def test_two_points_are_too_few():
    assert _codes(check_ring([(0, 0), (10, 0)])) == ["too_few_points"]


def test_collinear_points_have_zero_area():
    assert _codes(check_ring([(0, 0), (5, 0), (10, 0)])) == ["zero_area"]


def test_short_edge_is_reported_with_number_and_length():
    issues = check_ring([(0, 0), (10, 0), (10, 10), (0.03, 10), (0, 10)])
    assert _codes(issues) == ["short_edge"]
    assert "Ребро 4" in issues[0].message
    assert "0,03" in issues[0].message
    assert issues[0].point == pytest.approx((0.03, 10))


def test_big_survey_coordinates_keep_area_and_validity():
    dx, dy = 7_000_000.0, 500_000.0
    shifted = [(x + dx, y + dy) for x, y in [(0, 0), (37.25, 1.5), (40.125, 22.75), (3.5, 19.875)]]
    local = [(0, 0), (37.25, 1.5), (40.125, 22.75), (3.5, 19.875)]
    assert ring_area(shifted) == pytest.approx(ring_area(local), abs=0.01)
    assert check_ring(shifted) == []
    assert len(normalize_ring(shifted)) == 4


def test_local_frame_round_trip():
    frame = LocalFrame.of([(7_000_010.0, 500_020.0), (7_000_000.0, 500_000.0)])
    assert (frame.ox, frame.oy) == (7_000_000.0, 500_000.0)
    local = frame.to_local([(7_000_010.0, 500_020.0)])
    assert local == [(10.0, 20.0)]
    assert frame.to_world(local) == [(7_000_010.0, 500_020.0)]


def test_dense_arc_keeps_every_original_point_within_a_centimetre():
    # Круг R = 100 м с вершинами через 0,25 м: каждая вершина «на прямой» со
    # своими соседями, но убирать их подряд можно, только пока все исходные
    # точки остаются в 1 см от нового контура (раньше круг терял 0,1 % площади).
    import math as m

    from shapely.geometry import LinearRing, Point

    count = 2500
    circle = [(100 * m.cos(2 * m.pi * k / count), 100 * m.sin(2 * m.pi * k / count)) for k in range(count)]
    ring = normalize_ring(circle)

    outline = LinearRing(ring)
    assert max(outline.distance(Point(point)) for point in circle) <= 0.01 + 1e-9
    assert ring_area(ring) == pytest.approx(ring_area(circle), rel=2e-4)
    assert len(ring) < count


def test_long_ring_is_normalized_in_linear_time():
    import time

    # 20 000 вершин: первая половина — зубцы (не убираются), вторая — прямая.
    teeth = [(0.5 * k, 0.2 * (k % 2)) for k in range(10_000)]
    straight = [(5000.0 - 0.5 * k, -10.0) for k in range(10_000)]
    started = time.perf_counter()
    ring = normalize_ring([*teeth, *straight])
    elapsed = time.perf_counter() - started

    assert len(ring) == 10_002
    assert elapsed < 2.0, f"{elapsed:.2f} с"
