"""Реальный DWG блока 66 через dwg2dxf — тот же результат, что на фикстуре.

Нужны конвертер (`dwg2dxf` в Docker-образе API) и исходник в
`Docs/specs/block66/` (в git его нет: документ заказчика). Иначе тест
пропускается; запуск — в образе API с примонтированным репозиторием.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from design.spatial.cad.reader import read_cad
from design.spatial.cad.roles import RoleParams, assign_roles
from design.spatial.dwg import find_converter

SOURCES = Path(__file__).resolve().parent.parent / "Docs" / "specs" / "block66"
DWG = next(iter(sorted(SOURCES.glob("*.dwg"))), None) if SOURCES.exists() else None

pytestmark = pytest.mark.skipif(
    find_converter() is None or DWG is None, reason="нет dwg2dxf или исходного DWG блока 66"
)


def test_real_dwg_matches_the_fixture():
    assert DWG is not None
    drawing = read_cad(DWG.read_bytes(), DWG.name)
    assign_roles(drawing.entities, {}, RoleParams())

    assert drawing.source_format == "dwg"
    assert drawing.minimal_dxf is False
    assert drawing.insunits == 4
    assert Counter(item.kind for item in drawing.entities) == {
        "POLYLINE3D": 25,
        "LWPOLYLINE": 1,
        "POINT": 207,
        "TEXT": 203,
    }
    contour = next(item for item in drawing.entities if item.handle == "769")
    assert contour.role == "block_contour"
    assert contour.area_m2 == pytest.approx(2789.93, abs=0.05)
    lower = {item.handle for item in drawing.entities if item.role == "crest_bottom"}
    assert lower == {"733", "73B", "753", "75A"}
