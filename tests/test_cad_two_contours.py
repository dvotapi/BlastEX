"""Два контура с общими тылом и флангами, свободная поверхность, отметки
уступа (TASK-013, PR 2)."""
from __future__ import annotations

import math

import pytest

from design.spatial.cad.contour import crest_block
from design.spatial.cad.model import CadEntity
from design.spatial.cad.stitch import stitch_lines
from design.spatial.cad.rings import ring_area
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


def test_one_level_from_the_drawing_is_checked_together_with_the_passport_one():
    # Бровка из чертежа 100 м, подошвы в чертеже нет — остаётся подошва паспорта 410 м.
    low_crest = crest("T", [(40, -10), (40, 30)], 100.0)
    levels = bench_levels(BLOCK, [(1, 2)], stitched(low_crest), [], floor_z=None, passport=(420.0, 410.0))
    assert (levels.crest_z_m, levels.toe_z_m) == (pytest.approx(100.0), pytest.approx(410.0))
    assert (levels.crest_source, levels.toe_source) == ("crest_top", "passport")
    assert [issue.code for issue in levels.issues] == ["bench_inverted"]

    # Бровка 420 м, подошва паспорта по умолчанию −10 м: уступ 430 м — предупреждение.
    tall = bench_levels(BLOCK, [(1, 2)], stitched(EAST_TOP), [], floor_z=None, passport=(0.0, -10.0))
    assert tall.toe_source == "passport" and tall.issues == []
    assert "bench_height" in [warning.code for warning in tall.warnings]


def test_toe_not_below_the_crest_is_an_error_even_from_the_drawing():
    levels = bench_levels(BLOCK, [(1, 2)], stitched(EAST_TOP), [], floor_z=420.0)
    assert [issue.code for issue in levels.issues] == ["bench_inverted"]
    assert "bench_height" not in [warning.code for warning in levels.warnings]


def test_without_passport_levels_the_missing_ones_stay_empty():
    levels = bench_levels(BLOCK, [(1, 2)], stitched(EAST_TOP), [], floor_z=None)
    assert levels.toe_z_m is None and levels.issues == []


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


