"""Расчёт паспорта на бурение `drill-v1` на выгрузке SHOTPlus блока 66 (TASK-015, PR 1)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from design.drilling_passport import (
    DRILL_FORMULA_VERSION,
    first_row_check,
    first_row_ids,
    first_row_selection,
    holes_for_passport,
    passport_context,
    resolve_inputs,
    summary,
)
from design.models import FRONT_ROW_BASE, BenchSurface, BlastDesign, BlockContour, Hole, Point3

FIXTURE = Path(__file__).parent / "fixtures" / "drill_passport" / "block66_shotplus.xlsx"
BLOCK66_AREA_M2 = 2790.0
FIRST_ROW_SUBDRILL_M = 1.5


def _block66_rows() -> list[tuple]:
    if not FIXTURE.exists():
        pytest.skip(f"Нет выгрузки SHOTPlus блока 66: {FIXTURE}")
    openpyxl = pytest.importorskip("openpyxl")
    sheet = openpyxl.load_workbook(FIXTURE, read_only=True, data_only=False).worksheets[0]
    # Над таблицей — сводка с формулами; строки скважин — с числовой глубиной.
    return [
        row[:6]
        for row in sheet.iter_rows(values_only=True)
        if row and isinstance(row[0], (int, float)) and isinstance(row[4], (int, float))
    ]


def _block66_design(*, free_faces: bool = True) -> BlastDesign:
    holes: list[Hole] = []
    for col, (hole_id, x, y, z, length, subdrill) in enumerate(_block66_rows()):
        first = math.isclose(float(subdrill), FIRST_ROW_SUBDRILL_M)
        holes.append(
            Hole(
                id=str(hole_id),
                row=0 if first else 1,
                col=col,
                collar=Point3(float(x), float(y), float(z)),
                toe=Point3(float(x), float(y), float(z) - float(length)),
                diameter_mm=115.0,
                subdrill_m=float(subdrill),
            )
        )
    xs = [hole.collar.x for hole in holes]
    ys = [hole.collar.y for hole in holes]
    vertices = [
        Point3(min(xs), min(ys), 0.0),
        Point3(max(xs), min(ys), 0.0),
        Point3(max(xs), max(ys), 0.0),
        Point3(min(xs), max(ys), 0.0),
    ]
    contour = BlockContour(vertices=vertices, free_faces=[[0, 1]] if free_faces else [], name="66")
    return BlastDesign(design_id="block-66", name="Блок 66", contour=contour, holes=holes)


@pytest.fixture(scope="module")
def block66() -> BlastDesign:
    return _block66_design()


@pytest.fixture(scope="module")
def rows66(block66):
    return holes_for_passport(block66)


def test_formula_version():
    assert DRILL_FORMULA_VERSION == "drill-v1"


def test_block66_holes_and_order(block66, rows66):
    assert len(rows66) == 196
    assert [row.number for row in rows66] == [hole.id for hole in block66.holes]
    assert math.isclose(sum(row.length_m for row in rows66), 2280.5, abs_tol=1e-6)
    assert all(row.azimuth_deg is None for row in rows66)
    assert all(row.dip_deg == pytest.approx(90.0) for row in rows66)


def test_block66_first_row_by_logical_row(block66, rows66):
    ids = first_row_ids(block66)
    assert len(ids) == 43
    assert {row.number for row in rows66 if row.first_row} == ids
    assert all(row.subdrill_m == FIRST_ROW_SUBDRILL_M for row in rows66 if row.first_row)
    _, issues = first_row_selection(block66)
    assert issues == []


def test_block66_summary(rows66):
    data = summary(rows66, BLOCK66_AREA_M2)
    assert data["hole_count"] == 196
    assert data["total_length_m"] == pytest.approx(2280.5)
    assert (data["length_min_m"], data["length_max_m"]) == pytest.approx((10.0, 13.8))
    assert data["bench_height_avg_m"] == pytest.approx(10.5255, abs=1e-4)
    assert data["block_area_m2"] == BLOCK66_AREA_M2
    assert round(data["block_volume_m3"]) == 29366
    assert round(data["yield_m3_per_m"], 2) == 12.88
    assert data["subdrill_first_row_m"] == pytest.approx(1.5)
    assert data["subdrill_other_m"] == pytest.approx(1.0)
    assert data["vertical_only"] is True


@pytest.mark.parametrize(
    ("alpha", "gamma", "prism", "s"),
    [(70.0, 55.0, 3.93, 4.0), (75.0, 65.0, 2.32, 2.4)],
)
def test_block66_crest_distance(rows66, alpha, gamma, prism, s):
    check = first_row_check(rows66, alpha, gamma, None, None, None)
    assert check.h1_m == pytest.approx(11.7)
    assert round(check.prism_m, 2) == prism
    assert check.s_m == s


def test_block66_burden_warning(rows66):
    check = first_row_check(rows66, 75.0, 65.0, 1.2, 2.0, 4.9)
    assert check.c_min_m == pytest.approx(1.2)
    assert round(check.w_m, 2) == 5.14
    codes = [issue.code for issue in check.issues]
    assert codes == ["first_row_burden"]
    assert check.issues[0].level == "warning"
    # Номер скважины первого ряда с наибольшей высотой уступа (11,7 м) — в сообщении.
    tallest = max((row for row in rows66 if row.first_row), key=lambda row: row.bench_height_m)
    assert tallest.number in check.issues[0].message


def test_too_close_and_missing_offset(rows66):
    check = first_row_check(rows66, 75.0, 65.0, 0.0, 2.0, None)
    assert check.c_min_m == pytest.approx(2.4)
    assert "first_row_too_close" in [issue.code for issue in check.issues]
    missing = first_row_check(rows66, 75.0, 65.0, None, None, None)
    assert missing.c_min_m is None
    assert "axis_offset_missing" in [issue.code for issue in missing.issues]
    assert all(issue.level == "warning" for issue in missing.issues)


@pytest.mark.parametrize(("alpha", "gamma"), [(65.0, 65.0), (60.0, 65.0), (75.0, None), (None, 65.0)])
def test_slope_angles_required(rows66, alpha, gamma):
    check = first_row_check(rows66, alpha, gamma, 1.2, None, None)
    assert check.s_m is None
    errors = [issue for issue in check.issues if issue.level == "error"]
    assert [issue.code for issue in errors] == ["slope_angles_required"]


def test_s_has_floor_of_two_metres():
    design = BlastDesign(
        design_id="low",
        contour=BlockContour(vertices=[Point3(0, 0, 0), Point3(5, 0, 0), Point3(5, 5, 0)], free_faces=[[0, 1]]),
        holes=[Hole(id="1", row=0, col=0, collar=Point3(0, 0, 10), toe=Point3(0, 0, 5), diameter_mm=115, subdrill_m=0.5)],
    )
    check = first_row_check(holes_for_passport(design), 89.0, 88.0, None, None, None)
    assert check.s_m == 2.0


def test_inclined_hole_dip_and_azimuth():
    vertical = math.sqrt(100.0 - 4.0)
    design = BlastDesign(
        design_id="tilt",
        holes=[
            Hole(id="1", row=0, col=0, collar=Point3(0, 0, 0), toe=Point3(2.0, 0, -vertical), diameter_mm=115),
            Hole(id="2", row=0, col=1, collar=Point3(5, 0, 0), toe=Point3(5, 0, -10), diameter_mm=115),
        ],
    )
    tilted, plumb = holes_for_passport(design)
    assert tilted.dip_deg == pytest.approx(78.46, abs=0.01)
    assert tilted.azimuth_deg == pytest.approx(90.0)
    assert plumb.azimuth_deg is None
    assert summary([tilted, plumb], None)["vertical_only"] is False


def test_disabled_holes_are_left_out(block66):
    design = BlastDesign.from_dict(block66.to_dict())
    design.holes[0].enabled = False
    assert len(holes_for_passport(design)) == 195


def test_front_rows_ahead_of_first_take_precedence():
    holes = [
        Hole(id="F1", row=FRONT_ROW_BASE - 1, col=0, collar=Point3(0, 0, 0), toe=Point3(0, 0, -10), diameter_mm=115),
        Hole(id="A1", row=0, col=0, collar=Point3(0, 4, 0), toe=Point3(0, 4, -10), diameter_mm=115),
        Hole(id="K1", row=-1, col=0, collar=Point3(0, -2, 0), toe=Point3(0, -2, -10), diameter_mm=115, kind="contour"),
    ]
    design = BlastDesign(
        design_id="front",
        contour=BlockContour(vertices=[Point3(0, 0, 0), Point3(5, 0, 0), Point3(5, 5, 0)], free_faces=[[0, 1]]),
        holes=holes,
    )
    assert first_row_ids(design) == {"F1"}


def test_no_free_face_falls_back_to_max_subdrill():
    design = _block66_design(free_faces=False)
    ids, issues = first_row_selection(design)
    assert len(ids) == 43
    assert [issue.code for issue in issues] == ["first_row_guessed"]


def test_resolve_inputs_sources(block66):
    site = {"bench_face_angle_deg": "75", "stable_slope_angle_deg": "65"}
    rig = {"axis_offset_m": "1.2"}
    values, provenance = resolve_inputs(block66, site, rig, {})
    assert values["alpha_deg"] == 75.0 and provenance["alpha_deg"] == "REFERENCE"
    assert values["gamma_deg"] == 65.0 and provenance["gamma_deg"] == "REFERENCE"
    assert values["axis_offset_m"] == 1.2 and provenance["axis_offset_m"] == "REFERENCE"
    assert values["w_max_m"] is None and provenance["w_max_m"] is None

    values, provenance = resolve_inputs(block66, site, rig, {"alpha_deg": 70, "gamma_deg": 55, "w_max_m": 5})
    assert (values["alpha_deg"], provenance["alpha_deg"]) == (70.0, "MANUAL_OVERRIDE")
    assert (values["gamma_deg"], provenance["gamma_deg"]) == (55.0, "MANUAL_OVERRIDE")
    assert (values["w_max_m"], provenance["w_max_m"]) == (5.0, "MANUAL_OVERRIDE")

    design = BlastDesign.from_dict(block66.to_dict())
    design.contour.bench = BenchSurface(face_angle_deg=72.0)
    values, provenance = resolve_inputs(design, site, None, {})
    assert (values["alpha_deg"], provenance["alpha_deg"]) == (72.0, "DESIGN")
    assert values["axis_offset_m"] is None and provenance["axis_offset_m"] is None


def test_resolve_inputs_area(block66):
    values, provenance = resolve_inputs(block66, None, None, {"block_area_m2": 2790})
    assert (values["block_area_m2"], provenance["block_area_m2"]) == (2790.0, "MANUAL_OVERRIDE")
    values, provenance = resolve_inputs(block66, None, None, {})
    assert provenance["block_area_m2"] == "DESIGN"
    assert values["block_area_m2"] > 0


def test_passport_context_is_deterministic(block66):
    site = {"bench_face_angle_deg": 75, "stable_slope_angle_deg": 65}
    payload = {"block_area_m2": 2790, "first_row_offset_m": 2.0, "w_max_m": 4.9}
    first = passport_context(block66, payload, site, {"axis_offset_m": 1.2})
    second = passport_context(block66, dict(payload), dict(site), {"axis_offset_m": 1.2})
    assert first == second
    assert first["formula_version"] == "drill-v1"
    assert first["first_row_check"]["s_m"] == 2.4
    assert len(first["holes"]) == 196
    assert [issue["code"] for issue in first["issues"]] == ["first_row_burden"]
    assert first["provenance"]["first_row_offset_m"] == "MANUAL_OVERRIDE"
