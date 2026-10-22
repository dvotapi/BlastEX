"""Линия подошвы откоса: по съёмке нижней бровки или от верхней бровки по углу."""
from __future__ import annotations

import math

import pytest
from shapely.geometry import LineString
from shapely.geometry import Point as ShapelyPoint

from design.models import BenchSurface, BlastDesign, BlockContour, Hole, Point3
from design.maps import engineering_maps
from design.toe_line import (
    allowed_floor_burden_m,
    floor_burdens,
    floor_row_gaps,
    holes_beyond_toe,
    slope_offset_m,
    spoil_angle_toe_lines,
    toe_line,
    toe_positions,
)

PATTERN = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.7}


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
    assert line.source == "angle"
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
    assert toe_line(contour).source == "angle"


def test_survey_without_own_edges_falls_back_to_built():
    # Нижняя бровка не найдена: кольцо совпадает с верхним контуром (S низ = S верх).
    contour = rect_contour(cad={"bottom": [[0, 0], [40, 0], [40, 22], [0, 22]]})
    assert toe_line(contour).source == "angle"


def test_no_free_faces_gives_none():
    assert toe_line(rect_contour(free_faces=[])) is None


def vertical_hole(hole_id, x, y, row, subdrill=1.0, kind="production", enabled=True, bench_h=10.0) -> Hole:
    return Hole(
        id=hole_id, row=row, col=0, collar=Point3(x, y, 0.0),
        toe=Point3(x, y, -(bench_h + subdrill)), diameter_mm=215.0,
        subdrill_m=subdrill, kind=kind, enabled=enabled,
    )


def inclined_hole(hole_id, x, y, row, angle_deg, azimuth_deg, bench_h=10.0, subdrill=1.0) -> Hole:
    # Перебор откладывается вдоль оси: до подошвы (глубина H) ось идёт H / cos α,
    # забой — ещё на subdrill дальше по оси.
    a = math.radians(angle_deg)
    az = math.radians(azimuth_deg)
    length = bench_h / math.cos(a) + subdrill
    horizontal = length * math.sin(a)
    return Hole(
        id=hole_id, row=row, col=0, collar=Point3(x, y, 0.0),
        toe=Point3(x + horizontal * math.sin(az), y + horizontal * math.cos(az), -length * math.cos(a)),
        diameter_mm=215.0, subdrill_m=subdrill,
    )


def design_with(holes, pattern_params=None) -> BlastDesign:
    return BlastDesign(
        design_id="t", contour=rect_contour(), holes=holes,
        pattern_params=PATTERN if pattern_params is None else pattern_params,
    )


def test_vertical_hole_floor_burden_adds_slope_offset():
    hole = vertical_hole("1-01", x=10, y=3.7, row=0, subdrill=1.0)
    fb = floor_burdens(design_with([hole]))["1-01"]
    assert fb.value_m == pytest.approx(3.7 + 2.6795, abs=1e-3)
    assert fb.allowed_m == pytest.approx(3.811)
    assert fb.excess is True


def test_hole_inclined_15_degrees_to_face_cancels_offset():
    # Наклон 15° к откосу (азимут 180° — к линии y = 0): на глубине H = 10 м ось
    # уходит к откосу на 2,6795 м — ровно на смещение подошвы. ЛСП = расстоянию
    # от устья до верхней бровки.
    hole = inclined_hole("1-01", x=10, y=3.7, row=0, angle_deg=15, azimuth_deg=180, bench_h=10, subdrill=1.0)
    assert floor_burdens(design_with([hole]))["1-01"].value_m == pytest.approx(3.7, abs=1e-3)


def test_within_three_percent_is_not_excess():
    hole = vertical_hole("1-01", x=10, y=3.8 - 2.6795, row=0)
    assert floor_burdens(design_with([hole]))["1-01"].excess is False


def test_second_row_hole_has_no_floor_burden():
    first = vertical_hole("1-01", x=10, y=1.0, row=0)
    second = vertical_hole("2-01", x=10, y=4.7, row=1)
    result = floor_burdens(design_with([first, second]))
    assert "1-01" in result and "2-01" not in result


