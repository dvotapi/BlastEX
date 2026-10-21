"""Темп отбойки: мс/м по треугольникам между скважинами и сводка ровности."""
from __future__ import annotations

import math

import pytest

from design.models import BlastDesign, BlockContour, Hole, Point3
from design.relief import (
    ReliefTriangle,
    burden_relief,
    converging_edges,
    relief_stats,
    relief_triangles,
)


def hole(hid: str, x: float, y: float, kind: str = "production") -> Hole:
    return Hole(
        id=hid, row=0, col=0, collar=Point3(x, y, 0.0), toe=Point3(x, y, -10.0),
        diameter_mm=200.0, kind=kind,
    )


def grid_holes() -> list[Hole]:
    # 3 ряда × 4 скважины: a = 4 вдоль x, b = 3 вдоль y.
    return [hole(f"{j + 1}-{i + 1:02d}", 4.0 * i, 3.0 * j) for j in range(3) for i in range(4)]


def plane_times(per_hole: float, per_row: float) -> dict[str, float]:
    return {
        f"{j + 1}-{i + 1:02d}": per_hole * i + per_row * j for j in range(3) for i in range(4)
    }


def design_with(holes: list[Hole], pattern_params: dict | None = None) -> BlastDesign:
    return BlastDesign(
        design_id="t", contour=BlockContour(), holes=holes, pattern_params=pattern_params or {}
    )


def test_plane_timing_gives_constant_relief():
    tris = relief_triangles(grid_holes(), plane_times(25, 42), max_edge_m=1.6 * 4)
    assert len(tris) == 12  # 3 × 2 ячейки, по 2 треугольника
    expected = math.hypot(25 / 4, 42 / 3)  # 15,33 мс/м
    assert all(t.relief_ms_m == pytest.approx(expected, abs=1e-6) for t in tris)


def test_constant_relief_has_zero_spread():
    stats = relief_stats(relief_triangles(grid_holes(), plane_times(25, 42), 6.4))
    assert stats.cv == pytest.approx(0.0, abs=1e-9)
    assert stats.outside_share == pytest.approx(0.0)
    assert stats.median_ms_m == pytest.approx(math.hypot(25 / 4, 42 / 3))


def test_simultaneous_firing_gives_zero_relief_and_no_cv():
    stats = relief_stats(relief_triangles(grid_holes(), {h.id: 500.0 for h in grid_holes()}, 6.4))
    assert stats.mean_ms_m == 0.0 and stats.cv is None


def test_slow_corner_raises_spread_and_outside_share():
    times = plane_times(25, 42)
    times["3-04"] += 67  # угловая скважина задержана лишней ступенью
    stats = relief_stats(relief_triangles(grid_holes(), times, 6.4))
    assert stats.cv > 0.05
    assert 0 < stats.outside_share < 0.5


def test_long_edges_are_dropped():
    holes = grid_holes() + [hole("far", 40.0, 0.0)]
    times = plane_times(25, 42) | {"far": 300.0}
    tris = relief_triangles(holes, times, 6.4)
    assert all("far" not in t.hole_ids for t in tris)


def test_holes_without_time_and_walls_are_skipped():
    holes = grid_holes() + [hole("K1-01", 6.0, -1.0, kind="presplit")]
    times = plane_times(25, 42) | {"K1-01": 0.0}
    del times["2-02"]
    ids = {i for t in relief_triangles(holes, times, 6.4) for i in t.hole_ids}
    assert "K1-01" not in ids and "2-02" not in ids


def test_single_row_has_no_triangles():
    row = [hole(f"1-0{i}", 4.0 * i, 0.0) for i in range(4)]
    assert relief_triangles(row, {h.id: 25.0 * i for i, h in enumerate(row)}, 6.4) == []
    assert relief_stats([]) is None


