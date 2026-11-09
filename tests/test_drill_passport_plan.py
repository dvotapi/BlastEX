"""План расположения скважин на стр. 4 паспорта на бурение (TASK-015, PR 3)."""
from __future__ import annotations

from copy import deepcopy

import pytest

from design.reporting.drill.plan import (
    LABEL_PT,
    MIN_HOLE_MM,
    PLAN_H_MM,
    PLAN_PAD_MM,
    PLAN_W_MM,
    build_plan,
    plan_scale,
)
from tests.drill_passport_context import context66


def test_scale_rounds_up_to_ten():
    # 143,2 м на 216 мм поля → 1:663 → 1:670.
    assert plan_scale(40.0, 143.2, 180, 228) == 670


def test_scale_is_not_larger_than_200():
    assert plan_scale(10, 10, 180, 228) == 200


def test_scale_by_width_when_block_is_wide():
    # 300 м на 160 мм по ширине (за вычетом места под подписи) → 1:1875 → 1:1880.
    assert plan_scale(300, 50, 180, 228) == 1880


@pytest.fixture(scope="module")
def sheet66():
    return build_plan(context66())


def _inside(x: float, y: float) -> bool:
    eps = 1e-6
    return PLAN_PAD_MM - eps <= x <= PLAN_W_MM - PLAN_PAD_MM + eps and PLAN_PAD_MM - eps <= y <= PLAN_H_MM - PLAN_PAD_MM + eps


def test_block66_scale_and_holes(sheet66):
    assert sheet66.scale == 670
    assert len(sheet66.holes) == 196
    assert sum(hole.first_row for hole in sheet66.holes) == 44
    assert all(_inside(hole.x, hole.y) for hole in sheet66.holes)
    assert all(_inside(x, y) for x, y in sheet66.contour)
    assert sheet66.note == ""


def test_block66_labels(sheet66):
    by_number = {hole.number: hole for hole in sheet66.holes}
    assert by_number["1"].depth == "10,7"
    assert {hole.depth for hole in sheet66.holes} >= {"11,6", "13,8"}
    assert LABEL_PT[0] <= sheet66.label_pt <= LABEL_PT[1]


def test_north_is_up(sheet66):
    # Скважина 48 — на севере блока, 1 — на юге (эталон plan_66.png).
    by_number = {hole.number: hole for hole in sheet66.holes}
    assert by_number["48"].y > by_number["1"].y


def test_hole_circle_has_minimum_size(sheet66):
    # Ø 115 мм в 1:670 — 0,17 мм: кружок не мельче MIN_HOLE_MM.
    assert all(hole.r == pytest.approx(MIN_HOLE_MM / 2) for hole in sheet66.holes)


def test_scale_bar(sheet66):
    assert sheet66.bar_m == 20
    assert sheet66.bar_mm == pytest.approx(20_000 / 670)


def test_block66_crests_and_no_situation(sheet66):
    assert sheet66.crest_top and sheet66.crest_toe
    assert sheet66.toe_source == "angle"
    assert sheet66.situation == ()


def test_vertical_holes_have_no_toe_line(sheet66):
    assert all(hole.toe is None for hole in sheet66.holes)


def test_inclined_hole_has_toe_point():
    context = context66()
    row = context["holes"][0]
    row["azimuth_deg"] = 90.0
    row["toe"]["x"] = row["collar"]["x"] + 2.0
    hole = build_plan(context).holes[0]
    assert hole.toe is not None
    assert hole.toe[0] - hole.x == pytest.approx(2000 / 670)


def test_situation_is_clipped_to_field():
    context = context66()
    x, y = context["holes"][0]["collar"]["x"], context["holes"][0]["collar"]["y"]
    context["plan"]["situation"] = [
        {"kind": "road", "lines": [{"points": [[x - 200, y], [x + 200, y]], "closed": False}]},
    ]
    sheet = build_plan(context)
    (line,) = sheet.situation
    assert all(0 <= px <= PLAN_W_MM and 0 <= py <= PLAN_H_MM for px, py in line)
    assert line[0][0] == pytest.approx(0) and line[-1][0] == pytest.approx(PLAN_W_MM)