def test_walls_and_disabled_holes_are_skipped():
    wall = vertical_hole("K1-01", x=10, y=1.0, row=-1, kind="contour")
    off = vertical_hole("1-02", x=20, y=1.0, row=0, enabled=False)
    assert floor_burdens(design_with([wall, off])) == {}


def test_only_production_holes_get_floor_burden():
    satellite = vertical_hole("S1", x=10, y=1.0, row=0, kind="satellite")
    assert floor_burdens(design_with([satellite])) == {}


def test_square_pattern_uses_spacing_as_w():
    assert allowed_floor_burden_m({"pattern": "square", "spacing_a_m": 4.0}) == pytest.approx(4.12)


def test_no_w_means_no_check():
    hole = vertical_hole("1-01", x=10, y=20.0, row=0)
    fb = floor_burdens(design_with([hole], pattern_params={}))["1-01"]
    assert fb.allowed_m is None and fb.excess is False


def face_design() -> BlastDesign:
    """Прямоугольник 40×22 м, откос 75°: 1-01 у свободной грани (ЛСП 6,38 м), 2-01 — второй ряд."""
    return design_with([vertical_hole("1-01", 10, 3.7, 0), vertical_hole("2-01", 10, 7.4, 1)])


# --- Съёмка нижней бровки: выбор рёбер не зависит от угла откоса -------------


def test_flat_angle_is_clamped_to_30_degrees():
    flat = BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=1)
    at_30 = BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=30)
    assert slope_offset_m(flat) == pytest.approx(slope_offset_m(at_30))
    assert slope_offset_m(at_30) == pytest.approx(10 * math.tan(math.radians(60)))


def test_survey_used_with_vertical_face_angle():
    contour = rect_contour(cad={"bottom": [[0, -2.68], [40, -2.68], [40, 22], [0, 22]]})
    contour.bench.face_angle_deg = 90.0
    line = toe_line(contour)
    assert line.source == "survey"
    assert {round(y, 6) for poly in line.polylines for _, y in poly} == {-2.68}


def test_legacy_passport_with_default_angle_uses_survey():
    # Старый паспорт: угол не задан (умолчание 90°), съёмка нижней бровки есть.
    contour = BlockContour(
        vertices=[Point3(0, 0, 0), Point3(40, 0, 0), Point3(40, 22, 0), Point3(0, 22, 0)],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0, toe_z_m=-10),
        cad={"bottom": [[0, -2.68], [40, -2.68], [40, 22], [0, 22]]},
    )
    assert contour.bench.face_angle_deg == 90.0
    line = toe_line(contour)
    assert line.source == "survey"
    assert {round(y, 6) for poly in line.polylines for _, y in poly} == {-2.68}


def test_survey_farther_than_entered_angle_is_taken_whole():
    # Реальный откос положе введённого: подошва в 5,77 м (60°), угол на блоке 75°.
    toe = [[x, -5.77] for x in range(0, 41)]
    contour = rect_contour(cad={"bottom": [*toe, [40, 22], [0, 22]]})
    line = toe_line(contour)
    assert line.source == "survey"
    assert {round(y, 6) for poly in line.polylines for _, y in poly} == {-5.77}
    xs = [x for poly in line.polylines for x, _ in poly]
    assert min(xs) == pytest.approx(0) and max(xs) == pytest.approx(40)


def test_dense_flank_vertices_shared_with_top_are_not_toe_line():
    # Фланги контура — вершины через 1 м (как у контура из чертежа); кольцо по
    # нижней бровке делит их с верхним контуром и продлевает фланги до подошвы.
    right = [(40.0, float(y)) for y in range(1, 22)]
    left = [(0.0, float(y)) for y in range(21, 0, -1)]
    top = [(0.0, 0.0), (40.0, 0.0), *right, (40.0, 22.0), (0.0, 22.0), *left]
    toe = [(float(x), -2.68) for x in range(0, 41, 5)]
    bottom = [(0.0, 0.0), *toe, (40.0, 0.0), *right, (40.0, 22.0), (0.0, 22.0), *left]
    contour = BlockContour(
        vertices=[Point3(x, y, 0) for x, y in top],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75),
        cad={"bottom": [list(p) for p in bottom]},
    )
    line = toe_line(contour)
    assert line.source == "survey"
    assert all(y == pytest.approx(-2.68) for poly in line.polylines for _, y in poly)


