"""Расчёт паспорта на бурение `drill-v1` на выгрузке SHOTPlus блока 66 (TASK-015, PR 1)."""
from __future__ import annotations

import math
import json
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
# Контур для тестов: вогнутая оболочка устьев + 2 м, бровка — вдоль скважин
# с перебуром 1,5 м (первый ряд выгрузки). Шаг сетки блока 66 — 3,7 м.
CONTOUR_FIXTURE = FIXTURE.with_name("block66_contour.json")
BLOCK66_PATTERN = {"pattern": "square", "spacing_a_m": 3.7}
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
    shape = json.loads(CONTOUR_FIXTURE.read_text(encoding="utf-8"))
    contour = BlockContour(
        vertices=[Point3(x, y, 0.0) for x, y in shape["vertices"]],
        free_faces=shape["free_faces"] if free_faces else [],
        name="66",
    )
    return BlastDesign(
        design_id="block-66", name="Блок 66", contour=contour, holes=holes, pattern_params=dict(BLOCK66_PATTERN)
    )


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


def _shotplus_first_row(design: BlastDesign) -> set[str]:
    return {hole.id for hole in design.holes if math.isclose(hole.subdrill_m, FIRST_ROW_SUBDRILL_M)}


def test_block66_first_row_at_crest(block66, rows66):
    """Первый ряд — скважины у бровки (ранг 1): 43 с перебуром 1,5 м из
    выгрузки и угловая 193 на фланге, перед которой тоже нет соседей."""
    ids = first_row_ids(block66)
    assert len(_shotplus_first_row(block66)) == 43
    assert ids == _shotplus_first_row(block66) | {"193"}
    assert {row.number for row in rows66 if row.first_row} == ids
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
    # Нет e — по спеке §2.2 e = 0 (консервативно для c_min) с предупреждением; W считается.
    missing = first_row_check(rows66, 75.0, 65.0, None, None, 4.0)
    assert missing.c_min_m == pytest.approx(2.4)
    assert missing.c_m == pytest.approx(2.4)
    assert round(missing.w_m, 2) == 5.54
    codes = [issue.code for issue in missing.issues]
    assert codes == ["axis_offset_missing", "first_row_burden"]
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


def _plumb(hole_id: str, row: int, col: int, x: float, y: float, **extra) -> Hole:
    return Hole(id=hole_id, row=row, col=col, collar=Point3(x, y, 0), toe=Point3(x, y, -10), diameter_mm=115, **extra)


def test_first_row_is_whole_crest_not_only_rows_ahead():
    """Ряд впереди первого стоит лишь у одного столбца (остаток эшелона «от
    тыла», выступ контура): первый ряд паспорта — он и ряд 0 на остальной
    длине бровки; ряд 0 за ним и рядом с ним (сосед в коридоре к бровке —
    как у ЛСП), ряд 1 и стеночный ряд — нет."""
    holes = [
        _plumb("F1", FRONT_ROW_BASE - 1, 0, 0.0, 1.0),
        *[_plumb(f"A{i}", 0, i, 4.0 * i, 3.0) for i in range(5)],
        *[_plumb(f"B{i}", 1, i, 4.0 * i, 7.0) for i in range(5)],
        _plumb("K1", -1, 0, 18.0, 0.5, kind="contour"),
    ]
    design = BlastDesign(
        design_id="front",
        contour=BlockContour(
            vertices=[Point3(-2, 0, 0), Point3(20, 0, 0), Point3(20, 10, 0), Point3(-2, 10, 0)], free_faces=[[0, 1]]
        ),
        holes=holes,
        pattern_params={"pattern": "square", "spacing_a_m": 4.0},
    )
    assert first_row_ids(design) == {"F1", "A2", "A3", "A4"}


