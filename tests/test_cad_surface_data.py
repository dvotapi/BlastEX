"""Данные кровли по ролям линий чертежа (TASK-013, PR 3, §2 «Поверхность и подошва»).

Бровки и характерные линии с Z — жёсткие ограничители, линии без Z —
ограничители с Z по близости, горизонтали — точки через 2 м, отметки —
массовые точки. Всё за пределами контура + 20 м отсекается до триангуляции.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from design.spatial.cad.model import CadEntity
from design.spatial.cad.surface_data import (
    MAX_SURFACE_POINTS,
    SurfaceInputError,
    collect_surface_data,
)

BLOCK = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]
SHIFT = (7_000_000.0, 500_000.0)


def line(handle, role, points, kind="POLYLINE3D"):
    return CadEntity(handle=handle, layer="Слой", kind=kind, points=[tuple(map(float, p)) for p in points], role=role)


def point(handle, x, y, z):
    return CadEntity(handle=handle, layer="Отметки", kind="POINT", points=[(float(x), float(y), float(z))], role="spot_heights")


def world(data, index):
    x, y = data.xy[index]
    return (x + data.frame.ox, y + data.frame.oy)


def vertex_at(data, x, y, tolerance=1e-6):
    hits = [i for i in range(len(data.xy)) if math.dist(world(data, i), (x, y)) <= tolerance]
    assert hits, f"нет вершины в ({x}; {y})"
    return hits[0]


def test_crossing_with_a_half_metre_discrepancy_takes_the_top_crest_and_is_reported():
    top = line("T", "crest_top", [(10, -5, 420.0), (10, 25, 420.0)])
    feature = line("F", "feature_line", [(0, 10, 419.5), (20, 10, 419.5)])

    data = collect_surface_data([top, feature], BLOCK, None)

    crossing = vertex_at(data, 10.0, 10.0)
    assert data.z[crossing] == pytest.approx(420.0)
    assert len(data.conflicts) == 1
    conflict = data.conflicts[0]
    assert conflict.accepted_z == pytest.approx(420.0)
    assert sorted((item.role, round(item.z, 3)) for item in conflict.values) == [
        ("crest_top", 420.0),
        ("feature_line", 419.5),
    ]
    assert conflict.point == pytest.approx((10.0, 10.0))
    # Вершина вставлена в обе линии: рёбра обеих линий проходят через неё.
    lines_at = {int(data.edge_line[k]) for k, (a, b) in enumerate(data.edges) if crossing in (a, b)}
    assert {data.lines[i].handle for i in lines_at} == {"T", "F"}


def test_small_discrepancy_at_a_crossing_is_not_a_conflict():
    top = line("T", "crest_top", [(10, -5, 420.0), (10, 25, 420.0)])
    bottom = line("B", "crest_bottom", [(0, 10, 419.9), (20, 10, 419.9)])

    data = collect_surface_data([top, bottom], BLOCK, None)

    assert data.z[vertex_at(data, 10.0, 10.0)] == pytest.approx(420.0)
    assert data.conflicts == []


def test_crests_are_densified_to_one_metre_and_contour_lines_to_two():
    top = line("T", "crest_top", [(0, 5, 420.0), (10, 5, 421.0)])
    horizontal = line("H", "contour_line", [(0, 15, 415.0), (10, 15, 415.0)], kind="LWPOLYLINE")

    data = collect_surface_data([top, horizontal], BLOCK, None)

    crest_vertices = [i for i in range(len(data.xy)) if data.line_of[i] >= 0 and data.lines[data.line_of[i]].handle == "T"]
    assert len(crest_vertices) == 11
    middle = vertex_at(data, 5.0, 5.0)
    assert data.z[middle] == pytest.approx(420.5)
    contour_vertices = [i for i in range(len(data.xy)) if data.line_of[i] >= 0 and data.lines[data.line_of[i]].handle == "H"]
    assert len(contour_vertices) == 6
    assert data.lines[data.line_of[contour_vertices[0]]].soft


def test_point_close_to_a_constraint_takes_its_elevation_and_is_marked():
    top = line("T", "crest_top", [(10, -5, 420.0), (10, 25, 420.0)])
    near = point("P1", 10.05, 7.3, 418.0)
    far = point("P2", 15.0, 7.3, 418.0)

    data = collect_surface_data([top, near, far], BLOCK, None)

    assert data.z[data.point_id.index("P1")] == pytest.approx(420.0)
    assert data.z[data.point_id.index("P2")] == pytest.approx(418.0)
    assert [item.id for item in data.snapped] == ["P1"]
    assert data.snapped[0].from_z == pytest.approx(418.0)


def test_point_exactly_on_a_constraint_vertex_merges_into_it():
    top = line("T", "crest_top", [(10, 0, 420.0), (10, 10, 420.0)])
    on_vertex = point("P1", 10.0, 3.0, 417.0)

    data = collect_surface_data([top, on_vertex], BLOCK, None)

    assert "P1" not in data.point_id
    assert data.z[vertex_at(data, 10.0, 3.0)] == pytest.approx(420.0)
    assert [item.id for item in data.snapped] == ["P1"]


def test_flat_2d_crest_is_a_constraint_without_its_own_elevation():
    flat = line("T", "crest_top", [(10, -5, 0.0), (10, 25, 0.0)], kind="LWPOLYLINE")
    spot = point("P1", 5.0, 5.0, 420.0)

    data = collect_surface_data([flat, spot], BLOCK, None)

    crest = [i for i in range(len(data.xy)) if data.line_of[i] >= 0]
    assert crest and all(math.isnan(data.z[i]) for i in crest)
    assert not data.lines[0].has_z
    assert len(data.edges) == len(crest) - 1
    assert "no_crest_top" not in [warning.code for warning in data.warnings]


def test_2d_line_crossing_a_line_with_z_takes_its_elevation_at_the_crossing():
    flat = line("F", "feature_line", [(0, 10, 0.0), (20, 10, 0.0)], kind="LWPOLYLINE")
    top = line("T", "crest_top", [(10, -5, 420.0), (10, 25, 420.0)])

    data = collect_surface_data([flat, top], BLOCK, None)

    assert data.z[vertex_at(data, 10.0, 10.0)] == pytest.approx(420.0)
    assert data.conflicts == []


def test_everything_beyond_twenty_metres_of_the_contour_is_dropped():
    inside = point("IN", 50.0, 12.0, 420.0)  # 10 м от контура
    outside = point("OUT", 70.0, 12.0, 420.0)  # 30 м от контура
    long_line = line("L", "feature_line", [(-100, 10, 421.0), (200, 10, 421.0)])

    data = collect_surface_data([inside, outside, long_line], BLOCK, None)

    assert "IN" in data.point_id and "OUT" not in data.point_id
    xs = [world(data, i)[0] for i in range(len(data.xy)) if data.line_of[i] >= 0]
    assert min(xs) == pytest.approx(-20.0, abs=1e-6)
    assert max(xs) == pytest.approx(60.0, abs=1e-6)


def test_bottom_contour_widens_the_clipping_region():
    toe_side = point("P", 75.0, 10.0, 410.0)
    bottom = [(0.0, 0.0), (60.0, 0.0), (60.0, 20.0), (0.0, 20.0)]

    assert "P" not in collect_surface_data([toe_side], BLOCK, None).point_id
    assert "P" in collect_surface_data([toe_side], BLOCK, bottom).point_id


def test_excluded_points_are_left_out():
    data = collect_surface_data([point("P1", 5, 5, 420), point("P2", 6, 6, 421)], BLOCK, None, excluded={"P1"})

    assert data.point_id.count("P1") == 0
    assert "P2" in data.point_id
    assert data.excluded == ["P1"]


def test_vertices_of_a_survey_line_are_mass_points_with_their_own_ids():
    survey = line("S", "spot_heights", [(5, 5, 420.0), (6, 6, 0.0), (7, 7, 421.0)])

    data = collect_surface_data([survey], BLOCK, None)

    assert sorted(item for item in data.point_id if item) == ["S:0", "S:2"]
    assert len(data.edges) == 0


def test_duplicate_points_with_different_elevations_are_one_vertex_and_a_conflict():
    data = collect_surface_data([point("P1", 5, 5, 420.0), point("P2", 5.0005, 5, 421.0)], BLOCK, None)

    assert sum(1 for item in data.point_id if item) == 1
    assert len(data.conflicts) == 1
    assert data.conflicts[0].kind == "duplicate"


def test_roles_switched_off_are_not_used():
    data = collect_surface_data(
        [point("P1", 5, 5, 420.0), line("T", "crest_top", [(10, -5, 420.0), (10, 25, 420.0)])],
        BLOCK,
        None,
        roles={"crest_top"},
    )

    assert "P1" not in data.point_id


def test_without_a_top_crest_there_is_a_first_row_warning():
    data = collect_surface_data([point("P1", 5, 5, 420.0)], BLOCK, None)

    assert "no_crest_top" in [warning.code for warning in data.warnings]


def test_too_many_points_is_an_input_error():
    xs = np.linspace(0.0, 40.0, 251)
    ys = np.linspace(0.0, 20.0, 201)
    assert len(xs) * len(ys) > MAX_SURFACE_POINTS
    entities = [point(f"P{i}-{j}", x, y, 420.0) for i, x in enumerate(xs) for j, y in enumerate(ys)]

    with pytest.raises(SurfaceInputError, match="точек"):
        collect_surface_data(entities, BLOCK, None)


def test_too_long_constraints_are_an_input_error():
    # 30 000 м бровки в буфере = 30 000 отрезков по 1 м — больше предела.
    zigzag = [(x, 0.0 if k % 2 == 0 else 20.0, 420.0) for k, x in enumerate(np.linspace(0, 40, 1500))]

    with pytest.raises(SurfaceInputError, match="отрезков"):
        collect_surface_data([line("Z", "crest_top", zigzag)], BLOCK, None)


def test_msk_coordinates_give_the_same_local_data():
    entities = [
        line("T", "crest_top", [(10, -5, 420.0), (10, 25, 420.0)]),
        line("F", "feature_line", [(0, 10, 419.5), (20, 10, 419.5)]),
        point("P1", 5, 5, 421.0),
    ]
    shifted = [
        CadEntity(
            handle=item.handle,
            layer=item.layer,
            kind=item.kind,
            points=[(x + SHIFT[0], y + SHIFT[1], z) for x, y, z in item.points],
            role=item.role,
        )
        for item in entities
    ]
    block = [(x + SHIFT[0], y + SHIFT[1]) for x, y in BLOCK]

    plain = collect_surface_data(entities, BLOCK, None)
    moved = collect_surface_data(shifted, block, None)

    assert np.allclose(np.sort(plain.xy, axis=0), np.sort(moved.xy, axis=0), atol=1e-6)
    assert np.allclose(np.sort(plain.z), np.sort(moved.z), atol=1e-9)
    assert moved.conflicts[0].point == pytest.approx((10.0 + SHIFT[0], 10.0 + SHIFT[1]))


def test_constraint_of_a_single_point_has_no_edges():
    dot = line("D", "feature_line", [(5, 5, 421.0), (5, 5, 421.0)])

    data = collect_surface_data([dot, point("P1", 8, 8, 420.0)], BLOCK, None)

    assert len(data.edges) == 0
    assert data.z[vertex_at(data, 5.0, 5.0)] == pytest.approx(421.0)
