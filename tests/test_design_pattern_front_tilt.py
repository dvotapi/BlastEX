"""Плавный переход у откоса в генераторе сетки (оптимизатор, часть 3b): наклон 1–2 рядов, шаг b у подошвы."""
import math

import pytest

from design.geometry import face_azimuth_deg, local_basis, pattern_origin
from design.hole_recompute import recompute_hole
from design.models import FRONT_ROW_BASE, BenchSurface, BlastDesign, BlockContour, Point3, logical_row
from design.pattern import (
    FRONT_ROWS_TILT_DEFAULT_DEG,
    FRONT_ROWS_TILT_MAX_DEG,
    FRONT_TILT_MIN_FLOOR_BURDEN_M,
    front_row_ranks,
    generate_pattern,
    taper_tan_limit,
    tilt_floor_burden_target_m,
)
from design.toe_line import FLOOR_BURDEN_MIN_RATIO, floor_burdens, floor_point
from tests.front_rows_fixtures import (
    BASE,
    CONTOUR,
    FACE_ANGLE_DEG,
    SLANT,
    STEP,
    STEP_FACE,
    _arc_contour,
    _contour_of,
    _poly_contour,
    _rect_contour,
)


GRID_KINDS = ("production",)


def _r(value: float) -> float:
    value = round(value, 3)
    return 0.0 if value == 0 else value


def holes_signature(holes):
    return tuple(
        (h.id, h.row, _r(h.collar.x), _r(h.collar.y), _r(h.collar.z), _r(h.toe.x), _r(h.toe.y), _r(h.toe.z))
        for h in holes
    )


def rows(holes, kinds=GRID_KINDS):
    """Скважины основной сетки по логическим рядам, от откоса вглубь."""
    grouped: dict[int, list] = {}
    for hole in holes:
        if hole.kind in kinds:
            grouped.setdefault(logical_row(hole.row), []).append(hole)
    return [grouped[key] for key in sorted(grouped)]