# --- Съёмка с развалом: ЛСП по углу ---------------------------------------


def spoil_contour() -> BlockContour:
    # H = 10 м. Левая половина фронта: подошва по съёмке в 3 м от бровки (откос);
    # правая — в 12 м (> H: развал), переход — наклонное ребро.
    return rect_contour(cad={"bottom": [[0, -3], [20, -3], [24, -12], [40, -12], [40, 22], [0, 22]]})


def test_survey_spoil_part_uses_angle_line_near_part_keeps_survey():
    near = vertical_hole("1-01", x=5, y=1.0, row=0)
    far = vertical_hole("1-02", x=35, y=1.0, row=0)
    design = BlastDesign(design_id="t", contour=spoil_contour(), holes=[near, far], pattern_params=PATTERN)
    result = floor_burdens(design)
    assert result["1-01"].toe_source == "survey"
    assert result["1-01"].value_m == pytest.approx(4.0, abs=1e-3)
    assert result["1-02"].toe_source == "angle"
    assert result["1-02"].value_m == pytest.approx(1.0 + 2.6795, abs=1e-3)


def test_survey_within_bench_height_is_kept():
    # Подошва в 9,9 м от бровки при H = 10 м — откос, хоть и пологий.
    contour = rect_contour(cad={"bottom": [[0, -9.9], [40, -9.9], [40, 22], [0, 22]]})
    hole = vertical_hole("1-01", x=10, y=1.0, row=0)
    fb = floor_burdens(BlastDesign(design_id="t", contour=contour, holes=[hole], pattern_params=PATTERN))["1-01"]
    assert fb.toe_source == "survey"
    assert fb.value_m == pytest.approx(10.9, abs=1e-3)


def test_spoil_with_default_90_degrees_uses_15_from_vertical():
    # Старый черновик: угол 90° (умолчание сервера). Подошва по углу вместо
    # развала — 15° от вертикали, а не бровка: иначе ЛСП занижена.
    contour = spoil_contour()
    contour.bench.face_angle_deg = 90.0
    far = vertical_hole("1-02", x=35, y=1.0, row=0)
    fb = floor_burdens(BlastDesign(design_id="t", contour=contour, holes=[far], pattern_params=PATTERN))["1-02"]
    assert fb.toe_source == "angle"
    assert fb.value_m == pytest.approx(1.0 + 2.6795, abs=1e-3)


def test_no_survey_with_90_degrees_keeps_crest_as_toe():
    # Без съёмки угол блока берётся как есть: 90° — подошва под бровкой.
    contour = rect_contour()
    contour.bench.face_angle_deg = 90.0
    hole = vertical_hole("1-01", x=10, y=3.7, row=0)
    fb = floor_burdens(BlastDesign(design_id="t", contour=contour, holes=[hole], pattern_params=PATTERN))["1-01"]
    assert fb.toe_source == "angle"
    assert fb.value_m == pytest.approx(3.7, abs=1e-3)


def test_spoil_threshold_and_offset_use_hole_bench_height():
    # Съёмка правой части — в 12 м от бровки. H = 6 и 10 м: развал, ЛСП по углу
    # с высотой своей скважины; H = 14 м: 12 < 14 — откос, ЛСП по съёмке.
    low = vertical_hole("1-01", x=34, y=1.0, row=0, bench_h=6.0)
    mid = vertical_hole("1-02", x=36.5, y=1.0, row=0, bench_h=10.0)
    high = vertical_hole("1-03", x=39, y=1.0, row=0, bench_h=14.0)
    design = BlastDesign(design_id="t", contour=spoil_contour(), holes=[low, mid, high], pattern_params=PATTERN)
    result = floor_burdens(design)
    tan15 = math.tan(math.radians(15))
    assert result["1-01"].toe_source == "angle"
    assert result["1-01"].value_m == pytest.approx(1.0 + 6.0 * tan15, abs=1e-3)
    assert result["1-02"].toe_source == "angle"
    assert result["1-02"].value_m == pytest.approx(1.0 + 10.0 * tan15, abs=1e-3)
    assert result["1-03"].toe_source == "survey"
    assert result["1-03"].value_m == pytest.approx(13.0, abs=1e-3)


