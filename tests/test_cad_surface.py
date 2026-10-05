"""Кровля блока: TIN с ограничителями, качество, отметки уступа, объём
(TASK-013, PR 3, §2 «Поверхность и подошва», §3 PR 3 п. 8).

Оба пути `SurfaceBuilder` проходят одни и те же тесты.
"""
from __future__ import annotations

import os
import time

import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon

from design.spatial.cad.model import CadEntity
from design.spatial.cad.surface import build_roof, outside_cells, volume_in_polygon
from design.spatial.cad.surface_builder import CdtBuilder, ScipyBuilder

BLOCK = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]
SHIFT = (7_000_000.0, 500_000.0)


def _cdt():
    if os.environ.get("BLASTEX_REQUIRE_CDT") != "1":
        pytest.importorskip("PythonCDT", reason="PythonCDT не установлен")
    return CdtBuilder()


BUILDERS = [pytest.param(_cdt, id="cdt"), pytest.param(ScipyBuilder, id="scipy")]


def line(handle, role, points, kind="POLYLINE3D"):
    return CadEntity(handle=handle, layer="Слой", kind=kind, points=[tuple(map(float, p)) for p in points], role=role)


def point(handle, x, y, z):
    return CadEntity(handle=handle, layer="Отметки", kind="POINT", points=[(float(x), float(y), float(z))], role="spot_heights")


def grid(z_of, x_range=(-20, 61), y_range=(-20, 41), step=5.0, prefix="G"):
    return [
        point(f"{prefix}{i}-{j}", x, y, z_of(x, y))
        for i, x in enumerate(np.arange(*x_range, step))
        for j, y in enumerate(np.arange(*y_range, step))
    ]


def shifted(entities):
    return [
        CadEntity(
            handle=item.handle,
            layer=item.layer,
            kind=item.kind,
            points=[(x + SHIFT[0], y + SHIFT[1], z) for x, y, z in item.points],
            role=item.role,
        )
        for item in entities
    ]


def ring(points, shift=(0.0, 0.0)):
    return [(x + shift[0], y + shift[1]) for x, y in points]


# --- первый ряд (§3 PR 3, п. 8) ---------------------------------------------

TOP_CREST = line("T", "crest_top", [(40, -25, 420.0), (40, 45, 420.0)])
BOTTOM_CREST = line("B", "crest_bottom", [(43.6, -25, 410.0), (43.6, 45, 410.0)])
PLATFORM = [point(f"P{k}", 35.0, y, 420.0) for k, y in enumerate((-20, 0, 10, 20, 40))]
LOWER = [point(f"L{k}", 55.0, y, 410.0) for k, y in enumerate((-20, 0, 10, 20, 40))]
BOTTOM_RING = [(0.0, 0.0), (43.6, 0.0), (43.6, 20.0), (0.0, 20.0)]


@pytest.mark.parametrize("factory", BUILDERS)
def test_first_row_collar_lies_on_the_platform_thanks_to_the_crest(factory):
    entities = [TOP_CREST, BOTTOM_CREST, *PLATFORM, *LOWER]

    roof = build_roof(entities, BLOCK, BOTTOM_RING, floor_z=410.0, builder=factory())
    control = build_roof(
        entities,
        BLOCK,
        BOTTOM_RING,
        floor_z=410.0,
        roles={"crest_bottom", "feature_line", "contour_line", "spot_heights"},
        builder=factory(),
    )

    assert roof.elevation_at(37.0, 10.0) == pytest.approx(420.0, abs=0.05)
    assert control.elevation_at(37.0, 10.0) < 420.0 - 2.0
    assert "no_crest_top" in [warning.code for warning in control.warnings]


# --- объём и плоскость --------------------------------------------------------