# Снят на ветке до изменения generate_pattern (коммит d9f57fa): без новых
# ключей сетка обязана совпадать побитно — хэш утверждённых паспортов.
REFERENCE_SIGNATURE = (
    ('9-01', 0, 0.0, 2.0, 0.0, 0.0, 2.0, -11.0),
    ('9-02', 0, 4.0, 2.0, 0.0, 4.0, 2.0, -11.0),
    ('9-03', 0, 8.0, 2.0, 0.0, 8.0, 2.0, -11.0),
    ('9-04', 0, 12.0, 2.0, 0.0, 12.0, 2.0, -11.0),
    ('9-05', 0, 16.0, 2.0, 0.0, 16.0, 2.0, -11.0),
    ('9-06', 0, 20.0, 2.0, 0.0, 20.0, 2.0, -11.0),
    ('9-07', 0, 24.0, 2.0, 0.0, 24.0, 2.0, -11.0),
    ('9-08', 0, 28.0, 2.0, 0.0, 28.0, 2.0, -11.0),
    ('9-09', 0, 32.0, 2.0, 0.0, 32.0, 2.0, -11.0),
    ('9-10', 0, 36.0, 2.0, 0.0, 36.0, 2.0, -11.0),
    ('9-11', 0, 40.0, 2.0, 0.0, 40.0, 2.0, -11.0),
    ('8-01', 1, 0.0, 5.5, 0.0, 0.0, 5.5, -11.0),
    ('8-02', 1, 4.0, 5.5, 0.0, 4.0, 5.5, -11.0),
    ('8-03', 1, 8.0, 5.5, 0.0, 8.0, 5.5, -11.0),
    ('8-04', 1, 12.0, 5.5, 0.0, 12.0, 5.5, -11.0),
    ('8-05', 1, 16.0, 5.5, 0.0, 16.0, 5.5, -11.0),
    ('8-06', 1, 20.0, 5.5, 0.0, 20.0, 5.5, -11.0),
    ('8-07', 1, 24.0, 5.5, 0.0, 24.0, 5.5, -11.0),
    ('8-08', 1, 28.0, 5.5, 0.0, 28.0, 5.5, -11.0),
    ('8-09', 1, 32.0, 5.5, 0.0, 32.0, 5.5, -11.0),
    ('8-10', 1, 36.0, 5.5, 0.0, 36.0, 5.5, -11.0),
    ('8-11', 1, 40.0, 5.5, 0.0, 40.0, 5.5, -11.0),
    ('7-01', 2, 0.0, 9.0, 0.0, 0.0, 9.0, -11.0),
    ('7-02', 2, 4.0, 9.0, 0.0, 4.0, 9.0, -11.0),
    ('7-03', 2, 8.0, 9.0, 0.0, 8.0, 9.0, -11.0),
    ('7-04', 2, 12.0, 9.0, 0.0, 12.0, 9.0, -11.0),
    ('7-05', 2, 16.0, 9.0, 0.0, 16.0, 9.0, -11.0),
    ('7-06', 2, 20.0, 9.0, 0.0, 20.0, 9.0, -11.0),
    ('7-07', 2, 24.0, 9.0, 0.0, 24.0, 9.0, -11.0),
    ('7-08', 2, 28.0, 9.0, 0.0, 28.0, 9.0, -11.0),
    ('7-09', 2, 32.0, 9.0, 0.0, 32.0, 9.0, -11.0),
    ('7-10', 2, 36.0, 9.0, 0.0, 36.0, 9.0, -11.0),
    ('7-11', 2, 40.0, 9.0, 0.0, 40.0, 9.0, -11.0),
    ('6-01', 3, 0.0, 12.5, 0.0, 0.0, 12.5, -11.0),
    ('6-02', 3, 4.0, 12.5, 0.0, 4.0, 12.5, -11.0),
    ('6-03', 3, 8.0, 12.5, 0.0, 8.0, 12.5, -11.0),
    ('6-04', 3, 12.0, 12.5, 0.0, 12.0, 12.5, -11.0),
    ('6-05', 3, 16.0, 12.5, 0.0, 16.0, 12.5, -11.0),
    ('6-06', 3, 20.0, 12.5, 0.0, 20.0, 12.5, -11.0),
    ('6-07', 3, 24.0, 12.5, 0.0, 24.0, 12.5, -11.0),
    ('6-08', 3, 28.0, 12.5, 0.0, 28.0, 12.5, -11.0),
    ('6-09', 3, 32.0, 12.5, 0.0, 32.0, 12.5, -11.0),
    ('6-10', 3, 36.0, 12.5, 0.0, 36.0, 12.5, -11.0),
    ('6-11', 3, 40.0, 12.5, 0.0, 40.0, 12.5, -11.0),
    ('5-01', 4, 0.0, 16.0, 0.0, 0.0, 16.0, -11.0),
    ('5-02', 4, 4.0, 16.0, 0.0, 4.0, 16.0, -11.0),
    ('5-03', 4, 8.0, 16.0, 0.0, 8.0, 16.0, -11.0),
    ('5-04', 4, 12.0, 16.0, 0.0, 12.0, 16.0, -11.0),
    ('5-05', 4, 16.0, 16.0, 0.0, 16.0, 16.0, -11.0),
    ('5-06', 4, 20.0, 16.0, 0.0, 20.0, 16.0, -11.0),
    ('5-07', 4, 24.0, 16.0, 0.0, 24.0, 16.0, -11.0),
    ('5-08', 4, 28.0, 16.0, 0.0, 28.0, 16.0, -11.0),
    ('5-09', 4, 32.0, 16.0, 0.0, 32.0, 16.0, -11.0),
    ('5-10', 4, 36.0, 16.0, 0.0, 36.0, 16.0, -11.0),
    ('5-11', 4, 40.0, 16.0, 0.0, 40.0, 16.0, -11.0),
    ('4-01', 5, 0.0, 19.5, 0.0, 0.0, 19.5, -11.0),
    ('4-02', 5, 4.0, 19.5, 0.0, 4.0, 19.5, -11.0),
    ('4-03', 5, 8.0, 19.5, 0.0, 8.0, 19.5, -11.0),
    ('4-04', 5, 12.0, 19.5, 0.0, 12.0, 19.5, -11.0),
    ('4-05', 5, 16.0, 19.5, 0.0, 16.0, 19.5, -11.0),
    ('4-06', 5, 20.0, 19.5, 0.0, 20.0, 19.5, -11.0),
    ('4-07', 5, 24.0, 19.5, 0.0, 24.0, 19.5, -11.0),
    ('4-08', 5, 28.0, 19.5, 0.0, 28.0, 19.5, -11.0),
    ('4-09', 5, 32.0, 19.5, 0.0, 32.0, 19.5, -11.0),
    ('4-10', 5, 36.0, 19.5, 0.0, 36.0, 19.5, -11.0),
    ('4-11', 5, 40.0, 19.5, 0.0, 40.0, 19.5, -11.0),
    ('3-01', 6, 0.0, 23.0, 0.0, 0.0, 23.0, -11.0),
    ('3-02', 6, 4.0, 23.0, 0.0, 4.0, 23.0, -11.0),
    ('3-03', 6, 8.0, 23.0, 0.0, 8.0, 23.0, -11.0),
    ('3-04', 6, 12.0, 23.0, 0.0, 12.0, 23.0, -11.0),
    ('3-05', 6, 16.0, 23.0, 0.0, 16.0, 23.0, -11.0),
    ('3-06', 6, 20.0, 23.0, 0.0, 20.0, 23.0, -11.0),
    ('3-07', 6, 24.0, 23.0, 0.0, 24.0, 23.0, -11.0),
    ('3-08', 6, 28.0, 23.0, 0.0, 28.0, 23.0, -11.0),
    ('3-09', 6, 32.0, 23.0, 0.0, 32.0, 23.0, -11.0),
    ('3-10', 6, 36.0, 23.0, 0.0, 36.0, 23.0, -11.0),
    ('3-11', 6, 40.0, 23.0, 0.0, 40.0, 23.0, -11.0),
    ('2-01', 7, 0.0, 26.5, 0.0, 0.0, 26.5, -11.0),
    ('2-02', 7, 4.0, 26.5, 0.0, 4.0, 26.5, -11.0),
    ('2-03', 7, 8.0, 26.5, 0.0, 8.0, 26.5, -11.0),
    ('2-04', 7, 12.0, 26.5, 0.0, 12.0, 26.5, -11.0),
    ('2-05', 7, 16.0, 26.5, 0.0, 16.0, 26.5, -11.0),
    ('2-06', 7, 20.0, 26.5, 0.0, 20.0, 26.5, -11.0),
    ('2-07', 7, 24.0, 26.5, 0.0, 24.0, 26.5, -11.0),
    ('2-08', 7, 28.0, 26.5, 0.0, 28.0, 26.5, -11.0),
    ('2-09', 7, 32.0, 26.5, 0.0, 32.0, 26.5, -11.0),
    ('2-10', 7, 36.0, 26.5, 0.0, 36.0, 26.5, -11.0),
    ('2-11', 7, 40.0, 26.5, 0.0, 40.0, 26.5, -11.0),
    ('1-01', 8, 0.0, 30.0, 0.0, 0.0, 30.0, -11.0),
    ('1-02', 8, 4.0, 30.0, 0.0, 4.0, 30.0, -11.0),
    ('1-03', 8, 8.0, 30.0, 0.0, 8.0, 30.0, -11.0),
    ('1-04', 8, 12.0, 30.0, 0.0, 12.0, 30.0, -11.0),
    ('1-05', 8, 16.0, 30.0, 0.0, 16.0, 30.0, -11.0),
    ('1-06', 8, 20.0, 30.0, 0.0, 20.0, 30.0, -11.0),
    ('1-07', 8, 24.0, 30.0, 0.0, 24.0, 30.0, -11.0),
    ('1-08', 8, 28.0, 30.0, 0.0, 28.0, 30.0, -11.0),
    ('1-09', 8, 32.0, 30.0, 0.0, 32.0, 30.0, -11.0),
    ('1-10', 8, 36.0, 30.0, 0.0, 36.0, 30.0, -11.0),
    ('1-11', 8, 40.0, 30.0, 0.0, 40.0, 30.0, -11.0),
)