def test_first_row_on_generated_boot_contour():
    """Изогнутая бровка (PR #117): ряды впереди первого — только у кармана, а
    первый ряд паспорта идёт вдоль всей бровки — и ряд 0 тоже."""
    from design.models import logical_row
    from design.pattern import generate_pattern
    from design.geometry import distance_to_free_faces
    from tests.test_design_pattern_full_contour import BOOT, PARAMS, _contour

    contour = _contour(BOOT)
    holes = generate_pattern(contour, PARAMS)
    design = BlastDesign(design_id="boot", contour=contour, holes=holes, pattern_params=dict(PARAMS))
    ids, issues = first_row_selection(design)
    assert issues == []
    first = [hole for hole in holes if hole.id in ids]
    assert {logical_row(hole.row) < 0 for hole in first} == {True, False}
    a = float(PARAMS["spacing_a_m"])
    deepest = max(distance_to_free_faces((hole.collar.x, hole.collar.y), contour) for hole in first)
    assert deepest < float(PARAMS["offset_from_face_m"]) + a


def test_no_free_face_falls_back_to_max_subdrill():
    design = _block66_design(free_faces=False)
    ids, issues = first_row_selection(design)
    assert ids == _shotplus_first_row(design)
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

    # Угол откоса проекта (в интерфейсе по умолчанию 75°) не перекрывает объект.
    design = BlastDesign.from_dict(block66.to_dict())
    design.contour.bench = BenchSurface(face_angle_deg=72.0)
    values, provenance = resolve_inputs(design, site, None, {})
    assert (values["alpha_deg"], provenance["alpha_deg"]) == (75.0, "REFERENCE")
    assert values["axis_offset_m"] is None and provenance["axis_offset_m"] is None
    # У объекта α нет — берётся угол проекта.
    values, provenance = resolve_inputs(design, {"stable_slope_angle_deg": 55}, None, {})
    assert (values["alpha_deg"], provenance["alpha_deg"]) == (72.0, "DESIGN")


def test_alpha_mismatch_between_design_and_site(block66):
    design = BlastDesign.from_dict(block66.to_dict())
    design.contour.bench = BenchSurface(face_angle_deg=75.0)
    site = {"bench_face_angle_deg": 70, "stable_slope_angle_deg": 55}
    context = passport_context(design, {"block_area_m2": 2790, "w_max_m": 6}, site, {"axis_offset_m": 1.2})
    assert context["first_row_check"]["s_m"] == 4.0
    assert "alpha_mismatch" in [issue["code"] for issue in context["issues"]]
    same = passport_context(block66, {"block_area_m2": 2790, "w_max_m": 6}, site, {"axis_offset_m": 1.2})
    assert "alpha_mismatch" not in [issue["code"] for issue in same["issues"]]


def test_resolve_inputs_area(block66):
    values, provenance = resolve_inputs(block66, None, None, {"block_area_m2": 2790})
    assert (values["block_area_m2"], provenance["block_area_m2"]) == (2790.0, "MANUAL_OVERRIDE")
    values, provenance = resolve_inputs(block66, None, None, {})
    assert provenance["block_area_m2"] == "DESIGN"
    assert values["block_area_m2"] > 0


def test_passport_context_is_deterministic(block66):
    site = {"bench_face_angle_deg": 75, "stable_slope_angle_deg": 65}
    payload = {"block_area_m2": 2790, "first_row_offset_m": 2.0, "w_max_m": 4.9, "bit_diameter_mm": 140}
    first = passport_context(block66, payload, site, {"axis_offset_m": 1.2})
    second = passport_context(block66, dict(payload), dict(site), {"axis_offset_m": 1.2})
    assert first == second
    assert first["formula_version"] == "drill-v1"
    assert first["first_row_check"]["s_m"] == 2.4
    assert len(first["holes"]) == 196
    assert [issue["code"] for issue in first["issues"]] == ["first_row_burden"]
    assert first["provenance"]["first_row_offset_m"] == "MANUAL_OVERRIDE"


def test_axis_offset_larger_than_s_keeps_axis_behind_crest(rows66):
    """e > s: c_min = s − e ушёл бы за бровку и занизил W — берётся 0 с предупреждением."""
    check = first_row_check(rows66, 75.0, 65.0, 3.0, None, 4.0)
    assert check.s_m == 2.4
    assert check.c_min_m == 0.0
    assert check.c_m == 0.0
    assert check.w_m == pytest.approx(11.7 / math.tan(math.radians(75.0)))
    assert "axis_offset_exceeds_s" in [issue.code for issue in check.issues]