def test_burden_relief_uses_pattern_spacing_for_edge_limit():
    design = design_with(grid_holes(), pattern_params={"spacing_a_m": 4.0, "burden_b_m": 3.0})
    result = burden_relief(design, plane_times(25, 42))
    assert result.stats.triangles == 12
    assert burden_relief(design_with([]), {}) is None
    data = result.to_dict()
    assert set(data) == {"triangles", "stats", "converging"}
    assert len(data["triangles"][0]["points"]) == 3
    assert isinstance(data["triangles"][0]["points"][0], list)


def tri(value: float, area: float) -> ReliefTriangle:
    return ReliefTriangle(
        hole_ids=("a", "b", "c"),
        points=((0.0, 0.0), (1.0, 0.0), (0.0, 1.0)),
        relief_ms_m=value,
        area_m2=area,
    )


def test_noisy_simultaneous_times_give_exact_zero():
    # Одни и те же 52,8 мс, набранные разными путями: 17,6 × 3 ≠ 52,8 в float.
    noisy = 17.6 + 17.6 + 17.6
    assert noisy != 52.8
    times = {h.id: (noisy if k % 2 else 52.8) for k, h in enumerate(grid_holes())}
    tris = relief_triangles(grid_holes(), times, 6.4)
    assert tris and all(t.relief_ms_m == 0.0 for t in tris)
    stats = relief_stats(tris)
    assert stats.cv is None
    assert stats.mean_ms_m == 0.0 and stats.median_ms_m == 0.0
    assert stats.outside_share == 0.0


def test_stats_are_weighted_by_area():
    # Без весов медиана была бы 2, среднее 4,33; по площади — 10 и 103/12.
    stats = relief_stats([tri(1.0, 1.0), tri(2.0, 1.0), tri(10.0, 10.0)])
    assert stats.median_ms_m == pytest.approx(10.0)
    assert stats.mean_ms_m == pytest.approx(103 / 12)
    assert stats.min_ms_m == 1.0 and stats.max_ms_m == 10.0
    # Вне коридора ±25 % от 10 — два малых треугольника: 2 м² из 12.
    assert stats.outside_share == pytest.approx(2 / 12)


def test_zero_median_counts_nonzero_area_as_outside():
    stats = relief_stats([tri(0.0, 3.0), tri(0.0, 3.0), tri(5.0, 1.0)])
    assert stats.median_ms_m == 0.0
    assert stats.outside_share == pytest.approx(1 / 7)


def test_disabled_holes_are_skipped():
    holes = grid_holes()
    off = next(h for h in holes if h.id == "2-02")
    off.enabled = False
    ids = {i for t in relief_triangles(holes, plane_times(25, 42), 6.4) for i in t.hole_ids}
    assert "2-02" not in ids
    assert ids  # остальные треугольники на месте


def test_robust_spread_is_interquartile_range_over_median():
    # По площади: P25 = 4, медиана 8, P75 = 10 — (10 − 4) / 8.
    stats = relief_stats([tri(4.0, 1.0), tri(8.0, 1.0), tri(10.0, 1.0), tri(12.0, 1.0)])
    assert stats.robust_spread == pytest.approx(0.75)


def test_robust_spread_ignores_small_outliers():
    # Две малые площади с выбросами: доля вне коридора их видит, устойчивый разброс — нет.
    stats = relief_stats([tri(1.0, 1.0), tri(2.0, 1.0), tri(10.0, 10.0)])
    assert stats.robust_spread == pytest.approx(0.0)
    assert stats.outside_share > 0


def test_robust_spread_zero_for_even_relief_and_none_for_zero_median():
    even = relief_stats(relief_triangles(grid_holes(), plane_times(25, 42), 6.4))
    assert even.robust_spread == pytest.approx(0.0)
    assert relief_stats([tri(0.0, 3.0), tri(0.0, 3.0), tri(5.0, 1.0)]).robust_spread is None


