"""Два контура с общими тылом и флангами, свободная поверхность, отметки
уступа (TASK-013, PR 2)."""
from __future__ import annotations

import math

import pytest

from design.spatial.cad.contour import crest_block
from design.spatial.cad.model import CadEntity
from design.spatial.cad.stitch import stitch_lines
from design.spatial.cad.two_contours import bench_levels, free_face_edges, two_contours

BLOCK = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]


def crest(handle: str, points, z: float) -> CadEntity:
    return CadEntity(handle=handle, layer="Бровки", kind="POLYLINE3D", points=[(x, y, z) for x, y in points])


def stitched(*entities):
    return stitch_lines(list(entities))[0]


def codes(result):
    return [warning.code for warning in result.warnings]


EAST_TOP = crest("T", [(40, -10), (40, 30)], 420.0)
EAST_BOTTOM = crest("B", [(44, -10), (44, 30)], 410.0)


def test_only_the_edge_along_the_top_crest_is_free():
    assert free_face_edges(BLOCK, stitched(EAST_TOP)) == [(1, 2)]


def test_edge_touching_the_crest_with_its_end_only_is_not_free():
    north_end = crest("T", [(40, 20), (60, 20)], 420.0)
    assert free_face_edges(BLOCK, stitched(north_end)) == []


def test_flanks_are_extended_to_the_toe_and_the_slope_strip_is_added():
    result = two_contours(BLOCK, stitched(EAST_TOP), stitched(EAST_BOTTOM))

    assert result.area_top_m2 == pytest.approx(800.0)
    assert result.area_bottom_m2 == pytest.approx(880.0)
    assert result.area_mean_m2 == pytest.approx(840.0)
    assert result.perimeter_top_m == pytest.approx(120.0)
    assert [flank.length_m for flank in result.flanks] == [pytest.approx(4.0), pytest.approx(4.0)]
    assert result.warnings == []


def test_corner_block_with_one_run_over_two_sides():
    top = crest("T", [(40, -10), (40, 20), (-10, 20)], 420.0)
    bottom = crest("B", [(44, -10), (44, 24), (-10, 24)], 410.0)

    result = two_contours(BLOCK, stitched(top), stitched(bottom))

    assert result.free_faces == [(1, 2), (2, 3)]
    assert result.area_bottom_m2 == pytest.approx(44 * 24)


def test_two_separate_slopes_are_both_counted():
    tops = stitched(crest("E", [(40, -10), (40, 30)], 420.0), crest("W", [(0, -10), (0, 30)], 420.0))
    bottoms = stitched(crest("BE", [(44, -10), (44, 30)], 410.0), crest("BW", [(-4, -10), (-4, 30)], 410.0))

    result = two_contours(BLOCK, tops, bottoms)

    assert len(result.flanks) == 4
    assert result.area_bottom_m2 == pytest.approx(48 * 20)


def test_without_toe_the_slope_is_not_counted():
    result = two_contours(BLOCK, stitched(EAST_TOP), [])
    assert result.area_bottom_m2 == pytest.approx(result.area_top_m2)
    assert codes(result) == ["no_toe"]
    assert "откос не учтён" in result.warnings[0].message


def test_without_top_crest_there_is_no_free_face():
    result = two_contours(BLOCK, [], stitched(EAST_BOTTOM))
    assert result.free_faces == []
    assert result.area_bottom_m2 == pytest.approx(result.area_top_m2)
    assert codes(result) == ["no_free_face"]


def test_flank_that_misses_the_toe_is_reported():
    far = crest("B", [(200, -10), (200, 30)], 410.0)
    result = two_contours(BLOCK, stitched(EAST_TOP), stitched(far))
    assert result.area_bottom_m2 == pytest.approx(result.area_top_m2)
    assert codes(result) == ["flank_miss"]
    assert any(flank.end is None for flank in result.flanks)


def test_bench_levels_from_the_crest_and_the_design_floor():
    result = two_contours(BLOCK, stitched(EAST_TOP), stitched(EAST_BOTTOM))
    levels = bench_levels(BLOCK, result.free_faces, stitched(EAST_TOP), stitched(EAST_BOTTOM), floor_z=409.5)
    assert (levels.crest_z_m, levels.toe_z_m) == (pytest.approx(420.0), pytest.approx(409.5))
    assert (levels.crest_source, levels.toe_source) == ("crest_top", "floor")
    assert levels.warnings == []

    from_toe = bench_levels(BLOCK, result.free_faces, stitched(EAST_TOP), stitched(EAST_BOTTOM), floor_z=None)
    assert (from_toe.toe_z_m, from_toe.toe_source) == (pytest.approx(410.0), "crest_bottom")