def test_angle_toe_lines_drawn_only_near_spoil_holes():
    near = vertical_hole("1-01", x=5, y=1.0, row=0)
    far = vertical_hole("1-02", x=35, y=1.0, row=0)
    design = BlastDesign(design_id="t", contour=spoil_contour(), holes=[near, far], pattern_params=PATTERN)
    lines = spoil_angle_toe_lines(design, floor_burdens(design))
    assert len(lines) == 1
    xs = [x for x, _ in lines[0]]
    # ±a/2 (a = 4 м) от точки подошвы у скважины.
    assert min(xs) == pytest.approx(33.0, abs=1e-3) and max(xs) == pytest.approx(37.0, abs=1e-3)
    assert all(y == pytest.approx(-2.6795, abs=1e-3) for _, y in lines[0])
    maps = engineering_maps(design)
    assert maps["angle_toe_lines"] and maps["angle_toe_lines"][0][0][1] == pytest.approx(-2.68, abs=1e-2)


def test_angle_toe_lines_use_each_hole_bench_height():
    # Две скважины на развале с разной высотой уступа: куски линии по углу —
    # на своём удалении от бровки, как ЛСП каждой скважины.
    low = vertical_hole("1-01", x=33, y=1.0, row=0, bench_h=6.0)
    high = vertical_hole("1-02", x=37, y=1.0, row=0, bench_h=10.0)
    design = BlastDesign(design_id="t", contour=spoil_contour(), holes=[low, high], pattern_params=PATTERN)
    burdens = floor_burdens(design)
    assert {burdens["1-01"].toe_source, burdens["1-02"].toe_source} == {"angle"}
    lines = spoil_angle_toe_lines(design, burdens)
    assert len(lines) == 2
    tan15 = math.tan(math.radians(15))
    by_x = sorted(lines, key=lambda line: line[0][0])
    assert all(y == pytest.approx(-6.0 * tan15, abs=1e-3) for _, y in by_x[0])
    assert all(y == pytest.approx(-10.0 * tan15, abs=1e-3) for _, y in by_x[1])
    xs_low = [x for x, _ in by_x[0]]
    assert min(xs_low) == pytest.approx(31.0, abs=1e-3) and max(xs_low) == pytest.approx(35.0, abs=1e-3)


def test_no_angle_toe_lines_without_spoil_or_survey():
    near = vertical_hole("1-01", x=5, y=1.0, row=0)
    on_survey = BlastDesign(design_id="t", contour=spoil_contour(), holes=[near], pattern_params=PATTERN)
    assert spoil_angle_toe_lines(on_survey, floor_burdens(on_survey)) == []
    built = design_with([near])
    assert engineering_maps(built)["angle_toe_lines"] == []


def test_built_line_without_survey_reports_angle_source():
    fb = floor_burdens(design_with([vertical_hole("1-01", x=10, y=3.7, row=0)]))["1-01"]
    assert fb.toe_source == "angle"


# --- Первый ряд: геометрия, а не номер ряда ---------------------------------


def test_side_free_face_holes_get_floor_burden():
    # Свободны фронт (y = 0) и правый фланг (x = 40); ряды вдоль фронта. Скважины
    # у фланга стоят «за» скважинами предыдущего ряда, но к откосу фланга перед
    # ними никого нет.
    contour = rect_contour(free_faces=[[0, 1, 2]])
    holes = [
        vertical_hole(f"{r + 1}-{c + 1:02d}", 2.6 + 4 * c, 3.7 + 3.7 * r, row=r)
        for r in range(5)
        for c in range(9)
    ]
    design = BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=PATTERN)
    result = floor_burdens(design)
    # Ряды со второго: до откоса фланга (8,08 м) ближе, чем до фронта.
    side = [h for h in holes if h.collar.x == pytest.approx(34.6) and h.row > 0]
    assert len(side) == 4
    for hole in side:
        assert hole.id in result
        assert result[hole.id].value_m == pytest.approx(40 - 34.6 + 2.6795, abs=1e-3)
        assert result[hole.id].excess is True
    # Внутренние скважины второго и дальних рядов — без ЛСП.
    inner = [h for h in holes if h.collar.x < 30 and h.row > 0]
    assert not any(h.id in result for h in inner)


