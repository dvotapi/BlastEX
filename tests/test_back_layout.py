"""Шаблон раскладки «от тыла» (PR 2): тыл, решётка от тыла, конец эшелона."""
import math

import pytest

from design.back_layout import BACK_SPLIT_TURN_DEG, back_azimuth_deg, back_side
from design.models import BenchSurface, BlockContour, Point3, logical_row

H = 10.0


def _contour(verts, free) -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=float(x), y=float(y), z=0.0) for x, y in verts],
        free_faces=[list(edge) for edge in free],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=75.0),
    )


def rect(width, height, free=([0, 1],)) -> BlockContour:
    """Прямоугольник против часовой; ребро [0, 1] — нижнее (y = 0)."""
    return _contour([(0, 0), (width, 0), (width, height), (0, height)], free)


def arc_back_block(width=40.0, side=20.0, sagitta=6.0, segments=12) -> BlockContour:
    """Бровка внизу, фланги по `side`, тыл — пологая дуга из `segments` рёбер.

    Излом внутри дуги ~5,5°, на стыке с флангами ~57°: дуга — одна сторона.
    """
    half = width / 2.0
    radius = (half * half + sagitta * sagitta) / (2.0 * sagitta)
    cy = side + sagitta - radius
    start = math.atan2(side - cy, half)
    end = math.pi - start
    arc = [
        (half + radius * math.cos(start + (end - start) * k / segments),
         cy + radius * math.sin(start + (end - start) * k / segments))
        for k in range(segments + 1)
    ]
    verts = [(0.0, 0.0), (width, 0.0)] + arc
    return _contour(verts, [[0, 1]])


def l_shaped_back() -> BlockContour:
    """Треугольник: бровка — гипотенуза, несвободная цепь 30 м и 12 м с изломом 90°."""
    return _contour([(0, 0), (30, 0), (30, 12)], [[2, 0]])


def test_split_turn_constant():
    assert BACK_SPLIT_TURN_DEG == 45.0


def test_back_of_rectangle_is_the_long_side_opposite_the_face():
    c = rect(40, 22, free=[[0, 1]])
    assert back_side(c) == [(40.0, 22.0), (0.0, 22.0)]
    assert back_azimuth_deg(c) == pytest.approx(90.0)


def test_arc_back_is_one_side():
    c = arc_back_block()
    side = back_side(c)
    assert len(side) == 13
    assert side[0] == pytest.approx((40.0, 20.0))
    assert side[-1] == pytest.approx((0.0, 20.0))
    assert back_azimuth_deg(c) == pytest.approx(90.0)


def test_sharp_corner_splits_sides_longest_wins():
    side = back_side(l_shaped_back())
    assert math.dist(side[0], side[-1]) == pytest.approx(30.0)
    assert back_azimuth_deg(l_shaped_back()) == pytest.approx(90.0)


def test_no_back_when_whole_contour_is_free():
    c = rect(40, 22, free=[[0, 1], [1, 2], [2, 3], [3, 0]])
    assert back_side(c) is None
    assert back_azimuth_deg(c) is None


def test_free_face_given_as_chain_of_indices():
    """Свободная поверхность цепью [0, 1, 2]: нижнее и правое рёбра; тыл — верхнее."""
    c = rect(40, 22, free=[[0, 1, 2]])
    assert back_side(c) == [(40.0, 22.0), (0.0, 22.0)]


def test_repeated_vertex_does_not_split_the_back():
    """Повтор вершины на тыле (чертёж) — вырожденное ребро, сторона не рвётся."""
    c = _contour([(0, 0), (40, 0), (40, 22), (20, 22), (20, 22), (0, 22)], [[0, 1]])
    side = back_side(c)
    assert side[0] == (40.0, 22.0) and side[-1] == (0.0, 22.0)


# --- Решётка от тыла (Task 2) ---------------------------------------------------

