"""Контур блока 66 по фикстуре маркшейдера (TASK-013, PR 2, §3 «Тесты»).

Координаты фикстуры сдвинуты на секретную константу; тесты опираются только
на относительную геометрию: площади, длины, число вершин, handle.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import shapely

from design.spatial.cad.contour import ContourItem, assemble, click_contour, cut_polyline, line_xy, ready_contour
from design.spatial.cad.model import CadEntity
from design.spatial.cad.reader import read_cad
from design.spatial.cad.roles import RoleParams, assign_roles
from design.spatial.cad.rings import ring_area

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"
CONTOUR_AREA_M2 = 2789.93
BIG_SHIFT = (7_000_000.0, 500_000.0)


@pytest.fixture(scope="module")
def entities() -> dict[str, CadEntity]:
    drawing = read_cad(FIXTURE.read_bytes(), "block66.dxf")
    assign_roles(drawing.entities, {}, RoleParams())
    return {item.handle: item for item in drawing.entities}


def shifted(entity: CadEntity, dx: float, dy: float) -> CadEntity:
    return CadEntity(
        handle=entity.handle,
        layer=entity.layer,
        kind=entity.kind,
        points=[(x + dx, y + dy, z) for x, y, z in entity.points],
        closed=entity.closed,
        closed_by_gap=entity.closed_by_gap,
        role=entity.role,
    )


def four_open_pieces(contour: CadEntity, gaps=(0.2, 0.8, 1.5, 3.0)) -> list[CadEntity]:
    """Контур, разрезанный посреди четырёх самых длинных рёбер с разрывами `gaps`."""

    ring = line_xy(contour)
    edges = list(zip(ring, ring[1:]))
    starts = [0.0]
    for a, b in edges:
        starts.append(starts[-1] + math.dist(a, b))
    total = starts[-1]
    longest = sorted(range(len(edges)), key=lambda index: -math.dist(*edges[index]))[:4]
    centers = sorted(starts[index] + math.dist(*edges[index]) / 2 for index in longest)
    doubled = ring + ring[1:]
    pieces = []
    for number in range(4):
        start = centers[number] + gaps[number] / 2
        end = centers[(number + 1) % 4] - gaps[(number + 1) % 4] / 2 + (total if number == 3 else 0.0)
        points = cut_polyline(doubled, start, end)
        pieces.append(
            CadEntity(
                handle=f"P{number + 1}",
                layer="Проектная линия",
                kind="LWPOLYLINE",
                points=[(x, y, 419.85) for x, y in points],
            )
        )
    return pieces


def whole(entity: CadEntity) -> ContourItem:
    return ContourItem(kind="part", handle=entity.handle, start_m=0.0, end_m=entity.length_m)


def test_block_66_variant_2_is_a_simple_polygon(entities):
    draft = ready_contour(entities["769"])
    assert draft.ok, draft.issues
    assert len(draft.ring) == 33
    assert ring_area(draft.ring) == pytest.approx(CONTOUR_AREA_M2, abs=0.05)


@pytest.mark.parametrize("shift", [(0.0, 0.0), BIG_SHIFT])
def test_four_open_pieces_assemble_and_click_into_the_same_polygon(entities, shift):
    contour = shifted(entities["769"], *shift)
    pieces = four_open_pieces(contour)
    lines = {item.handle: item for item in pieces}

    assembled = assemble([whole(item) for item in pieces], lines, 0.5)
    assert assembled.ok, assembled.issues
    assert ring_area(assembled.ring) == pytest.approx(CONTOUR_AREA_M2, rel=0.001)
    assert [info.link for info in assembled.item_info].count("closing") == 3

    inside = shapely.Polygon(assembled.ring).representative_point()
    clicked = click_contour(pieces, (inside.x, inside.y), 0.5, 5.0)
    assert clicked.ok, clicked.issues
    assert len(clicked.ring) == len(assembled.ring)
    difference = shapely.Polygon(clicked.ring).symmetric_difference(shapely.Polygon(assembled.ring))
    assert difference.area < 0.01


def test_crest_29_points_with_fragment_6_points_is_rejected_as_self_intersecting(entities):
    crest, fragment = entities["6C3"], entities["733"]
    assert (crest.vertex_count, fragment.vertex_count) == (29, 6)

    draft = assemble([whole(crest), whole(fragment)], {"6C3": crest, "733": fragment}, 0.5)

    assert not draft.ok
    assert [issue.code for issue in draft.issues] == ["self_intersection"]
    assert draft.issues[0].point is not None


# --- два контура, свободная поверхность, отметки уступа -------------------


def _crests(entities):
    from design.spatial.cad.stitch import stitch_lines

    tops = stitch_lines([item for item in entities.values() if item.role == "crest_top"])[0]
    bottoms = stitch_lines([item for item in entities.values() if item.role == "crest_bottom"])[0]
    return tops, bottoms


def test_east_side_of_block_66_is_the_free_face(entities):
    from design.spatial.cad.two_contours import two_contours

    ring = ready_contour(entities["769"]).ring
    tops, bottoms = _crests(entities)

    result = two_contours(ring, tops, bottoms)

    free = {edge for edge, _ in result.free_faces}
    fixed = [index for index in range(len(ring)) if index not in free]
    assert (len(free), len(fixed)) == (27, 6)
    fixed_length = sum(math.dist(ring[index], ring[(index + 1) % len(ring)]) for index in fixed)
    assert fixed_length == pytest.approx(186.45, abs=0.05)
    # Тыл и фланги — на западе: все несвободные рёбра западнее свободных.
    east = min(min(ring[edge][0], ring[(edge + 1) % len(ring)][0]) for edge in free)
    west = min(ring[index][0] for index in fixed)
    assert west < east


def test_block_66_flanks_reach_the_toe_and_the_bench_is_10_metres(entities):
    from design.spatial.cad.two_contours import bench_levels, two_contours

    ring = ready_contour(entities["769"]).ring
    tops, bottoms = _crests(entities)

    result = two_contours(ring, tops, bottoms)

    assert sorted(flank.length_m for flank in result.flanks) == [
        pytest.approx(5.29, abs=0.2),
        pytest.approx(16.92, abs=0.2),
    ]
    assert result.warnings == []
    assert result.area_bottom_m2 > result.area_top_m2
    assert result.area_top_m2 == pytest.approx(CONTOUR_AREA_M2, abs=0.05)

    levels = bench_levels(ring, result.free_faces, tops, bottoms, floor_z=410.0)
    assert levels.crest_z_m == pytest.approx(420.0, abs=0.7)
    assert levels.toe_z_m == 410.0
    assert levels.warnings == []


def test_block_66_by_crest_has_both_contours(entities):
    from design.spatial.cad.contour import crest_block
    from design.spatial.cad.two_contours import two_contours

    tops, bottoms = _crests(entities)
    main = next(line for line in tops if {"6C3", "6BE", "72E"} <= set(line.handles))
    xy = [(x, y) for x, y, _ in main.points]
    start, end = cut_polyline(xy, 0, 30)[-1], cut_polyline(xy, 0, 90)[-1]

    draft = crest_block(tops, bottoms, entities, start, end, 20.0)
    # Свободная поверхность блока по бровке — только вдоль выбранного участка:
    # тыл в 20 м проходит у чужих фрагментов бровки на западе блока 66.
    from design.spatial.cad.stitch import StitchedLine

    chosen = StitchedLine(points=[(x, y, 0.0) for x, y in draft.crest_line])
    result = two_contours(draft.ring, tops, bottoms, face_lines=[chosen])

    assert draft.ok, draft.issues
    assert len(result.flanks) == 2 and all(flank.end is not None for flank in result.flanks)
    assert result.area_bottom_m2 > result.area_top_m2