def test_constants():
    assert FRONT_ROWS_TILT_MAX_DEG == 30.0
    assert FRONT_ROWS_TILT_DEFAULT_DEG == 15.0


def test_without_keys_pattern_is_unchanged():
    plain = generate_pattern(CONTOUR, BASE)
    assert holes_signature(plain) == REFERENCE_SIGNATURE
    assert holes_signature(plain) == holes_signature(
        generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 0})
    )
    assert holes_signature(plain) == holes_signature(
        generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 0, "front_rows_tilt_deg": 20})
    )
    assert all(h.angle_deg == pytest.approx(0.0) for h in plain)


H = 10.0
TAN15 = math.tan(math.radians(15.0))
TAN7_5 = math.tan(math.radians(7.5))
# Предел угла по зазору устьев (MIN_COLLAR_ROW_GAP_M = 1 м) при b = 3,5,
# H = 10: один ряд перехода — H·tg α₁ ≤ b − 1 → α₁ = atan(0,25) ≈ 14,04°;
# два ряда при α = 30° — H·(tg α₁ − tg(α₁/2)) ≤ 2,5 → α₁ ≈ 25,44°; при
# α = 15° предел не срабатывает (1,36 и 1,32 м ≤ 2,5 м).
ONE_ROW_DEG = math.degrees(math.atan(0.25))
TWO_ROWS_30_DEG = math.degrees(math.atan(taper_tan_limit(2, 3.5, 10.0)))


def test_taper_tan_limit_is_zero_when_burden_leaves_no_collar_gap():
    assert taper_tan_limit(1, 1.0, 10.0) == 0.0
    assert taper_tan_limit(2, 1.0, 10.0) == 0.0
    assert taper_tan_limit(2, 0.8, 10.0) == 0.0


def _column_x(holes):
    return sorted(round(h.collar.x, 6) for h in holes)


def test_first_row_tilted_toward_face():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 1})
    grid = rows(holes)
    first, second = grid[0], grid[1]
    assert first and second
    assert all(h.angle_deg == pytest.approx(ONE_ROW_DEG) for h in first)
    # Азимут — вдоль линии столбца к откосу.
    assert all(h.azimuth_deg == pytest.approx(180.0) for h in first)
    assert all(h.angle_deg == pytest.approx(0.0) for h in second)
    plain = rows(generate_pattern(CONTOUR, BASE))
    # Устья ряда 1 на месте; ряда 2 и дальше — сдвинуты к откосу на H·tg α₁ = 2,5 м
    # (зазор устьев 1→2 — ровно 1 м),
    # вдоль ряда не смещаются; номера те же.
    assert [(h.id, h.collar) for h in first] == [(h.id, h.collar) for h in plain[0]]
    for tilted_row, plain_row in zip(grid[1:], plain[1:]):
        assert [h.id for h in tilted_row] == [h.id for h in plain_row]
        for tilted, vertical in zip(tilted_row, plain_row):
            assert tilted.collar.x == pytest.approx(vertical.collar.x, abs=1e-9)
            assert vertical.collar.y - tilted.collar.y == pytest.approx(2.5, abs=1e-6)
    # Шаг b — у подошвы.
    for a, b in zip(first, second):
        assert floor_point(b)[1] - floor_point(a)[1] == pytest.approx(3.5, abs=0.01)


def test_taper_two_rows_keeps_burden_at_floor():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 15})
    first, second, third = rows(holes)[:3]
    assert all(h.angle_deg == pytest.approx(15.0) for h in first)
    assert all(h.angle_deg == pytest.approx(7.5) and h.azimuth_deg == pytest.approx(180.0) for h in second)
    assert all(h.angle_deg == pytest.approx(0.0) for h in third)
    assert _column_x(first) == _column_x(second) == _column_x(third)
    for a, b, c in zip(first, second, third):
        assert a.collar.x == pytest.approx(b.collar.x) and b.collar.x == pytest.approx(c.collar.x)
        assert floor_point(b)[1] - floor_point(a)[1] == pytest.approx(3.5, abs=0.01)
        assert floor_point(c)[1] - floor_point(b)[1] == pytest.approx(3.5, abs=0.01)
        assert b.collar.y - a.collar.y == pytest.approx(3.5 - H * (TAN15 - TAN7_5), abs=1e-6)
        assert c.collar.y - b.collar.y == pytest.approx(3.5 - H * TAN7_5, abs=1e-6)


def test_mode_key():
    plain = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2})
    taper = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2, "front_rows_mode": "taper"})
    assert holes_signature(plain) == holes_signature(taper)
    assert any(h.angle_deg > 1.0 for h in plain)
    # Неизвестная схема — сетка без изменений.
    unknown = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2, "front_rows_mode": "что-то"})
    assert holes_signature(unknown) == REFERENCE_SIGNATURE


def _axes(contour, row_azimuth_deg):
    """Ось ряда и направление продвижения вглубь блока (как у генератора)."""
    row_dir, advance = local_basis(row_azimuth_deg)
    return row_dir, pattern_origin(contour, row_dir, advance)[1]


def _columns(holes, contour, row_azimuth_deg, tolerance=1.0):
    """Столбцы сетки по проекции устья на ось ряда; внутри — от откоса по точке на подошве."""
    row_dir, advance = _axes(contour, row_azimuth_deg)
    across = lambda h: h.collar.x * row_dir[0] + h.collar.y * row_dir[1]  # noqa: E731
    depth = lambda h: floor_point(h)[0] * advance[0] + floor_point(h)[1] * advance[1]  # noqa: E731
    columns: list[list] = []
    for hole in sorted((h for h in holes if h.kind == "production"), key=across):
        if columns and across(hole) - across(columns[-1][-1]) <= tolerance:
            columns[-1].append(hole)
        else:
            columns.append([hole])
    return [sorted(column, key=depth) for column in columns], across, depth