from design.back_layout import (  # noqa: E402
    BACK_BREAK_DIAMETERS,
    BACK_OFFSET_HALF_WIDTH_RATIO,
    back_columns,
    back_offset_m,
)
from design.geometry import local_basis  # noqa: E402


def _ring(c):
    return c.points_xy


def _dist_to_back(c, xy):
    import shapely

    return shapely.distance(shapely.Point(xy), shapely.LineString(back_side(c)))


def test_back_offset_constants_and_key():
    # Линия отрыва за последним рядом — 20·d, d — диаметр скважины с вкладки
    # «Сетка»: он уже с учётом разбуривания (маркшейдер, решение владельца 07.11.2026).
    assert BACK_BREAK_DIAMETERS == 20.0
    assert BACK_OFFSET_HALF_WIDTH_RATIO == 0.15
    assert back_offset_m({"diameter_mm": 145}) == pytest.approx(2.9)
    assert back_offset_m({}) == pytest.approx(20 * 0.152)  # диаметр по умолчанию генератора
    assert back_offset_m({"back_offset_m": 3, "diameter_mm": 145}) == 3.0
    for bad in (None, 0, -1, float("nan"), "x", ""):
        assert back_offset_m({"back_offset_m": bad, "diameter_mm": 145}) == pytest.approx(2.9)
        assert back_offset_m({"diameter_mm": bad}) == pytest.approx(20 * 0.152)


def test_first_node_corridor_is_centred_on_offset():
    """Коридор первого узла — отступ ± 0,15·b, а не 0,5–0,8·b: при отступе
    3,045 м и b = 3,7 первый узел столбца на дуге тыла — ближайший к коридору
    вокруг отступа, а не к 1,85–2,96 м (тогда узлы в 4,25–4,9 м от тыла
    уступали узлу в 0,55–1,2 м)."""
    from design.geometry import point_in_polygon

    b = 3.7
    offset = 20 * 0.145 * 1.05
    lo, hi = offset - 0.15 * b, offset + 0.15 * b

    def gap(d):
        return max(lo - d, d - hi, 0.0)

    c = arc_back_block()
    checked = 0
    for shift in (0.0, 0.9, 1.8, 2.7):
        for col in back_columns(c, _ring(c), 90.0, 3.7, b, offset, shift):
            d = _dist_to_back(c, col.nodes[0])
            x0, y0 = col.nodes[0]
            for j in (-2, -1, 1, 2):
                xy = (x0, y0 - j * b)
                if point_in_polygon(xy, _ring(c)):
                    assert gap(_dist_to_back(c, xy)) >= gap(d) - 1e-9, (shift, col.index, d)
                    checked += 1
    assert checked


def test_straight_back_first_row_at_offset():
    c = rect(40, 30)
    columns = back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 0.0)
    assert len(columns) >= 7
    for column in columns:
        x, y = column.nodes[0]
        assert y == pytest.approx(30.0 - 2.6)
        assert column.rows[0] == 0


def test_columns_are_parallel_and_step_b():
    c = rect(40, 30)
    columns = back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 0.0)
    row_dir, _ = local_basis(90.0)
    xs = []
    for column in columns:
        for (x0, y0), (x1, y1), r0, r1 in zip(column.nodes, column.nodes[1:], column.rows, column.rows[1:]):
            assert math.hypot(x1 - x0, y1 - y0) == pytest.approx(4.0)
            assert (x1 - x0) * row_dir[0] + (y1 - y0) * row_dir[1] == pytest.approx(0.0, abs=1e-9)
            assert y1 < y0  # к бровке (y = 0)
            assert r1 == r0 + 1
        xs.append(column.nodes[0][0])
    steps = [b - a for a, b in zip(xs, xs[1:])]
    assert all(s == pytest.approx(5.0) for s in steps)


def test_nodes_inside_boundary_only():
    from design.geometry import point_in_polygon

    c = rect(40, 30)
    for column in back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 0.0):
        assert all(point_in_polygon(xy, _ring(c)) for xy in column.nodes)