# --- Hs: высота уступа для безопасного расстояния (форма v0.7) -------------


def test_crest_distance_by_design_bench_height(rows66):
    """Утверждённый пример формы v0.7: Hs = 10,0 → Bпр 1,98, s 2,0; H₁ 11,7 > 10,5 — предупреждение."""
    check = first_row_check(rows66, 75.0, 65.0, 1.2, None, 6.0, hs_m=10.0)
    assert check.h1_m == pytest.approx(11.7)
    assert check.hs_m == 10.0
    assert check.hs_source == "MANUAL_OVERRIDE"
    assert round(check.prism_m, 2) == 1.98
    assert check.s_m == 2.0
    # W — по фактической высоте каждой скважины первого ряда, а не по Hs.
    assert check.c_min_m == pytest.approx(0.8)
    assert check.w_m == pytest.approx(11.7 / math.tan(math.radians(75.0)) + 0.8)
    warning = next(issue for issue in check.issues if issue.code == "bench_above_design")
    assert warning.level == "warning"
    tallest = max((row for row in rows66 if row.first_row), key=lambda row: row.bench_height_m)
    assert tallest.number in warning.message
    assert "11.7" in warning.message and "10.0" in warning.message
    listed = warning.message.split("(скв. ")[1].split(")")[0].split(", ")
    assert 1 <= len(listed) <= 5
    assert check.to_dict()["hs_m"] == 10.0
    assert check.to_dict()["hs_source"] == "MANUAL_OVERRIDE"


def test_hs_defaults_to_first_row_height(rows66):
    check = first_row_check(rows66, 75.0, 65.0, 1.2, None, 6.0)
    assert check.hs_m == pytest.approx(11.7)
    assert check.hs_source == "CALCULATED"
    assert check.s_m == 2.4
    assert "bench_above_design" not in [issue.code for issue in check.issues]


def test_hs_within_half_metre_is_not_warned(rows66):
    check = first_row_check(rows66, 75.0, 65.0, 1.2, None, 6.0, hs_m=11.5, hs_source="REFERENCE")
    assert check.hs_source == "REFERENCE"
    assert "bench_above_design" not in [issue.code for issue in check.issues]


def test_resolve_inputs_bench_height_for_s(block66):
    site = {"bench_face_angle_deg": 75, "stable_slope_angle_deg": 65, "design_bench_height_m": "10"}
    values, provenance = resolve_inputs(block66, site, None, {})
    assert (values["bench_height_for_s_m"], provenance["bench_height_for_s_m"]) == (10.0, "REFERENCE")
    values, provenance = resolve_inputs(block66, site, None, {"bench_height_for_s_m": 11})
    assert (values["bench_height_for_s_m"], provenance["bench_height_for_s_m"]) == (11.0, "MANUAL_OVERRIDE")
    values, provenance = resolve_inputs(block66, None, None, {})
    assert values["bench_height_for_s_m"] is None and provenance["bench_height_for_s_m"] is None


def test_passport_context_hs_from_site(block66):
    site = {"bench_face_angle_deg": 75, "stable_slope_angle_deg": 65, "design_bench_height_m": 10}
    context = passport_context(block66, {"block_area_m2": 2790, "w_max_m": 6}, site, {"axis_offset_m": 1.2})
    check = context["first_row_check"]
    assert (check["hs_m"], check["hs_source"], check["s_m"]) == (10.0, "REFERENCE", 2.0)
    assert context["inputs"]["bench_height_for_s_m"] == 10.0
    assert context["provenance"]["bench_height_for_s_m"] == "REFERENCE"
    assert "bench_above_design" in [issue["code"] for issue in context["issues"]]

    # Hs нигде не задана — берётся H₁, источник CALCULATED, без предупреждения.
    plain = passport_context(block66, {"block_area_m2": 2790, "w_max_m": 6}, {**site, "design_bench_height_m": None}, {"axis_offset_m": 1.2})
    assert plain["inputs"]["bench_height_for_s_m"] == pytest.approx(11.7)
    assert plain["provenance"]["bench_height_for_s_m"] == "CALCULATED"
    assert plain["first_row_check"]["s_m"] == 2.4
    assert "bench_above_design" not in [issue["code"] for issue in plain["issues"]]