def test_manual_hole_in_middle_has_no_floor_burden():
    from design.editing import insert_manual_hole
    from design.pattern import generate_pattern

    contour = rect_contour()
    params = {**PATTERN, "offset_from_face_m": 1.1, "depth_m": 11.0}
    holes = generate_pattern(contour, params)
    manual = insert_manual_hole(holes, 20.0, 12.0, contour, {})
    holes.append(manual)
    result = floor_burdens(BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params))
    assert manual.id not in result
    # ЛСП есть только у скважин без соседей между ними и подошвой: все — у фронта.
    for hole_id in result:
        hole = next(h for h in holes if h.id == hole_id)
        assert hole.collar.y <= 4.0 + 1e-6


def test_boot_holes_under_pocket_crest_get_floor_burden():
    from design.geometry import distance_to_free_faces
    from design.pattern import generate_pattern
    from tests.test_design_pattern_full_contour import BOOT, BOOT_FACE, PARAMS

    contour = BlockContour(
        vertices=[Point3(x, y, 0.0) for x, y in BOOT],
        free_faces=BOOT_FACE,
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=75.0),
    )
    params = {**PARAMS, "burden_b_m": 5.0}
    holes = generate_pattern(contour, params)
    result = floor_burdens(BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params))
    # Скважины под бровкой кармана (ребро (55; 33)–(28; 35)): ближе 5 м к бровке,
    # бровка над ними, а не сбоку.
    crest = LineString([(55.0, 33.0), (28.0, 35.0)])
    under = [
        h for h in holes
        if h.kind == "production" and h.enabled
        and crest.distance(ShapelyPoint(h.collar.x, h.collar.y)) < 5.0
        and 28.0 < h.collar.x < 55.0 and h.collar.y < 33.0
        and distance_to_free_faces((h.collar.x, h.collar.y), contour) < 5.0
    ]
    assert len(under) >= 4
    for hole in under:
        assert hole.id in result, hole.id
        assert result[hole.id].value_m > 5.15
        assert result[hole.id].excess is True


# --- Шахматная сетка ---------------------------------------------------------


def staggered_along_face(spacing_a: float) -> list[Hole]:
    # Ряды вдоль фронта (y = 0), второй ряд сдвинут на a/2: соседи первого ряда
    # стоят ровно в a/2 сбоку от коридора скважины второго ряда.
    holes = []
    for r in range(3):
        shift = spacing_a / 2 if r % 2 else 0.0
        c = 0
        while 2.0 + shift + spacing_a * c <= 38.0:
            holes.append(vertical_hole(f"{r + 1}-{c + 1:02d}", 2.0 + shift + spacing_a * c, 3.7 * (r + 1), row=r))
            c += 1
    return holes


@pytest.mark.parametrize("spacing_a", [4.0, 5.0, 3.9])
def test_staggered_rows_along_face_second_row_has_no_floor_burden(spacing_a):
    holes = staggered_along_face(spacing_a)
    params = {"pattern": "staggered", "spacing_a_m": spacing_a, "burden_b_m": 3.7}
    result = floor_burdens(design_with(holes, params))
    first = [h for h in holes if h.row == 0]
    assert first and all(h.id in result for h in first)
    for hole in first:
        assert result[hole.id].value_m == pytest.approx(3.7 + 2.6795, abs=1e-3)
    assert not any(h.id in result for h in holes if h.row > 0)


def test_generated_staggered_rows_across_face_end_holes_behind_neighbours_not_excess():
    from design.pattern import generate_pattern

    contour = rect_contour()
    a, b = 4.0, 3.7
    params = {
        "pattern": "staggered", "spacing_a_m": a, "burden_b_m": b,
        "offset_from_face_m": 1.1, "depth_m": 11.0, "row_azimuth_deg": 0.0,
    }
    holes = generate_pattern(contour, params)
    result = floor_burdens(BlastDesign(design_id="t", contour=contour, holes=holes, pattern_params=params))
    grid = [h for h in holes if h.enabled]

    def has_hole_in_front(hole: Hole) -> bool:
        # Перед скважиной: на полшага a ближе к фронту, в соседнем ряду (до b сбоку).
        return any(
            other is not hole
            and hole.collar.y - other.collar.y >= a / 2 - 1e-6
            and abs(hole.collar.x - other.collar.x) <= b + 1e-6
            for other in grid
        )

    behind = [h for h in grid if h.kind == "production" and has_hole_in_front(h)]
    assert behind
    assert not any(result[h.id].excess for h in behind if h.id in result)
    # Скважины, перед которыми никого нет, по-прежнему проверяются.
    assert any(fb.excess for fb in result.values())