def test_shift_along_moves_columns_by_phase():
    c = rect(40, 30)
    base = back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 0.0)
    moved = back_columns(c, _ring(c), 90.0, 5.0, 4.0, 2.6, 1.5)
    bx = sorted(col.nodes[0][0] for col in base)
    mx = sorted(col.nodes[0][0] for col in moved)
    assert {round((m - bx[0]) % 5.0, 6) for m in mx} == {1.5}


def test_arc_back_first_row_is_a_staircase():
    """Дуга: первый узел каждого эшелона — узел решётки в коридоре отступ ± 0,15·b
    (здесь 0,5–0,8·b), а если такого нет — ближайший к коридору; первые узлы не
    на одной прямой."""
    from design.geometry import point_in_polygon

    b = 4.0
    c = arc_back_block()
    # Сдвиг 1 м: эшелоны не на флангах (узел на ребре контура — пограничный случай).
    columns = back_columns(c, _ring(c), 90.0, 4.0, b, 0.65 * b, 1.0)
    assert len(columns) >= 8
    firsts = [col.nodes[0] for col in columns]
    assert len({round(y, 6) for _, y in firsts}) > 1  # лесенка
    in_range = 0
    for col in columns:  # в диапазоне — не все: решётка одна, шаг b больше ширины диапазона
        d = _dist_to_back(c, col.nodes[0])
        gap = max(0.5 * b - d, d - 0.8 * b, 0.0)
        in_range += gap == 0.0
        # Ни один другой узел решётки этого эшелона внутри блока не ближе к диапазону.
        x0, y0 = col.nodes[0]
        for j in range(-6, 7):
            xy = (x0, y0 - j * b)
            if j == 0 or not point_in_polygon(xy, _ring(c)):
                continue
            dj = _dist_to_back(c, xy)
            assert max(0.5 * b - dj, dj - 0.8 * b, 0.0) >= gap - 1e-9
        assert 0.15 * b - 1e-9 <= d <= 1.15 * b + 1e-9
    assert in_range >= 1
    # Ряд решётки — один на всю сетку: у узлов на одной высоте один номер ряда.
    rows_by_y = {}
    for col in columns:
        for (x, y), r in zip(col.nodes, col.rows):
            rows_by_y.setdefault(round(y, 6), set()).add(r)
    assert all(len(rs) == 1 for rs in rows_by_y.values())
    assert min(r for col in columns for r in col.rows) == 0


# --- Конец эшелона у бровки (Task 4) --------------------------------------------

from design.back_layout import back_grid  # noqa: E402
from design.toe_line import floor_point, toe_positions  # noqa: E402

# Прямоугольник 40×30, бровка y = 0, тыл y = 30; уступ 10 м, откос 75°:
# линия подошвы y = −2,68, ЛСП вертикальной с устьем в y — y + 2,68.
SLOPE_M = H * math.tan(math.radians(15.0))
W = 3.5
ALLOWED = W * 1.03
END = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": W,
    "row_azimuth_deg": 90.0,
    "subdrill_m": 1.0,
    # Явно: умолчание бэкенда меняется отдельным PR (решение владельца 06.11.2026).
    "min_crest_offset_m": 0.5,
}


def _end_params(back_offset, **extra):
    return {**END, "back_offset_m": back_offset, **extra}


def _lsp(contour, hole):
    return toe_positions(contour, [floor_point(hole)], [contour.bench.height_m])[0].distance_m


def _angle(hole):
    dx, dy, dz = hole.toe.x - hole.collar.x, hole.toe.y - hole.collar.y, hole.toe.z - hole.collar.z
    return math.degrees(math.atan2(math.hypot(dx, dy), -dz))


def _echelons(holes):
    by_col = {}
    for h in holes:
        by_col.setdefault(h.col, []).append(h)
    return [sorted(v, key=lambda h: -h.collar.y) for _, v in sorted(by_col.items())]