@pytest.mark.parametrize("factory", BUILDERS)
def test_volume_of_a_tilted_plane_is_exact(factory):
    entities = grid(lambda x, y: 420.0 + 0.01 * x)

    roof = build_roof(entities, BLOCK, None, floor_z=410.0, builder=factory())

    assert roof.volume_m3 == pytest.approx(8160.0, rel=1e-9)
    assert roof.coverage_pct == pytest.approx(100.0)
    assert roof.mean_height_m == pytest.approx(10.2, abs=1e-9)
    assert roof.area_top_m2 == pytest.approx(800.0)
    assert not roof.needs_confirmation


@pytest.mark.parametrize("factory", BUILDERS)
def test_volume_is_counted_inside_the_bottom_contour(factory):
    entities = grid(lambda x, y: 420.0)
    bottom = [(0.0, 0.0), (50.0, 0.0), (50.0, 20.0), (0.0, 20.0)]

    roof = build_roof(entities, BLOCK, bottom, floor_z=410.0, builder=factory())

    assert roof.volume_m3 == pytest.approx(1000.0 * 10.0)
    assert roof.area_mean_m2 == pytest.approx(900.0)
    assert roof.mean_area_volume_m3 == pytest.approx(900.0 * 10.0)


def test_volume_in_polygon_with_msk_coordinates():
    vertices = np.array([[0, 0, 420], [40, 0, 420.4], [40, 20, 420.4], [0, 20, 420]], dtype=float)
    triangles = np.array([[0, 1, 2], [0, 2, 3]])
    moved = vertices + np.array([SHIFT[0], SHIFT[1], 0.0])

    plain = volume_in_polygon(vertices, triangles, BLOCK, 410.0)
    msk = volume_in_polygon(moved, triangles, ring(BLOCK, SHIFT), 410.0)

    assert plain.volume_m3 == pytest.approx(8160.0, rel=1e-12)
    assert msk.volume_m3 == pytest.approx(plain.volume_m3, rel=1e-4)
    assert msk.covered_m2 == pytest.approx(800.0, rel=1e-9)


def test_uncovered_part_of_the_polygon_takes_the_nearest_roof_vertex():
    # Кровля z = 420 − 0,3·x до x = 20, дальше кровли нет: часть вне неё — по
    # ближайшей вершине (414), как устья скважин, а не по бровке 415.
    vertices = np.array([[0, 0, 420], [20, 0, 414], [20, 20, 414], [0, 20, 420]], dtype=float)
    triangles = np.array([[0, 1, 2], [0, 2, 3]])

    result = volume_in_polygon(vertices, triangles, BLOCK, 410.0, fallback_z=415.0)

    assert result.covered_m2 == pytest.approx(400.0)
    assert result.volume_m3 == pytest.approx(400 * 7 + 400 * 4)
    assert result.mean_height_m() == pytest.approx((400 * 7 + 400 * 4) / 800)


def test_without_triangles_the_uncovered_part_falls_back_to_the_crest():
    result = volume_in_polygon(np.zeros((0, 3)), np.zeros((0, 3), dtype=int), BLOCK, 410.0, fallback_z=415.0)

    assert result.volume_m3 == pytest.approx(800 * 5)
    assert result.mean_height_m() == pytest.approx(5.0)


def test_without_fallback_the_uncovered_part_is_left_out():
    vertices = np.array([[0, 0, 420], [20, 0, 414], [20, 20, 414], [0, 20, 420]], dtype=float)
    triangles = np.array([[0, 1, 2], [0, 2, 3]])

    result = volume_in_polygon(vertices, triangles, BLOCK, 410.0)

    assert result.volume_m3 == pytest.approx(400 * 7)
    assert result.mean_height_m() == pytest.approx(7.0)


# Треугольник у подножия откоса: высота над подошвой 410 — h = 5 − x, от +5
# до −5. Выше подошвы — часть x < 5, объём ∫₀⁵ (5 − x)(10 − x) dx = 625/6;
# по центру тяжести треугольник дал бы 50 × 5/3.
TOE = np.array([[0, 0, 415], [10, 0, 405], [0, 10, 415]], dtype=float)
TOE_VOLUME = 625 / 6


