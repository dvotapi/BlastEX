"""Наклон 1–2 ряда у откоса в генераторе сетки (оптимизатор, часть 3)."""
import math

import pytest

from design.geometry import face_azimuth_deg
from design.hole_recompute import recompute_hole
from design.models import FRONT_ROW_BASE, BenchSurface, BlastDesign, BlockContour, Point3, logical_row
from design.pattern import (
    FRONT_ROWS_TILT_DEFAULT_DEG,
    FRONT_ROWS_TILT_MAX_DEG,
    FRONT_TILT_MIN_FLOOR_BURDEN_M,
    front_row_ranks,
    generate_pattern,
)
from design.toe_line import floor_burdens, floor_point


# Откос 60° от горизонтали: подошва в 10·tan 30° = 5,77 м от бровки — запас,
# при котором наклон до 30° не упирается в ограничение по ЛСП (оно — отдельно).
FACE_ANGLE_DEG = 60.0


def _rect_contour(width: float, height: float, free_faces=((0, 1),), face_angle_deg=FACE_ANGLE_DEG) -> BlockContour:
    """Прямоугольник как в tests/test_design_pattern.py; откос — нижнее ребро y = 0."""
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return _contour_of(verts, free_faces, face_angle_deg)


def _contour_of(verts, free_faces, face_angle_deg=FACE_ANGLE_DEG) -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        free_faces=[list(edge) for edge in free_faces],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=face_angle_deg),
    )


CONTOUR = _rect_contour(40.0, 30.0)
# Ряды вдоль бровки (по +X), a = 4, b = 3,5, первый ряд в 2 м от откоса.
BASE = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": 3.5,
    "row_azimuth_deg": 90.0,
    "offset_from_face_m": 2.0,
    "edge_margin_m": 0.0,
    "subdrill_m": 1.0,
}
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


def test_first_row_tilted_toward_face():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 1})
    grid = rows(holes)
    first, second = grid[0], grid[1]
    assert first and second
    assert all(h.angle_deg == pytest.approx(15.0) for h in first)
    assert all(h.azimuth_deg == pytest.approx(180.0) for h in first)
    assert all(h.angle_deg == pytest.approx(0.0) for h in second)
    # Устья на месте, номера те же.
    plain = generate_pattern(CONTOUR, BASE)
    assert [(h.id, h.collar) for h in holes] == [(h.id, h.collar) for h in plain]


def test_two_rows_tilted_with_custom_angle_and_clamp():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 45})
    grid = rows(holes)
    assert all(h.angle_deg == pytest.approx(30.0) for h in grid[0] + grid[1])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[2])


def test_negative_angle_is_clamped_to_zero():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": -10})
    assert all(h.angle_deg == pytest.approx(0.0) for h in holes)


def test_count_is_clamped():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 5})
    grid = rows(holes)
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0] + grid[1])
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
    assert shift == pytest.approx(10.0 * math.tan(math.radians(15)), abs=0.05)  # H = 10 м
    # Длина — та же формула L = H / cos α + Δ.
    assert tilted.length_m == pytest.approx(10.0 / math.cos(math.radians(15)) + 1.0, abs=1e-6)


def test_face_following_row_is_row_one():
    params = BASE | {"first_row_follow_face": True}
    holes = generate_pattern(CONTOUR, params | {"front_rows_tilt_count": 1})
    grid = rows(holes)
    face_row = [h for h in holes if h.kind == "production" and h.row == 0]
    assert face_row and grid[0] == face_row
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0])
    assert all(h.azimuth_deg == pytest.approx(180.0) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[1])

    holes = generate_pattern(CONTOUR, params | {"front_rows_tilt_count": 2})
    grid = rows(holes)
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0] + grid[1])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[2])


# Ступенчатая бровка: слева откос на y = 0, справа отступает к y = 8.
STEP = [(0.0, 0.0), (20.0, 0.0), (20.0, 8.0), (40.0, 8.0), (40.0, 30.0), (0.0, 30.0)]
STEP_FACE = ((0, 1, 2, 3),)


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
    assert all(h.angle_deg == pytest.approx(15.0) and h.azimuth_deg == pytest.approx(180.0) for h in front.values())
    for x in (24.0, 28.0, 32.0, 36.0, 40.0):
        assert third[x].angle_deg == pytest.approx(15.0)
        assert third[x].azimuth_deg == pytest.approx(180.0)
        assert fourth[x].angle_deg == pytest.approx(0.0)
    # Левый участок: за рядом впереди первого ряда решётки — без наклона.
    for x in (0.0, 4.0, 8.0, 12.0):
        assert first[x].angle_deg == pytest.approx(0.0)
        assert third[x].angle_deg == pytest.approx(0.0)

    # Два ряда: следующий за рядом 1 — и слева, и на отступившем участке.
    front, first, third, fourth = _by_row(generate_pattern(contour, BASE | {"front_rows_tilt_count": 2}))[:4]
    for x in (0.0, 4.0, 8.0, 12.0):
        assert first[x].angle_deg == pytest.approx(15.0)
        assert third[x].angle_deg == pytest.approx(0.0)
    for x in (24.0, 28.0, 32.0, 36.0, 40.0):
        assert fourth[x].angle_deg == pytest.approx(15.0)


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
    # Каждая наклонённая скважина — ряд 1 у откоса, каждая ряда 1 — наклонена.
    production = [h for h in holes if h.kind == "production"]
    ranks = front_row_ranks([(h.collar.x, h.collar.y) for h in production], contour, 5.0, 5.0)
    assert [h.angle_deg > 1.0 for h in production] == [rank == 1 for rank in ranks]