# --- направление наклона в ЛСПП и горизонтальные скважины (ревью Codex) ----

_TAN75 = math.tan(math.radians(75.0))


def _tilted_row_design(shift_x: float, shift_y: float, *, free_faces=([0, 1],), toe_dz: float = -10.0) -> BlastDesign:
    """Ряд у прямой бровки y = 0 (откос к югу), все скважины наклонены на (shift_x, shift_y)."""
    holes = [
        Hole(
            id=f"A{i}",
            row=0,
            col=i,
            collar=Point3(4.0 * i, 3.0, 0.0),
            toe=Point3(4.0 * i + shift_x, 3.0 + shift_y, toe_dz),
            diameter_mm=115,
        )
        for i in range(5)
    ]
    return BlastDesign(
        design_id="tilted",
        contour=BlockContour(
            vertices=[Point3(-2, 0, 0), Point3(20, 0, 0), Point3(20, 10, 0), Point3(-2, 10, 0)],
            free_faces=[list(face) for face in free_faces],
        ),
        holes=holes,
        pattern_params={"pattern": "square", "spacing_a_m": 4.0},
    )


@pytest.mark.parametrize(
    ("shift", "expected_w"),
    [
        # β = 75°, H = 10: смещение подошвы по оси 10·ctg 75° = 2,68 м.
        ((0.0, -10.0 / _TAN75), 2.0),  # к откосу: W = H·(ctg α − ctg β) + c
        ((10.0 / _TAN75, 0.0), 2.0 + 10.0 / _TAN75),  # вдоль бровки: как вертикальная
        ((0.0, 10.0 / _TAN75), 2.0 + 2 * 10.0 / _TAN75),  # в массив: 7,36 м
    ],
)
def test_first_row_burden_follows_tilt_direction(shift, expected_w):
    design = _tilted_row_design(*shift)
    rows = holes_for_passport(design)
    assert {row.number for row in rows if row.first_row} == {f"A{i}" for i in range(5)}
    check = first_row_check(rows, 75.0, 65.0, None, 2.0, 4.9)
    assert check.w_m == pytest.approx(expected_w, abs=1e-6)
    over = "first_row_burden" in [issue.code for issue in check.issues]
    assert over is (expected_w > 4.9)


def test_tilt_direction_unknown_without_crest_is_warned():
    """Без бровки направление к откосу не известно: W — как при наклоне к откосу, с предупреждением."""
    design = _tilted_row_design(0.0, 10.0 / _TAN75, free_faces=())
    context = passport_context(design, {"w_max_m": 6}, {"bench_face_angle_deg": 75, "stable_slope_angle_deg": 65}, None)
    codes = [issue["code"] for issue in context["issues"]]
    assert "first_row_tilt_direction_unknown" in codes
    assert context["first_row_check"]["w_m"] == pytest.approx(context["first_row_check"]["c_m"], abs=1e-6)


def test_horizontal_hole_is_validation_error_not_crash():
    design = _tilted_row_design(5.0, 0.0, toe_dz=0.0)
    context = passport_context(design, {"w_max_m": 6}, {"bench_face_angle_deg": 75, "stable_slope_angle_deg": 65}, None)
    errors = [issue for issue in context["issues"] if issue["level"] == "error"]
    assert [issue["code"] for issue in errors] == ["hole_not_downward"]
    assert "A0" in errors[0]["message"]


# --- данные для печати (PR 2) --------------------------------------------