def test_last_hole_fits_nothing_added():
    """Последняя в y = 0,8: ЛСП 3,48 ≤ 3,605 — все вертикальные, только узлы решётки."""
    c = rect(40, 30)
    holes = back_grid(c, _end_params(1.2), c.points_xy)
    for echelon in _echelons(holes):
        assert len(echelon) == 9
        assert echelon[-1].collar.y == pytest.approx(0.8)
        assert all(_angle(h) == pytest.approx(0.0, abs=1e-9) for h in echelon)
        assert _lsp(c, echelon[-1]) <= ALLOWED
    assert all(h.kind == "production" and h.source == "generated" for h in holes)


def _floor_gap(a, b):
    (ax, ay), (bx, by) = floor_point(a), floor_point(b)
    return math.hypot(ax - bx, ay - by)


def test_last_hole_tilted_toward_face():
    """Последняя в y = 1,0: ЛСП 3,68 > 3,605 — наклон к откосу; угол ограничен
    разрывом у подошвы до предыдущей ≤ b + 3 % (анти-цель спецификации)."""
    c = rect(40, 30)
    holes = back_grid(c, _end_params(1.0), c.points_xy)
    for echelon in _echelons(holes):
        assert len(echelon) == 9
        last = echelon[-1]
        assert last.collar.y == pytest.approx(1.0)
        assert 0.0 < _angle(last) <= 30.0 + 1e-9
        assert last.toe.y < last.collar.y  # к бровке
        assert 0.8 * W - 1e-6 <= _lsp(c, last) <= ALLOWED + 1e-6
        assert _floor_gap(echelon[-2], last) <= ALLOWED + 1e-6
        assert all(_angle(h) == pytest.approx(0.0, abs=1e-9) for h in echelon[:-1])


def test_last_hole_tilt_is_the_least_angle_to_w():
    """Эшелон из одного узла (y = 1,0, ЛСП 3,68, предыдущей нет — разрыв не
    ограничивает): угол — наименьший, при котором ЛСП ≈ W, а не наибольший до
    0,8·W (решение владельца 06.11.2026, как у пары)."""
    c = rect(40, 3)
    holes = back_grid(c, _end_params(2.0), c.points_xy)
    assert holes
    for echelon in _echelons(holes):
        assert len(echelon) == 1
        last = echelon[0]
        assert last.collar.y == pytest.approx(1.0)
        assert _angle(last) > 0.0
        assert _lsp(c, last) == pytest.approx(W, abs=0.01)


def test_tilt_breaking_floor_gap_gives_way_to_remainder():
    """Последняя в y = 3,0: ЛСП 5,68. Наклон, который вводит ЛСП в допуск,
    разрывает подошву до предыдущей больше b + 3 % — вместо него скважина на остатке."""
    c = rect(40, 30)
    holes = back_grid(c, _end_params(2.5), c.points_xy)
    for echelon in _echelons(holes):
        assert len(echelon) == 9
        last, extra = echelon[-2], echelon[-1]
        assert last.collar.y == pytest.approx(3.0)
        assert _angle(last) == pytest.approx(0.0, abs=1e-9)
        assert _angle(extra) == pytest.approx(0.0, abs=1e-9)
        assert _lsp(c, extra) == pytest.approx(W, abs=0.01)


def test_remainder_tilts_when_vertical_does_not_fit():
    """Последняя в y = 1,82: ЛСП 4,5. Вертикальный остаток должен встать на
    0,4·min(a, b) = 1,4 м впереди (y = 0,42) — ближе отступа 0,5 м к бровке.
    Остаток — устье в 0,5 м от бровки (1,32 м от последней) с наклоном к
    откосу ровно таким, чтобы у подошвы он стоял впереди последней на 1,4 м."""
    from design.toe_line import floor_burdens

    c = rect(40, 30)
    params = _end_params(3.68)
    holes = back_grid(c, params, c.points_xy)
    for echelon in _echelons(holes):
        assert len(echelon) == 9
        last, extra = echelon[-2], echelon[-1]
        assert last.collar.y == pytest.approx(1.82)
        assert _angle(last) == pytest.approx(0.0, abs=1e-9)
        assert extra.collar.y == pytest.approx(0.5, abs=1e-3)
        assert last.collar.y - extra.collar.y >= 1.0
        assert 0.0 < _angle(extra) <= 30.0
        assert extra.toe.y < extra.collar.y
        advance = floor_point(last)[1] - floor_point(extra)[1]
        assert advance == pytest.approx(0.4 * W, abs=0.01)
        assert 0.8 * W - 1e-6 <= _lsp(c, extra) <= ALLOWED + 1e-6
        assert (logical_row(extra.row), extra.col) == (logical_row(last.row) - 1, last.col)
    burdens = floor_burdens(BlastDesign(design_id="t", contour=c, holes=holes, pattern_params=params))
    assert all(not v.excess and not v.short for v in burdens.values())


