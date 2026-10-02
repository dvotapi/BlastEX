"""Построитель кровли `SurfaceBuilder` (TASK-013, PR 3).

Основной путь — CDT (PythonCDT, колесо собирается из исходников), запасной —
scipy Delaunay с исправлением рёбер. Оба пути проходят одни и те же тесты.
Без PythonCDT тесты CDT пропускаются с причиной; в Docker-образе
(`BLASTEX_REQUIRE_CDT=1`) они обязаны пройти.
"""
from __future__ import annotations

import os

import numpy as np
import pytest


def _require_cdt():
    if os.environ.get("BLASTEX_REQUIRE_CDT") == "1":
        import PythonCDT  # noqa: F401 — в образе модуль обязан быть

        return PythonCDT
    return pytest.importorskip("PythonCDT", reason="PythonCDT не установлен: колесо собирается из исходников")


def test_pythoncdt_triangulates_with_a_constraint():
    cdt = _require_cdt()
    triangulation = cdt.Triangulation(
        cdt.VertexInsertionOrder.AUTO, cdt.IntersectingConstraintEdges.TRY_RESOLVE, 0.0
    )
    triangulation.insert_vertices(np.array([[0, 0], [10, 0], [10, 10], [0, 10], [1, 1], [9, 9]], dtype=float))
    triangulation.insert_edges(np.array([[4, 5]], dtype=np.uintc))
    triangulation.erase_super_triangle()

    triangles = triangulation.triangles_array()["vertices"]
    edges = {tuple(sorted((int(a), int(b)))) for tri in triangles for a, b in zip(tri, np.roll(tri, -1))}
    assert (4, 5) in edges