# --- Выход в откос: точка на подошве за линией подошвы ---


def test_hole_exiting_into_slope_is_beyond_toe_and_excess():
    # Подошва по углу — y = −2,68. Наклон 30° от устья в 1 м: на H = 10 м ось
    # уходит к откосу на 5,77 м — точка на подошве y = −4,77, за линией подошвы.
    hole = inclined_hole("1-01", x=10, y=1.0, row=0, angle_deg=30, azimuth_deg=180)
    fb = floor_burdens(design_with([hole], {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.0}))["1-01"]
    assert fb.beyond_toe is True
    assert fb.value_m == pytest.approx(5.7735 - 1.0 - 2.6795, abs=1e-3)  # расстояние с другой стороны
    assert fb.value_m < fb.allowed_m
    assert fb.excess is True  # без знака ЛСП «в допуске», но скважина выходит в откос


def test_beyond_toe_hole_is_not_hidden_by_row_behind():
    # Скважина за ней (ряд 2) не закрывает: коридора к подошве у вышедшей в откос нет.
    first = inclined_hole("1-01", x=10, y=1.0, row=0, angle_deg=30, azimuth_deg=180)
    second = vertical_hole("2-01", x=10, y=4.7, row=1)
    result = floor_burdens(design_with([first, second]))
    assert result["1-01"].beyond_toe is True


def test_hole_inside_toe_is_not_beyond():
    hole = inclined_hole("1-01", x=10, y=3.7, row=0, angle_deg=15, azimuth_deg=180)
    fb = floor_burdens(design_with([hole]))["1-01"]
    assert fb.beyond_toe is False


def test_hole_past_back_edge_is_not_beyond_toe():
    # Наклон наружу через тыл (y = 22, не свободная поверхность) — не откос.
    hole = inclined_hole("1-01", x=10, y=21.0, row=5, angle_deg=30, azimuth_deg=0)
    assert holes_beyond_toe(design_with([hole])) == []


def test_survey_toe_beyond_uses_bottom_ring():
    # Съёмка нижней бровки y = −3 (ближе H — откос, не развал).
    contour = rect_contour(cad={"bottom": [[0, -3], [40, -3], [40, 22], [0, 22]]})
    inside = inclined_hole("1-01", x=10, y=3.0, row=0, angle_deg=15, azimuth_deg=180)  # y_подошва = 0,32
    out = inclined_hole("1-02", x=20, y=1.0, row=0, angle_deg=30, azimuth_deg=180)  # y_подошва = −4,77
    design = BlastDesign(design_id="t", contour=contour, holes=[inside, out], pattern_params=PATTERN)
    assert holes_beyond_toe(design) == ["1-02"]
    assert floor_burdens(design)["1-02"].beyond_toe is True


def test_manual_and_non_production_grid_holes_are_checked():
    hole = inclined_hole("M-1", x=10, y=1.0, row=0, angle_deg=30, azimuth_deg=180)
    hole.source = "manual"
    hole.kind = "infill"
    assert holes_beyond_toe(design_with([hole])) == ["M-1"]


def test_toe_positions_for_vertical_floor_points():
    positions = toe_positions(rect_contour(), [(10.0, 3.0), (10.0, -5.0)], [10.0, 10.0])
    assert positions[0].distance_m == pytest.approx(3.0 + 2.6795, abs=1e-3)
    assert positions[0].beyond is False
    assert positions[1].beyond is True