def _floor_gaps(holes, contour, row_azimuth_deg):
    """Расстояния у подошвы между соседями столбца."""
    columns, _, depth = _columns(holes, contour, row_azimuth_deg)
    return [depth(b) - depth(a) for column in columns for a, b in zip(column, column[1:])]


def test_slanted_crest_one_angle_per_row_segment():
    contour = _contour_of(SLANT, ((0, 1),), face_angle_deg=75.0)
    params = BASE | {"offset_from_face_m": 4.0, "front_rows_tilt_count": 2, "front_rows_tilt_deg": 30}
    plain = [h for h in generate_pattern(contour, params | {"front_rows_tilt_count": 0}) if h.kind == "production"]
    holes = [h for h in generate_pattern(contour, params) if h.kind == "production"]
    first = [h for h in holes if h.row == 0]
    assert first and all(abs(h.collar.y - 6.0) < 1e-9 for h in first)
    angles = [h.angle_deg for h in first]
    # Один угол на участок — наименьший из допустимых: у ближней к откосу
    # скважины ЛСП ровно цель, у остальных запас разный.
    assert max(angles) - min(angles) < 1e-6 and 5.0 < angles[0] < 29.0
    target = tilt_floor_burden_target_m(params)
    burdens = floor_burdens(BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params))
    values = [burdens[h.id].value_m for h in first]
    assert min(values) == pytest.approx(target, abs=1e-2)
    assert max(values) - min(values) > 3.0
    assert not any(burdens[h.id].beyond_toe for h in first)
    # Ряд 2 — α₁/2, у подошвы — шаг b, столбцы на месте.
    assert all(h.angle_deg == pytest.approx(angles[0] / 2.0) for h in holes if h.row == 1)
    assert all(gap == pytest.approx(3.5, abs=0.01) for gap in _floor_gaps(holes, contour, 90.0))
    assert {round(h.collar.x, 6) for h in holes} == {round(h.collar.x, 6) for h in plain}


@pytest.mark.parametrize("count, deg", [(1, 15.0), (2, 15.0), (2, 30.0)])
def test_stepped_crest_rotated_rows_keep_burden_at_floor(count, deg):
    # Ряды под 80°: столбцы косые к ступени бровки; у подошвы в каждом
    # столбце — шаг b, устья столбца — на линии сетки.
    contour = _contour_of(STEP, STEP_FACE)
    params = BASE | {"row_azimuth_deg": 80.0, "front_rows_tilt_count": count, "front_rows_tilt_deg": deg}
    holes = generate_pattern(contour, params)
    plain = generate_pattern(contour, params | {"front_rows_tilt_count": 0})
    gaps = _floor_gaps(holes, contour, 80.0)
    assert gaps and all(gap == pytest.approx(3.5, abs=0.01) for gap in gaps)
    _, across, _ = _columns(plain, contour, 80.0)
    lines = sorted(across(h) for h in plain if h.kind == "production")
    for hole in holes:
        if hole.kind == "production":
            assert min(abs(across(hole) - x) for x in lines) < 1e-3
    assert any(h.angle_deg > 1.0 for h in holes)


def test_curved_crest_keeps_burden_at_floor():
    # Бровка — дуга, откос 70°, два ряда перехода, 30°.
    arc = [(-20.0, 25.0)] + [
        (20.0 * math.cos(math.pi * (1 + i / 12)), -20.0 + 20.0 * math.sin(math.pi * (1 + i / 12))) for i in range(13)
    ] + [(20.0, 25.0)]
    contour = _contour_of(arc, (tuple(range(1, 14)),), face_angle_deg=70.0)
    holes = generate_pattern(contour, BASE | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 30})
    gaps = _floor_gaps(holes, contour, 90.0)
    assert gaps and min(gaps) >= 3.5 * 0.97
    assert any(h.angle_deg > 1.0 for h in holes)


@pytest.mark.parametrize(
    "keys",
    [
        {"front_rows_tilt_count": 1},
        {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 30},
        {"front_rows_mode": "taper", "front_rows_tilt_count": 2, "min_crest_offset_m": 3},
    ],
)
def test_staggered_grid_ignores_taper(keys):
    # Шахматка в оптимизатор не входит: плавный переход на ней не применяется —
    # сетка побитно как без ключей.
    params = BASE | {"pattern": "staggered", "offset_from_face_m": 0.5}
    assert holes_signature(generate_pattern(CONTOUR, params | keys)) == holes_signature(generate_pattern(CONTOUR, params))


def test_staggered_grid_keeps_pair_mode():
    params = BASE | {"pattern": "staggered", "front_rows_mode": "pair", "offset_from_face_m": 3.5}
    assert any(h.kind == "face_toe" for h in generate_pattern(CONTOUR, params))


def test_row_segments_get_their_own_angles():
    # Ступень бровки, откос 70°: у рядов 1 на левом и правом участке разная
    # ЛСП — разный угол, но один на участок.
    contour = _contour_of(STEP, STEP_FACE, face_angle_deg=70.0)
    holes = generate_pattern(contour, BASE | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 30})
    left = [h for h in holes if h.kind == "production" and logical_row(h.row) == logical_row(FRONT_ROW_BASE - 1)]
    right = [h for h in holes if h.kind == "production" and h.row == 1 and h.collar.x > 22.0]
    assert left and right
    for part in (left, right):
        assert max(h.angle_deg for h in part) - min(h.angle_deg for h in part) < 1e-6
    assert left[0].angle_deg > 1.0 and right[0].angle_deg > 1.0
    assert abs(left[0].angle_deg - right[0].angle_deg) > 1.0
    assert all(gap == pytest.approx(3.5, abs=0.01) for gap in _floor_gaps(holes, contour, 90.0))