@pytest.mark.parametrize(
    "polygon",
    [
        pytest.param([(-1.0, -1.0), (11.0, -1.0), (11.0, 11.0), (-1.0, 11.0)], id="inside"),
        pytest.param([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], id="on-boundary"),
    ],
)
def test_triangle_crossing_the_floor_counts_only_the_part_above_it(polygon):
    result = volume_in_polygon(TOE, np.array([[0, 1, 2]]), polygon, 410.0)

    assert result.volume_m3 == pytest.approx(TOE_VOLUME, rel=1e-9)
    # Интеграл со знаком — как был: площадь × высота центра тяжести.
    assert result.integral_m3 == pytest.approx(50 * 5 / 3, rel=1e-9)


def test_triangle_crossing_the_floor_is_cut_by_the_polygon_too():
    # Полигон отрезает x > 2: выше подошвы ∫₀² (5 − x)(10 − x) dx.
    polygon = [(-1.0, -1.0), (2.0, -1.0), (2.0, 11.0), (-1.0, 11.0)]

    result = volume_in_polygon(TOE, np.array([[0, 1, 2]]), polygon, 410.0)

    assert result.volume_m3 == pytest.approx(100 - 30 + 8 / 3, rel=1e-9)


def test_triangle_below_the_floor_gives_no_volume():
    result = volume_in_polygon(TOE - [0, 0, 20], np.array([[0, 1, 2]]), [(-1, -1), (11, -1), (11, 11), (-1, 11)], 410.0)

    assert result.volume_m3 == 0.0


# --- данные без отметок -------------------------------------------------------


@pytest.mark.parametrize("factory", BUILDERS)
def test_without_marks_the_roof_is_a_plane_at_the_mean_top_crest(factory):
    crest = line("T", "crest_top", [(40, -5, 419.0), (40, 25, 421.0)])

    roof = build_roof([crest], BLOCK, None, floor_z=410.0, builder=factory())

    assert roof.plane
    assert roof.elevation_at(10.0, 10.0) == pytest.approx(420.0)
    assert "no_marks" in [warning.code for warning in roof.warnings]
    assert roof.coverage_pct == pytest.approx(100.0)
    # Плоскость не описывает откос: объём — S ср × H, а не по нижней бровке.
    assert roof.volume_basis == "mean"
    assert roof.volume_m3 == pytest.approx(roof.area_mean_m2 * 10.0)


@pytest.mark.parametrize("factory", BUILDERS)
def test_2d_crest_takes_its_elevation_from_the_surface_without_it(factory):
    flat = line("T", "crest_top", [(40, -25, 0.0), (40, 45, 0.0)], kind="LWPOLYLINE")
    entities = [flat, *grid(lambda x, y: 420.0 + 0.1 * x, x_range=(-20, 61), step=10.0)]

    roof = build_roof(entities, BLOCK, None, floor_z=410.0, builder=factory())

    assert roof.elevation_at(40.0, 10.0) == pytest.approx(424.0, abs=1e-6)
    assert not roof.plane


@pytest.mark.parametrize("factory", BUILDERS)
def test_long_edges_and_triangles_outside_the_buffer_are_dropped(factory):
    sparse = [point("A", -15, 5, 420), point("B", 55, 5, 420), point("C", 55, 15, 420), point("D", -15, 15, 420)]

    roof = build_roof(sparse, BLOCK, None, floor_z=410.0, builder=factory())

    assert roof.triangle_count == 0
    assert roof.coverage_pct == pytest.approx(0.0)
    assert roof.volume_m3 is None or roof.volume_m3 == pytest.approx(0.0)


# --- защита от плоских треугольников -----------------------------------------