def test_spiky_contour_still_detects_beyond_toe():
    # Кольцо с «усом» (5,10)→(5,15)→(5,10): make_valid даёт GeometryCollection
    # (полигон + линия); берётся полигон, и «за подошвой» находится.
    from design.toe_line import _valid_polygon

    ring = [(0, 0), (40, 0), (40, 22), (5, 22), (5, 27), (5, 22), (0, 22)]
    assert _valid_polygon(ring).geom_type == "Polygon"
    assert _valid_polygon(ring).area == pytest.approx(40 * 22)
    contour = BlockContour(
        vertices=[Point3(x, y, 0) for x, y in ring],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75),
    )
    positions = toe_positions(contour, [(10.0, 3.0), (10.0, -5.0)], [10.0, 10.0])
    assert [p.beyond for p in positions] == [False, True]


def test_floor_report_matches_separate_calls():
    from design.toe_line import floor_report

    out = inclined_hole("1-01", x=10, y=1.0, row=0, angle_deg=30, azimuth_deg=180)
    ok = inclined_hole("1-02", x=20, y=3.7, row=0, angle_deg=15, azimuth_deg=180)
    design = design_with([out, ok])
    burdens, beyond = floor_report(design)
    assert burdens == floor_burdens(design)
    assert beyond == holes_beyond_toe(design) == ["1-01"]


# --- Нижняя граница ЛСП: 0,8·W ---


def test_min_floor_burden_is_0_8_w():
    from design.toe_line import FLOOR_BURDEN_MIN_RATIO, min_floor_burden_m

    assert FLOOR_BURDEN_MIN_RATIO == 0.8
    assert min_floor_burden_m(PATTERN) == pytest.approx(0.8 * 3.7)
    assert min_floor_burden_m({"pattern": "square", "spacing_a_m": 5.0}) == pytest.approx(4.0)
    assert min_floor_burden_m({"pattern": "rectangular", "spacing_a_m": 4.0}) is None


def test_short_floor_burden_is_flagged():
    # Подошва по углу y = −2,68; ЛСП 0,8·3,7 = 2,96 — граница.
    short = vertical_hole("1-01", x=10, y=0.2, row=0)  # ЛСП 2,88
    ok = vertical_hole("1-02", x=20, y=0.4, row=0)  # ЛСП 3,08
    result = floor_burdens(design_with([short, ok]))
    assert result["1-01"].short is True and result["1-01"].min_m == pytest.approx(2.96)
    assert result["1-02"].short is False
    assert result["1-01"].excess is False


def test_beyond_toe_is_not_short():
    hole = inclined_hole("1-01", x=10, y=1.0, row=0, angle_deg=30, azimuth_deg=180)
    fb = floor_burdens(design_with([hole]))["1-01"]
    assert fb.beyond_toe is True and fb.short is False


def test_no_w_means_no_short():
    hole = vertical_hole("1-01", x=10, y=0.0, row=0)
    fb = floor_burdens(design_with([hole], {"pattern": "rectangular", "spacing_a_m": 4.0}))["1-01"]
    assert fb.min_m is None and fb.short is False


# --- Пара у откоса: ЛСП у наклонной, вертикальная за ней закрыта -------------


def test_face_toe_pair_gets_floor_burden_and_closes_its_vertical():
    vertical = vertical_hole("1-01", x=10, y=3.0, row=0)
    pair = vertical_hole("1-01T", x=10, y=2.0, row=0, kind="face_toe")
    other = vertical_hole("1-03", x=30, y=3.0, row=0)
    result = floor_burdens(design_with([vertical, pair, other]))
    assert set(result) == {"1-01T", "1-03"}
    assert result["1-01T"].value_m == pytest.approx(2.0 + 2.6795, abs=1e-3)


def test_disabled_pair_does_not_close_its_vertical():
    vertical = vertical_hole("1-01", x=10, y=3.0, row=0)
    pair = vertical_hole("1-01T", x=10, y=2.0, row=0, kind="face_toe", enabled=False)
    assert set(floor_burdens(design_with([vertical, pair]))) == {"1-01"}


def test_default_kind_of_main_grid_gets_floor_burden():
    hole = vertical_hole("1-01", x=10, y=3.0, row=0, kind="infill")
    params = PATTERN | {"default_kind": "infill"}
    assert set(floor_burdens(design_with([hole], pattern_params=params))) == {"1-01"}
    assert floor_burdens(design_with([hole])) == {}