def test_steep_single_row_keeps_one_metre_between_collars():
    # Один ряд перехода, α = 30°: без предела ряд 2 сдвинулся бы на 5,77 м —
    # впереди ряда 1. Предел: H·tg α₁ ≤ b − 1 → α₁ = atan(0,25), зазор 1 м.
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 1, "front_rows_tilt_deg": 30})
    first, second = rows(holes)[:2]
    assert len(second) == len(first) == 11
    assert all(h.angle_deg == pytest.approx(ONE_ROW_DEG) for h in first)
    for a, b in zip(first, second):
        assert b.collar.y - a.collar.y == pytest.approx(1.0, abs=0.01)
        assert floor_point(b)[1] - floor_point(a)[1] == pytest.approx(3.5, abs=0.01)


@pytest.mark.parametrize("shape", [_arc_contour, _poly_contour])
@pytest.mark.parametrize("face_angle", [45.0, 70.0])
@pytest.mark.parametrize("count", [1, 2])
def test_collars_in_column_stay_one_metre_apart(shape, face_angle, count):
    contour = shape(face_angle)
    params = BASE | {"front_rows_tilt_count": count, "front_rows_tilt_deg": 30}
    holes = generate_pattern(contour, params)
    columns, _, _ = _columns(holes, contour, 90.0)
    distances = [
        math.hypot(b.collar.x - a.collar.x, b.collar.y - a.collar.y)
        for column in columns
        for a, b in zip(column, column[1:])
    ]
    assert distances and min(distances) >= 1.0 - 0.01
    # Ряд 2 не теряется: скважин сетки не меньше, чем без наклона.
    plain = generate_pattern(contour, BASE)
    assert len([h for h in holes if h.kind == "production"]) >= len([h for h in plain if h.kind == "production"])


def test_back_of_block_is_filled_after_shift():
    # 30° (предел — 25,44°): ряды за наклонными сдвинуты к откосу на 4,76 м — у тыла добавлены
    # ряды решётки, и полоса без скважин не шире остатка шага сетки.
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 30})
    production = [h for h in holes if h.kind == "production"]
    shift = H * math.tan(math.radians(TWO_ROWS_30_DEG))
    back = max(h.collar.y for h in production)
    assert 30.0 - back == pytest.approx((30.0 - 2.0 + shift) % 3.5, abs=1e-6)
    assert 30.0 - back < 3.5
    assert all(-1e-6 <= h.collar.x <= 40.0 + 1e-6 and -1e-6 <= h.collar.y <= 30.0 + 1e-6 for h in production)
    assert len(production) > len([h for h in generate_pattern(CONTOUR, BASE) if h.kind == "production"])
    assert len({h.id for h in holes}) == len(holes)


def test_two_rows_tilted_with_custom_angle_and_clamp():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 45})
    grid = rows(holes)
    assert all(h.angle_deg == pytest.approx(TWO_ROWS_30_DEG) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(TWO_ROWS_30_DEG / 2.0) for h in grid[1])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[2])


def test_negative_angle_is_clamped_to_zero():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": -10})
    assert all(h.angle_deg == pytest.approx(0.0) for h in holes)


def test_count_is_clamped():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 5})
    grid = rows(holes)
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(7.5) for h in grid[1])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[2])


@pytest.mark.parametrize("count", [float("inf"), float("-inf"), float("nan"), "много"])
def test_count_not_a_number_means_no_tilt(count):
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": count})
    assert holes_signature(holes) == REFERENCE_SIGNATURE
    assert all(h.angle_deg == pytest.approx(0.0) for h in holes)


def test_tilt_moves_floor_point_toward_face():
    vertical = rows(generate_pattern(CONTOUR, BASE))[0][0]
    tilted = rows(generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 1}))[0][0]
    shift = floor_point(vertical)[1] - floor_point(tilted)[1]
    assert shift == pytest.approx(2.5, abs=1e-6)  # H = 10 м
    # Длина — та же формула L = H / cos α + Δ.
    assert tilted.length_m == pytest.approx(10.0 / math.cos(math.radians(ONE_ROW_DEG)) + 1.0, abs=1e-6)


def test_face_following_row_is_row_one():
    params = BASE | {"first_row_follow_face": True}
    holes = generate_pattern(CONTOUR, params | {"front_rows_tilt_count": 1})
    grid = rows(holes)
    face_row = [h for h in holes if h.kind == "production" and h.row == 0]
    assert face_row and grid[0] == face_row
    assert all(h.angle_deg == pytest.approx(ONE_ROW_DEG) for h in grid[0])
    assert all(h.azimuth_deg == pytest.approx(180.0) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[1])

    holes = generate_pattern(CONTOUR, params | {"front_rows_tilt_count": 2})
    grid = rows(holes)
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(7.5) for h in grid[1])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[2])


def _by_row(holes):
    grouped: dict[int, dict[float, object]] = {}
    for hole in holes:
        if hole.kind == "production":
            grouped.setdefault(logical_row(hole.row), {})[round(hole.collar.x, 1)] = hole
    return [grouped[key] for key in sorted(grouped)]


def test_stepped_crest_tilts_row_facing_retreated_face():
    # Ранг местный: на отступившем участке (x ≥ 24) у откоса стоит третий ряд
    # решётки — он ряд 1 у откоса и наклоняется, хотя впереди него на левом
    # участке ещё два ряда.
    contour = _contour_of(STEP, STEP_FACE)
    front, first, third, fourth = _by_row(generate_pattern(contour, BASE | {"front_rows_tilt_count": 1}))[:4]
    assert all(h.angle_deg == pytest.approx(ONE_ROW_DEG) and h.azimuth_deg == pytest.approx(180.0) for h in front.values())
    for x in (24.0, 28.0, 32.0, 36.0, 40.0):
        assert third[x].angle_deg == pytest.approx(ONE_ROW_DEG)
        assert third[x].azimuth_deg == pytest.approx(180.0)
        assert fourth[x].angle_deg == pytest.approx(0.0)
    # Левый участок: за рядом впереди первого ряда решётки — без наклона.
    for x in (0.0, 4.0, 8.0, 12.0):
        assert first[x].angle_deg == pytest.approx(0.0)
        assert third[x].angle_deg == pytest.approx(0.0)

    # Два ряда: следующий за рядом 1 — α/2, и слева, и на отступившем участке.
    front, first, third, fourth = _by_row(generate_pattern(contour, BASE | {"front_rows_tilt_count": 2}))[:4]
    for x in (0.0, 4.0, 8.0, 12.0):
        assert first[x].angle_deg == pytest.approx(7.5)
        assert third[x].angle_deg == pytest.approx(0.0)
    for x in (24.0, 28.0, 32.0, 36.0, 40.0):
        assert fourth[x].angle_deg == pytest.approx(7.5)