@pytest.mark.parametrize("factory", BUILDERS)
def test_flat_triangles_inside_a_bend_of_a_horizontal_get_a_centre_point(factory):
    # Вершина «языка» горизонтали 415 обращена вниз по склону: ближе к ней
    # горизонталь 420, и центр изгиба должен подняться над 415.
    bend = line("H415", "contour_line", [(15, 18, 415), (15, 4, 415), (25, 4, 415), (25, 18, 415)], kind="LWPOLYLINE")
    upper = line("H420", "contour_line", [(-15, 19.5, 420), (55, 19.5, 420)], kind="LWPOLYLINE")
    lower = line("H410", "contour_line", [(-15, -12, 410), (55, -12, 410)], kind="LWPOLYLINE")

    roof = build_roof([bend, upper, lower], BLOCK, None, floor_z=405.0, builder=factory())

    assert roof.elevation_at(20.0, 10.0) > 415.1
    assert roof.flat_fixed > 0


# --- качество ----------------------------------------------------------------


@pytest.mark.parametrize("factory", BUILDERS)
def test_spike_is_an_outlier_and_can_be_excluded(factory):
    entities = [*grid(lambda x, y: 420.0), point("SPIKE", 22.0, 12.0, 425.0)]

    roof = build_roof(entities, BLOCK, None, floor_z=410.0, builder=factory())
    again = build_roof(entities, BLOCK, None, floor_z=410.0, excluded={"SPIKE"}, builder=factory())

    assert [item.id for item in roof.outliers] == ["SPIKE"]
    assert roof.outliers[0].deviation_m == pytest.approx(5.0, abs=0.01)
    assert again.outliers == []
    assert again.excluded == ["SPIKE"]
    assert again.elevation_at(22.0, 12.0) == pytest.approx(420.0)


@pytest.mark.parametrize("factory", BUILDERS)
def test_quality_counts_marks_and_the_largest_gap(factory):
    entities = grid(lambda x, y: 420.0, step=10.0)

    roof = build_roof(entities, BLOCK, None, floor_z=410.0, builder=factory())

    inside = shapely.contains_xy(Polygon(BLOCK).buffer(20.0), *np.array([e.points[0][:2] for e in entities]).T)
    assert roof.spot_count == int(inside.sum())
    # Контур 40 × 20 по точкам сетки 10 м: самая дальняя точка контура — середина
    # стороны между узлами, в 5 м от ближайшего.
    assert roof.max_gap_m == pytest.approx(5.0, abs=0.01)


# --- отметки уступа -----------------------------------------------------------


@pytest.mark.parametrize("factory", BUILDERS)
def test_bottom_crest_above_the_floor_is_a_possible_threshold(factory):
    toe = line("B", "crest_bottom", [(44, -5, 410.2), (44, 5, 410.2), (44, 6, 411.0), (44, 10, 411.2), (44, 11, 410.2), (44, 25, 410.2)])
    entities = [*grid(lambda x, y: 420.0), toe]
    bottom = [(0.0, 0.0), (44.0, 0.0), (44.0, 20.0), (0.0, 20.0)]

    roof = build_roof(entities, BLOCK, bottom, floor_z=410.0, builder=factory())

    assert len(roof.thresholds) == 1
    threshold = roof.thresholds[0]
    assert threshold.excess_m == pytest.approx(1.2)
    ys = [y for segment in threshold.segments for _, y in segment]
    assert min(ys) >= 5.0 and max(ys) <= 11.0


@pytest.mark.parametrize("factory", BUILDERS)
def test_bench_of_0_6_metres_needs_confirmation(factory):
    entities = grid(lambda x, y: 410.6)

    roof = build_roof(entities, BLOCK, None, floor_z=410.0, builder=factory())

    assert roof.mean_height_m == pytest.approx(0.6)
    assert roof.needs_confirmation
    assert "bench_height" in [warning.code for warning in roof.warnings]


