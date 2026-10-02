"""Отметки устьев и длины скважин по кровле и подошве (TASK-013, PR 3, §2
«Длины скважин», §3 PR 3 п. 8).

Решение владельца 02.10.2026: перебур откладывается вдоль оси,
L = (S − Z)/cos α + Δ. Одна формула для генерации сетки, правок и пересчёта.
"""
from __future__ import annotations

import math

import pytest

from design.geometry import collar_on_roof, drape_collar, hole_from_collar
from design.hole_recompute import explicit_depth_m, recompute_holes
from design.models import BenchSurface, BlockContour, Hole, Point3
from design.spatial.surfaces import SurfaceModel, SurfaceSet
from design.spatial.tin import TIN

FLOOR = 410.0


def plane_roof(x0=-10.0, x1=60.0, y0=-10.0, y1=40.0) -> SurfaceSet:
    """Кровля z = 420 + 0,01·x двумя треугольниками."""

    z = lambda x: 420.0 + 0.01 * x  # noqa: E731
    tin = TIN(
        vertices=[Point3(x0, y0, z(x0)), Point3(x1, y0, z(x1)), Point3(x1, y1, z(x1)), Point3(x0, y1, z(x0))],
        triangles=[(0, 1, 2), (0, 2, 3)],
    )
    return SurfaceSet(top=SurfaceModel(kind="top", tin=tin))


def contour() -> BlockContour:
    return BlockContour(
        vertices=[Point3(0, 0, 420), Point3(40, 0, 420), Point3(40, 20, 420), Point3(0, 20, 420)],
        bench=BenchSurface(crest_z_m=420.0, toe_z_m=FLOOR),
    )


def hole(x, y, *, angle=0.0, azimuth=90.0, subdrill=1.0, length=12.0, z=420.0, kind="production", manual=None, enabled=True):
    collar = Point3(x, y, z)
    return Hole(
        id=f"{x:g}-{y:g}",
        row=0,
        col=0,
        collar=collar,
        toe=hole_from_collar(collar, length, angle, azimuth),
        diameter_mm=152.0,
        subdrill_m=subdrill,
        kind=kind,
        enabled=enabled,
        manual=list(manual or []),
    )


@pytest.mark.parametrize("x", [0.0, 10.0, 35.5])
def test_vertical_hole_length_is_roof_minus_floor_plus_subdrill(x):
    collar, toe = drape_collar(x, 5.0, 0.0, 0.0, 1.0, contour(), plane_roof())

    assert collar.z == pytest.approx(420.0 + 0.01 * x)
    assert math.dist((collar.x, collar.y, collar.z), (toe.x, toe.y, toe.z)) == pytest.approx(10.0 + 0.01 * x + 1.0, abs=0.01)


def test_inclined_hole_subdrill_lies_along_the_axis():
    alpha = 10.0
    collar, toe = drape_collar(10.0, 5.0, alpha, 90.0, 1.0, contour(), plane_roof())

    expected = (420.1 - FLOOR) / math.cos(math.radians(alpha)) + 1.0
    assert math.dist((collar.x, collar.y, collar.z), (toe.x, toe.y, toe.z)) == pytest.approx(expected, abs=0.01)


def test_bench_without_a_surface_uses_the_same_formula():
    collar, toe = drape_collar(10.0, 5.0, 10.0, 90.0, 1.0, contour(), None)

    assert collar.z == 420.0
    expected = 10.0 / math.cos(math.radians(10.0)) + 1.0
    assert math.dist((collar.x, collar.y, collar.z), (toe.x, toe.y, toe.z)) == pytest.approx(expected, abs=1e-9)


def test_collar_outside_the_roof_takes_the_nearest_vertex_and_a_flag():
    roof = plane_roof(x0=0.0, x1=30.0)

    z, outside = collar_on_roof(45.0, 5.0, contour(), roof)

    assert outside is True
    assert z == pytest.approx(420.3)
    assert collar_on_roof(10.0, 5.0, contour(), roof) == (pytest.approx(420.1), False)