def test_ranks_follow_corridor_not_lattice_row():
    contour = _contour_of(STEP, STEP_FACE)
    collars = [(10.0, 2.0), (10.0, 5.5), (10.0, 9.0), (30.0, 10.0), (30.0, 13.5), (30.0, 17.0)]
    assert front_row_ranks(collars, contour, 4.0, 3.5) == [1, 2, 3, 1, 2, 3]
    # Ряд вдоль бровки — ряд 1 всегда, даже если впереди что-то стоит.
    assert front_row_ranks(collars[1:2] + collars[:1], contour, 4.0, 3.5, forced_first=1) == [1, 1]


def test_boot_crest_tilts_holes_at_each_part_of_face():
    # «Сапог» (tests/test_design_pattern_full_contour.py): ряды решётки идут
    # поперёк полосы, вдоль полосы у откоса стоит четвёртый ряд решётки —
    # он ряд 1 у откоса и наклоняется к полосе (азимут 90°).
    from tests.test_design_pattern_full_contour import BOOT, BOOT_FACE, PARAMS

    contour = _contour_of(BOOT, BOOT_FACE)
    holes = generate_pattern(contour, PARAMS | {"front_rows_tilt_count": 1})
    strip = [h for h in holes if h.kind == "production" and h.row == 3 and h.collar.y >= 40.0]
    behind = [h for h in holes if h.kind == "production" and h.row == 4 and h.collar.y >= 40.0]
    assert strip and behind
    for hole in strip:
        assert hole.angle_deg == pytest.approx(15.0)
        assert hole.azimuth_deg == pytest.approx(90.0)
    assert all(h.angle_deg == pytest.approx(0.0) for h in behind)
    # Наклонены только первые от откоса скважины своих столбцов (ряды по Y,
    # столбцы по X, откос — к востоку), азимут — вдоль столбца; столбцы не
    # смещаются вдоль ряда.
    plain = [h for h in generate_pattern(contour, PARAMS) if h.kind == "production"]
    ys = {round(h.collar.y, 6) for h in plain}
    for hole in holes:
        if hole.kind != "production":
            continue
        assert round(hole.collar.y, 6) in ys
        if hole.angle_deg > 1.0:
            assert hole.azimuth_deg == pytest.approx(90.0)
            ahead = [h for h in plain if abs(h.collar.y - hole.collar.y) < 1e-6 and h.collar.x > hole.collar.x + 0.1]
            assert not ahead


def test_face_following_row_is_rank_one_on_boot():
    from tests.test_design_pattern_full_contour import BOOT, BOOT_FACE, PARAMS

    contour = _contour_of(BOOT, BOOT_FACE)
    params = PARAMS | {"first_row_follow_face": True, "front_rows_tilt_count": 1}
    holes = generate_pattern(contour, params)
    face = [h for h in holes if h.kind == "production" and h.row == 0]
    assert face
    # Ряд вдоль бровки — ранг 1 весь; наклон — вдоль линии столбца. Участки,
    # где решётка за рядом ближе b − 1 м к нему по столбцу (угол бровки),
    # остаются вертикальными: зазор устьев не меньше 1 м.
    tilted = [h for h in face if h.angle_deg > 1.0]
    assert tilted and len({round(h.angle_deg, 6) for h in tilted}) <= 2
    for hole in tilted:
        assert hole.azimuth_deg == pytest.approx(90.0)


def test_bent_face_tilts_along_columns():
    # Откос с изгибом (запад и юг): азимут — вдоль линии столбца, а не к
    # ближайшему участку бровки; столбцы не смещаются вдоль ряда.
    contour = _rect_contour(40.0, 30.0, free_faces=((3, 0, 1),))
    holes = generate_pattern(contour, BASE | {"front_rows_tilt_count": 1})
    plain = generate_pattern(contour, BASE)
    first = rows(holes)[0]
    assert first and all(h.angle_deg > 1.0 and h.azimuth_deg == pytest.approx(180.0) for h in first)
    assert {
        face_azimuth_deg((h.collar.x, h.collar.y), contour) for h in first
    } != {180.0}
    # Столбец на западной бровке (x = 0) — ближе 1 м к кромке: при заданной
    # схеме первого ряда генератор его не ставит; остальные столбцы — на своих x.
    assert not any(h.collar.x < 1.0 for h in holes)
    far = [h for h in plain if h.collar.x >= 1.0]
    assert len(holes) == len(far)
    for tilted, vertical in zip(holes, far):
        assert tilted.collar.x == pytest.approx(vertical.collar.x, abs=1e-9)


def test_no_free_faces_means_no_tilt():
    contour = _rect_contour(40.0, 30.0, free_faces=())
    plain = generate_pattern(contour, BASE)
    tilted = generate_pattern(contour, BASE | {"front_rows_tilt_count": 2})
    assert holes_signature(plain) == holes_signature(tilted)


def test_common_angle_kept_for_rows_behind():
    holes = generate_pattern(
        CONTOUR, BASE | {"angle_deg": 5.0, "azimuth_deg": 0.0, "front_rows_tilt_count": 1}
    )
    grid = rows(holes)
    assert all(h.angle_deg == pytest.approx(ONE_ROW_DEG) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(5.0) and h.azimuth_deg == pytest.approx(0.0) for h in grid[1])