def test_remainder_is_ahead_along_the_corridor_not_the_column():
    """Ряды косо к бровке (азимут 80°): путь к подошве отклонён от столбца на
    10°. Остаток должен стоять впереди последней на 0,4·min(a, b) по этому
    пути (как считает проверка ЛСП), а не только по столбцу."""
    from design.toe_line import floor_burdens

    c = rect(60, 30)
    params = {**_end_params(3.3, front_rows_tilt_deg=0), "row_azimuth_deg": 80.0}
    holes = back_grid(c, params, c.points_xy)
    burdens = floor_burdens(BlastDesign(design_id="t", contour=c, holes=holes, pattern_params=params))
    remainders = 0
    for echelon in _echelons(holes):
        last, extra = echelon[-2], echelon[-1]
        if math.dist((last.collar.x, last.collar.y), (extra.collar.x, extra.collar.y)) < W - 1e-6:
            remainders += 1
            assert last.id not in burdens  # остаток закрывает последнюю
            assert not burdens[extra.id].excess
    assert remainders >= 5


def test_no_tilted_remainder_when_tilt_is_off():
    """Наклон выключен (0°): наклонного остатка нет — последняя остаётся вертикальной."""
    c = rect(40, 30)
    holes = back_grid(c, _end_params(3.68, front_rows_tilt_deg=0), c.points_xy)
    for echelon in _echelons(holes):
        assert len(echelon) == 8
        assert all(_angle(h) == pytest.approx(0.0, abs=1e-9) for h in echelon)


def test_remainder_hole_added_when_tilt_is_not_enough():
    """Наклон выключен (0°), последняя в y = 3: ЛСП 5,68 — вертикальная на остатке с ЛСП ≈ W."""
    c = rect(40, 30)
    holes = back_grid(c, _end_params(2.5, front_rows_tilt_deg=0), c.points_xy)
    for echelon in _echelons(holes):
        assert len(echelon) == 9
        last, extra = echelon[-2], echelon[-1]
        assert last.collar.y == pytest.approx(3.0)
        assert _angle(last) == pytest.approx(0.0, abs=1e-9)
        assert _angle(extra) == pytest.approx(0.0, abs=1e-9)
        assert _lsp(c, extra) == pytest.approx(W, abs=0.01)
        step = last.collar.y - extra.collar.y
        assert 1.0 <= step < W
        assert extra.collar.y >= 0.5
        assert extra.collar.x == pytest.approx(last.collar.x)
        assert (logical_row(extra.row), extra.col) == (logical_row(last.row) - 1, last.col)
        assert extra.kind == "production"


def test_remainder_closes_the_last_hole_in_floor_burdens():
    """Остаток не ближе 0,4·min(a, b) (порог «впереди» у ЛСП) к последней: иначе
    проверка ЛСП не считает последнюю закрытой и показывает у неё превышение.
    Последняя в y = 2,2 (ЛСП 4,88), наклон выключен: остаток в 1,1 м с ЛСП = W
    не закрыл бы её — остаток ставится на 1,4 м (ЛСП 3,48), а не ближе."""
    from design.toe_line import floor_burdens

    c = rect(40, 30)
    params = _end_params(3.3, front_rows_tilt_deg=0)
    holes = back_grid(c, params, c.points_xy)
    for echelon in _echelons(holes):
        last, extra = echelon[-2], echelon[-1]
        assert last.collar.y == pytest.approx(2.2)
        assert last.collar.y - extra.collar.y == pytest.approx(0.4 * W, abs=1e-4)
    burdens = floor_burdens(BlastDesign(design_id="t", contour=c, holes=holes, pattern_params=params))
    assert all(not v.excess for v in burdens.values())


