"""Пара у откоса (оптимизатор, часть 3b): вертикальная первого ряда + наклонная на 1 м ближе к уступу."""
import math

import pytest

from design.models import BenchSurface, BlastDesign, BlockContour, Hole, Point3, PRESERVED_HOLE_KINDS
from design.pattern import (
    FACE_PAIR_OFFSET_M,
    FRONT_ROWS_MODE_PAIR,
    MIN_CREST_OFFSET_DEFAULT_M,
    generate_pattern,
)
from design.relief import is_relief_kind, relief_triangles
from design.toe_line import floor_burdens, floor_point

H = 10.0
# Откос 75° от горизонтали: в плане 10·tg 15° = 2,68 м.
SLOPE_M = H * math.tan(math.radians(15.0))


def _contour(width=40.0, height=30.0) -> BlockContour:
    """Прямоугольник, откос — нижнее ребро y = 0 (к откосу — азимут 180°)."""
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=75.0),
    )


CONTOUR = _contour()
# Ряды вдоль бровки, a = 4, W = b = 3,5, первый ряд в 3 м от кромки:
# ЛСП вертикальной 3 + 2,68 = 5,68 > 3,5·1,03 = 3,605.
BASE = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": 3.5,
    "row_azimuth_deg": 90.0,
    "offset_from_face_m": 3.0,
    "edge_margin_m": 0.0,
    "subdrill_m": 1.0,
    "front_rows_mode": "pair",
}


def _pairs(holes):
    return [h for h in holes if h.kind == "face_toe"]


def _first_row(holes):
    production = [h for h in holes if h.kind == "production"]
    y0 = min(h.collar.y for h in production)
    return [h for h in production if abs(h.collar.y - y0) < 1e-6]


def _design(holes, params=BASE, contour=CONTOUR) -> BlastDesign:
    return BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params)


def test_constants():
    assert FACE_PAIR_OFFSET_M == 1.0
    assert MIN_CREST_OFFSET_DEFAULT_M == 1.0
    assert FRONT_ROWS_MODE_PAIR == "pair"
    assert "face_toe" not in PRESERVED_HOLE_KINDS


def test_pair_added_one_metre_closer_along_column():
    holes = generate_pattern(CONTOUR, BASE)
    first = _first_row(holes)
    pairs = _pairs(holes)
    assert len(first) == 11
    assert len(pairs) == len(first)
    by_id = {h.id: h for h in holes}
    for pair in pairs:
        assert pair.id.endswith("T")
        vertical = by_id[pair.id[:-1]]
        assert vertical.kind == "production"
        assert vertical.collar.y == pytest.approx(3.0)
        assert (pair.row, pair.col) == (vertical.row, vertical.col)
        # Устье на 1 м ближе к откосу по линии столбца, без сдвига вдоль ряда.
        assert pair.collar.x == pytest.approx(vertical.collar.x, abs=1e-9)
        assert pair.collar.y == pytest.approx(vertical.collar.y - 1.0, abs=1e-9)
        # Азимут вдоль линии столбца к откосу.
        assert pair.toe.x == pytest.approx(pair.collar.x, abs=1e-9)
        assert pair.toe.y < pair.collar.y
        assert pair.azimuth_deg == pytest.approx(180.0, abs=1e-6)
        # Наибольший угол ≤ 15°, при котором ЛСП ≥ max(0,8·W, 1) = 2,8:
        # ЛСП = 2 + 2,68 − 10·tg α = 2,8 → tg α = 0,188.
        expected = math.degrees(math.atan((2.0 + SLOPE_M - 2.8) / H))
        assert pair.angle_deg == pytest.approx(expected, abs=1e-3)
        assert pair.angle_deg <= 15.0
        assert pair.source == "generated"
        # Вертикальная осталась на месте.
        assert vertical.angle_deg == pytest.approx(0.0)
    ids = [h.id for h in holes]
    assert len(ids) == len(set(ids))


def test_pair_angle_capped_by_max_tilt():
    # α = 5°: ЛСП пары 4,68 − 10·tg 5° = 3,81 ≥ 2,8 — угол не ограничен ЛСП.
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_deg": 5})
    assert _pairs(holes)
    assert all(p.angle_deg == pytest.approx(5.0, abs=1e-6) for p in _pairs(holes))