def test_context_carries_print_data(block66):
    ctx = passport_context(block66, {}, None, None)
    assert ctx["summary"]["grid_a_m"] == pytest.approx(3.7)
    assert ctx["summary"]["grid_b_m"] == pytest.approx(3.7)
    # Диаметр скважины (с разбуриванием, 115 мм) — не диаметр инструмента.
    assert ctx["summary"]["bit_diameter_mm"] is None
    assert "bit_diameter_missing" in [issue["code"] for issue in ctx["issues"]]
    profile = ctx["profile"]
    assert profile["code"] == ""
    assert len(profile["safety_items"]) == 10
    assert profile["safety_items"][2].startswith("Устанавливать станок не ближе безопасного расстояния")
    assert " s " not in profile["safety_items"][2]
    # П. 4 — решение владельца 10.11.2026: запрет — без достаточного освещения
    # (ФНП 505 п. 968, табл. 16: место буровых работ — не менее 10 лк).
    assert profile["safety_items"][3] == (
        "Работа на первом ряду в тёмное время суток без достаточного освещения (не менее 10 лк на высоту станка) "
        "запрещена. Находиться в призме возможного обрушения запрещено."
    )
    assert profile["safety_basis"] == "Основание: ФНП 505 пп. 968, 989–991, 993; ФНП 494 п. 187."
    assert profile["drilling_technology"].startswith("В раздробленных и обводнённых породах")


def test_payload_diameter_wins(block66):
    ctx = passport_context(block66, {"bit_diameter_mm": 140}, None, None)
    assert ctx["summary"]["bit_diameter_mm"] == 140
    assert "bit_diameter_missing" not in [issue["code"] for issue in ctx["issues"]]


def test_grid_unknown_without_pattern_steps(block66):
    design = BlastDesign.from_dict(block66.to_dict())
    design.pattern_params = {}
    ctx = passport_context(design, {}, None, None)
    assert ctx["summary"]["grid_a_m"] is None
    assert ctx["summary"]["grid_b_m"] is None


def test_profile_record_goes_to_snapshot(block66):
    record = {
        "safety_items": [{"text": "Пункт один."}, {"text": "  "}, {"text": "Пункт два."}],
        "safety_basis": "Основание: местное.",
        "drilling_technology": "",
    }
    profile = passport_context(block66, {}, None, None, profile=record, profile_code="KGOK")["profile"]
    assert profile["code"] == "KGOK"
    assert profile["safety_items"] == ["Пункт один.", "Пункт два."]
    assert profile["safety_basis"] == "Основание: местное."
    # Пустое поле профиля — текст по умолчанию, а не пустая строка в паспорте.
    assert profile["drilling_technology"].startswith("В раздробленных")


def test_grid_unknown_without_spacing_a(block66):
    design = BlastDesign.from_dict(block66.to_dict())
    design.pattern_params = {"pattern": "rectangular", "burden_b_m": 4.0}
    ctx = passport_context(design, {}, None, None)
    assert ctx["summary"]["grid_a_m"] is None
    assert ctx["summary"]["grid_b_m"] is None


# --- PR 3: геометрия плана в снимке ревизии ---------------------------------


def test_plan_geometry_block66(block66):
    from design.drilling_passport import plan_geometry

    plan = plan_geometry(block66)
    assert len(plan["contour"]) == 31
    assert plan["crest_top"] and all(len(line) >= 2 for line in plan["crest_top"])
    assert plan["crest_toe"] and all(len(line) >= 2 for line in plan["crest_toe"])
    assert plan["toe_source"] == "angle"
    assert plan["situation"] == []
    # Координаты — до миллиметра: снимок стабилен.
    assert all(round(v, 3) == v for point in plan["contour"] for v in point)


def test_plan_geometry_without_contour_or_faces():
    design = BlastDesign(design_id="x", name="x", contour=BlockContour(), holes=[])
    plan = plan_geometry_of(design)
    assert plan == {"contour": [], "crest_top": [], "crest_toe": [], "toe_source": None, "situation": []}


def plan_geometry_of(design):
    from design.drilling_passport import plan_geometry

    return plan_geometry(design)


def test_rows_carry_toe_and_diameter(rows66):
    row = rows66[0].to_dict()
    assert row["toe"]["z"] < row["collar"]["z"]
    assert row["diameter_mm"] == 115.0