def test_face_following_row_is_rank_one_on_boot():
    from tests.test_design_pattern_full_contour import BOOT, BOOT_FACE, PARAMS

    contour = _contour_of(BOOT, BOOT_FACE)
    params = PARAMS | {"first_row_follow_face": True, "front_rows_tilt_count": 1}
    holes = generate_pattern(contour, params)
    face = [h for h in holes if h.kind == "production" and h.row == 0]
    assert face
    for hole in face:
        assert hole.angle_deg == pytest.approx(15.0)
        assert hole.azimuth_deg == pytest.approx(face_azimuth_deg((hole.collar.x, hole.collar.y), contour))


def test_bent_face_gives_each_hole_its_own_azimuth():
    contour = _rect_contour(40.0, 30.0, free_faces=((3, 0, 1),))
    holes = generate_pattern(contour, BASE | {"front_rows_tilt_count": 1})
    first = rows(holes)[0]
    azimuths = set()
    for hole in first:
        expected = face_azimuth_deg((hole.collar.x, hole.collar.y), contour)
        assert hole.azimuth_deg == pytest.approx(expected)
        azimuths.add(round(expected))
    assert {180, 270} <= azimuths


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
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0])
    assert all(h.angle_deg == pytest.approx(5.0) and h.azimuth_deg == pytest.approx(0.0) for h in grid[1])


def test_variable_and_domain_rows_are_tilted():
    from design.models import BlastDomain

    variable = generate_pattern(
        CONTOUR,
        BASE | {
            "pattern": "variable",
            "row_params": [{"spacing_a_m": 3.0, "burden_b_m": 3.0}, {"spacing_a_m": 4.0}],
            "front_rows_tilt_count": 1,
        },
    )
    grid = rows(variable)
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0])
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
    assert all(h.angle_deg == pytest.approx(15.0) for h in grid[0] + grid[1])
    assert all(h.angle_deg == pytest.approx(0.0) for h in grid[2])


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
    other = ("contour", "presplit", "trim", "buffer", "stab", "satellite")
    plain = generate_pattern(CONTOUR, BASE | extras)
    tilted = generate_pattern(CONTOUR, BASE | extras | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 20})
    pick = lambda holes: [h for h in holes if h.kind in other]  # noqa: E731
    assert pick(plain)
    assert holes_signature(pick(plain)) == holes_signature(pick(tilted))
    assert any(h.kind == "stab" for h in pick(tilted))


def test_recompute_keeps_tilt():
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_count": 1, "front_rows_tilt_deg": 20})
    hole = rows(holes)[0][0]
    result = recompute_hole(hole, CONTOUR, None, BASE)
    assert result.hole.angle_deg == pytest.approx(20.0)
    assert result.hole.azimuth_deg == pytest.approx(180.0)
    assert result.hole.toe.x == pytest.approx(hole.toe.x)
    assert result.hole.toe.y == pytest.approx(hole.toe.y)


# --- Ограничение угла: забой не ближе 1 м к линии подошвы ---


def test_tilt_angle_is_capped_by_floor_burden():
    # Откос вертикальный (90°): подошва — сама бровка y = 0. Первый ряд в 3 м:
    # ЛСП вертикальной 3 м, H = 10 м — угол не больше atan((3 − 1)/10) ≈ 11,3°.
    contour = _rect_contour(40.0, 30.0, face_angle_deg=90.0)
    params = BASE | {"offset_from_face_m": 3.0, "front_rows_tilt_count": 1, "front_rows_tilt_deg": 30}
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
        assert burdens[hole.id].value_m == pytest.approx(1.0, abs=1e-6)
        assert burdens[hole.id].beyond_toe is False
    # Второй ряд не наклоняется (ряд 2 при count 1).
    assert all(h.angle_deg == pytest.approx(0.0) for h in second)


def test_small_angle_is_not_capped():
    contour = _rect_contour(40.0, 30.0, face_angle_deg=90.0)
    params = BASE | {"offset_from_face_m": 3.0, "front_rows_tilt_count": 1, "front_rows_tilt_deg": 5}
    assert all(h.angle_deg == pytest.approx(5.0) for h in rows(generate_pattern(contour, params))[0])


def test_no_room_means_common_angle():
    # ЛСП вертикальной 1 м — не больше запаса: ряд остаётся с общим углом.
    contour = _rect_contour(40.0, 30.0, face_angle_deg=90.0)
    params = BASE | {"offset_from_face_m": 1.0, "angle_deg": 3.0, "azimuth_deg": 0.0, "front_rows_tilt_count": 1}
    first = rows(generate_pattern(contour, params))[0]
    assert all(h.angle_deg == pytest.approx(3.0) and math.cos(math.radians(h.azimuth_deg)) == pytest.approx(1.0) for h in first)
