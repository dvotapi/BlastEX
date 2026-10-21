"""Линия подошвы откоса: по съёмке нижней бровки или от верхней бровки по углу."""
from __future__ import annotations

import pytest

from design.models import BenchSurface, BlockContour, Point3
from design.toe_line import slope_offset_m, toe_line


def rect_contour(cad=None, free_faces=None) -> BlockContour:
    return BlockContour(
        vertices=[Point3(0, 0, 0), Point3(40, 0, 0), Point3(40, 22, 0), Point3(0, 22, 0)],
        free_faces=[[0, 1]] if free_faces is None else free_faces,
        bench=BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75),
        cad=cad,
    )


def test_offset_for_15_degrees_from_vertical():
    bench = BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75)
    assert slope_offset_m(bench) == pytest.approx(2.6795, abs=1e-4)


def test_vertical_face_has_zero_offset():
    bench = BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=90)
    assert slope_offset_m(bench) == pytest.approx(0.0)


def test_built_toe_line_lies_outside_block_at_offset():
    line = toe_line(rect_contour())
    assert line.source == "built"
    ys = [y for poly in line.polylines for _, y in poly]
    assert all(y == pytest.approx(-2.6795, abs=1e-3) for y in ys)


def test_survey_toe_line_uses_bottom_ring_edge_near_free_face():
    # cad.bottom — кольцо по нижней бровке: фронт на y = -3, тыл и фланги совпадают с контуром.
    contour = rect_contour(cad={"bottom": [[0, -3], [40, -3], [40, 22], [0, 22]]})
    line = toe_line(contour)
    assert line.source == "survey"
    ys = {round(y, 6) for poly in line.polylines for _, y in poly}
    assert ys == {-3.0}  # только фронтальное ребро, без тыла y = 22


def test_edited_contour_ignores_survey():
    contour = rect_contour(cad={"bottom": [[0, -3], [40, -3], [40, 22], [0, 22]], "edited": True})
    assert toe_line(contour).source == "built"


def test_survey_without_edge_near_face_falls_back_to_built():
    contour = rect_contour(cad={"bottom": [[0, -30], [40, -30], [40, 22], [0, 22]]})
    assert toe_line(contour).source == "built"


def test_no_free_faces_gives_none():
    assert toe_line(rect_contour(free_faces=[])) is None