def test_situation_is_clipped_around_block(block66):
    from design.drilling_passport import plan_geometry

    x, y = block66.holes[0].collar.x, block66.holes[0].collar.y
    far = {"kind": "road", "lines": [{"points": [[0, 0, 0], [1, 1, 0]], "closed": False}]}
    near = {"kind": "power_line", "lines": [{"points": [[x - 500, y, 5], [x + 500, y, 5]], "closed": False}]}
    plan = plan_geometry(block66, [far, near])
    assert [layer["kind"] for layer in plan["situation"]] == ["power_line"]
    points = [p for line in plan["situation"][0]["lines"] for p in line["points"]]
    xs = [p[0] for p in points]
    assert max(xs) - min(xs) < 600   # обрезано (запас 1,4 × 143 м), а не 1000 м
    assert all(len(p) == 2 for p in points)


def test_closed_situation_ring_stays_line(block66):
    from design.drilling_passport import plan_geometry

    x, y = block66.holes[0].collar.x, block66.holes[0].collar.y
    ring = {"kind": "building", "lines": [{
        "points": [[x - 5, y - 5], [x + 5, y - 5], [x + 5, y + 5], [x - 5, y + 5]], "closed": True,
    }]}
    (layer,) = plan_geometry(block66, [ring])["situation"]
    (line,) = layer["lines"]
    assert line["points"][0] == line["points"][-1]
    assert len(line["points"]) == 5


def test_context_has_plan(block66):
    context = passport_context(block66, {}, None, None)
    assert context["plan"]["contour"]
    assert context["plan"]["situation"] == []


def _flat_design() -> BlastDesign:
    holes = [
        Hole(id=str(i), row=0, col=i, collar=Point3(1000.0 + i * 10, 5000.0, 400.0),
             toe=Point3(1000.0 + i * 10, 5000.0, 388.0), diameter_mm=140.0)
        for i in range(41)
    ]
    return BlastDesign(design_id="flat", name="flat", contour=BlockContour(), holes=holes)


def test_situation_margin_covers_sheet_of_long_block():
    from design.drilling_passport import plan_geometry

    # Блок 400 × 0 м: лист в 1:2390 покрывает ~545 м по вертикали.
    road = {"kind": "road", "lines": [{"points": [[1200.0, 4700.0], [1200.0, 5300.0]], "closed": False}]}
    (layer,) = plan_geometry(_flat_design(), [road])["situation"]
    ys = [p[1] for p in layer["lines"][0]["points"]]
    assert min(ys) <= 4750 and max(ys) >= 5250


def test_non_finite_situation_points_are_skipped(block66):
    from design.drilling_passport import plan_geometry

    x, y = block66.holes[0].collar.x, block66.holes[0].collar.y
    bad = {"kind": "road", "lines": [
        {"points": [[float("nan"), y], [x, y]], "closed": False},
        {"points": [["x", y], [x, y]], "closed": False},
        {"points": [[x - 5, y], [x + 5, y]], "closed": False},
    ]}
    (layer,) = plan_geometry(block66, [bad])["situation"]
    assert len(layer["lines"]) == 1


def test_context_carries_coordinate_system(block66):
    assert passport_context(block66, {}, None, None)["crs"] == {"name": "local", "epsg": None, "height_system": ""}


def test_context_carries_named_coordinate_system():
    from design.spatial.coordinates import CoordinateSystem

    design = _block66_design()
    design.coordinate_system = CoordinateSystem(name="МСК-66 зона 1", epsg=None, height_system="Балтийская 1977")
    crs = passport_context(design, {}, None, None)["crs"]
    assert crs == {"name": "МСК-66 зона 1", "epsg": None, "height_system": "Балтийская 1977"}


def test_floor_horizon_from_holes(block66):
    from design.drilling_passport import floor_horizon

    # Подошва — устье минус высота уступа скважины; медиана, до 1 м.
    assert floor_horizon(block66) == "+410"


def test_drilling_days_by_norm():
    from design.drilling_passport import drilling_days

    assert drilling_days(2280.5, speed_m_per_h=25, unproductive_h=1.5, shift_hours=11) == 5
    assert drilling_days(100, speed_m_per_h=25, unproductive_h=1.5, shift_hours=11) == 1
    assert drilling_days(100, speed_m_per_h=0, unproductive_h=1.5, shift_hours=11) is None
    assert drilling_days(100, speed_m_per_h=25, unproductive_h=11, shift_hours=11) is None
