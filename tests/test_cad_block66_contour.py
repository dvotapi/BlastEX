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