def test_numbering_of_grid_is_unchanged_by_pairs():
    plain = generate_pattern(CONTOUR, {k: v for k, v in BASE.items() if k != "front_rows_mode"})
    paired = generate_pattern(CONTOUR, BASE)
    assert [h.id for h in plain] == [h.id for h in paired if h.kind != "face_toe"]
    assert {p.id for p in _pairs(paired)} == {h.id + "T" for h in _first_row(paired)}


def test_no_pair_when_vertical_fits_w():
    # W = 5,6: допуск 5,768 ≥ 5,68 — вертикальная укладывается.
    holes = generate_pattern(CONTOUR, BASE | {"burden_b_m": 5.6})
    assert _pairs(holes) == []


def test_pair_is_vertical_when_it_fits_w_at_zero_degrees():
    # W = 4,6: вертикальная 5,68 > 4,738, пара в 2 м от кромки — 4,68 ≤ 4,738.
    holes = generate_pattern(CONTOUR, BASE | {"burden_b_m": 4.6})
    pairs = _pairs(holes)
    assert pairs
    assert all(p.angle_deg == pytest.approx(0.0, abs=1e-9) for p in pairs)


def test_no_pair_when_collar_too_close_to_crest():
    # Первый ряд в 1,8 м: устье пары в 0,8 м < 1 м от кромки.
    holes = generate_pattern(CONTOUR, BASE | {"offset_from_face_m": 1.8})
    assert _pairs(holes) == []
    # Отступ 0,5 м — пара ставится.
    holes = generate_pattern(CONTOUR, BASE | {"offset_from_face_m": 1.8, "min_crest_offset_m": 0.5})
    assert len(_pairs(holes)) == len(_first_row(holes))


def test_no_pair_without_w():
    # Без burden_b_m у прямоугольной сетки W не задана — сравнивать не с чем.
    params = {k: v for k, v in BASE.items() if k != "burden_b_m"}
    assert _pairs(generate_pattern(CONTOUR, params)) == []


def test_floor_burden_counted_at_pair_vertical_closed():
    holes = generate_pattern(CONTOUR, BASE)
    burdens = floor_burdens(_design(holes))
    pairs = _pairs(holes)
    assert {p.id for p in pairs} <= set(burdens)
    for pair in pairs:
        assert pair.id[:-1] not in burdens
        assert burdens[pair.id].value_m == pytest.approx(2.8, abs=1e-3)
        assert not burdens[pair.id].short and not burdens[pair.id].excess


def test_vertical_pair_still_closes_its_vertical():
    # Вертикальная пара в 1 м впереди — меньше 0,4·b по коридору, но вертикальная за ней закрыта.
    holes = generate_pattern(CONTOUR, BASE | {"burden_b_m": 4.6})
    burdens = floor_burdens(_design(holes, BASE | {"burden_b_m": 4.6}))
    for pair in _pairs(holes):
        assert pair.id in burdens
        assert pair.id[:-1] not in burdens


def test_pair_not_in_relief_grid():
    assert not is_relief_kind("face_toe")
    assert not is_relief_kind("face_toe", "production")
    holes = generate_pattern(CONTOUR, BASE)
    times = {h.id: float(i) for i, h in enumerate(holes)}
    tris = relief_triangles(holes, times, max_edge_m=100.0)
    pair_ids = {p.id for p in _pairs(holes)}
    assert tris
    assert all(not (set(t.hole_ids) & pair_ids) for t in tris)


def test_regeneration_one_pair_per_hole_and_manual_kept():
    first = generate_pattern(CONTOUR, BASE)
    manual = Hole(
        id="M1", row=0, col=0, collar=Point3(x=20.0, y=20.0, z=0.0), toe=Point3(x=20.0, y=20.0, z=-11.0),
        diameter_mm=152.0, subdrill_m=1.0, kind="production", source="manual",
    )
    manual_pair = Hole(
        id="M2", row=0, col=0, collar=Point3(x=22.0, y=20.0, z=0.0), toe=Point3(x=22.0, y=20.0, z=-11.0),
        diameter_mm=152.0, subdrill_m=1.0, kind="face_toe", source="manual",
    )
    again = generate_pattern(CONTOUR, BASE, existing_holes=first + [manual, manual_pair])
    assert len(_pairs(again)) == len(_pairs(first)) + 1
    assert [h for h in again if h.id == "M1"] and [h for h in again if h.id == "M2"]
    generated = [h for h in again if h.source == "generated"]
    assert [h.id for h in generated] == [h.id for h in first]
    ids = [h.id for h in again]
    assert len(ids) == len(set(ids))