@pytest.mark.parametrize("factory", BUILDERS)
def test_floor_above_the_roof_is_an_issue(factory):
    roof = build_roof(grid(lambda x, y: 405.0), BLOCK, None, floor_z=410.0, builder=factory())

    assert "bench_inverted" in [issue.code for issue in roof.issues]
    assert not roof.ok


# --- координаты МСК и скорость -----------------------------------------------


@pytest.mark.parametrize("factory", BUILDERS)
def test_msk_shift_gives_the_same_roof(factory):
    entities = [TOP_CREST, BOTTOM_CREST, *PLATFORM, *LOWER, *grid(lambda x, y: 420.0 + 0.02 * y, x_range=(-20, 36))]

    plain = build_roof(entities, BLOCK, BOTTOM_RING, floor_z=410.0, builder=factory())
    moved = build_roof(shifted(entities), ring(BLOCK, SHIFT), ring(BOTTOM_RING, SHIFT), floor_z=410.0, builder=factory())

    for x, y in [(37.0, 10.0), (41.8, 3.3), (10.0, 10.0), (50.0, 15.0)]:
        assert moved.elevation_at(x + SHIFT[0], y + SHIFT[1]) == pytest.approx(plain.elevation_at(x, y), abs=0.001)
    assert moved.volume_m3 == pytest.approx(plain.volume_m3, rel=1e-4)
    assert moved.world_vertices()[:, 0].min() > SHIFT[0] - 100


@pytest.mark.parametrize("factory", BUILDERS)
def test_fifty_thousand_points_build_in_under_five_seconds(factory):
    rng = np.random.default_rng(3)
    xy = rng.uniform(-19.0, 59.0, size=(49_000, 2))
    xy[:, 1] = rng.uniform(-19.0, 39.0, size=len(xy))
    entities = [point(f"R{k}", x, y, 420.0 + 0.01 * x + 0.3 * np.sin(y / 3)) for k, (x, y) in enumerate(xy)]

    started = time.perf_counter()
    roof = build_roof(entities, BLOCK, None, floor_z=410.0, builder=factory())
    elapsed = time.perf_counter() - started

    assert roof.ok
    assert elapsed < 5.0, f"{elapsed:.2f} с"


# --- правки по ревью ---------------------------------------------------------


def _flat_count(roof, level):
    z = roof.vertices[:, 2]
    tri = roof.triangles
    return int(np.sum(np.all(np.abs(z[tri] - level) < 1e-6, axis=1)))


@pytest.mark.parametrize("factory", BUILDERS)
def test_wide_bend_of_a_horizontal_keeps_no_flat_triangles(factory):
    # Изгиб 16 м: горизонталь уплотнена через 2 м, и все ближайшие к центру
    # вершины — той же отметки; соседняя отметка — в 17 м.
    bend = line("H415", "contour_line", [(12, 19, 415), (12, 3, 415), (28, 3, 415), (28, 19, 415)], kind="LWPOLYLINE")
    lower = line("H410", "contour_line", [(-15, -14, 410), (55, -14, 410)], kind="LWPOLYLINE")
    upper = line("H420", "contour_line", [(-15, 36, 420), (55, 36, 420)], kind="LWPOLYLINE")

    roof = build_roof([bend, lower, upper], BLOCK, None, floor_z=405.0, builder=factory())

    assert roof.flat_fixed > 0
    assert _flat_count(roof, 415.0) == 0


@pytest.mark.parametrize("factory", BUILDERS)
def test_pieces_of_one_horizontal_cut_by_the_buffer_are_still_protected(factory):
    # U выходит за буфер 20 м и режется на два куска одной отметки.
    bend = line("H415", "contour_line", [(12, 60, 415), (12, 3, 415), (28, 3, 415), (28, 60, 415)], kind="LWPOLYLINE")
    lower = line("H410", "contour_line", [(-15, -14, 410), (55, -14, 410)], kind="LWPOLYLINE")

    roof = build_roof([bend, lower], BLOCK, None, floor_z=405.0, builder=factory())

    assert _flat_count(roof, 415.0) == 0


