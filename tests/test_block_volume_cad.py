"""Объём блока по нижней бровке (TASK-013, PR 3, решение владельца 02.10.2026).

`block_volume` берёт `contour.cad.bottom`, если контур построен из чертежа и
его не правили (`cad.edited` = false). Паспорта без `contour.cad` считаются
как раньше.
"""
from __future__ import annotations

import pytest

from design.geometry import _volume_from_surfaces, block_volume, mean_bench_height
from design.models import BenchSurface, BlockContour, Point3
from design.spatial.surfaces import SurfaceModel, SurfaceSet
from design.spatial.tin import TIN

TOP = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]
BOTTOM = [[0.0, 0.0], [44.0, 0.0], [44.0, 20.0], [0.0, 20.0]]


def contour(cad=None) -> BlockContour:
    return BlockContour(
        vertices=[Point3(x, y, 420.0) for x, y in TOP],
        bench=BenchSurface(crest_z_m=420.0, toe_z_m=410.0),
        cad=cad,
    )


def cad(edited=False) -> dict:
    return {"source_id": "s", "top": [list(p) for p in TOP], "bottom": BOTTOM, "area_mean_m2": 840.0, "edited": edited}


def roof() -> SurfaceSet:
    """Кровля z = 420 + 0,01·x."""

    z = lambda x: 420.0 + 0.01 * x  # noqa: E731
    tin = TIN(
        vertices=[Point3(-10, -10, z(-10)), Point3(60, -10, z(60)), Point3(60, 40, z(60)), Point3(-10, 40, z(-10))],
        triangles=[(0, 1, 2), (0, 2, 3)],
    )
    return SurfaceSet(top=SurfaceModel(kind="top", tin=tin))


def test_passport_without_a_drawing_keeps_its_volume():
    assert block_volume(contour()) == pytest.approx(800.0 * 10.0)
    plain = contour()
    assert block_volume(plain, roof()) == _volume_from_surfaces(plain, roof().top, None)


def test_drawing_contour_without_a_roof_keeps_the_passport_contour_volume():
    # Без кровли откос не описан: плоскость бровки над ним завысила бы объём
    # на (S низ − S верх)·H/2 — объём как раньше, по контуру паспорта.
    assert block_volume(contour(cad())) == pytest.approx(800.0 * 10.0)


def test_plane_roof_counts_mean_area_times_height():
    plane = roof()
    plane.top.tin = TIN(
        vertices=[Point3(-10, -10, 420), Point3(60, -10, 420), Point3(60, 40, 420), Point3(-10, 40, 420)],
        triangles=[(0, 1, 2), (0, 2, 3)],
    )
    plane.top.cad = {"plane": True}

    assert block_volume(contour(cad()), plane) == pytest.approx(840.0 * 10.0)


def test_drawing_contour_with_a_roof_is_exact_inside_the_bottom_crest():
    assert block_volume(contour(cad()), roof()) == pytest.approx(880.0 * 10.0 + 0.01 * 20.0 * 44.0**2 / 2)


def test_edited_contour_falls_back_to_the_passport_contour():
    edited = contour(cad(edited=True))

    assert block_volume(edited) == pytest.approx(8000.0)
    assert block_volume(edited, roof()) == _volume_from_surfaces(edited, roof().top, None)


def test_mean_bench_height_over_the_top_contour():
    assert mean_bench_height(contour(cad()), roof()) == pytest.approx(10.2)
    assert mean_bench_height(contour(), None) == pytest.approx(10.0)


def floor_tin() -> SurfaceModel:
    """Подошва z = 408 + 0,1·y — не плоскость отметки подошвы 410."""

    z = lambda y: 408.0 + 0.1 * y  # noqa: E731
    tin = TIN(
        vertices=[Point3(-10, -10, z(-10)), Point3(60, -10, z(-10)), Point3(60, 40, z(40)), Point3(-10, 40, z(40))],
        triangles=[(0, 1, 2), (0, 2, 3)],
    )
    return SurfaceModel(kind="floor", tin=tin)


def test_mean_bench_height_uses_the_floor_tin():
    # Ревью Codex #104: при подошве из TIN средняя высота вычитала отметку
    # подошвы 410, а объём — подошву из TIN; показатели расходились.
    surfaces = roof()
    surfaces.floor = floor_tin()
    plain = contour()

    # Кровля в среднем 420,2, подошва — 408 + 0,1 · 10 = 409.
    assert mean_bench_height(plain, surfaces) == pytest.approx(11.2)
    assert block_volume(plain, surfaces) == pytest.approx(800.0 * mean_bench_height(plain, surfaces))