def test_pair_floor_point_lies_toward_face():
    holes = generate_pattern(CONTOUR, BASE)
    for pair in _pairs(holes):
        fx, fy = floor_point(pair)
        assert fx == pytest.approx(pair.collar.x, abs=1e-9)
        assert fy == pytest.approx(2.8 - SLOPE_M, abs=1e-3)


def test_no_pair_when_collar_outside_boundary():
    # Отступ от контура 2,5 м: ряд в 3 м внутри, устье пары в 2 м — вне границы
    # (до кромки 2 м — больше минимального отступа, отсекает только граница).
    holes = generate_pattern(CONTOUR, BASE | {"edge_margin_m": 2.5})
    assert _first_row(holes)
    assert _pairs(holes) == []


# --- Предел угла по построенной скважине (волна перед финалом) -------------


def _floor_rising_to_face(gap_m: float):
    """Съёмка подошвы в `gap_m` от бровки; подошва (TIN) поднимается к откосу.

    Подошва z = −10,5 + 0,2·(3 − y): у вертикальной (y = 3) H = 10,5, у пары
    (y = 2) — 10,3, а у наклонной на подошве H тем меньше, чем дальше её низ
    к откосу. Съёмка — откос, пока H ≥ `gap_m` (`SURVEY_SPOIL_WIDTH_FACTOR` = 1),
    иначе развал и подошва по углу — ближе к устью.
    """
    from design.spatial.surfaces import SurfaceSet, floor_surface

    contour = _contour()
    contour.cad = {"bottom": [[0.0, -gap_m], [40.0, -gap_m], [40.0, 30.0], [0.0, 30.0]]}
    points = [
        Point3(x=x, y=y, z=-10.5 + 0.2 * (3.0 - y))
        for x in (-10.0, 20.0, 50.0)
        for y in (-20.0, 5.0, 40.0)
    ]
    return contour, SurfaceSet(floor=floor_surface(points))


@pytest.mark.parametrize("mode", ["pair", "taper"])
def test_tilt_cap_holds_across_survey_to_spoil_switch(mode):
    # Оценка угла по высоте у устья (10,3) пропускает 30°: съёмка, ЛСП ~5,9.
    # У построенной скважины H у низа < 9,9 — развал, подошва по углу в
    # 2,5 м от бровки, низ за ней или ближе 0,8·W. Угол должен уменьшиться до прохода проверки.
    contour, surfaces = _floor_rising_to_face(9.9)
    params = BASE | {"front_rows_tilt_deg": 30.0}
    if mode == "taper":
        params = params | {"front_rows_mode": "taper", "front_rows_tilt_count": 1, "offset_from_face_m": 2.0}
    holes = generate_pattern(contour, params, [], surfaces)
    burdens = floor_burdens(_design(holes, params, contour))
    tilted = [h for h in holes if h.angle_deg > 1e-6 and (mode == "taper" or h.kind == "face_toe")]
    assert tilted
    for hole in tilted:
        burden = burdens[hole.id]
        assert not burden.beyond_toe
        assert not burden.short
        assert burden.value_m >= 0.8 * 3.5 - 1e-6


def test_pair_cap_uses_own_collar_on_sloped_roof():
    # Кровля опускается вглубь блока: у пары (1 м ближе к откосу) H больше,
    # чем у вертикальной. Предел по H вертикальной дал бы ЛСП чуть меньше 0,8·W.
    from design.spatial.surfaces import SurfaceSet, top_surface

    roof = [Point3(x=x, y=y, z=2.0 - 0.3 * y) for x in (-10.0, 20.0, 50.0) for y in (-20.0, 5.0, 40.0)]
    surfaces = SurfaceSet(top=top_surface(roof))
    holes = generate_pattern(CONTOUR, BASE, [], surfaces)
    burdens = floor_burdens(_design(holes))
    pairs = _pairs(holes)
    assert pairs
    for pair in pairs:
        burden = burdens[pair.id]
        assert not burden.short
        assert burden.value_m == pytest.approx(0.8 * 3.5, abs=1e-5)
