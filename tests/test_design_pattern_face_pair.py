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
    assert MIN_CREST_OFFSET_DEFAULT_M == 0.2
    assert FRONT_ROWS_MODE_PAIR == "pair"
    assert "face_toe" not in PRESERVED_HOLE_KINDS


# Откос 60° от горизонтали: в плане 10·tg 30° = 5,77 м — пара у кромки
# всё ещё не укладывается без наклона.
STEEP_SLOPE_M = H * math.tan(math.radians(30.0))


def _steep_contour(width=40.0, height=30.0) -> BlockContour:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=60.0),
    )


W = 3.5
GAP_MAX = 1.03 * W


def test_pair_collar_moves_toward_crest_instead_of_tilting():
    # Вертикальная в 3 м: ЛСП 5,68. Пара сдвигается к кромке, пока ЛСП не станет W:
    # сдвиг 5,68 − 3,5 = 2,18 м, устье в 0,82 м от кромки, без наклона.
    holes = generate_pattern(CONTOUR, BASE)
    first = _first_row(holes)
    pairs = _pairs(holes)
    assert len(pairs) == len(first) == 11
    by_id = {h.id: h for h in holes}
    burdens = floor_burdens(_design(holes))
    for pair in pairs:
        vertical = by_id[pair.id[:-1]]
        assert pair.id.endswith("T") and (pair.row, pair.col) == (vertical.row, vertical.col)
        assert pair.collar.x == pytest.approx(vertical.collar.x, abs=1e-9)
        assert pair.collar.y == pytest.approx(W - SLOPE_M, abs=1e-3)
        assert pair.angle_deg == pytest.approx(0.0, abs=1e-9)
        assert burdens[pair.id].value_m == pytest.approx(W, abs=1e-3)
        assert vertical.angle_deg == pytest.approx(0.0)


def test_pair_collar_stops_at_crest_offset_then_smallest_tilt():
    # Откос 60°, вертикальная в 1,2 м: ЛСП 6,97; пара упирается в 0,2 м от
    # кромки (сдвиг 1 м), ЛСП 5,97 — наименьший наклон до ЛСП = W: tg α = 2,47/10.
    holes = generate_pattern(_steep_contour(), BASE | {"offset_from_face_m": 1.2})
    pairs = _pairs(holes)
    assert pairs
    expected = math.degrees(math.atan((1.2 - 1.0 + STEEP_SLOPE_M - W) / H))
    burdens = floor_burdens(_design(holes, contour=_steep_contour()))
    for pair in pairs:
        assert pair.collar.y == pytest.approx(0.2, abs=1e-3)
        assert pair.angle_deg == pytest.approx(expected, abs=0.05)
        assert burdens[pair.id].value_m == pytest.approx(W, abs=0.01)


def test_pair_shift_limited_by_floor_gap():
    # Вертикальная в 4,5 м: ЛСП 7,18; сдвиг не больше b + 3 % = 3,605 м (разрыв у
    # подошвы между парой и её вертикальной), ЛСП 3,575 ≤ 3,605 — без наклона.
    holes = generate_pattern(CONTOUR, BASE | {"offset_from_face_m": 4.5})
    pairs = _pairs(holes)
    assert pairs
    for pair in pairs:
        assert pair.collar.y == pytest.approx(4.5 - GAP_MAX, abs=1e-3)
        assert pair.angle_deg == pytest.approx(0.0, abs=1e-9)


def test_far_first_row_pair_keeps_excess_without_breaking_floor_gap():
    # Вертикальная в 9 м: сдвиг упирается в 3,605 м, на наклон разрыва не остаётся —
    # пара вертикальная, ЛСП больше допуска с предупреждением.
    from design.analysis import validate

    params = BASE | {"offset_from_face_m": 9.0}
    holes = generate_pattern(CONTOUR, params)
    pairs = _pairs(holes)
    assert pairs and all(p.angle_deg == pytest.approx(0.0, abs=1e-9) for p in pairs)
    assert all(p.collar.y == pytest.approx(9.0 - GAP_MAX, abs=1e-3) for p in pairs)
    assert "floor_burden_excess" in {w["code"] for w in validate(_design(holes, params))}


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
    # Первый ряд в 1,15 м: устье пары в 0,15 м < 0,2 м от кромки (умолчание).
    holes = generate_pattern(CONTOUR, BASE | {"offset_from_face_m": 1.15})
    assert _pairs(holes) == []
    # Отступ 0,05 м — пара ставится (ЛСП 2,83 ≥ 0,8·W).
    holes = generate_pattern(CONTOUR, BASE | {"offset_from_face_m": 1.15, "min_crest_offset_m": 0.05})
    assert len(_pairs(holes)) == len(_first_row(holes))
    # Первый ряд в 1,4 м: устье пары в 0,4 м — по умолчанию (0,2 м) пара ставится.
    holes = generate_pattern(CONTOUR, BASE | {"offset_from_face_m": 1.4})
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
        assert burdens[pair.id].value_m == pytest.approx(W, abs=1e-3)
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
        assert fy == pytest.approx(W - SLOPE_M, abs=1e-3)


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
    # Кровля опускается вглубь блока: у пары (ближе к откосу) H своя — сдвиг
    # подбирается по её собственной точке на подошве, ЛСП = W.
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
        assert burden.value_m == pytest.approx(W, abs=1e-3)