@pytest.mark.parametrize("factory", BUILDERS)
def test_2d_horizontals_alone_are_no_marks(factory):
    flat = line("H", "contour_line", [(-15, 10, 0.0), (55, 10, 0.0)], kind="LWPOLYLINE")
    crest = line("T", "crest_top", [(40, -5, 420.0), (40, 25, 420.0)])

    roof = build_roof([flat, crest], BLOCK, None, floor_z=410.0, builder=factory())

    assert roof.plane
    assert roof.mean_height_m == pytest.approx(10.0)
    assert all(np.isfinite(roof.vertices[:, 2]))


@pytest.mark.parametrize("factory", BUILDERS)
def test_marks_on_one_line_give_no_roof_and_an_issue(factory):
    marks = [point(f"P{k}", 5.0 + 5 * k, 10.0, 420.0) for k in range(4)]

    roof = build_roof(marks, BLOCK, None, floor_z=410.0, builder=factory())

    assert not roof.ok
    assert [issue.code for issue in roof.issues] == ["no_triangles"]


@pytest.mark.parametrize("factory", BUILDERS)
def test_bottom_crest_of_another_bench_is_not_a_threshold(factory):
    # Нижняя бровка вышележащего уступа (420) за тылом блока — не порог этого блока.
    upper_toe = line("U", "crest_bottom", [(-15, -5, 420.0), (-15, 25, 420.0)])
    toe = line("B", "crest_bottom", [(44, -5, 410.2), (44, 25, 410.2)])
    bottom = [(0.0, 0.0), (44.0, 0.0), (44.0, 20.0), (0.0, 20.0)]

    roof = build_roof([*grid(lambda x, y: 420.0), upper_toe, toe], BLOCK, bottom, floor_z=410.0, builder=factory())

    assert roof.thresholds == []


@pytest.mark.parametrize("factory", BUILDERS)
def test_noisy_fifty_thousand_points_on_a_large_block_in_under_five_seconds(factory):
    # Блок 200 × 200 м, отметки с шумом 1 м — выбросов больше предела списка.
    rng = np.random.default_rng(3)
    xy = rng.uniform(-19.0, 219.0, size=(49_000, 2))
    z = 420.0 + 0.01 * xy[:, 0] + 0.3 * np.sin(xy[:, 1] / 3) + rng.normal(0.0, 1.0, len(xy))
    entities = [point(f"R{k}", x, y, value) for k, ((x, y), value) in enumerate(zip(xy, z))]
    block = [(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)]

    started = time.perf_counter()
    roof = build_roof(entities, block, None, floor_z=410.0, builder=factory())
    elapsed = time.perf_counter() - started

    assert len(roof.outliers) == 500
    assert "outliers_capped" in [warning.code for warning in roof.warnings]
    assert elapsed < 5.0, f"{elapsed:.2f} с"


def test_outliers_are_found_from_the_strongest_one_by_one():
    # Два соседних пика: после исключения сильного слабый остаётся выбросом
    # относительно ровной площадки, а соседи пиков — нет.
    entities = [*grid(lambda x, y: 420.0), point("BIG", 22.0, 12.0, 428.0), point("SMALL", 24.5, 13.0, 423.0)]

    roof = build_roof(entities, BLOCK, None, floor_z=410.0, builder=ScipyBuilder())

    assert [item.id for item in roof.outliers] == ["BIG", "SMALL"]
    assert roof.outliers[0].deviation_m > roof.outliers[1].deviation_m > 1.5


def test_flat_protection_without_other_levels_is_bounded():
    # Десятки горизонталей одной отметки, других отметок нет: соседей другой
    # отметки искать негде — без квадратичной памяти и за доли секунды.
    lines = [
        line(f"H{k}", "contour_line", [(-15, -15 + 0.8 * k, 415), (55, -15 + 0.8 * k + 0.3, 415)], kind="LWPOLYLINE")
        for k in range(70)
    ]

    started = time.perf_counter()
    roof = build_roof(lines, BLOCK, None, floor_z=405.0, builder=ScipyBuilder())

    assert time.perf_counter() - started < 1.0
    assert roof.flat_fixed == 0