def test_last_regular_too_close_is_dropped():
    """Узел в 0,3 м от бровки убран; конец эшелона — от узла в y = 3,8 (ЛСП
    6,48): наклон разорвал бы подошву, поэтому скважина на остатке."""
    c = rect(40, 30)
    holes = back_grid(c, _end_params(1.7), c.points_xy)
    assert all(h.collar.y >= 0.5 for h in holes)
    for echelon in _echelons(holes):
        last, extra = echelon[-2], echelon[-1]
        assert last.collar.y == pytest.approx(3.8)
        assert logical_row(extra.row) == logical_row(last.row) - 1
        assert _lsp(c, extra) <= ALLOWED + 1e-6


def test_echelon_without_nodes_is_empty():
    """Узкая полоса у бровки: узлы ближе отступа к бровке — эшелонов нет, без ошибок."""
    c = rect(40, 0.8)
    assert back_grid(c, _end_params(0.4), c.points_xy) == []
    assert back_grid(c, _end_params(2.0), c.points_xy) == []


def test_remainder_closer_than_one_metre_falls_back_to_max_tilt():
    """Откос 45°: ЛСП последней (y = 1,2) 11,2, наклона мало, места для остатка
    (0,7 м до отступа 0,5 м) нет — последняя с наибольшим допустимым углом:
    его ограничивает разрыв у подошвы до предыдущей (≤ b + 3 %)."""
    c = _contour([(0, 0), (40, 0), (40, 30), (0, 30)], [[0, 1]])
    c.bench = BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=45.0)
    holes = back_grid(c, _end_params(0.8), c.points_xy)
    for echelon in _echelons(holes):
        assert len(echelon) == 9
        last = echelon[-1]
        assert last.collar.y == pytest.approx(1.2)
        assert _angle(last) > 0.0
        assert _floor_gap(echelon[-2], last) == pytest.approx(ALLOWED, abs=1e-3)
        assert _lsp(c, last) > ALLOWED


def test_without_w_only_regular_nodes():
    """Без W (нет `burden_b_m`) — только узлы решётки, без наклона и остатка."""
    c = rect(40, 30)
    params = {k: v for k, v in _end_params(3.68).items() if k != "burden_b_m"}
    params["spacing_a_m"] = 4.0
    holes = back_grid(c, {**params, "burden_b_m": None}, c.points_xy)
    assert holes
    assert all(_angle(h) == pytest.approx(0.0, abs=1e-9) for h in holes)


# --- Режим «от тыла» в generate_pattern (Task 5) ----------------------------------

from design.analysis import validate  # noqa: E402
from design.models import BlastDesign  # noqa: E402
from design.pattern import LAYOUT_ANCHOR_BACK, generate_pattern  # noqa: E402

BACK_MODE = {**END, "back_offset_m": 3.68, "layout_anchor": "back"}


def _collars(holes):
    return sorted((round(h.collar.x, 6), round(h.collar.y, 6), round(h.toe.x, 6), round(h.toe.y, 6)) for h in holes)


def test_layout_anchor_constant():
    assert LAYOUT_ANCHOR_BACK == "back"


def test_back_mode_generates_back_grid():
    c = rect(40, 30)
    holes = generate_pattern(c, BACK_MODE)
    assert _collars(holes) == _collars(back_grid(c, BACK_MODE, c.points_xy))
    assert len({h.id for h in holes}) == len(holes)
    assert not [h for h in holes if h.kind == "face_toe"]


