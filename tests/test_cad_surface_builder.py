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
import shapely

from design.spatial.cad.surface_builder import CdtBuilder, ScipyBuilder, SurfaceBuildError, make_builder


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


# --- оба пути построителя ---------------------------------------------------


def _cdt():
    _require_cdt()
    return CdtBuilder()


BUILDERS = [pytest.param(_cdt, id="cdt"), pytest.param(ScipyBuilder, id="scipy")]


def _triangles(result):
    return shapely.polygons(result.vertices[result.triangles])


def assert_conforms(result, points, constraints):
    """Каждый ограничитель — рёбра триангуляции: ни один треугольник его не пересекает внутри."""

    triangles = _triangles(result)
    covered = shapely.union_all(triangles)
    # Вершина пересечения лежит на отрезке с точностью арифметики: треугольники
    # сжимаются на 1 мкм, чтобы касание по ребру не считалось пересечением.
    inner = shapely.buffer(triangles, -1e-6)
    for a, b in constraints:
        segment = shapely.linestrings([points[a], points[b]])
        crossing = shapely.intersects(inner, segment)
        assert not np.any(crossing), f"ограничитель {a}–{b} пересекает треугольник"
        assert covered.buffer(1e-9).covers(segment)


SQUARE = np.array([[0, 0], [20, 0], [20, 20], [0, 20]], dtype=float)


def _cloud(seed=1, count=60):
    rng = np.random.default_rng(seed)
    return np.vstack([SQUARE, rng.uniform(0.5, 19.5, size=(count, 2))])


@pytest.mark.parametrize("factory", BUILDERS)
def test_every_constraint_is_an_edge_of_the_triangulation(factory):
    points = np.vstack([_cloud(), [[1.0, 10.0], [19.0, 10.3], [10.0, 1.0], [10.2, 19.0]]])
    n = len(points)
    constraints = np.array([[n - 4, n - 3], [n - 2, n - 1]])

    result = factory().build(points, constraints)

    assert len(result.vertices) >= n
    assert np.allclose(result.vertices[:n], points)
    assert_conforms(result, result.vertices, constraints)


@pytest.mark.parametrize("factory", BUILDERS)
def test_crossing_constraints_get_a_vertex_from_both(factory):
    points = np.vstack([SQUARE, [[2.0, 10.0], [18.0, 10.0], [10.0, 2.0], [10.0, 18.0]]])
    constraints = np.array([[4, 5], [6, 7]])

    result = factory().build(points, constraints)

    new = [index for index in range(len(points), len(result.vertices))]
    crossing = [index for index in new if np.allclose(result.vertices[index], [10.0, 10.0])]
    assert crossing, "нет вершины в пересечении"
    assert sorted(result.origins[crossing[0]]) == [0, 1]
    for index in new:
        assert set(result.origins[index]) <= {0, 1}


@pytest.mark.parametrize("factory", BUILDERS)
def test_long_constraint_through_a_dense_cloud_is_kept(factory):
    rng = np.random.default_rng(7)
    points = np.vstack([SQUARE, rng.uniform(0.5, 19.5, size=(400, 2)), [[0.3, 0.7], [19.7, 19.1]]])
    n = len(points)
    constraints = np.array([[n - 2, n - 1]])

    result = factory().build(points, constraints)

    assert_conforms(result, result.vertices, constraints)
    for index in range(n, len(result.vertices)):
        assert result.origins[index] == [0]


@pytest.mark.parametrize("factory", BUILDERS)
def test_vertex_lying_on_a_constraint_splits_it(factory):
    points = np.vstack([SQUARE, [[2.0, 10.0], [18.0, 10.0], [10.0, 10.0]]])

    result = factory().build(points, np.array([[4, 5]]))

    assert_conforms(result, result.vertices, [(4, 5)])
    edges = {tuple(sorted(edge)) for tri in result.triangles.tolist() for edge in zip(tri, tri[1:] + tri[:1])}
    assert (4, 6) in edges and (5, 6) in edges


@pytest.mark.parametrize("factory", BUILDERS)
def test_collinear_points_give_no_triangles(factory):
    points = np.array([[0, 0], [1, 0], [2, 0], [3, 0]], dtype=float)

    result = factory().build(points, np.zeros((0, 2), dtype=int))

    assert len(result.triangles) == 0


@pytest.mark.parametrize("factory", BUILDERS)
def test_duplicate_points_are_one_vertex(factory):
    points = np.vstack([SQUARE, [[5.0, 5.0], [5.0, 5.0], [15.0, 15.0]]])

    result = factory().build(points, np.array([[5, 6]]))

    used = set(result.triangles.ravel().tolist())
    assert 4 in used and 5 not in used
    assert_conforms(result, result.vertices, [(4, 6)])


def test_scipy_fallback_is_chosen_by_the_flag(monkeypatch):
    monkeypatch.setenv("BLASTEX_SURFACE_BUILDER", "scipy")
    assert make_builder().name == "scipy"


def test_cdt_is_the_default_when_installed(monkeypatch):
    _require_cdt()
    monkeypatch.delenv("BLASTEX_SURFACE_BUILDER", raising=False)
    assert make_builder().name == "cdt"


def test_without_pythoncdt_the_default_falls_back_to_scipy(monkeypatch, caplog):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PythonCDT":
            raise ImportError("нет модуля")
        return real_import(name, *args, **kwargs)

    monkeypatch.delenv("BLASTEX_SURFACE_BUILDER", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert make_builder().name == "scipy"
    assert "PythonCDT" in caplog.text


def test_unknown_builder_name_is_an_error(monkeypatch):
    monkeypatch.setenv("BLASTEX_SURFACE_BUILDER", "triangle")
    with pytest.raises(SurfaceBuildError, match="BLASTEX_SURFACE_BUILDER"):
        make_builder()