@pytest.mark.parametrize("factory", BUILDERS)
def test_hill_of_ring_horizontals_builds(factory):
    # Холм из замкнутых горизонталей: вырожденные (нулевой площади) «плоские»
    # треугольники у границы не должны давать центр на самом ограничителе.
    def ring(radius, level, count=48):
        angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
        points = [(20 + radius * np.cos(a), 10 + radius * np.sin(a), level) for a in angles]
        return points + [points[0]]

    rings = [line(f"R{k}", "contour_line", ring(4 + 6 * k, 420 - 2 * k), kind="LWPOLYLINE") for k in range(5)]

    roof = build_roof(rings, BLOCK, None, floor_z=405.0, builder=factory())

    assert roof.ok, roof.issues


@pytest.mark.parametrize("factory", BUILDERS)
def test_threshold_of_a_block_with_one_contour_is_found_below_the_slope(factory):
    # Нижнего контура нет: подножие откоса лежит в H·ctg α от контура блока.
    toe = line("B", "crest_bottom", [(44, -5, 410.2), (44, 5, 410.2), (44, 6, 411.0), (44, 10, 411.2), (44, 11, 410.2), (44, 25, 410.2)])

    roof = build_roof([*grid(lambda x, y: 420.0), toe], BLOCK, None, floor_z=410.0, builder=factory())

    assert len(roof.thresholds) == 1


@pytest.mark.parametrize("factory", BUILDERS)
def test_mean_height_counts_the_part_beyond_the_roof_like_the_volume(factory):
    # Ревью Codex #104: средняя высота считалась только по покрытой части.
    # Часть вне кровли — по ближайшей вершине (418 на x = 20), не по бровке.
    entities = grid(lambda x, y: 420.0 - 0.1 * x, x_range=(-20, 21))

    roof = build_roof(entities, BLOCK, None, floor_z=410.0, crest_z=415.0, builder=factory())

    assert roof.coverage_pct == pytest.approx(50.0)
    assert roof.volume_m3 == pytest.approx(400 * 9 + 400 * 8)
    assert roof.mean_height_m == pytest.approx(8.5)
    assert roof.mean_height_m * roof.area_top_m2 == pytest.approx(roof.volume_m3)


def test_hole_inside_the_roof_is_counted_as_outside():
    # Кровля z = 420 + 0,1·x сеткой 10 м на 30 × 30 м без средней клетки:
    # дыра берёт ближайшие вершины (421 и 422 поровну), как линейная кровля.
    xs = np.arange(0.0, 31.0, 10.0)
    vertices = np.array([[x, y, 420 + 0.1 * x] for y in xs for x in xs])
    triangles = []
    for j in range(3):
        for i in range(3):
            if (i, j) == (1, 1):
                continue
            a, b, c, d = j * 4 + i, j * 4 + i + 1, (j + 1) * 4 + i + 1, (j + 1) * 4 + i
            triangles += [[a, b, c], [a, c, d]]
    square = [(0.0, 0.0), (30.0, 0.0), (30.0, 30.0), (0.0, 30.0)]

    result = volume_in_polygon(vertices, np.array(triangles), square, 410.0, fallback_z=400.0)

    assert result.covered_m2 == pytest.approx(800.0)
    # Ячейки дыры по 0,16 м: граница «ближе к 421 / к 422» режет ряд ячеек.
    assert result.volume_m3 == pytest.approx(900 * 11.5, rel=1e-4)


