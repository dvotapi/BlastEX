"""Кровля блока 66 по фикстуре маркшейдера (TASK-013, PR 3, задача 5).

Координаты фикстуры сдвинуты на секретную константу; тесты опираются только
на относительную геометрию: площади, высоты, объёмы, число точек. Для
проверки координат МСК — только синтетический сдвиг (7 000 000; 500 000).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from design.spatial.cad.contour import ready_contour
from design.spatial.cad.model import CadEntity
from design.spatial.cad.reader import read_cad
from design.spatial.cad.roles import RoleParams, assign_roles
from design.spatial.cad.stitch import stitch_lines
from design.spatial.cad.surface import build_roof, volume_in_polygon
from design.spatial.cad.surface_builder import CdtBuilder, ScipyBuilder
from design.spatial.cad.two_contours import bench_levels, two_contours

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"
BIG_SHIFT = (7_000_000.0, 500_000.0)
FLOOR_Z = 410.0
# Блоковая карта: 2772,49 м² × 10,2 м.
MAP_VOLUME_M3 = 28_279.39


def _cdt():
    if os.environ.get("BLASTEX_REQUIRE_CDT") != "1":
        pytest.importorskip("PythonCDT", reason="PythonCDT не установлен")
    return CdtBuilder()


BUILDERS = [pytest.param(_cdt, id="cdt"), pytest.param(ScipyBuilder, id="scipy")]


@pytest.fixture(scope="module")
def block():
    drawing = read_cad(FIXTURE.read_bytes(), "block66.dxf")
    assign_roles(drawing.entities, {}, RoleParams())
    entities = drawing.entities
    by_handle = {item.handle: item for item in entities}
    draft = ready_contour(by_handle["769"])
    tops, _ = stitch_lines([item for item in entities if item.role == "crest_top" and item.geometry_type == "line"])
    bottoms, _ = stitch_lines([item for item in entities if item.role == "crest_bottom" and item.geometry_type == "line"])
    two = two_contours(draft.ring, tops, bottoms)
    levels = bench_levels(draft.ring, two.free_faces, tops, bottoms, FLOOR_Z)
    return entities, draft.ring, two.bottom, levels.crest_z_m


def _shift(entities, dx, dy):
    return [
        CadEntity(
            handle=item.handle,
            layer=item.layer,
            kind=item.kind,
            points=[(x + dx, y + dy, z) for x, y, z in item.points],
            role=item.role,
        )
        for item in entities
    ]


@pytest.mark.parametrize("factory", BUILDERS)
def test_block_66_roof_from_marks_and_crests(block, factory):
    entities, top, bottom, crest_z = block

    started = time.perf_counter()
    roof = build_roof(entities, top, bottom, floor_z=FLOOR_Z, crest_z=crest_z, builder=factory())
    elapsed = time.perf_counter() - started

    assert roof.ok, roof.issues
    assert not roof.plane
    assert elapsed < 1.0
    # 206 отметок из 207 — у контура; многие совпадают с вершинами бровок
    # (бровку маркшейдер вёл через точки съёмки).
    assert roof.spot_count == 206
    # У юго-западного угла нижнего контура данных нет: треугольник с ребром
    # 42 м срезан пределом 30 м — 3 м² из 4121.
    assert roof.coverage_pct > 99.9
    assert roof.mean_height_m == pytest.approx(10.5, abs=0.1)
    assert not roof.needs_confirmation
    assert roof.outliers == []
    assert roof.data.conflicts == []
    assert [warning.code for warning in roof.warnings] == []
    # Нижняя бровка местами выше подошвы 410: до 1,95 м.
    assert max(item.excess_m for item in roof.thresholds) == pytest.approx(1.95, abs=0.05)


@pytest.mark.parametrize("factory", BUILDERS)
def test_block_66_volumes_next_to_the_block_map(block, factory):
    entities, top, bottom, crest_z = block

    roof = build_roof(entities, top, bottom, floor_z=FLOOR_Z, crest_z=crest_z, builder=factory())
    world = roof.world_vertices()
    in_top = volume_in_polygon(world, roof.triangles, top, FLOOR_Z)

    # Объём блока — по нижней бровке (решение владельца 02.10.2026): откос
    # между бровками входит в блок, карта считает по контуру по верхней.
    assert roof.volume_basis == "bottom"
    assert roof.volume_m3 == pytest.approx(36_939, rel=0.01)
    assert in_top.volume_m3 == pytest.approx(MAP_VOLUME_M3, rel=0.05)
    assert roof.mean_area_volume_m3 == pytest.approx(roof.area_mean_m2 * roof.mean_height_m)


@pytest.mark.parametrize("factory", BUILDERS)
def test_block_66_roof_does_not_depend_on_msk_coordinates(block, factory):
    entities, top, bottom, crest_z = block
    dx, dy = BIG_SHIFT

    plain = build_roof(entities, top, bottom, floor_z=FLOOR_Z, crest_z=crest_z, builder=factory())
    moved = build_roof(
        _shift(entities, dx, dy),
        [(x + dx, y + dy) for x, y in top],
        [(x + dx, y + dy) for x, y in bottom],
        floor_z=FLOOR_Z,
        crest_z=crest_z,
        builder=factory(),
    )

    assert moved.volume_m3 == pytest.approx(plain.volume_m3, rel=1e-4)
    assert moved.mean_height_m == pytest.approx(plain.mean_height_m, abs=1e-3)
    for x, y in top[::4]:
        assert moved.elevation_at(x + dx, y + dy) == pytest.approx(plain.elevation_at(x, y), abs=1e-3)