def test_bench_height_outside_2_to_25_metres_is_a_warning():
    levels = bench_levels(BLOCK, [(1, 2)], stitched(EAST_TOP), [], floor_z=419.4)
    assert [warning.code for warning in levels.warnings] == ["bench_height"]
    assert "0,6" in levels.warnings[0].message


def test_missing_crest_keeps_the_passport_levels():
    levels = bench_levels(BLOCK, [], [], [], floor_z=None)
    assert levels.crest_z_m is None and levels.toe_z_m is None
    assert [warning.code for warning in levels.warnings] == ["crest_z_missing", "toe_z_missing"]


# --- блок по бровке: S низ − S верх = полоса откоса (§3) -------------------


def _arc(radius, start_deg, end_deg):
    return [
        (radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle)))
        for angle in range(start_deg, end_deg + 1)
    ]


def test_crest_block_straight_slope_strip():
    top = crest("T", [(x, 0.0) for x in range(0, 101, 10)], 420.0)
    bottom = crest("B", [(x, -4.0) for x in range(-20, 121, 10)], 410.0)
    tops, bottoms = stitched(top), stitched(bottom)
    draft = crest_block(tops, bottoms, {"T": top, "B": bottom}, (20, 0), (60, 0), 20.0)

    result = two_contours(draft.ring, tops, bottoms)

    assert result.area_bottom_m2 - result.area_top_m2 == pytest.approx(160.0, rel=0.01)
    assert all(flank.end is not None for flank in result.flanks)


def test_crest_block_curved_slope_strip():
    top = crest("T", _arc(100, 30, 150), 420.0)
    bottom = crest("B", _arc(104, 20, 160), 410.0)
    tops, bottoms = stitched(top), stitched(bottom)
    start = (100 * math.cos(math.radians(60)), 100 * math.sin(math.radians(60)))
    end = (100 * math.cos(math.radians(120)), 100 * math.sin(math.radians(120)))
    draft = crest_block(tops, bottoms, {"T": top, "B": bottom}, start, end, 20.0)

    result = two_contours(draft.ring, tops, bottoms)

    strip = math.pi * (104**2 - 100**2) / 6
    assert result.area_bottom_m2 - result.area_top_m2 == pytest.approx(strip, rel=0.01)


def test_a_missed_slope_does_not_cancel_the_others():
    tops = stitched(crest("E", [(40, -10), (40, 30)], 420.0), crest("W", [(0, -10), (0, 30)], 420.0))
    # Нижняя бровка есть только у восточного откоса.
    result = two_contours(BLOCK, tops, stitched(crest("BE", [(44, -10), (44, 30)], 410.0)))

    assert result.area_bottom_m2 == pytest.approx(880.0)
    assert codes(result) == ["flank_miss"]


def test_face_lines_limit_the_free_face():
    tops = stitched(crest("E", [(40, -10), (40, 30)], 420.0), crest("W", [(0, -10), (0, 30)], 420.0))
    only_east = stitched(crest("E", [(40, -10), (40, 30)], 420.0))
    result = two_contours(BLOCK, tops, stitched(EAST_BOTTOM), face_lines=only_east)
    assert result.free_faces == [(1, 2)]


def test_toe_broken_between_flanks_is_bridged_for_the_bottom_contour():
    # Нижняя бровка разорвана на 3 м между флангами: разрывы > 1 м не сшиваются (§2).
    bottoms = stitched(crest("B1", [(44, -10), (44, 8.5)], 410.0), crest("B2", [(44, 11.5), (44, 30)], 410.0))

    result = two_contours(BLOCK, stitched(EAST_TOP), bottoms)

    assert result.area_bottom_m2 == pytest.approx(880.0)
    assert codes(result) == ["toe_gap"]
    assert result.warnings[0].level == "info"
    assert "разорвана" in result.warnings[0].message and "3,0 м" in result.warnings[0].message


def test_toe_with_a_wide_gap_between_flanks_is_reported_as_such():
    bottoms = stitched(crest("B1", [(44, -10), (44, 6)], 410.0), crest("B2", [(44, 14), (44, 30)], 410.0))

    result = two_contours(BLOCK, stitched(EAST_TOP), bottoms)

    assert result.area_bottom_m2 == pytest.approx(result.area_top_m2)
    assert codes(result) == ["toe_gap"]
    assert result.warnings[0].level == "warning"
    assert "не учтён" in result.warnings[0].message