def test_repeated_triangles_do_not_hide_the_part_beyond_the_roof():
    # Ревью безопасности: повтор треугольника стирал границу сети, и область
    # кровли собиралась объединением всех треугольников — секунды на запрос.
    vertices = np.array([[0, 0, 420], [20, 0, 414], [20, 20, 414], [0, 20, 420]], dtype=float)
    triangles = np.array([[0, 1, 2], [0, 2, 3], [2, 0, 1], [3, 0, 2]])

    result = volume_in_polygon(vertices, triangles, BLOCK, 410.0, fallback_z=415.0)

    assert result.covered_m2 == pytest.approx(400.0)
    assert result.volume_m3 == pytest.approx(400 * 7 + 400 * 4)



def test_thin_frame_beyond_the_roof_is_cut_into_few_cells():
    # Ревью Codex #116: кровля чуть меньше контура оставляет рамку, а сетка
    # над её габаритом давала ~400 000 ячеек на каждый пересчёт.
    edge = 0.05
    frame = shapely.difference(
        Polygon([(0, 0), (300, 0), (300, 300), (0, 300)]),
        Polygon([(edge, edge), (300 - edge, edge), (300 - edge, 300 - edge), (edge, 300 - edge)]),
    )

    cells = outside_cells(shapely.get_parts(frame))

    assert len(cells) < 20_000
    assert shapely.area(cells).sum() == pytest.approx(frame.area, rel=1e-9)


def test_nearest_roof_vertex_includes_vertices_without_triangles():
    # Ревью Codex #116: устье берёт ближайшую из всех вершин сети
    # (`TIN.nearest_vertex`) — часть вне кровли тоже, иначе отметки расходятся.
    vertices = np.array([[0, 0, 420], [20, 0, 420], [20, 20, 420], [0, 20, 420], [21, 10, 412]], dtype=float)
    triangles = np.array([[0, 1, 2], [0, 2, 3]])

    result = volume_in_polygon(vertices, triangles, BLOCK, 410.0, fallback_z=415.0)

    # Ячейки x > 20 ближе к вершине (21, 10, 412), кроме углов у (20, 0) и (20, 20).
    assert result.outside_integral_m3 < 400 * 10 * 0.75


def test_many_pieces_beyond_the_roof_are_cells_themselves(monkeypatch):
    # Ревью безопасности: кусков больше предела ячеек — каждая строка дала
    # бы по ячейке на кусок, и удвоение шага не кончилось бы никогда.
    monkeypatch.setattr("design.spatial.cad.surface.OUTSIDE_CELLS_MAX", 2)
    pieces = shapely.box(np.arange(3) * 10.0, 0.0, np.arange(3) * 10.0 + 1, 1.0)

    assert list(outside_cells(pieces)) == list(pieces)


def test_cells_give_up_on_too_much_work(monkeypatch):
    # Сложный остаток: каждая строка пересекается с куском во много вершин —
    # работа ограничена, при переборе пределов кусок — одна ячейка.
    monkeypatch.setattr("design.spatial.cad.surface.OUTSIDE_WORK_MAX", 10)
    ring = shapely.Point(0, 0).buffer(50, quad_segs=64)

    cells = outside_cells(np.array([ring]))

    assert len(cells) == 1
    assert shapely.area(cells).sum() == pytest.approx(ring.area)


def test_roof_full_of_holes_falls_back_to_the_crest(monkeypatch):
    # Ревью безопасности: сборка области сети в тысячах дыр — секунды на
    # каждый пересчёт; рёбер границы больше предела — часть вне кровли по бровке.
    monkeypatch.setattr("design.spatial.cad.surface.TIN_BORDER_EDGES_MAX", 3)
    vertices = np.array([[0, 0, 420], [20, 0, 414], [20, 20, 414], [0, 20, 420]], dtype=float)
    triangles = np.array([[0, 1, 2], [0, 2, 3]])

    result = volume_in_polygon(vertices, triangles, BLOCK, 410.0, fallback_z=415.0)

    assert result.outside_integral_m3 == pytest.approx(400 * 5)