def test_pair_added_when_variable_row_gives_front_row_another_kind():
    """Ряд у откоса с видом из `row_params` (infill) — всё равно основная сетка: пара ставится."""
    params = BASE | {"pattern": "variable", "row_params": [{"kind": "infill"}, {}]}
    holes = generate_pattern(CONTOUR, params)
    front = [h for h in holes if h.kind == "infill" and abs(h.collar.y - 3.0) < 1e-6]
    pairs = _pairs(holes)
    assert len(front) == 11
    assert len(pairs) == len(front)
    by_id = {h.id: h for h in holes}
    assert all(by_id[p.id[:-1]].kind == "infill" for p in pairs)


@pytest.mark.parametrize("kind", ["buffer", "contour"])
def test_wall_row_from_row_params_gets_no_pair_and_keeps_crest_offset(kind):
    """Стенку из `row_params` схема не трогает: ни пары, ни удаления по отступу от кромки."""
    params = BASE | {"pattern": "variable", "row_params": [{"kind": kind}, {}]}
    holes = generate_pattern(CONTOUR, params)
    wall = [h for h in holes if h.kind == kind]
    assert len(wall) == 11
    assert all(not h.id.endswith("T") or h.kind == "face_toe" for h in holes)
    by_id = {h.id: h for h in holes}
    assert all(by_id[p.id[:-1]].kind != kind for p in _pairs(holes))
    # Отступ 4 м больше расстояния ряда до кромки (3 м): стенка остаётся.
    far = generate_pattern(CONTOUR, params | {"min_crest_offset_m": 4.0})
    assert len([h for h in far if h.kind == kind]) == 11


def _slanted_contour(deg: float) -> BlockContour:
    """Откос — ребро (0, 0)–(40, 40·tg deg) к рядам под углом deg; его нормаль наружу — 180° − deg."""
    verts = [(0.0, 0.0), (40.0, 40.0 * math.tan(math.radians(deg))), (40.0, 30.0), (0.0, 30.0)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=60.0),
    )


def test_pair_tilts_toward_slanted_face_within_limit():
    # Ряды — азимут 90°, бровка повёрнута на 10°: азимут пары — нормаль к бровке, 170°.
    holes = generate_pattern(_slanted_contour(10.0), BASE | {"offset_from_face_m": 1.6})
    # Пара на самом фланге (x = 40) смотрит на конец линии подошвы — ей своё направление.
    pairs = [p for p in _pairs(holes) if p.angle_deg > 1e-6 and p.collar.x < 39.0]
    assert pairs
    for pair in pairs:
        assert pair.azimuth_deg == pytest.approx(170.0, abs=0.5)


def test_pair_azimuth_clamped_to_fifteen_degrees_from_column():
    holes = generate_pattern(_slanted_contour(30.0), BASE | {"offset_from_face_m": 1.6})
    pairs = [p for p in _pairs(holes) if p.angle_deg > 1e-6]
    assert pairs
    for pair in pairs:
        assert pair.azimuth_deg == pytest.approx(165.0, abs=0.5)


def test_pair_on_straight_face_keeps_column_azimuth():
    holes = generate_pattern(_steep_contour(), BASE | {"offset_from_face_m": 1.2})
    pairs = [p for p in _pairs(holes) if p.angle_deg > 1e-6]
    assert pairs and all(p.azimuth_deg == pytest.approx(180.0, abs=1e-6) for p in pairs)


def test_zero_preferred_tilt_keeps_pairs_vertical():
    # 0° — наклона пары нет совсем, подъём не включается (решение по ревью 06.11.2026).
    holes = generate_pattern(_steep_contour(), BASE | {"offset_from_face_m": 1.2, "front_rows_tilt_deg": 0})
    assert _pairs(holes)
    assert all(p.angle_deg == pytest.approx(0.0, abs=1e-9) for p in _pairs(holes))


def test_raise_checks_floor_burden_in_batches(monkeypatch):
    # Подъём угла — делением пополам пакетом: число вызовов линии подошвы не растёт с числом пар.
    import design.pattern as pattern

    calls = {"n": 0}
    real = pattern.toe_positions

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(pattern, "toe_positions", counting)
    wide = _steep_contour(width=200.0)
    holes = generate_pattern(wide, BASE | {"offset_from_face_m": 1.2})
    assert len(_pairs(holes)) > 40
    assert calls["n"] < 120