def test_far_away_crests_do_not_slow_the_preview():
    import time

    # Свободная грань 300 м и тысяча бровок по 20 отрезков вдали — чертёж карьера.
    block = [(0.0, 0.0), (300.0, 0.0), (300.0, 20.0), (0.0, 20.0)]
    top = [crest("T", [(x, 20.0) for x in range(-10, 311, 10)], 420.0)]
    far = [
        crest(f"F{k}", [(2000 + (k % 40) * 30 + i, (k // 40) * 30.0) for i in range(21)], 425.0) for k in range(1000)
    ]
    bottom = [crest("B", [(x, 24.0) for x in range(-10, 311, 10)], 410.0)]
    tops = stitched(*top, *far)
    bottoms = stitched(*bottom)

    started = time.perf_counter()
    result = two_contours(block, tops, bottoms)
    levels = bench_levels(block, result.free_faces, tops, bottoms, floor_z=410.0)
    elapsed = time.perf_counter() - started

    assert result.free_faces == [(2, 3)]
    assert levels.crest_z_m == pytest.approx(420.0)
    assert elapsed < 0.5, f"{elapsed:.2f} с"


def test_closed_toe_ring_with_its_seam_between_the_flanks():
    # Нижняя бровка — замкнутое кольцо вокруг выемки, шов (начало кольца) — у откоса блока.
    ring = CadEntity(
        handle="RING",
        layer="Бровки",
        kind="LWPOLYLINE",
        points=[(x, y, 410.0) for x, y in [(44, 10), (44, 50), (-100, 50), (-100, -50), (44, -50)]],
        closed=True,
    )

    result = two_contours(BLOCK, stitched(EAST_TOP), stitched(ring))

    assert result.area_bottom_m2 == pytest.approx(880.0)


def test_crest_block_across_the_seam_of_a_closed_crest():
    top = CadEntity(
        handle="TOP",
        layer="Бровки",
        kind="LWPOLYLINE",
        points=[(x, y, 420.0) for x, y in [(50, 0), (100, 0), (100, 100), (0, 100), (0, 0)]],
        closed=True,
    )
    bottom = crest("B", [(-5, -4), (105, -4)], 410.0)
    tops, bottoms = stitched(top), stitched(bottom)

    draft = crest_block(tops, bottoms, {"TOP": top, "B": bottom}, (40, 0), (60, 0), 10.0)

    assert draft.ok, draft.issues
    assert ring_area(draft.ring) == pytest.approx(200.0, abs=0.5)


def test_several_toe_gaps_between_flanks_are_described_honestly():
    bottoms = stitched(
        crest("B1", [(44, -10), (44, 5)], 410.0),
        crest("B2", [(44, 7), (44, 13)], 410.0),
        crest("B3", [(44, 15), (44, 30)], 410.0),
    )
    result = two_contours(BLOCK, stitched(EAST_TOP), bottoms)
    assert codes(result) == ["toe_gap"]
    assert "больше чем на 5 м" not in result.warnings[0].message
    assert "несколько разрывов" in result.warnings[0].message


def test_closed_toe_arc_follows_the_free_face_not_the_shortest_way():
    # Откос с трёх сторон блока: верная дуга кольцевой нижней бровки — длинная
    # (вокруг откоса), а короткая идёт с тыла.
    square = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]
    top = crest("T", [(20, -5), (20, 20), (0, 20), (0, -5)], 420.0)
    ring = CadEntity(
        handle="RING",
        layer="Бровки",
        kind="LWPOLYLINE",
        points=[(x, y, 410.0) for x, y in [(24, -10), (24, 24), (-4, 24), (-4, -10)]],
        closed=True,
    )

    result = two_contours(square, stitched(top), stitched(ring))

    assert result.area_bottom_m2 == pytest.approx(28 * 24)


def test_toe_level_from_a_long_line_whose_vertices_are_far_away():
    # Нижняя бровка — одна длинная линия: вершины в 200 м, сама линия — в 4 м от блока.
    toe = crest("B", [(44, -200), (44, 200)], 410.0)
    levels = bench_levels(BLOCK, [(1, 2)], stitched(EAST_TOP), stitched(toe), floor_z=None)
    assert (levels.toe_z_m, levels.toe_source) == (pytest.approx(410.0), "crest_bottom")


def test_drawing_in_millimetres_keeps_the_sampling_bounded(monkeypatch):
    # Блок 1 × 0,5 км в миллиметрах: масштаб 0,001 только предложен, а готовый
    # контур уже в предпросмотре. Шаг выборки 1 «метр» дал бы 3 млн точек.
    from design.spatial.cad import two_contours as module

    k = 1000.0
    ring = [(0.0, 0.0), (1000 * k, 0.0), (1000 * k, 500 * k), (0.0, 500 * k)]
    tops = stitched(crest("T", [(1000 * k, -100 * k), (1000 * k, 600 * k)], 420_000.0))
    bottoms = stitched(crest("B", [(1000 * k + 30, -100 * k), (1000 * k + 30, 600 * k)], 410_000.0))

    shapely_points = module.shapely.points
    made: list[int] = []
    monkeypatch.setattr(module.shapely, "points", lambda *args: made.append(len(args[0])) or shapely_points(*args))
    z_at_samples = module._z_at_samples
    asked: list[int] = []
    monkeypatch.setattr(
        module,
        "_z_at_samples",
        lambda lines, frame, samples, distance: asked.append(len(samples)) or z_at_samples(lines, frame, samples, distance),
    )

    bound = module.MAX_RING_SAMPLES + 2 * len(ring)
    free = free_face_edges(ring, tops)
    assert free == [(1, 2)]
    assert sum(made) <= bound

    levels = bench_levels(ring, free, tops, bottoms, floor_z=None)
    assert levels.crest_z_m == pytest.approx(420_000.0)
    assert levels.toe_z_m == pytest.approx(410_000.0)
    assert asked and max(asked) <= bound


def test_metre_blocks_are_still_sampled_every_metre():
    from design.spatial.cad import two_contours as module

    # Периметр до MAX_RING_SAMPLES метров — шаг 1 м, как раньше.
    assert module._sample_step(BLOCK) == pytest.approx(module.FREE_FACE_SAMPLE_M)