def test_recompute_puts_collars_on_the_roof_and_lengths_to_the_floor():
    holes = [hole(10.0, 5.0), hole(20.0, 5.0, angle=10.0)]

    result = recompute_holes(holes, contour(), plane_roof(), {})

    first, second = result
    assert first.hole.collar.z == pytest.approx(420.1)
    assert first.hole.length_m == pytest.approx(11.1, abs=0.01)
    assert second.hole.length_m == pytest.approx(10.2 / math.cos(math.radians(10.0)) + 1.0, abs=0.01)
    assert second.hole.angle_deg == pytest.approx(10.0)
    assert second.hole.azimuth_deg == pytest.approx(90.0)
    assert first.flags == [] and second.flags == []


def test_hole_beyond_the_roof_gets_a_flag():
    roof = plane_roof(x0=0.0, x1=30.0)

    (result,) = recompute_holes([hole(38.0, 5.0)], contour(), roof, {})

    assert result.flags == ["outside_surface"]
    assert result.hole.collar.z == pytest.approx(420.3)


def test_manual_collar_and_length_survive_recompute():
    keep_z = hole(10.0, 5.0, z=425.0, manual=["collar_z"])
    keep_length = hole(20.0, 5.0, length=7.5, manual=["length"])
    both = hole(30.0, 5.0, z=419.0, length=3.0, manual=["collar_z", "length"])

    by_id = {item.hole.id: item.hole for item in recompute_holes([keep_z, keep_length, both], contour(), plane_roof(), {})}

    assert by_id[keep_z.id].collar.z == 425.0
    assert by_id[keep_z.id].length_m == pytest.approx(425.0 - FLOOR + 1.0)
    assert by_id[keep_length.id].collar.z == pytest.approx(420.2)
    assert by_id[keep_length.id].length_m == pytest.approx(7.5)
    assert by_id[both.id].collar == both.collar and by_id[both.id].toe == both.toe
    assert by_id[keep_z.id].manual == ["collar_z"]


def test_short_bench_is_flagged():
    roof = plane_roof()
    low = BlockContour(vertices=contour().vertices, bench=BenchSurface(crest_z_m=420.0, toe_z_m=419.5))

    (result,) = recompute_holes([hole(10.0, 5.0)], low, roof, {})

    assert result.flags == ["short_bench"]


def test_holes_with_an_explicit_depth_keep_their_length_and_move_with_the_roof():
    stab = hole(10.0, 5.0, length=3.0, kind="stab")
    contour_hole = hole(20.0, 5.0, length=6.0, kind="contour")
    params = {"contour_depth_m": 6.0}

    by_kind = {item.hole.kind: item.hole for item in recompute_holes([stab, contour_hole], contour(), plane_roof(), params)}

    assert by_kind["stab"].collar.z == pytest.approx(420.1)
    assert by_kind["stab"].length_m == pytest.approx(3.0)
    assert by_kind["contour"].length_m == pytest.approx(6.0)


def test_explicit_depth_by_kind():
    assert explicit_depth_m("stab", {}) == 3.0
    assert explicit_depth_m("contour", {"depth_m": 9.0}) == 9.0
    assert explicit_depth_m("contour", {"contour_depth_m": 6.0, "depth_m": 9.0}) == 6.0
    assert explicit_depth_m("satellite", {"satellite_depth_m": 4.0}) == 4.0
    assert explicit_depth_m("production", {}) is None
    assert explicit_depth_m("production", {"depth_m": 12.0}) == 12.0


def test_disabled_holes_are_recomputed_the_same_way():
    (result,) = recompute_holes([hole(10.0, 5.0, enabled=False)], contour(), plane_roof(), {})

    assert result.hole.length_m == pytest.approx(11.1, abs=0.01)
    assert result.hole.enabled is False


def test_validation_lists_holes_outside_the_roof_and_on_a_short_bench():
    from design.analysis import validate
    from design.models import BlastDesign

    low = hole(10.0, 5.0, z=410.5)
    outside = hole(38.0, 5.0)
    design = BlastDesign(design_id="d", contour=contour(), holes=[low, outside], surfaces=plane_roof(x0=0.0, x1=30.0))

    codes = {(item["code"], item["hole_id"]) for item in validate(design)}

    assert ("hole_short_bench", low.id) in codes
    assert ("hole_outside_surface", outside.id) in codes
    assert ("hole_outside_surface", low.id) not in codes