def test_back_mode_ignores_front_rows_mode():
    c = rect(40, 30)
    holes = generate_pattern(c, {**BACK_MODE, "front_rows_mode": "pair", "front_rows_tilt_count": 1})
    assert _collars(holes) == _collars(back_grid(c, BACK_MODE, c.points_xy))


def test_back_mode_ignored_for_staggered():
    c = rect(40, 30)
    plain = {**END, "pattern": "staggered"}
    assert _collars(generate_pattern(c, {**plain, "layout_anchor": "back"})) == _collars(generate_pattern(c, plain))


def test_back_mode_without_back_falls_back():
    c = rect(40, 30, free=[[0, 1], [1, 2], [2, 3], [3, 0]])
    assert _collars(generate_pattern(c, BACK_MODE)) == _collars(generate_pattern(c, END))


def test_back_mode_keeps_walls():
    c = rect(40, 30)
    holes = generate_pattern(c, {**BACK_MODE, "contour_row": True, "contour_spacing_m": 2.0})
    assert any(h.kind == "contour" for h in holes)


def test_back_mode_passes_validate_rejects():
    c = rect(40, 30)
    for offset in (1.0, 1.2, 1.7, 2.5, 3.68):
        params = {**BACK_MODE, "back_offset_m": offset}
        holes = generate_pattern(c, params)
        design = BlastDesign(design_id="t", contour=c, holes=holes, pattern_params=params)
        codes = {w["code"] for w in validate(design)}
        assert not codes & {"floor_beyond_toe", "floor_row_gap_excess", "collar_too_close_to_crest"}, (offset, codes)


# --- Ряды от откоса, как у всего конвейера (финальное ревью) ----------------------



def test_rows_are_numbered_from_the_face():
    """Ряд 0 — у бровки, к тылу номера растут (как у раскладки от бровки:
    тайминг, монтаж, стабилизация считают ряд 0 первым у откоса)."""
    c = rect(40, 30)
    holes = generate_pattern(c, {**BACK_MODE, "back_offset_m": 1.2})
    front = min(logical_row(h.row) for h in holes)
    assert front == 0
    nearest = min(holes, key=lambda h: h.collar.y)
    farthest = max(holes, key=lambda h: h.collar.y)
    assert logical_row(nearest.row) == 0
    assert logical_row(farthest.row) == max(logical_row(h.row) for h in holes)


def test_remainder_is_one_row_ahead_of_the_last():
    """Остаток — на ряд впереди последней: у последней в ряду 0 — ряд впереди
    (`FRONT_ROW_BASE − 1`, логический −1)."""
    c = rect(40, 30)
    holes = back_grid(c, _end_params(2.5), c.points_xy)
    for echelon in _echelons(holes):
        last, extra = echelon[-2], echelon[-1]
        assert logical_row(extra.row) == logical_row(last.row) - 1
        assert logical_row(last.row) == 0


def test_stab_row_and_row_timing_start_at_the_face():
    from design.timing import build_template_network, resolve_times

    c = rect(40, 30)
    params = {**BACK_MODE, "back_offset_m": 1.2, "stab_row": True}
    holes = generate_pattern(c, params)
    stab = [h for h in holes if h.kind == "stab"]
    assert stab and max(h.collar.y for h in stab) < 5.0
    network = build_template_network(holes, "row", {})
    times, _ = resolve_times(network, holes)
    by_id = {h.id: h for h in holes}
    first = min(times, key=times.get)
    last = max(times, key=times.get)
    assert by_id[first].collar.y < by_id[last].collar.y


# --- Ревью PR #154 ---------------------------------------------------------


def test_no_toe_line_keeps_the_lattice(monkeypatch):
    """Бровка есть, а линию подошвы построить не удалось (`toe_positions` —
    None): конец эшелона не считается, решётка остаётся, а не стирается
    шагом «ЛСП < 0,8·W» (ЛСП без подошвы — не 0)."""
    import design.back_layout as back_layout

    c = rect(40, 30)
    expected = len(back_grid(c, _end_params(1.2), c.points_xy))
    monkeypatch.setattr(back_layout, "toe_positions", lambda *a, **k: None)
    holes = back_grid(c, _end_params(1.2), c.points_xy)
    assert len(holes) == expected > 0
    assert all(_angle(h) == pytest.approx(0.0, abs=1e-9) for h in holes)


