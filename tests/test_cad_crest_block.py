"""Блок по бровке: две точки на верхней бровке и ширина (TASK-013, PR 2)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from design.spatial.cad.contour import crest_block
from design.spatial.cad.model import CadEntity
from design.spatial.cad.rings import ring_area
from design.spatial.cad.stitch import stitch_lines

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"


def crest(handle: str, points, z: float) -> CadEntity:
    return CadEntity(handle=handle, layer="Бровки", kind="POLYLINE3D", points=[(x, y, z) for x, y in points])


def arc(radius: float, start_deg: float, end_deg: float, step_deg: float = 1.0):
    count = round((end_deg - start_deg) / step_deg)
    return [
        (radius * math.cos(math.radians(start_deg + k * step_deg)), radius * math.sin(math.radians(start_deg + k * step_deg)))
        for k in range(count + 1)
    ]


STRAIGHT_TOP = crest("T", [(x, 0.0) for x in range(0, 101, 10)], 420.0)
STRAIGHT_BOTTOM = crest("B", [(x, -4.0) for x in range(-20, 121, 10)], 410.0)


def build(top_entities, bottom_entities, start, end, width, side="auto"):
    top, _ = stitch_lines(top_entities)
    bottom, _ = stitch_lines(bottom_entities)
    lines = {item.handle: item for item in [*top_entities, *bottom_entities]}
    return crest_block(top, bottom, lines, start, end, width, side, 0.5)


def test_straight_crest_gives_a_rectangle_on_the_side_away_from_the_toe():
    draft = build([STRAIGHT_TOP], [STRAIGHT_BOTTOM], (20, 0), (60, 0), 20.0)
    assert draft.ok, draft.issues
    assert ring_area(draft.ring) == pytest.approx(800.0)
    assert sorted(draft.ring) == pytest.approx(sorted([(20, 0), (60, 0), (60, 20), (20, 20)]))
    kinds = [item.kind for item in draft.items]
    assert kinds.count("part") == 1 and kinds.count("segment") == 2 and kinds.count("polyline") == 1


def test_curved_crest_gives_an_annular_sector_with_radial_flanks():
    top = crest("T", arc(100, 30, 150), 420.0)
    bottom = crest("B", arc(104, 20, 160), 410.0)
    start = (100 * math.cos(math.radians(60)), 100 * math.sin(math.radians(60)))
    end = (100 * math.cos(math.radians(120)), 100 * math.sin(math.radians(120)))

    draft = build([top], [bottom], start, end, 20.0)

    assert draft.ok, draft.issues
    sector = math.pi * (100**2 - 80**2) / 6
    assert ring_area(draft.ring) == pytest.approx(sector, rel=0.01)
    flanks = [item for item in draft.items if item.kind == "segment"]
    for flank in flanks:
        (ax, ay), (bx, by) = flank.points
        # Фланг идёт по нормали к бровке, то есть по радиусу дуги.
        cross = abs(ax * by - ay * bx) / (math.hypot(ax, ay) * math.hypot(bx, by))
        assert cross < math.sin(math.radians(1.5))


def test_points_on_different_crest_lines_are_rejected():
    left = crest("L", [(0, 0), (40, 0)], 420.0)
    right = crest("R", [(45, 0), (90, 0)], 420.0)
    draft = build([left, right], [STRAIGHT_BOTTOM], (10, 0), (70, 0), 20.0)
    assert [issue.code for issue in draft.issues] == ["not_on_crest"]


def test_without_toe_the_side_must_be_given():
    draft = build([STRAIGHT_TOP], [], (20, 0), (60, 0), 20.0)
    assert [issue.code for issue in draft.issues] == ["side_required"]

    right = build([STRAIGHT_TOP], [], (20, 0), (60, 0), 20.0, side="right")
    assert right.ok
    assert min(y for _, y in right.ring) == pytest.approx(-20.0)


def test_block_66_by_its_top_crest():
    from design.spatial.cad.reader import read_cad
    from design.spatial.cad.roles import RoleParams, assign_roles

    drawing = read_cad(FIXTURE.read_bytes(), "block66.dxf")
    assign_roles(drawing.entities, {}, RoleParams())
    tops = [item for item in drawing.entities if item.role == "crest_top"]
    bottoms = [item for item in drawing.entities if item.role == "crest_bottom"]
    top_lines, _ = stitch_lines(tops)
    main = next(line for line in top_lines if {"6C3", "6BE", "72E"} <= set(line.handles))
    # Точки в 30 м и 90 м от начала сшитой бровки.
    from design.spatial.cad.contour import cut_polyline

    xy = [(x, y) for x, y, _ in main.points]
    start = cut_polyline(xy, 0, 30)[-1]
    end = cut_polyline(xy, 0, 90)[-1]

    draft = build(tops, bottoms, start, end, 20.0)

    assert draft.ok, draft.issues
    assert 900 < ring_area(draft.ring) < 1500


def test_back_line_that_cannot_be_offset_is_a_visible_issue():
    # Тугая дуга R = 5 м, тыл на 20 м внутрь: смещение пустое (Codex P2).
    top = crest("T", arc(5, 30, 150, 5.0), 420.0)
    bottom = crest("B", arc(9, 20, 160, 5.0), 410.0)
    start = (5 * math.cos(math.radians(45)), 5 * math.sin(math.radians(45)))
    end = (5 * math.cos(math.radians(135)), 5 * math.sin(math.radians(135)))

    draft = build([top], [bottom], start, end, 20.0)

    assert not draft.ok
    assert [issue.code for issue in draft.issues] == ["back_failed"]


def test_far_away_toe_of_another_bench_does_not_choose_the_side():
    # У выбранного участка нижней бровки нет; есть только у другого уступа за 500 м.
    far_toe = crest("B", [(x, 500.0) for x in range(0, 101, 10)], 400.0)
    draft = build([STRAIGHT_TOP], [far_toe], (20, 0), (60, 0), 20.0)
    assert [issue.code for issue in draft.issues] == ["side_required"]

    # Ближняя нижняя бровка по-прежнему решает сама.
    near = build([STRAIGHT_TOP], [far_toe, STRAIGHT_BOTTOM], (20, 0), (60, 0), 20.0)
    assert near.ok, near.issues
    assert min(y for _, y in near.ring) == pytest.approx(0.0)


def test_points_across_the_seam_of_a_closed_crest_are_checked_by_the_arc():
    # Кольцевая бровка: шов в (0, 0). Точки по разные стороны шва в 0,3 м от него —
    # по расстояниям вдоль линии они «далеко», а дуга между ними — 0,6 м.
    ring = CadEntity(
        handle="R", layer="Бровки", kind="POLYLINE3D",
        points=[(0, 0, 420.0), (100, 0, 420.0), (100, 100, 420.0), (0, 100, 420.0)], closed=True,
    )
    toe = CadEntity(
        handle="B", layer="Бровки", kind="POLYLINE3D",
        points=[(-4, -4, 410.0), (104, -4, 410.0), (104, 104, 410.0), (-4, 104, 410.0)], closed=True,
    )
    draft = build([ring], [toe], (0, 0.3), (0.3, 0), 20.0)
    assert [issue.code for issue in draft.issues] == ["not_on_crest"]
    assert "слишком близко" in draft.issues[0].message


def test_side_toe_distance_matches_the_flank_limit():
    from design.spatial.cad.contour import SIDE_TOE_NEAR_M
    from design.spatial.cad.two_contours import FLANK_MAX_EXTENSION_M

    assert SIDE_TOE_NEAR_M == FLANK_MAX_EXTENSION_M