def _grid_context(width_m: float, height_m: float) -> dict:
    context = context66()
    rows = []
    for index in range(60):
        row = deepcopy(context["holes"][index])
        row["collar"]["x"] = 1000.0 + (index % 10) * width_m / 9
        row["collar"]["y"] = 5000.0 + (index // 10) * height_m / 5
        rows.append(row)
    context["holes"] = rows
    context["plan"] = {"contour": [], "crest_top": [], "crest_toe": [], "toe_source": None, "situation": []}
    return context


def test_big_block_keeps_minimum_label():
    # Блок 300 × 300 м с сеткой 4 м: масштаб мелкий, подписи — не мельче LABEL_PT[0].
    context = _grid_context(36, 20)
    context["plan"]["contour"] = [[990.0, 4990.0], [1290.0, 4990.0], [1290.0, 5290.0], [990.0, 5290.0]]
    sheet = build_plan(context)
    assert sheet.scale == plan_scale(300, 300, PLAN_W_MM, PLAN_H_MM)
    assert sheet.label_pt == LABEL_PT[0]
    assert all(_inside(hole.x, hole.y) for hole in sheet.holes)


def test_no_contour_scales_by_holes():
    sheet = build_plan(_grid_context(60, 100))
    assert sheet.contour == () and sheet.crest_top == () and sheet.crest_toe == ()
    assert sheet.toe_source is None
    assert sheet.scale == plan_scale(60, 100, PLAN_W_MM, PLAN_H_MM)
    assert sheet.note == ""


def test_revision_before_plan_draws_collars():
    context = context66()
    del context["plan"]
    for row in context["holes"]:
        row.pop("toe", None)
        row.pop("diameter_mm", None)
    sheet = build_plan(context)
    assert len(sheet.holes) == 196
    assert sheet.contour == ()
    assert sheet.note == "Контур и бровки не сохранены в ревизии"


def test_no_holes_and_no_contour():
    context = context66()
    context["holes"] = []
    context["plan"] = {"contour": [], "crest_top": [], "crest_toe": [], "toe_source": None, "situation": []}
    sheet = build_plan(context)
    assert sheet.holes == () and sheet.scale == 200


# --- отрисовка ---------------------------------------------------------------

from reportlab.graphics.shapes import Circle, Group, PolyLine  # noqa: E402

from design.reporting.drill.pdf import FONT, FONT_BOLD, RED, _register_fonts  # noqa: E402
from design.reporting.drill.plan_drawing import drawing  # noqa: E402


def _shapes(node, kind) -> list:
    found = []
    for item in getattr(node, "contents", ()):
        if isinstance(item, kind):
            found.append(item)
        if isinstance(item, Group):
            found += _shapes(item, kind)
    return found


def _draw(sheet):
    _register_fonts()
    return drawing(sheet, font=FONT, bold_font=FONT_BOLD)


def test_drawing_has_circle_per_hole(sheet66):
    circles = [c for c in _shapes(_draw(sheet66), Circle) if c.r == pytest.approx(MIN_HOLE_MM / 2 * MM)]
    assert len(circles) == 196
    assert len([c for c in circles if c.strokeColor == RED]) == 44


def test_drawing_size(sheet66):
    d = _draw(sheet66)
    assert (d.width, d.height) == pytest.approx((PLAN_W_MM * MM, PLAN_H_MM * MM))


def test_inclined_hole_gets_toe_line(sheet66):
    context = context66()
    row = context["holes"][0]
    row["azimuth_deg"] = 90.0
    row["toe"]["x"] = row["collar"]["x"] + 2.0
    before = len(_shapes(_draw(sheet66), PolyLine))
    assert len(_shapes(_draw(build_plan(context)), PolyLine)) == before + 1


MM = 72 / 25.4


def test_many_holes_are_fast():
    import time

    context = context66()
    rows = []
    for index in range(4000):
        row = deepcopy(context["holes"][index % 196])
        row["number"] = str(index + 1)
        row["collar"]["x"] = 1000.0 + (index % 80) * 4.0
        row["collar"]["y"] = 5000.0 + (index // 80) * 4.0
        rows.append(row)
    context["holes"] = rows
    start = time.perf_counter()
    sheet = build_plan(context)
    assert time.perf_counter() - start < 1.0
    assert len(sheet.holes) == 4000


def test_labels_fit_right_edge(sheet66):
    from design.reporting.drill.plan import LABEL_RESERVE_MM

    wide = build_plan(_grid_context(300, 20))
    for sheet in (sheet66, wide):
        assert max(hole.x for hole in sheet.holes) <= PLAN_W_MM - PLAN_PAD_MM - LABEL_RESERVE_MM + 1e-6


def test_north_arrow_is_in_legend_not_on_plan(sheet66):
    from reportlab.graphics.shapes import String

    from design.reporting.drill.plan_drawing import legend

    _register_fonts()
    assert "С" not in [s.text for s in _shapes(_draw(sheet66), String)]
    assert "С" in [s.text for s in _shapes(legend(sheet66, 180 * MM, font=FONT, bold_font=FONT_BOLD), String)]


def test_bad_points_in_snapshot_are_skipped():
    context = context66()
    context["plan"]["contour"].append(["x", "y"])
    context["plan"]["toe_source"] = ["angle"]
    sheet = build_plan(context)
    assert len(sheet.contour) == 31
    from design.reporting.drill.plan_drawing import legend

    _register_fonts()
    legend(sheet, 180 * MM, font=FONT, bold_font=FONT_BOLD)


def test_circle_uses_bit_diameter_of_passport():
    # Кружок — диаметр инструмента из паспорта, а не скважины с разбуриванием.
    context = _grid_context(4, 4)
    context["summary"]["bit_diameter_mm"] = 400.0
    for row in context["holes"]:
        row["diameter_mm"] = 600.0
    sheet = build_plan(context)
    assert sheet.scale == 200
    assert sheet.holes[0].r == pytest.approx(400.0 / 200 / 2)


def test_circle_falls_back_to_hole_diameter():
    context = _grid_context(4, 4)
    context["summary"]["bit_diameter_mm"] = None
    for row in context["holes"]:
        row["diameter_mm"] = 600.0
    assert build_plan(context).holes[0].r == pytest.approx(600.0 / 200 / 2)
