"""Источник линии подошвы (решение владельца 07.11.2026): по умолчанию — по углу.

Нижнюю бровку на съёмке часто снять нельзя (горная масса, снег), поэтому
подошва по умолчанию строится от верхней бровки по углу откоса блока; угол
90° (умолчание сервера у старых паспортов) — «не задан», берётся 75° от
горизонтали. Съёмка — только когда на блоке выбрано `toe_source = "survey"`.
"""
from __future__ import annotations

import math

import pytest

from design.models import BenchSurface, BlastDesign, BlockContour, Point3
from design.toe_line import (
    DEFAULT_FACE_ANGLE_DEG,
    effective_face_angle_deg,
    floor_burdens,
    holes_beyond_toe,
    survey_toe_line,
    toe_line,
)
from tests.front_rows_fixtures import PATTERN, vertical_hole

SURVEY = {"bottom": [[0, -1.5], [40, -1.5], [40, 22], [0, 22]]}
TAN15 = math.tan(math.radians(15))


def _contour(cad=None, face_angle_deg=75.0, toe_source=None) -> BlockContour:
    return BlockContour(
        vertices=[Point3(0, 0, 0), Point3(40, 0, 0), Point3(40, 22, 0), Point3(0, 22, 0)],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=face_angle_deg),
        cad=cad,
        toe_source=toe_source,
    )


def _ys(line) -> set[float]:
    return {round(y, 4) for poly in line.polylines for _, y in poly}


# --- Модель: ключ пишется только когда задан ------------------------------------


def test_contour_without_toe_source_has_no_key():
    data = _contour(cad=SURVEY).to_dict()
    assert "toe_source" not in data
    assert BlockContour.from_dict(data).toe_source is None


def test_toe_source_round_trips():
    data = _contour(cad=SURVEY, toe_source="survey").to_dict()
    assert data["toe_source"] == "survey"
    assert BlockContour.from_dict(data).toe_source == "survey"
    assert BlockContour.from_dict({**data, "toe_source": "angle"}).toe_source == "angle"


@pytest.mark.parametrize("raw", [None, "", "чертёж", 5])
def test_unknown_toe_source_is_dropped(raw):
    data = {**_contour().to_dict(), "toe_source": raw}
    contour = BlockContour.from_dict(data)
    assert contour.toe_source is None
    assert "toe_source" not in contour.to_dict()


# --- Угол откоса: 90° — не задан -------------------------------------------------


def test_effective_angle():
    assert DEFAULT_FACE_ANGLE_DEG == 75.0
    assert effective_face_angle_deg(BenchSurface(face_angle_deg=90.0)) == 75.0
    assert effective_face_angle_deg(BenchSurface(face_angle_deg=70.0)) == 70.0


# --- Линия подошвы ---------------------------------------------------------------


def test_default_is_angle_even_with_survey():
    line = toe_line(_contour(cad=SURVEY))
    assert line.source == "angle"
    assert _ys(line) == {round(-10 * TAN15, 4)}


def test_survey_only_when_selected():
    line = toe_line(_contour(cad=SURVEY, toe_source="survey"))
    assert line.source == "survey"
    assert _ys(line) == {-1.5}


def test_explicit_angle_ignores_survey():
    assert toe_line(_contour(cad=SURVEY, toe_source="angle")).source == "angle"


def test_selected_survey_without_survey_falls_back_to_angle():
    assert toe_line(_contour(toe_source="survey")).source == "angle"


def test_angle_with_90_degrees_uses_75():
    # Старый блок без угла (90°): подошва — на H·tg 15° от бровки, а не под ней.
    line = toe_line(_contour(face_angle_deg=90.0))
    assert _ys(line) == {round(-10 * TAN15, 4)}


def test_survey_toe_line_is_available_for_comparison():
    # Снятая бровка нужна плану пунктиром и тогда, когда ЛСП — по углу.
    survey = survey_toe_line(_contour(cad=SURVEY))
    assert survey is not None and survey.source == "survey"
    assert _ys(survey) == {-1.5}
    assert survey_toe_line(_contour()) is None
    assert survey_toe_line(_contour(cad={**SURVEY, "edited": True})) is None


# --- ЛСП и «за подошвой» по углу -------------------------------------------------


def _design(contour, holes):
    return BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=PATTERN)


def test_floor_burden_by_angle_with_survey_present():
    hole = vertical_hole("1-01", x=10, y=2.0, row=0)
    fb = floor_burdens(_design(_contour(cad=SURVEY), [hole]))["1-01"]
    assert fb.toe_source == "angle"
    assert fb.value_m == pytest.approx(2.0 + 10 * TAN15, abs=1e-3)
    fb = floor_burdens(_design(_contour(cad=SURVEY, toe_source="survey"), [hole]))["1-01"]
    assert fb.toe_source == "survey"
    assert fb.value_m == pytest.approx(3.5, abs=1e-3)


def test_beyond_toe_uses_default_angle_for_90_degrees():
    # Устье за бровкой на 2 м (подошва 75° — на 2,68 м): не за подошвой; на 3 м — за.
    near = vertical_hole("1-01", x=10, y=-2.0, row=0)
    far = vertical_hole("1-02", x=20, y=-3.0, row=0)
    beyond = holes_beyond_toe(_design(_contour(face_angle_deg=90.0), [near, far]))
    assert beyond == ["1-02"]


def test_layout_search_algorithm_version_bumped():
    # Подошва по углу по умолчанию меняет итог перебора при тех же входах:
    # прежние итоги — «Устарел».
    from design.layout_search.jobs import SEARCH_ALGORITHM_VERSION

    assert SEARCH_ALGORITHM_VERSION >= 3