def test_variable_and_domain_rows_are_tilted():
    from design.models import BlastDomain

    variable = generate_pattern(
        CONTOUR,
        BASE | {
            "pattern": "variable",
            "row_params": [{"spacing_a_m": 4.0, "burden_b_m": 3.0}, {"spacing_a_m": 4.0, "burden_b_m": 4.0}],
            "front_rows_tilt_count": 1,
        },
    )
    grid = rows(variable)
    # Шаг рядов у устьев 3 м: предел H·tg α₁ ≤ 3 − 1 → atan(0,2) ≈ 11,31°.
    assert all(h.angle_deg == pytest.approx(math.degrees(math.atan(0.2))) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[1])

    domain = BlastDomain.from_dict(
        {
            "id": "d1",
            "name": "Д1",
            "polygon": [{"x": 0, "y": 0}, {"x": 40, "y": 0}, {"x": 40, "y": 30}, {"x": 0, "y": 30}],
            "spacing_a_m": 5.0,
            "burden_b_m": 4.0,
        }
    )
    walked = generate_pattern(
        CONTOUR,
        BASE | {"pattern": "domain_dependent", "front_rows_tilt_count": 2},
        domains=[domain],
    )
    grid = rows(walked)
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(7.5) for h in grid[1])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[2])


def test_variable_rows_with_different_spacing_tilt_only_face_holes():
    # Разный шаг a по рядам: столбцы не совпадают, и у скважин глубже
    # первого ряда «впереди в столбце» никого нет. Наклоняется только ряд у
    # откоса; глубже — ни наклона, ни сдвига.
    params = BASE | {
        "pattern": "variable",
        "row_params": [{"spacing_a_m": 3.0, "burden_b_m": 3.0}, {"spacing_a_m": 4.0}],
    }
    holes = generate_pattern(CONTOUR, params | {"front_rows_tilt_count": 1})
    plain = generate_pattern(CONTOUR, params)
    grid = rows(holes)
    # Шаг первого ряда 3 м: предел atan((3 − 1)/10) ≈ 11,31°.
    assert all(h.angle_deg == pytest.approx(math.degrees(math.atan(0.2))) for h in grid[0])
    face_y = max(h.collar.y for h in grid[0])
    tilted = [h for h in holes if h.kind == "production" and h.angle_deg > 1e-6]
    assert tilted and all(h.collar.y <= face_y + 1e-9 for h in tilted)
    plain_xy = {(round(h.collar.x, 6), round(h.collar.y, 6)) for h in plain if h.kind == "production"}
    for hole in holes:
        if hole.kind == "production" and hole.collar.y > face_y + 1e-9 and hole.angle_deg <= 1e-6:
            moved = (round(hole.collar.x, 6), round(hole.collar.y, 6)) not in plain_xy
            # Сдвинуты только скважины столбцов, начатых наклонённым рядом 1.
            if moved:
                assert any(abs(t.collar.x - hole.collar.x) < 0.4 for t in grid[0])
    # Скважины в столбцах, начатых глубже ряда у откоса, — на месте.
    assert any(
        (round(h.collar.x, 6), round(h.collar.y, 6)) in plain_xy
        for h in holes
        if h.kind == "production" and h.collar.y > face_y + 1e-9
    )


def test_walls_and_stab_keep_their_angles():
    extras = {
        "contour_row": True,
        "presplit_row": True,
        "presplit_angle_deg": 10.0,
        "trim_row": True,
        "buffer_row": True,
        "stab_row": True,
        "satellite_holes": True,
        "angle_deg": 3.0,
        "azimuth_deg": 90.0,
    }
    other = ("contour", "presplit", "trim", "buffer", "stab")
    plain = generate_pattern(CONTOUR, BASE | extras)
    tilted = generate_pattern(CONTOUR, BASE | extras | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 20})
    pick = lambda holes, kinds=other: [h for h in holes if h.kind in kinds]  # noqa: E731
    assert pick(plain)
    assert holes_signature(pick(plain)) == holes_signature(pick(tilted))
    assert any(h.kind == "stab" for h in pick(tilted))
    # Сателлиты идут за своей скважиной (её устье сдвинуто), угол — свой.
    satellites = pick(tilted, ("satellite",))
    assert satellites and len(satellites) >= len(pick(plain, ("satellite",)))
    assert all(h.angle_deg == pytest.approx(3.0) for h in satellites)


def test_recompute_keeps_tilt():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 1, "front_rows_tilt_deg": 20})
    hole = rows(holes)[0][0]
    result = recompute_hole(hole, CONTOUR, None, BASE)
    assert result.hole.angle_deg == pytest.approx(ONE_ROW_DEG)
    assert result.hole.azimuth_deg == pytest.approx(180.0)
    assert result.hole.toe.x == pytest.approx(hole.toe.x)
    assert result.hole.toe.y == pytest.approx(hole.toe.y)


# --- Ограничение угла: забой не ближе 1 м к линии подошвы ---


def test_tilt_angle_is_capped_by_floor_burden():
    # Откос вертикальный (90°): подошва — сама бровка y = 0. W не задана
    # (нет burden_b_m) — цель 1 м. Первый ряд в 3 м: ЛСП вертикальной 3 м,
    # H = 10 м — угол не больше atan((3 − 1)/10) ≈ 11,3°.
    contour = _rect_contour(40.0, 30.0, face_angle_deg=90.0)
    base = {k: v for k, v in BASE.items() if k != "burden_b_m"} | {"spacing_a_m": 3.5}
    params = base | {"offset_from_face_m": 3.0, "front_rows_tilt_count": 1, "front_rows_tilt_deg": 30}
    assert tilt_floor_burden_target_m(params) == FRONT_TILT_MIN_FLOOR_BURDEN_M
    holes = generate_pattern(contour, params)
    first, second = rows(holes)[:2]
    expected = math.degrees(math.atan((3.0 - FRONT_TILT_MIN_FLOOR_BURDEN_M) / 10.0))
    assert expected == pytest.approx(11.31, abs=0.01)
    for hole in first:
        assert hole.angle_deg == pytest.approx(expected, abs=1e-6)
        assert hole.azimuth_deg == pytest.approx(180.0)
    design = BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params)
    burdens = floor_burdens(design)
    for hole in first:
        assert burdens[hole.id].value_m == pytest.approx(FRONT_TILT_MIN_FLOOR_BURDEN_M, abs=1e-6)
        assert burdens[hole.id].beyond_toe is False
    # Второй ряд не наклоняется (ряд 2 при count 1).
    assert all(h.angle_deg == pytest.approx(0.0) for h in second)


