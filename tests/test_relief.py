"""Темп отбойки: мс/м по треугольникам между скважинами и сводка ровности."""
from __future__ import annotations

import math

import pytest

from design.models import BlastDesign, BlockContour, Hole, Point3
from design.relief import ReliefTriangle, burden_relief, relief_stats, relief_triangles


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
    assert set(data) == {"triangles", "stats"}
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