def test_smallest_angle_falls_back_to_ceiling_when_it_breaks_lower_bound(monkeypatch):
    # У скачка съёмка ↔ развал ЛСП немонотонна: наименьший угол, не прошедший
    # проверку ЛСП ≥ max(0,8·W, 1 м), заменяется наибольшим допустимым.
    import design.pattern as pattern

    real = pattern._tilt_holds
    expected = math.degrees(math.atan((1.2 - 1.0 + STEEP_SLOPE_M - W) / H))

    def jumpy(contour, holes, target_m):
        return [ok and not (abs(h.angle_deg - expected) < 0.5) for h, ok in zip(holes, real(contour, holes, target_m))]

    monkeypatch.setattr(pattern, "_tilt_holds", jumpy)
    holes = generate_pattern(_steep_contour(), BASE | {"offset_from_face_m": 1.2})
    # Наибольший допустимый: ЛСП ≥ 2,8 и разрыв у подошвы 1 + t ≤ 3,605.
    ceiling = math.degrees(math.atan(min(1.2 - 1.0 + STEEP_SLOPE_M - 2.8, GAP_MAX - 1.0) / H))
    assert _pairs(holes)
    assert all(p.angle_deg == pytest.approx(ceiling, abs=0.05) for p in _pairs(holes))


def _contour_at(face_angle_deg: float) -> BlockContour:
    verts = [(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=face_angle_deg),
    )


def test_no_pair_when_minimum_shift_undershoots_lower_bound():
    # Откос 85° (в плане 0,875 м), вертикальная в 2,83 м: ЛСП 3,705 > 3,605.
    # Пара на 1 м ближе дала бы 2,705 < 0,8·W = 2,8 — её не ставим.
    holes = generate_pattern(_contour_at(85.0), BASE | {"offset_from_face_m": 2.83})
    assert _first_row(holes)
    assert _pairs(holes) == []


def test_floor_gap_limit_uses_row_own_burden():
    # Переменная сетка: у первого ряда b = 3,0 — сдвиг пары не больше 3,09 м, а не 3,605.
    params = BASE | {"pattern": "variable", "offset_from_face_m": 4.5, "row_params": [{"burden_b_m": 3.0}, {}]}
    holes = generate_pattern(CONTOUR, params)
    pairs = _pairs(holes)
    assert pairs
    assert all(p.collar.y == pytest.approx(4.5 - 3.0 * 1.03, abs=1e-3) for p in pairs)


# --- Замечания Codex к PR #153 ---------------------------------------------


def test_pair_shift_uses_pair_own_bench_height_on_sloping_floor():
    # Съёмка подошвы в 10,2 м от бровки, подошва круто поднимается к откосу
    # (z = −10,5 + (3 − y)): чем ближе пара к кромке, тем ниже её уступ и тем
    # раньше съёмка сменяется развалом. Сдвиг считается по высоте самой пары —
    # ЛСП не меньше 0,8·W и низ не за подошвой.
    from design.spatial.surfaces import SurfaceSet, floor_surface

    contour = _contour()
    contour.cad = {"bottom": [[0.0, -10.2], [40.0, -10.2], [40.0, 30.0], [0.0, 30.0]]}
    points = [Point3(x=x, y=y, z=-10.5 + (3.0 - y)) for x in (-10.0, 20.0, 50.0) for y in (-20.0, 5.0, 40.0)]
    surfaces = SurfaceSet(floor=floor_surface(points))
    params = BASE | {"front_rows_tilt_deg": 0.0}
    holes = generate_pattern(contour, params, [], surfaces)
    burdens = floor_burdens(_design(holes, params, contour))
    for pair in _pairs(holes):
        burden = burdens[pair.id]
        assert not burden.beyond_toe
        assert burden.value_m >= 0.8 * W - 1e-6, (pair.id, burden.value_m)


def test_pair_collar_not_in_concave_notch():
    # Выемка у бокового края (x 0–8, y 0,6–1,0): упор сдвига внутри блока, но
    # промежуточный сдвиг попал бы в выемку — устье пары всегда внутри контура.
    import shapely

    ring = [(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0), (0.0, 1.0), (8.0, 1.0), (8.0, 0.6), (0.0, 0.6)]
    contour = BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in ring],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=75.0),
    )
    holes = generate_pattern(contour, BASE | {"offset_from_face_m": 4.0})
    polygon = shapely.Polygon(ring).buffer(1e-6)
    pairs = _pairs(holes)
    assert pairs
    for pair in pairs:
        assert polygon.contains(shapely.Point(pair.collar.x, pair.collar.y)), (pair.id, pair.collar)


def test_floor_gap_limit_uses_domain_burden():
    # Сетка по доменам: у домена b = 7 м — предел разрыва у подошвы 7,21 м, а
    # не общий 3,605: пара доходит до ЛСП ≤ W + 3 %.
    from design.models import BlastDomain

    domain = BlastDomain(id="d", name="d", spacing_a_m=4.0, burden_b_m=7.0)
    params = BASE | {"pattern": "domain_dependent", "offset_from_face_m": 6.0}
    holes = generate_pattern(CONTOUR, params, domains=[domain])
    pairs = _pairs(holes)
    assert pairs
    burdens = floor_burdens(BlastDesign(design_id="t", contour=CONTOUR, holes=holes, pattern_params=params, domains=[domain]))
    for pair in pairs:
        assert burdens[pair.id].value_m <= GAP_MAX + 1e-6, (pair.id, burdens[pair.id].value_m)