def test_tilt_angle_is_capped_at_lower_floor_burden_bound():
    # W = 3,5 м: цель 0,8·W = 2,8 м. ЛСП вертикальной 5 м, H = 10 м —
    # угол atan((5 − 2,8)/10) ≈ 12,4°, ЛСП после наклона 2,8 м — не «мало».
    contour = _rect_contour(40.0, 30.0, face_angle_deg=90.0)
    params = BASE | {"offset_from_face_m": 5.0, "front_rows_tilt_count": 1, "front_rows_tilt_deg": 30}
    target = tilt_floor_burden_target_m(params)
    assert target == pytest.approx(FLOOR_BURDEN_MIN_RATIO * 3.5)
    holes = generate_pattern(contour, params)
    first = rows(holes)[0]
    expected = math.degrees(math.atan((5.0 - target) / 10.0))
    assert expected == pytest.approx(12.41, abs=0.01)
    design = BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params)
    burdens = floor_burdens(design)
    for hole in first:
        assert hole.angle_deg == pytest.approx(expected, abs=1e-6)
        assert burdens[hole.id].value_m == pytest.approx(target, abs=1e-6)
        assert burdens[hole.id].short is False
        assert burdens[hole.id].excess is False
    # ЛСП вертикальной меньше цели (первый ряд в 2,5 м) — без наклона.
    near = rows(generate_pattern(contour, params | {"offset_from_face_m": 2.5}))[0]
    assert all(h.angle_deg == pytest.approx(0.0) for h in near)


def test_small_angle_is_not_capped():
    contour = _rect_contour(40.0, 30.0, face_angle_deg=90.0)
    params = BASE | {"offset_from_face_m": 5.0, "front_rows_tilt_count": 1, "front_rows_tilt_deg": 5}
    assert all(h.angle_deg == pytest.approx(5.0) for h in rows(generate_pattern(contour, params))[0])


def test_no_room_means_common_angle():
    # ЛСП вертикальной 1 м — не больше запаса: ряд остаётся с общим углом.
    contour = _rect_contour(40.0, 30.0, face_angle_deg=90.0)
    params = BASE | {"offset_from_face_m": 1.0, "angle_deg": 3.0, "azimuth_deg": 0.0, "front_rows_tilt_count": 1}
    first = rows(generate_pattern(contour, params))[0]
    assert all(h.angle_deg == pytest.approx(3.0) and math.cos(math.radians(h.azimuth_deg)) == pytest.approx(1.0) for h in first)


def _naive_ranks(collars, contour, a, b, forced_first=0):
    """Ранг по определению: полный список закрывающих по `corridor_blockers`."""
    import shapely

    from design.toe_line import corridor_blockers, crest_geometry, shadow_limits

    crest = crest_geometry(contour)
    points = shapely.points(collars)
    tree = shapely.STRtree(points)
    min_advance, reach = shadow_limits(a, b)
    blockers = []
    for i, point in enumerate(points):
        value = float(shapely.distance(point, crest))
        target = shapely.get_point(shapely.shortest_line(crest, point), 0)
        if i < forced_first or value <= 0:
            blockers.append(set())
        else:
            blockers.append(set(corridor_blockers(i, value, points, target, tree, min_advance, reach)))
    first = {i for i, items in enumerate(blockers) if not items}
    return [1 if i in first else 2 if items <= first else 3 for i, items in enumerate(blockers)]


@pytest.mark.parametrize("case", ["step", "boot", "boot_face", "bent"])
def test_fast_ranks_match_definition(case):
    from tests.test_design_pattern_full_contour import BOOT, BOOT_FACE, PARAMS

    if case == "step":
        contour, params, a, b = _contour_of(STEP, STEP_FACE), BASE, 4.0, 3.5
    elif case == "bent":
        contour, params, a, b = _rect_contour(40.0, 30.0, free_faces=((3, 0, 1),)), BASE, 4.0, 3.5
    else:
        contour, params, a, b = _contour_of(BOOT, BOOT_FACE), PARAMS, 5.0, 5.0
        if case == "boot_face":
            params = PARAMS | {"first_row_follow_face": True}
    holes = generate_pattern(contour, params)
    collars = [(h.collar.x, h.collar.y) for h in holes if h.kind == "production"]
    # Короткий шаг: коридоры длиннее «ближней» части — проверяется и полный поиск.
    for step_a, step_b in ((a, b), (a / 3.0, b / 3.0)):
        assert front_row_ranks(collars, contour, step_a, step_b) == _naive_ranks(collars, contour, step_a, step_b)
    assert front_row_ranks(collars, contour, a, b, forced_first=5) == _naive_ranks(collars, contour, a, b, 5)


def test_taper_tilts_front_row_of_another_kind_in_variable_grid():
    """Вид ряда у откоса из `row_params` (infill) не выводит его из плавного перехода."""
    keys = {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 15}
    same = BASE | keys | {"pattern": "variable", "row_params": [{}, {}]}
    other = BASE | keys | {"pattern": "variable", "row_params": [{"kind": "infill"}, {"kind": "infill"}, {}]}
    expected = rows(generate_pattern(CONTOUR, same))[:3]
    got = rows(generate_pattern(CONTOUR, other), kinds=("production", "infill"))[:3]
    assert [h.kind for h in got[0]] == ["infill"] * len(got[0])
    for row_got, row_expected in zip(got, expected):
        assert [(h.collar, h.toe) for h in row_got] == [(h.collar, h.toe) for h in row_expected]
    assert all(h.angle_deg == pytest.approx(15.0) for h in got[0])
    assert all(h.angle_deg == pytest.approx(7.5) for h in got[1])