def test_back_anchor_turns_on_crest_offset_check():
    """У паспорта «от тыла» без `min_crest_offset_m` проверка отступа устья от
    кромки включена: шаблон ставит устья у самой кромки, перебор проверяет
    отступ всегда — `validate` не должен молчать."""
    from design.toe_line import crest_offset_checked

    assert crest_offset_checked({"pattern": "rectangular", "layout_anchor": "back"})
    assert not crest_offset_checked({"pattern": "rectangular"})


def test_gap_limit_counts_skipped_rows():
    """Эшелон с выходом из контура: предыдущая скважина на два ряда позади.
    Предел разрыва у подошвы — |Δряд|·b (как у проверки `_row_gaps`), а не b:
    иначе наклон режется до 0 там, где проверка разрыва не видит (допуск 3 % —
    тоже от 2b, поэтому угол не меньше, чем при соседней предыдущей)."""
    from design.back_layout import _gap_limited_angle
    from design.geometry import drape_collar
    from design.models import Hole

    c = rect(40, 30)

    def make(x, y, row, col, angle, azimuth):
        collar, toe = drape_collar(x, y, angle, azimuth, 1.0, c, None, None)
        return Hole(id=f"{row}-{col}", row=row, col=col, collar=collar, toe=toe, diameter_mm=152.0, subdrill_m=1.0)

    advance = (0.0, -1.0)
    corridor = (0.0, -1.0)
    hole = make(20.0, 1.0, 3, 0, 0.0, 180.0)
    adjacent = make(20.0, 1.0 + W, 2, 0, 0.0, 180.0)
    skipped = make(20.0, 1.0 + 2 * W, 1, 0, 0.0, 180.0)
    near = _gap_limited_angle(c, hole, adjacent, corridor, 30.0, 180.0, advance, W, make)
    far = _gap_limited_angle(c, hole, skipped, corridor, 30.0, 180.0, advance, W, make)
    assert 0.0 < near < 30.0
    assert near <= far < 30.0


def test_over_tolerance_vertical_remainder_gives_way_to_tilted():
    """Codex, PR #154: на наибольшем шаге вертикальный остаток с ЛСП > W + 3 %,
    а наклонный (~5°) входит в допуск — ставится наклонный. Прямоугольник
    40×30, подошва в y = −4 (откос ≈ 68,2°), отступ от тыла 3,3: последняя в y = 2,2."""
    c = BlockContour(
        vertices=[Point3(x=float(x), y=float(y), z=0.0) for x, y in [(0, 0), (40, 0), (40, 30), (0, 30)]],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-H, face_angle_deg=math.degrees(math.atan2(H, 4.0))),
    )
    holes = back_grid(c, _end_params(3.3), c.points_xy)
    for echelon in _echelons(holes):
        last, extra = echelon[-2], echelon[-1]
        assert last.collar.y == pytest.approx(2.2)
        assert 0.0 < _angle(extra) <= 30.0
        assert 0.8 * W - 1e-6 <= _lsp(c, extra) <= ALLOWED + 1e-6
        assert _floor_gap(last, extra) <= ALLOWED + 1e-6


def test_back_mode_default_offset_is_twenty_diameters():
    """Без ключа `back_offset_m` приконтурный ряд — в 20·d от тыла, d — диаметр скважины."""
    c = rect(40, 30)
    params = {k: v for k, v in BACK_MODE.items() if k != "back_offset_m"} | {"diameter_mm": 145.0}
    holes = generate_pattern(c, params)
    top = max(h.collar.y for h in holes if h.kind == params.get("default_kind", "production"))
    assert top == pytest.approx(30.0 - 2.9, abs=1e-6)