def test_stats_to_dict_rounds_robust_spread():
    # P25 = 3, медиана 7, P75 = 9: (9 − 3) / 7 = 0,857142…
    stats = relief_stats([tri(3.0, 1.0), tri(7.0, 1.0), tri(9.0, 1.0)])
    assert stats.to_dict()["robust_spread"] == 0.8571
    zero = relief_stats([tri(0.0, 3.0), tri(0.0, 3.0), tri(5.0, 1.0)])
    assert zero.to_dict()["robust_spread"] is None


def v_holes() -> list[Hole]:
    # 3 ряда × 5 столбцов: a = 4 вдоль x, b = 3 вдоль y; вруб — средний столбец i = 2.
    return [hole(f"{j + 1}-{i + 1:02d}", 4.0 * i, 3.0 * j) for j in range(3) for i in range(5)]


def v_times() -> dict[str, float]:
    return {
        f"{j + 1}-{i + 1:02d}": 25.0 * abs(i - 2) + 42.0 * j for j in range(3) for i in range(5)
    }


def test_plane_timing_is_not_fast_and_has_no_converging_fronts():
    relief = burden_relief(
        design_with(grid_holes(), pattern_params={"spacing_a_m": 4.0, "burden_b_m": 3.0}),
        plane_times(25, 42),
    )
    assert relief.stats.fast_share == 0.0 and relief.converging == []
    assert relief.stats.min_bound_ms_m == 3.0 and relief.stats.max_bound_ms_m is None


def test_simultaneous_firing_is_all_fast_without_fronts():
    tris = relief_triangles(grid_holes(), {h.id: 500.0 for h in grid_holes()}, 6.4)
    assert relief_stats(tris).fast_share == 1.0
    assert converging_edges(tris) == []


def test_bounds_from_caller():
    stats = relief_stats(
        relief_triangles(grid_holes(), plane_times(25, 42), 6.4), min_ms_m=16.0, max_ms_m=15.0
    )
    assert stats.fast_share == 1.0 and stats.slow_share == 1.0


def test_v_cut_valley_gives_converging_line_along_cut():
    tris = relief_triangles(v_holes(), v_times(), 6.4)
    edges = converging_edges(tris)
    assert edges and all(abs(a[0] - 8.0) < 1e-6 and abs(b[0] - 8.0) < 1e-6 for a, b in edges)
    stats = burden_relief(
        design_with(v_holes(), pattern_params={"spacing_a_m": 4.0, "burden_b_m": 3.0}), v_times()
    ).stats
    assert stats.converging_length_m == pytest.approx(6.0)  # средняя линия x = 8: два ребра по 3 м


def test_ridge_is_not_converging():
    tris = relief_triangles(v_holes(), {k: -v for k, v in v_times().items()}, 6.4)
    assert converging_edges(tris) == []


def test_slow_share_is_zero_without_upper_bound_and_to_dict_rounds_new_fields():
    relief = burden_relief(
        design_with(v_holes(), pattern_params={"spacing_a_m": 4.0, "burden_b_m": 3.0}),
        v_times(),
        min_ms_m=16.0,
    )
    assert relief.stats.slow_share == 0.0
    data = relief.to_dict()
    assert data["stats"]["min_bound_ms_m"] == 16.0
    assert data["stats"]["max_bound_ms_m"] is None
    assert data["stats"]["fast_share"] == 1.0
    assert data["stats"]["converging_length_m"] == 6.0
    assert all(len(seg) == 2 and all(len(p) == 2 for p in seg) for seg in data["converging"])


def test_motion_almost_along_edge_is_not_converging():
    # 2 мс между скважинами против 42 между рядами: подход к x = 8 под ≈ 2° < 10°.
    times = {
        f"{j + 1}-{i + 1:02d}": 2.0 * abs(i - 2) + 42.0 * j for j in range(3) for i in range(5)
    }
    assert converging_edges(relief_triangles(v_holes(), times, 6.4)) == []