def test_square_pattern_w_is_spacing_even_with_burden_key():
    # Квадратная сетка строится с b = a (generate_pattern) — W тоже a.
    assert allowed_floor_burden_m({"pattern": "square", "spacing_a_m": 4.0, "burden_b_m": 3.0}) == pytest.approx(4.12)
    # Без ключа pattern сетка квадратная.
    assert allowed_floor_burden_m({"spacing_a_m": 4.0, "burden_b_m": 3.0}) == pytest.approx(4.12)
    assert allowed_floor_burden_m({"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.0}) == pytest.approx(3.09)


def test_tilted_pair_shadows_only_its_own_vertical():
    # A с парой; B без пары — сбоку и впереди пары по коридору: пара его не закрывает.
    a = vertical_hole("1-01", x=10, y=3.0, row=0)
    pair = inclined_hole("1-01T", x=10, y=2.0, row=0, angle_deg=10, azimuth_deg=180)
    pair = Hole(**{**pair.__dict__, "kind": "face_toe"})
    b = vertical_hole("1-02", x=14, y=1.8, row=0)
    result = floor_burdens(design_with([a, pair, b]))
    assert set(result) == {"1-01T", "1-02"}


def test_square_w_without_spacing_uses_generator_default():
    # generate_pattern строит квадратную сетку без spacing_a_m с a = 5.
    assert allowed_floor_burden_m({"pattern": "square", "burden_b_m": 3.0}) == pytest.approx(5.15)
    assert allowed_floor_burden_m({}) is None


# --- Разрыв между рядами у подошвы (часть 3b) ---------------------------------

GAP_PATTERN = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.5}


def grid_rows(row_one_tilt_deg: float = 0.0, rows: int = 4) -> list[Hole]:
    """Сетка 4×3,5 м у грани y = 0: устья по сетке, ряд 1 (y = 2) наклонён к откосу."""
    holes = []
    for r in range(rows):
        for c, x in enumerate((8.0, 12.0, 16.0, 20.0, 24.0)):
            y = 2.0 + 3.5 * r
            hid = f"{r + 1}-{c + 1:02d}"
            if r == 0 and row_one_tilt_deg:
                hole = inclined_hole(hid, x, y, r, row_one_tilt_deg, 180)
            else:
                hole = vertical_hole(hid, x, y, r)
            holes.append(Hole(**{**hole.__dict__, "col": c}))
    return holes


def test_tilted_row_one_on_grid_opens_gap_at_floor_before_row_two():
    gaps = floor_row_gaps(design_with(grid_rows(15.0), pattern_params=GAP_PATTERN))
    row_two = {hid: g for hid, g in gaps.items() if hid.startswith("2-")}
    assert set(row_two) == {f"2-{c:02d}" for c in range(1, 6)}
    for gap in row_two.values():
        assert gap.value_m == pytest.approx(3.5 + 2.6795, abs=1e-3)
        assert gap.allowed_m == pytest.approx(3.605)
        assert gap.excess is True
    # Ряд 3 — за вертикальным рядом 2: шаг b, без превышения; ряд 1 — у откоса, разрыва нет.
    assert all(not g.excess for hid, g in gaps.items() if hid.startswith("3-"))
    assert not any(hid.startswith("1-") for hid in gaps)


def test_plain_vertical_grid_has_no_gap_excess():
    gaps = floor_row_gaps(design_with(grid_rows(), pattern_params=GAP_PATTERN))
    assert gaps and not any(g.excess for g in gaps.values())


def test_face_pairs_do_not_create_gap():
    holes = grid_rows()
    pairs = [
        Hole(**{**inclined_hole(f"{h.id}T", h.collar.x, h.collar.y - 1.0, 0, 15, 180).__dict__, "kind": "face_toe"})
        for h in holes
        if h.row == 0
    ]
    gaps = floor_row_gaps(design_with(holes + pairs, pattern_params=GAP_PATTERN))
    assert not any(g.excess for g in gaps.values())
    assert not any(hid.endswith("T") for hid in gaps)


def test_gap_without_w_is_not_checked():
    assert floor_row_gaps(design_with(grid_rows(15.0), pattern_params={})) == {}
