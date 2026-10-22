"""Automatic blast-hole pattern generation inside a block contour."""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Callable

import numpy as np
import shapely

from design.geometry import (
    distance_to_free_faces,
    drape_collar,
    ensure_ccw,
    local_basis,
    offset_polygon,
    pattern_origin,
    point_in_polygon,
)
from design.geology import domain_at
from design.numbering import number_by_position
from design.models import FRONT_ROW_BASE, HOLE_KINDS, BlastDomain, BlockContour, Hole, Point3, logical_row
from design.toe_line import corridor_blocker_pairs, crest_geometry, min_floor_burden_m, shadow_limits, toe_positions

PATTERN_TYPES = ("square", "rectangular", "staggered", "variable", "domain_dependent")
REGULAR_PATTERNS = ("square", "rectangular", "staggered")

# Наклон 1–2 ряда у откоса (оптимизатор, часть 3): угол от вертикали, °.
FRONT_ROWS_TILT_MAX_DEG = 30.0
FRONT_ROWS_TILT_DEFAULT_DEG = 15.0
FRONT_ROWS_TILT_MAX_COUNT = 2
# Наклон не уводит точку оси на уровне подошвы ближе этого к линии подошвы
# (ЛСП), даже если W не задана: иначе забой выходит в откос (решение
# владельца 22.10.2026, блок №66), м. При заданной W цель — не меньше
# нижней границы ЛСП 0,8·W (`toe_line.min_floor_burden_m`); см.
# `tilt_floor_burden_target_m`.
FRONT_TILT_MIN_FLOOR_BURDEN_M = 1.0


def generate_pattern(
    contour: BlockContour,
    params: dict[str, Any],
    existing_holes: list[Hole] | None = None,
    surfaces: object | None = None,
    domains: list[BlastDomain] | None = None,
) -> list[Hole]:
    """Build a production blast pattern inside the block contour.

    params:
      pattern                 square | rectangular | staggered | variable | domain_dependent
      spacing_a_m             in-row spacing, m
      burden_b_m              inter-row burden, m (ignored for square — uses a)
      row_shift_ratio         odd-row shift as a fraction of a (staggered, default 0.5)
      row_azimuth_deg         row azimuth, deg (0 = north / +Y)
      offset_from_face_m      first-row offset from the free face when first_row_burden_m is unset
      first_row_burden_m      optional first-row burden (face → row 0); later rows use burden_b_m
      first_row_follow_face   place row 0 along an inward offset of the free faces
      edge_margin_m           inset from the contour, m
      diameter_mm / subdrill_m / angle_deg / azimuth_deg / depth_m
      default_kind            kind assigned to the main grid (default production)
      row_params              per-row overrides for variable: spacing_a_m, burden_b_m, shift_ratio, kind
      front_rows_tilt_count   0–2 рядов у откоса с наклоном к откосу (нет ключа — 0)
      front_rows_tilt_deg     угол этих рядов от вертикали, 0–30° (нет ключа — 15°)
      contour_row / presplit_row / trim_row / buffer_row / stab_row
      satellite_holes / infill_holes
    """
    pattern = str(params.get("pattern", "square"))
    if pattern not in PATTERN_TYPES:
        pattern = "square"

    spacing_a = float(params.get("spacing_a_m", 5.0))
    burden_b = spacing_a if pattern == "square" else float(params.get("burden_b_m", spacing_a))
    row_shift_ratio = float(params.get("row_shift_ratio", 0.5)) if pattern == "staggered" else 0.0
    row_azimuth_deg = float(params.get("row_azimuth_deg", 0.0))
    first_row_burden = params.get("first_row_burden_m")
    first_row_burden = float(first_row_burden) if first_row_burden not in (None, "") else None
    offset_from_face = (
        first_row_burden
        if first_row_burden is not None
        else float(params.get("offset_from_face_m", burden_b / 2))
    )
    follow_face = bool(params.get("first_row_follow_face", False))
    edge_margin = float(params.get("edge_margin_m", 0.0))
    diameter_mm = float(params.get("diameter_mm", 152.0))
    subdrill_m = float(params.get("subdrill_m", 1.0))
    angle_deg = float(params.get("angle_deg", 0.0))
    azimuth_deg = float(params.get("azimuth_deg", row_azimuth_deg))
    depth_override = params.get("depth_m")
    depth_override = float(depth_override) if depth_override is not None else None
    default_kind = _normalize_kind(params.get("default_kind", "production"), "production")
    domain_list = list(domains or [])
    tilt_count, tilt_deg = _front_rows_tilt(params)
    if not contour.free_faces:
        tilt_count = 0
    mode = front_rows_mode(params, tilt_count) if contour.free_faces else None
    taper = mode == FRONT_ROWS_MODE_TAPER and tilt_count > 0

    verts = ensure_ccw(contour.points_xy)
    if len(verts) < 3 or spacing_a <= 0 or burden_b <= 0:
        return _keep_manual(existing_holes)

    boundary = offset_polygon(verts, edge_margin) if edge_margin > 0 else verts
    row_dir, advance_dir = local_basis(row_azimuth_deg)
    origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)

    us = [(vx - origin[0]) * row_dir[0] + (vy - origin[1]) * row_dir[1] for vx, vy in verts]
    vs = [
        (vx - origin[0]) * advance_dir[0] + (vy - origin[1]) * advance_dir[1] for vx, vy in verts
    ]
    u_min, u_max = min(us) - spacing_a, max(us) + spacing_a
    v_min, v_max = min(vs) - burden_b, max(vs) + burden_b
    crest_z = contour.bench.crest_z_m

    holes: list[Hole] = []
    first_lattice_row = 0
    skip_regular_first = False
    face_row_count = 0

    if follow_face and contour.free_faces:
        face_row = _generate_face_following_row(
            contour,
            params,
            boundary,
            origin,
            row_dir,
            advance_dir,
            offset_from_face,
            spacing_a,
            diameter_mm,
            subdrill_m,
            angle_deg,
            azimuth_deg,
            depth_override,
            default_kind,
            surfaces,
        )
        if face_row:
            holes.extend(face_row)
            face_row_count = len(face_row)
            first_lattice_row = 1
            skip_regular_first = True

    def domain_probe(v: float, accept: Callable[[float, float], bool] | None) -> tuple[float, float]:
        """Точка ряда, по которой выбирается домен.

        Середина ряда по bbox; если она вне контура (или вне допустимой зоны у
        бровки), — первый узел ряда, который реально встанет в контур.
        """
        mid = _world_xy(origin, row_dir, advance_dir, 0.5 * (u_min + u_max), v)
        if accept is None or (point_in_polygon(mid, boundary) and accept(*mid)):
            return mid
        probe_step = max(0.25, spacing_a * 0.25)
        u = u_min
        while u <= u_max:
            x, y = _world_xy(origin, row_dir, advance_dir, u, v)
            if point_in_polygon((x, y), boundary) and accept(x, y):
                return x, y
            u += probe_step
        return mid

    def row_settings(
        lattice_row: int, v: float, accept: Callable[[float, float], bool] | None = None
    ) -> tuple[float, float, float, str]:
        """Шаг по ряду, шаг до следующего ряда, сдвиг шахматки и вид скважин ряда.

        `accept` — фильтр узлов ряда: домен берётся по его принятой части.
        """
        local_a, local_b, shift_ratio, row_kind = _row_config(
            params, pattern, max(lattice_row, 0), spacing_a, burden_b, row_shift_ratio, default_kind
        )
        if pattern == "domain_dependent" and domain_list:
            mid = domain_probe(v, accept) if accept is not None else _world_xy(
                origin, row_dir, advance_dir, 0.5 * (u_min + u_max), v
            )
            domain = domain_at(domain_list, Point3(x=mid[0], y=mid[1], z=crest_z))
            if domain is not None:
                if domain.spacing_a_m:
                    local_a = float(domain.spacing_a_m)
                if domain.burden_b_m:
                    local_b = float(domain.burden_b_m)
                if pattern == "square" and domain.spacing_a_m and not domain.burden_b_m:
                    local_b = local_a
        if local_b <= 0:
            local_b = burden_b
        return local_a, local_b, shift_ratio, row_kind

    def place_row(
        lattice_row: int,
        row_index: int,
        v: float,
        min_face_m: float | None = None,
        inside: Callable[[float, float], bool] | None = None,
    ) -> tuple[list[Hole], float]:
        """Узлы одного ряда решётки внутри контура и шаг до следующего ряда.

        `lattice_row` — номер ряда решётки, первый ряд у бровки — `first_lattice_row`
        (впереди него — меньше): от него зависят сдвиг шахматки и строка
        `row_params`. `row_index` — номер ряда в паспорте. `min_face_m`
        отбрасывает узлы ближе этого расстояния к свободной поверхности.
        `inside` — где узел ставится (по умолчанию — внутри контура).
        """
        if inside is None:
            inside = lambda x, y: point_in_polygon((x, y), boundary)  # noqa: E731
        accept = _off_face_filter(contour, min_face_m) if min_face_m is not None else None
        local_a, local_b, shift_ratio, row_kind = row_settings(lattice_row, v, accept)

        shift = shift_ratio * local_a if lattice_row % 2 == 1 else 0.0
        if pattern == "domain_dependent" and domain_list:
            placed = _walk_domain_row(
                contour,
                domain_list,
                boundary,
                origin,
                row_dir,
                advance_dir,
                u_min + shift,
                u_max,
                v,
                local_a,
                row_index,
                row_kind,
                diameter_mm,
                subdrill_m,
                angle_deg,
                azimuth_deg,
                depth_override,
                surfaces,
                crest_z,
                accept,
                inside,
            )
            return placed, local_b

        placed: list[Hole] = []
        col_index = 0
        u = u_min + shift
        while u <= u_max:
            x, y = _world_xy(origin, row_dir, advance_dir, u, v)
            if inside(x, y) and (accept is None or accept(x, y)):
                collar, toe = drape_collar(
                    x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_override
                )
                placed.append(
                    Hole(
                        id=_grid_id(row_kind, row_index, col_index),
                        row=row_index,
                        col=col_index,
                        collar=collar,
                        toe=toe,
                        diameter_mm=diameter_mm,
                        subdrill_m=subdrill_m,
                        kind=row_kind,
                        source="generated",
                    )
                )
                col_index += 1
            u += local_a
        return placed, local_b

    v_first = offset_from_face + burden_b if skip_regular_first else offset_from_face

    # Ряды впереди первого: при изогнутой бровке её средняя точка лежит внутри
    # блока, и часть контура оказывается впереди начала отсчёта. Фаза та же —
    # шаг назад от первого ряда до крайней проекции вершин контура; шаг —
    # burden первого ряда (строка row_params[0]; домен — по положению ряда). Узлы
    # этих рядов не ближе offset_from_face к бровке — иначе скважина у
    # откоса недогружена. С рядом вдоль бровки узлы не ближе
    # offset_from_face + burden_b: ближе — место ряда вдоль бровки. Без
    # свободной поверхности впереди нет ничего, кроме полосы между краем
    # контура и первым рядом.
    min_face_m = offset_from_face + burden_b if skip_regular_first else offset_from_face
    def _front_row_number(lattice_row: int) -> int:
        return FRONT_ROW_BASE - (first_lattice_row - lattice_row)

    front_rows: list[tuple[int, float]] = []
    front_accept = _off_face_filter(contour, min_face_m)
    if contour.free_faces:
        v_row = v_first
        for step in range(1, 501):
            lattice_row = first_lattice_row - step
            v_prev = v_row - burden_b
            # Домен выбирается по положению ряда, шаг — по домену. Если граница домена
            # зациклила поиск, берём более далёкую из двух последних позиций: шаг
            # больше, и ряд не окажется недогружен против домена с большим burden.
            visited: list[float] = []
            for _ in range(8):
                v_next = v_row - row_settings(lattice_row, v_prev, front_accept)[1]
                if abs(v_next - v_prev) < 1e-9:
                    break
                visited.append(v_next)
                v_prev = v_next
            else:
                # Цикл — от первого повтора последней позиции; берём его самую далёкую
                # точку. Если повтора нет, — самую далёкую из всех пробованных.
                last = visited[-1] if visited else v_prev
                start = next((i for i, v in enumerate(visited) if abs(v - last) < 1e-9), None)
                cycle = visited[start:] if start is not None else visited
                if cycle:
                    v_prev = min(cycle)
            if v_prev < v_min:
                break
            front_rows.insert(0, (lattice_row, v_prev))
            v_row = v_prev
    # Пустые ряды перед первым непустым номера не получают — для блока, где
    # бровка целиком впереди контура, нумерация остаётся прежней. Каждый ряд
    # размещается один раз: результат пустого ряда отбрасывается, а не пересчитывается.
    front_placed = [
        place_row(lattice_row, _front_row_number(lattice_row), v, min_face_m)[0]
        for lattice_row, v in front_rows
    ]
    while front_placed and not front_placed[0]:
        front_placed.pop(0)
        front_rows.pop(0)
    for placed in front_placed:
        holes.extend(placed)

    # Плавный переход сдвигает устья рядов за наклонными к откосу (до H·tg α):
    # узлы решётки, которые сдвиг вернёт в контур (у тыла и флангов), ставятся
    # заранее — лишние отсеет `_taper_front_rows`.
    taper_back = taper_reach_m(contour, tilt_deg) if taper else 0.0
    lattice_inside = _swept_inside(boundary, advance_dir, taper_back) if taper_back > 0 else None
    lattice_row = first_lattice_row
    row_index = first_lattice_row
    v = v_first
    safety = 0
    while v <= v_max + taper_back and safety < 500:
        safety += 1
        placed, local_b = place_row(lattice_row, row_index, v, inside=lattice_inside)
        holes.extend(placed)
        lattice_row += 1
        row_index += 1
        v += local_b

    # Сейчас в `holes` — вся основная сетка: ряд вдоль бровки, ряды впереди
    # первого ряда решётки и ряды решётки. Схема первого ряда у откоса — после
    # раскладки, по местному рангу (см. `_taper_front_rows`).
    lattice_xy: dict[int, tuple[float, float]] = {}
    if mode == FRONT_ROWS_MODE_PAIR:
        pass  # «Пара у откоса» — часть 3b, задача 2.
    elif taper:
        holes, lattice_xy = _taper_front_rows(
            holes,
            face_row_count,
            contour,
            boundary,
            advance_dir,
            tilt_count,
            tilt_deg,
            tilt_floor_burden_target_m(params),
            {"production", default_kind},
            spacing_a,
            burden_b,
            subdrill_m,
            surfaces,
            depth_override,
        )

    holes.extend(
        _generate_wall_row(
            contour, params, "contour", "K", "contour_row", "contour_spacing_m",
            "contour_offset_m", "contour_diameter_mm", "contour_depth_m",
            "contour_subdrill_m", "contour_angle_deg", diameter_mm, depth_override,
            subdrill_m, surfaces,
        )
    )
    holes.extend(
        _generate_wall_row(
            contour, params, "presplit", "P", "presplit_row", "presplit_spacing_m",
            "presplit_offset_m", "presplit_diameter_mm", "presplit_depth_m",
            "presplit_subdrill_m", "presplit_angle_deg", diameter_mm, depth_override,
            subdrill_m, surfaces,
        )
    )
    holes.extend(
        _generate_wall_row(
            contour, params, "trim", "T", "trim_row", "trim_spacing_m",
            "trim_offset_m", "trim_diameter_mm", "trim_depth_m",
            "trim_subdrill_m", "trim_angle_deg", diameter_mm, depth_override,
            subdrill_m, surfaces,
        )
    )
    if params.get("buffer_row"):
        holes.extend(
            _generate_buffer_row(
                contour, params, boundary, origin, row_dir, advance_dir,
                spacing_a, burden_b, diameter_mm, subdrill_m, angle_deg, azimuth_deg,
                depth_override, surfaces,
            )
        )
    if params.get("stab_row"):
        holes.extend(_generate_stab_holes(holes, contour, params, surfaces))
    if params.get("satellite_holes"):
        holes.extend(_generate_satellite_holes(holes, contour, params, surfaces))
    if params.get("infill_holes"):
        holes.extend(_generate_infill_holes(holes, contour, params, surfaces))

    # Id — по расположению (север→юг, запад→восток); row/col остаются техническими.
    # Сдвинутые плавным переходом — по месту в сетке до сдвига.
    numbered = _keep_manual(existing_holes) + holes
    return number_by_position(
        numbered,
        row_azimuth_deg=float(params.get("row_azimuth_deg", 0.0)),
        positions=[lattice_xy.get(id(h)) for h in numbered] if lattice_xy else None,
    )


def _normalize_kind(value: Any, default: str) -> str:
    kind = str(value or default).strip().lower()
    return kind if kind in HOLE_KINDS else default


def _front_rows_tilt(params: dict[str, Any]) -> tuple[int, float]:
    """Число наклонных рядов у откоса (0–2) и их угол от вертикали (0–30°)."""
    try:
        count = int(float(params.get("front_rows_tilt_count") or 0))
    except (TypeError, ValueError, OverflowError):
        count = 0
    raw_deg = params.get("front_rows_tilt_deg")
    try:
        deg = float(raw_deg) if raw_deg not in (None, "") else FRONT_ROWS_TILT_DEFAULT_DEG
    except (TypeError, ValueError):
        deg = FRONT_ROWS_TILT_DEFAULT_DEG
    if not math.isfinite(deg):
        deg = FRONT_ROWS_TILT_DEFAULT_DEG
    count = max(0, min(FRONT_ROWS_TILT_MAX_COUNT, count))
    deg = max(0.0, min(FRONT_ROWS_TILT_MAX_DEG, deg))
    return count, deg


def front_row_ranks(
    collars_xy: list[tuple[float, float]],
    contour: BlockContour,
    spacing_a: float,
    burden_b: float,
    forced_first: int = 0,
) -> list[int]:
    """Местный ранг скважин основной сетки от откоса: 1, 2 или 3 (дальше).

    Ранг 1 — впереди скважины, в её коридоре к ближайшей точке верхней бровки,
    нет другой скважины сетки; ранг 2 — впереди только скважины ранга 1.
    Коридор и «впереди» — та же проверка, что у ЛСП (`toe_line.corridor_blockers`,
    здесь пакетом — `corridor_blocker_pairs`: продвижение не меньше
    0,4·min(a, b), отступ вбок не больше 1,05·max(a, b)), но по устьям и к бровке. Так на ступенчатой бровке ранг 1 получает ряд,
    который реально стоит у своего участка откоса, а не только первый ряд
    решётки. Первые `forced_first` скважин (ряд вдоль бровки) — ранг 1 всегда.

    Это ранг для ЛСП и проверок; плавный переход ранжирует по столбцам сетки
    (`_taper_columns`), чтобы шаг b у подошвы держался в каждом столбце.
    """
    crest = crest_geometry(contour)
    if crest is None or not collars_xy:
        return [3] * len(collars_xy)
    points = shapely.points(collars_xy)
    tree = shapely.STRtree(points)
    distances = shapely.distance(points, crest)
    targets = shapely.get_point(shapely.shortest_line(crest, points), 0)
    min_advance, reach = shadow_limits(spacing_a, burden_b)
    # Коридор от глубоких скважин тянется через весь блок, а решают ближние
    # соседи: сначала начало коридора у всех, весь — только у тех, кому там
    # ответа не нашлось. Запросы — пакетом (`corridor_blocker_pairs`).
    near = min_advance + 2.0 * reach
    count = len(collars_xy)
    values = np.asarray(distances, dtype=float)
    candidates = [i for i in range(count) if i >= forced_first and values[i] > 0]

    def pairs(indices, length):
        return corridor_blocker_pairs(indices, points, targets, values, tree, min_advance, reach, length)

    # Ряд 1: нет закрывающего соседа.
    blocked = np.zeros(count, dtype=bool)
    near_i, near_j = pairs(candidates, near)
    blocked[near_i] = True
    far = [i for i in candidates if not blocked[i] and values[i] > near]
    far_i, far_j = pairs(far, None)
    blocked[far_i] = True
    # Ряд 2: среди закрывающих нет никого, кроме ряда 1.
    deep = np.zeros(count, dtype=bool)
    deep[near_i[blocked[near_j]]] = True
    deep[far_i[blocked[far_j]]] = True
    searched = set(far)
    rest = [i for i in range(count) if blocked[i] and not deep[i] and values[i] > near and i not in searched]
    rest_i, rest_j = pairs(rest, None)
    deep[rest_i[blocked[rest_j]]] = True
    return [3 if deep[i] else 2 if blocked[i] else 1 for i in range(count)]


def tilt_floor_burden_target_m(params: dict[str, Any]) -> float:
    """Наименьшая ЛСП после наклона: max(0,8·W, `FRONT_TILT_MIN_FLOOR_BURDEN_M`); без W — последняя."""
    minimum = min_floor_burden_m(params)
    return max(minimum, FRONT_TILT_MIN_FLOOR_BURDEN_M) if minimum is not None else FRONT_TILT_MIN_FLOOR_BURDEN_M


# Схемы первого ряда у откоса (`front_rows_mode`): «плавный переход» — один
# угол на участок ряда, шаг b у подошвы; «пара» — вертикальная + наклонная
# у откоса (часть 3b, задача 2).
FRONT_ROWS_MODE_TAPER = "taper"
FRONT_ROWS_MODE_PAIR = "pair"
FRONT_ROWS_MODES = (FRONT_ROWS_MODE_PAIR, FRONT_ROWS_MODE_TAPER)


def front_rows_mode(params: dict[str, Any], tilt_count: int) -> str | None:
    """Схема первого ряда у откоса; None — вертикальный первый ряд (как без ключей).

    Без `front_rows_mode` и с `front_rows_tilt_count` > 0 — «плавный переход»
    (ключи, введённые до выбора схемы). Неизвестное значение — None: сетка не
    меняется.
    """
    raw = params.get("front_rows_mode")
    if raw in (None, ""):
        return FRONT_ROWS_MODE_TAPER if tilt_count > 0 else None
    mode = str(raw).strip().lower()
    return mode if mode in FRONT_ROWS_MODES else None


def _tilt_caps_m(
    contour: BlockContour,
    collars: list[tuple[float, float]],
    heights: list[float],
    direction: tuple[float, float],
    tilt_deg: float,
    target_m: float,
) -> list[float] | None:
    """Наибольший вынос точки оси на уровне подошвы вдоль `direction`, м, по скважинам.

    Вынос t = H·tg α не больше H·tg `tilt_deg`; точка устье + t·direction не
    ближе `target_m` к линии подошвы (та же линия, что у ЛСП, с правилом
    развала) и не за ней. Начальная оценка — по проекции направления на путь к
    ближайшей точке подошвы (точна для прямого участка), затем проверка
    `toe_positions` и, где не прошла, деление пополам. ЛСП вертикальной не
    больше `target_m` — 0. None — линии подошвы нет.
    """
    base = toe_positions(contour, collars, heights)
    if base is None:
        return None
    tan_max = math.tan(math.radians(tilt_deg))
    caps: list[float] = []
    for (x, y), height, position in zip(collars, heights, base):
        room = position.distance_m - target_m
        if height <= 0 or room <= 1e-6 or position.beyond:
            caps.append(0.0)
            continue
        limit = height * tan_max
        ux, uy = position.toe_point[0] - x, position.toe_point[1] - y
        norm = math.hypot(ux, uy)
        cos = (ux * direction[0] + uy * direction[1]) / norm if norm > 1e-12 else 0.0
        caps.append(min(limit, room / cos) if cos > 1e-9 else limit)

    def failing(indices: list[int], shifts: list[float]) -> list[bool]:
        points = [(collars[i][0] + direction[0] * t, collars[i][1] + direction[1] * t) for i, t in zip(indices, shifts)]
        found = toe_positions(contour, points, [heights[i] for i in indices]) or []
        return [p.beyond or p.distance_m < target_m - 1e-6 for p in found]

    todo = [i for i, t in enumerate(caps) if t > 0]
    bad = [i for i, fail in zip(todo, failing(todo, [caps[i] for i in todo])) if fail]
    # Деление пополам: [0, lo] проходит, hi — нет.
    low = {i: 0.0 for i in bad}
    high = {i: caps[i] for i in bad}
    for _ in range(40):
        if not bad:
            break
        mids = [0.5 * (low[i] + high[i]) for i in bad]
        for i, mid, fail in zip(bad, mids, failing(bad, mids)):
            if fail:
                high[i] = mid
            else:
                low[i] = mid
        bad = [i for i in bad if high[i] - low[i] > 1e-7]
    for i in low:
        caps[i] = low[i]
    return caps


# Столбец сетки для плавного перехода: устья с проекцией на ось ряда в
# пределах этой доли шага a — один столбец (у шахматки соседний столбец — в
# полшага, он свой; у variable с разным a по рядам совпадают лишь общие узлы).
TAPER_COLUMN_TOLERANCE_RATIO = 0.1
# Разрыв участка ряда: соседние по ряду устья дальше этого числа шагов ряда.
TAPER_SEGMENT_GAP_RATIO = 1.5


def taper_reach_m(contour: BlockContour, tilt_deg: float) -> float:
    """Наибольший сдвиг устья к откосу при плавном переходе: H·tg α, м."""
    return contour.bench.height_m * math.tan(math.radians(tilt_deg))


# Точка на границе контура — внутри (допуск округления), м.
_ON_EDGE_M = 1e-7


def _swept_inside(
    boundary: list[tuple[float, float]], advance_dir: tuple[float, float], reach_m: float
) -> Callable[[float, float], bool]:
    """Узел внутри контура или вернётся в него сдвигом к откосу не больше `reach_m`.

    Область — контур, протянутый на `reach_m` вглубь (по `advance_dir`):
    объединение контура, его копии со сдвигом и параллелограммов на рёбрах.
    """
    ox, oy = advance_dir[0] * reach_m, advance_dir[1] * reach_m
    ring = list(boundary)
    parts = [shapely.Polygon(ring), shapely.Polygon([(x + ox, y + oy) for x, y in ring])]
    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
        quad = shapely.Polygon([(ax, ay), (bx, by), (bx + ox, by + oy), (ax + ox, ay + oy)])
        if quad.area > 1e-12:
            parts.append(quad)
    region = shapely.union_all([shapely.make_valid(part) for part in parts]).buffer(_ON_EDGE_M)
    shapely.prepare(region)

    def inside(x: float, y: float) -> bool:
        return bool(shapely.intersects_xy(region, x, y))

    return inside


def _covered(boundary: list[tuple[float, float]], points: np.ndarray) -> np.ndarray:
    """Точки внутри контура или на его границе (как `point_in_polygon`), пакетом."""
    if len(points) == 0:
        return np.zeros(0, dtype=bool)
    polygon = shapely.make_valid(shapely.Polygon(boundary))
    shapely.prepare(polygon)
    return np.asarray(shapely.dwithin(polygon, shapely.points(points), _ON_EDGE_M), dtype=bool)


def _taper_columns(
    collars: np.ndarray, direction: tuple[float, float], tolerance: float, skip: int
) -> list[list[int]]:
    """Столбцы сетки: скважины (с индекса `skip`) с одной проекцией на ось ряда.

    Проекции сортируются и режутся там, где соседние дальше `tolerance`.
    Внутри столбца — от откоса вглубь (по продвижению вдоль `direction`, к
    откосу — первая).
    """
    indices = np.arange(skip, len(collars))
    if indices.size == 0:
        return []
    across = collars[indices, 0] * -direction[1] + collars[indices, 1] * direction[0]
    toward = collars[indices, 0] * direction[0] + collars[indices, 1] * direction[1]
    order = np.argsort(across, kind="stable")
    columns: list[list[int]] = []
    current = [int(order[0])]
    for k in order[1:]:
        if across[k] - across[current[-1]] > tolerance:
            columns.append(current)
            current = []
        current.append(int(k))
    columns.append(current)
    return [[int(indices[k]) for k in sorted(column, key=lambda k: -toward[k])] for column in columns]


def _row_segments(
    grid: list[Hole], collars: np.ndarray, direction: tuple[float, float], first: list[bool], spacing_a: float
) -> list[list[int]]:
    """Участки ряда: подряд идущие скважины одного ряда решётки, первые в своих столбцах.

    Участок рвёт скважина ряда, которая в своём столбце не первая (или не
    наклоняется — `first` ложно), и пропуск столбца: соседние по ряду устья
    дальше 1,5 шага ряда (шаг — наименьший промежуток в ряду, у ряда из двух
    скважин — не больше `spacing_a`).
    """
    by_row: dict[int, list[int]] = {}
    for i, hole in enumerate(grid):
        by_row.setdefault(hole.row, []).append(i)
    segments: list[list[int]] = []
    for indices in by_row.values():
        along = {i: collars[i, 0] * -direction[1] + collars[i, 1] * direction[0] for i in indices}
        indices.sort(key=lambda i: along[i])
        gaps = [along[b] - along[a] for a, b in zip(indices, indices[1:])]
        step = min(gaps) if len(gaps) > 1 else min(gaps + [spacing_a])
        current: list[int] = []
        previous: int | None = None
        for i in indices:
            broken = previous is not None and along[i] - along[previous] > TAPER_SEGMENT_GAP_RATIO * step
            if current and (broken or not first[i]):
                segments.append(current)
                current = []
            if first[i]:
                current.append(i)
            previous = i
        if current:
            segments.append(current)
    return segments


def _taper_front_rows(
    grid: list[Hole],
    face_row_count: int,
    contour: BlockContour,
    boundary: list[tuple[float, float]],
    advance_dir: tuple[float, float],
    tilt_count: int,
    tilt_deg: float,
    target_m: float,
    tilt_kinds: set[str],
    spacing_a: float,
    burden_b: float,
    subdrill_m: float,
    surfaces: object | None,
    depth_override: float | None,
) -> tuple[list[Hole], dict[int, tuple[float, float]]]:
    """Плавный переход: ряды 1–`tilt_count` у откоса наклонены, шаг b — у подошвы.

    Все наклоны и сдвиги — вдоль линии столбца к откосу (−`advance_dir`):
    скважины соседних рядов остаются на одной линии (поперечные заходки
    зарядной машины). Ранг здесь — по столбцу (`_taper_columns`): первая от
    откоса скважина столбца — ранг 1, вторая — 2, дальше — 3 и глубже. Ряд
    вдоль бровки (первые `face_row_count`) — ранг 1 весь, скважины решётки за
    ним — со второго; их столбец берёт угол ближайшей по оси ряда скважины
    ряда вдоль бровки. Первая в столбце получает ранг 1, только если и по
    коридору к бровке (`front_row_ranks`) она ранг 1; иначе столбец начинается
    в глубине блока — он остаётся без наклона и сдвига.

    Участок ряда (`_row_segments`) получает один угол α₁ — наименьший из
    допустимых по его скважинам (`_tilt_caps_m`: не больше `tilt_deg`, ЛСП
    не меньше `target_m`, низ не за подошвой), устья ранга 1 — на месте.
    Столбец берёт угол своей первой скважины: ранг 2 при `tilt_count` = 2 —
    α₁/2, остальные — общий угол паспорта; устья ранга k ≥ 2 сдвигаются к
    откосу на H·(tg α₁ − tg α_k) (α_k = 0 за переходом, H — высота уступа
    блока): у подошвы между соседями столбца — шаг сетки. Наклоняются только
    виды `tilt_kinds`; сдвигаются все скважины столбца.

    В `grid` могут быть узлы решётки за контуром (у тыла и флангов), которые
    сдвиг вернёт внутрь: они не бывают первыми в столбце, а скважина, чьё
    устье после сдвига вне контура (`boundary`), не ставится.

    Возвращает скважины и место в сетке до сдвига у сдвинутых (по `id()`
    объекта) — для нумерации: ряды остаются рядами решётки, даже когда
    устья соседних рядов сблизились меньше допуска нумерации.
    """
    if not grid:
        return grid, {}
    direction = (-advance_dir[0], -advance_dir[1])
    azimuth = math.degrees(math.atan2(direction[0], direction[1])) % 360.0
    collars = np.asarray([(h.collar.x, h.collar.y) for h in grid], dtype=float)
    inside = _covered(boundary, collars)
    inside[:face_row_count] = True

    # Ранг по столбцу; узлы за контуром идут за скважинами внутри.
    rank = [1] * len(grid)
    head = [-1] * len(grid)  # первая скважина столбца (или ряда вдоль бровки)
    for i in range(face_row_count):
        head[i] = i
    face_across = collars[:face_row_count, 0] * -direction[1] + collars[:face_row_count, 1] * direction[0]
    tolerance = TAPER_COLUMN_TOLERANCE_RATIO * spacing_a
    corridor = front_row_ranks([tuple(xy) for xy in collars], contour, spacing_a, burden_b, forced_first=face_row_count)
    for column in _taper_columns(collars, direction, tolerance, face_row_count):
        ordered = [i for i in column if inside[i]] + [i for i in column if not inside[i]]
        if not inside[ordered[0]]:
            for i in ordered:
                rank[i] = 0  # столбец целиком за контуром — не ставится
            continue
        anchor = ordered[0]
        if not face_row_count and corridor[anchor] != 1:
            # Первая в столбце, но не у откоса (столбец начинается в глубине
            # блока — у variable с разным a по рядам): без наклона и сдвига.
            for i in ordered:
                rank[i] = 3
            continue
        if face_row_count:
            across = collars[anchor, 0] * -direction[1] + collars[anchor, 1] * direction[0]
            anchor = int(np.argmin(np.abs(face_across - across)))
        for k, i in enumerate(ordered):
            rank[i] = k + (2 if face_row_count else 1)
            head[i] = anchor

    first = [rank[i] == 1 and grid[i].kind in tilt_kinds for i in range(len(grid))]
    picked = [i for i in range(len(grid)) if first[i]]
    tan_first = [0.0] * len(grid)
    if picked:
        heights = [grid[i].bench_height_m for i in picked]
        caps = _tilt_caps_m(contour, [tuple(collars[i]) for i in picked], heights, direction, tilt_deg, target_m)
        if caps is not None:
            tan_of = {i: (cap / height if height > 0 else 0.0) for i, cap, height in zip(picked, caps, heights)}
            # Угол участка — наименьший из допустимых по его скважинам.
            for segment in _row_segments(grid, collars, direction, first, spacing_a):
                value = min(tan_of[i] for i in segment)
                for i in segment:
                    tan_first[i] = value

    height = contour.bench.height_m
    tan_1s = np.zeros(len(grid))
    tan_ks = np.zeros(len(grid))
    for i, hole in enumerate(grid):
        if rank[i] == 0:
            continue
        tan_1 = tan_first[head[i]] if head[i] >= 0 else 0.0
        if rank[i] == 1:
            tan_k = tan_first[i]
        elif rank[i] == 2 and tilt_count >= 2 and hole.kind in tilt_kinds:
            tan_k = math.tan(0.5 * math.atan(tan_1))
        else:
            tan_k = 0.0
        tan_1s[i], tan_ks[i] = tan_1, tan_k
    ranks_arr = np.asarray(rank)
    shifts = np.where(ranks_arr > 1, height * (tan_1s - tan_ks), 0.0)
    moved_xy = collars + np.outer(shifts, direction)
    check = (shifts > 1e-12) | ~inside
    keep = ranks_arr > 0
    keep[check] &= _covered(boundary, moved_xy[check])

    result: list[Hole] = []
    lattice_xy: dict[int, tuple[float, float]] = {}
    for i, hole in enumerate(grid):
        if not keep[i]:
            continue
        shift, tan_k = float(shifts[i]), float(tan_ks[i])
        if tan_k <= 1e-12 and shift <= 1e-12:
            result.append(hole)
            continue
        x, y = float(moved_xy[i, 0]), float(moved_xy[i, 1])
        if tan_k > 1e-12:
            collar, toe = drape_collar(
                x, y, math.degrees(math.atan(tan_k)), azimuth, subdrill_m, contour, surfaces, depth_override
            )
        elif surfaces is None:
            # Плоский уступ: отметки и глубина от положения не зависят — перенос.
            collar = Point3(x=x, y=y, z=hole.collar.z)
            toe = Point3(x=x + (hole.toe.x - hole.collar.x), y=y + (hole.toe.y - hole.collar.y), z=hole.toe.z)
        else:
            # Общий угол паспорта — тот же вектор оси, что у скважины сетки.
            dx, dy, dz = hole.toe.x - hole.collar.x, hole.toe.y - hole.collar.y, hole.toe.z - hole.collar.z
            angle = math.degrees(math.atan2(math.hypot(dx, dy), -dz)) if dz < 0 else 0.0
            own_azimuth = math.degrees(math.atan2(dx, dy)) % 360.0 if (dx or dy) else 0.0
            collar, toe = drape_collar(x, y, angle, own_azimuth, subdrill_m, contour, surfaces, depth_override)
        moved = replace(hole, collar=collar, toe=toe)
        if shift > 1e-12:
            lattice_xy[id(moved)] = (float(collars[i, 0]), float(collars[i, 1]))
        result.append(moved)
    return result, lattice_xy


def _grid_id(kind: str, row_index: int, col_index: int) -> str:
    prefixes = {
        "buffer": "B",
        "stab": "S",
        "infill": "I",
        "satellite": "SAT",
    }
    prefix = prefixes.get(kind)
    if prefix:
        return f"{prefix}{row_index + 1}-{col_index + 1:02d}"
    return f"{row_index + 1}-{col_index + 1:02d}"


def _world_xy(
    origin: tuple[float, float],
    row_dir: tuple[float, float],
    advance_dir: tuple[float, float],
    u: float,
    v: float,
) -> tuple[float, float]:
    return (
        origin[0] + row_dir[0] * u + advance_dir[0] * v,
        origin[1] + row_dir[1] * u + advance_dir[1] * v,
    )


def _row_config(
    params: dict[str, Any],
    pattern: str,
    row_index: int,
    spacing_a: float,
    burden_b: float,
    row_shift_ratio: float,
    default_kind: str,
) -> tuple[float, float, float, str]:
    row_params = params.get("row_params") or []
    override: dict[str, Any] = {}
    if pattern == "variable" and isinstance(row_params, list) and row_params:
        if row_index < len(row_params) and isinstance(row_params[row_index], dict):
            override = row_params[row_index]
        elif isinstance(row_params[-1], dict):
            override = row_params[-1]
    local_a = float(override.get("spacing_a_m", spacing_a))
    local_b = float(override.get("burden_b_m", burden_b))
    shift_ratio = float(override.get("shift_ratio", row_shift_ratio))
    kind = _normalize_kind(override.get("kind", default_kind), default_kind)
    if local_a <= 0:
        local_a = spacing_a
    if local_b <= 0:
        local_b = burden_b
    return local_a, local_b, shift_ratio, kind


def _walk_domain_row(
    contour: BlockContour,
    domains: list[BlastDomain],
    boundary: list[tuple[float, float]],
    origin: tuple[float, float],
    row_dir: tuple[float, float],
    advance_dir: tuple[float, float],
    u_start: float,
    u_max: float,
    v: float,
    fallback_a: float,
    row_index: int,
    row_kind: str,
    diameter_mm: float,
    subdrill_m: float,
    angle_deg: float,
    azimuth_deg: float,
    depth_override: float | None,
    surfaces: object | None,
    crest_z: float,
    accept: Callable[[float, float], bool] | None = None,
    inside: Callable[[float, float], bool] | None = None,
) -> list[Hole]:
    holes: list[Hole] = []
    u = u_start
    col_index = 0
    probe = max(0.25, fallback_a * 0.25)
    safety = 0
    while u <= u_max and safety < 2000:
        safety += 1
        x, y = _world_xy(origin, row_dir, advance_dir, u, v)
        placeable = inside(x, y) if inside is not None else point_in_polygon((x, y), boundary)
        if not placeable or (accept is not None and not accept(x, y)):
            u += probe
            continue
        domain = domain_at(domains, Point3(x=x, y=y, z=crest_z))
        local_a = fallback_a
        if domain is not None and domain.spacing_a_m:
            local_a = float(domain.spacing_a_m)
        if local_a <= 0:
            local_a = fallback_a
        collar, toe = drape_collar(
            x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_override
        )
        holes.append(
            Hole(
                id=_grid_id(row_kind, row_index, col_index),
                row=row_index,
                col=col_index,
                collar=collar,
                toe=toe,
                diameter_mm=diameter_mm,
                subdrill_m=subdrill_m,
                kind=row_kind,
                source="generated",
            )
        )
        col_index += 1
        u += local_a
    return holes


def _off_face_filter(contour: BlockContour, min_distance_m: float) -> Callable[[float, float], bool]:
    def accept(x: float, y: float) -> bool:
        distance = distance_to_free_faces((x, y), contour)
        return distance is None or distance >= min_distance_m - 1e-9

    return accept


def _keep_manual(existing_holes: list[Hole] | None) -> list[Hole]:
    if not existing_holes:
        return []
    return [h for h in existing_holes if h.source == "manual"]


def _inward_normal(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (0.0, 0.0)
    ux, uy = dx / length, dy / length
    return (-uy, ux)


def _generate_face_following_row(
    contour: BlockContour,
    params: dict[str, Any],
    boundary: list[tuple[float, float]],
    origin: tuple[float, float],
    row_dir: tuple[float, float],
    advance_dir: tuple[float, float],
    burden_m: float,
    spacing_a: float,
    diameter_mm: float,
    subdrill_m: float,
    angle_deg: float,
    azimuth_deg: float,
    depth_m: float | None,
    kind: str,
    surfaces: object | None,
) -> list[Hole]:
    """Place row 0 at a constant burden from the actual free-face polyline."""
    verts = ensure_ccw(contour.points_xy)
    start_offset = float(params.get("first_row_start_offset_m", 0.0))
    holes: list[Hole] = []
    col_index = 0
    for edge in contour.free_faces:
        for i in range(len(edge) - 1):
            if not (0 <= edge[i] < len(verts) and 0 <= edge[i + 1] < len(verts)):
                continue
            a, b = verts[edge[i]], verts[edge[i + 1]]
            nx, ny = _inward_normal(a, b)
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 1e-9 or spacing_a <= 0:
                continue
            ux, uy = dx / length, dy / length
            distance = start_offset
            while distance <= length:
                x = a[0] + ux * distance + nx * burden_m
                y = a[1] + uy * distance + ny * burden_m
                if point_in_polygon((x, y), boundary):
                    collar, toe = drape_collar(
                        x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
                    )
                    holes.append(
                        Hole(
                            id=_grid_id(kind, 0, col_index),
                            row=0,
                            col=col_index,
                            collar=collar,
                            toe=toe,
                            diameter_mm=diameter_mm,
                            subdrill_m=subdrill_m,
                            kind=kind,
                            source="generated",
                        )
                    )
                    col_index += 1
                distance += spacing_a
    return holes


def _generate_wall_row(
    contour: BlockContour,
    params: dict[str, Any],
    kind: str,
    prefix: str,
    flag_key: str,
    spacing_key: str,
    offset_key: str,
    diameter_key: str,
    depth_key: str,
    subdrill_key: str,
    angle_key: str,
    default_diameter_mm: float,
    default_depth_m: float | None,
    default_subdrill_m: float,
    surfaces: object | None = None,
) -> list[Hole]:
    if not params.get(flag_key):
        return []
    spacing = float(params.get(spacing_key, 2.0))
    start_offset = float(params.get(offset_key, 1.0))
    if spacing <= 0:
        return []
    diameter_mm = float(params.get(diameter_key, default_diameter_mm))
    raw_depth = params.get(depth_key, default_depth_m)
    depth_m = float(raw_depth) if raw_depth is not None else None
    subdrill_m = float(params.get(subdrill_key, default_subdrill_m))
    angle_deg = float(params.get(angle_key, 0.0))

    verts = contour.points_xy
    holes: list[Hole] = []
    for edge_idx, edge in enumerate(contour.free_faces):
        col_index = 0
        for i in range(len(edge) - 1):
            a = verts[edge[i]]
            b = verts[edge[i + 1]]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue
            ux, uy = dx / length, dy / length
            azimuth_deg = math.degrees(math.atan2(ux, uy)) % 360.0
            distance = start_offset
            while distance <= length:
                x = a[0] + ux * distance
                y = a[1] + uy * distance
                collar, toe = drape_collar(
                    x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
                )
                holes.append(
                    Hole(
                        id=f"{prefix}{edge_idx + 1}-{col_index + 1:02d}",
                        row=-(edge_idx + 1),
                        col=col_index,
                        collar=collar,
                        toe=toe,
                        diameter_mm=diameter_mm,
                        subdrill_m=subdrill_m,
                        kind=kind,
                        source="generated",
                    )
                )
                col_index += 1
                distance += spacing
    return holes


def _generate_buffer_row(
    contour: BlockContour,
    params: dict[str, Any],
    boundary: list[tuple[float, float]],
    origin: tuple[float, float],
    row_dir: tuple[float, float],
    advance_dir: tuple[float, float],
    spacing_a: float,
    burden_b: float,
    diameter_mm: float,
    subdrill_m: float,
    angle_deg: float,
    azimuth_deg: float,
    depth_m: float | None,
    surfaces: object | None,
) -> list[Hole]:
    spacing = float(params.get("buffer_spacing_m", spacing_a))
    offset = float(params.get("buffer_offset_m", max(0.5, burden_b * 0.5)))
    if spacing <= 0:
        return []
    verts = ensure_ccw(contour.points_xy)
    holes: list[Hole] = []
    col_index = 0
    if contour.free_faces:
        for edge in contour.free_faces:
            for i in range(len(edge) - 1):
                if not (0 <= edge[i] < len(verts) and 0 <= edge[i + 1] < len(verts)):
                    continue
                a, b = verts[edge[i]], verts[edge[i + 1]]
                nx, ny = _inward_normal(a, b)
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dy)
                if length < 1e-9:
                    continue
                ux, uy = dx / length, dy / length
                distance = 0.0
                while distance <= length:
                    x = a[0] + ux * distance + nx * offset
                    y = a[1] + uy * distance + ny * offset
                    if point_in_polygon((x, y), boundary):
                        collar, toe = drape_collar(
                            x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
                        )
                        holes.append(
                            Hole(
                                id=_grid_id("buffer", 0, col_index),
                                row=-10,
                                col=col_index,
                                collar=collar,
                                toe=toe,
                                diameter_mm=float(params.get("buffer_diameter_mm", diameter_mm)),
                                subdrill_m=subdrill_m,
                                kind="buffer",
                                source="generated",
                            )
                        )
                        col_index += 1
                    distance += spacing
        return holes

    us = [(vx - origin[0]) * row_dir[0] + (vy - origin[1]) * row_dir[1] for vx, vy in verts]
    u = min(us)
    while u <= max(us):
        x, y = _world_xy(origin, row_dir, advance_dir, u, offset)
        if point_in_polygon((x, y), boundary):
            collar, toe = drape_collar(
                x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
            )
            holes.append(
                Hole(
                    id=_grid_id("buffer", 0, col_index),
                    row=-10,
                    col=col_index,
                    collar=collar,
                    toe=toe,
                    diameter_mm=float(params.get("buffer_diameter_mm", diameter_mm)),
                    subdrill_m=subdrill_m,
                    kind="buffer",
                    source="generated",
                )
            )
            col_index += 1
        u += spacing
    return holes


def _generate_stab_holes(
    holes: list[Hole],
    contour: BlockContour,
    params: dict[str, Any],
    surfaces: object | None,
) -> list[Hole]:
    """Short holes midway between first-row production holes (or in front if a single hole).

    «Первый ряд» — ряд, ближайший к свободной поверхности: самый дальний впереди
    (наименьший логический номер). Без рядов впереди это ряд 0, как и прежде.
    """
    production = [h for h in holes if h.enabled and h.kind == "production"]
    if not production:
        return []
    face_row = min(logical_row(h.row) for h in production)
    first_row = [h for h in production if logical_row(h.row) == face_row]
    ordered = sorted(first_row, key=lambda h: h.col)
    depth_m = float(params.get("stab_depth_m", 3.0))
    angle_deg = float(params.get("stab_angle_deg", params.get("angle_deg", 0.0)))
    azimuth_deg = float(params.get("stab_azimuth_deg", params.get("azimuth_deg", 0.0)))
    subdrill_m = float(params.get("stab_subdrill_m", 0.0))
    diameter_mm = float(params.get("stab_diameter_mm", params.get("diameter_mm", 152.0)))
    created: list[Hole] = []
    if len(ordered) == 1:
        hole = ordered[0]
        x = hole.collar.x
        y = hole.collar.y
        collar, toe = drape_collar(x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m)
        created.append(
            Hole(
                id="S1-01",
                row=hole.row,
                col=0,
                collar=collar,
                toe=toe,
                diameter_mm=diameter_mm,
                subdrill_m=subdrill_m,
                kind="stab",
                source="generated",
            )
        )
        return created
    for index, (left, right) in enumerate(zip(ordered, ordered[1:])):
        x = 0.5 * (left.collar.x + right.collar.x)
        y = 0.5 * (left.collar.y + right.collar.y)
        collar, toe = drape_collar(x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m)
        created.append(
            Hole(
                id=f"S1-{index + 1:02d}",
                row=left.row,
                col=index,
                collar=collar,
                toe=toe,
                diameter_mm=diameter_mm,
                subdrill_m=subdrill_m,
                kind="stab",
                source="generated",
            )
        )
    return created


def _generate_satellite_holes(
    holes: list[Hole],
    contour: BlockContour,
    params: dict[str, Any],
    surfaces: object | None,
) -> list[Hole]:
    production = [h for h in holes if h.enabled and h.kind == "production"]
    if not production:
        return []
    radius = float(params.get("satellite_radius_m", 1.5))
    count = max(1, int(params.get("satellite_count", 1)))
    depth_override = params.get("satellite_depth_m", params.get("depth_m"))
    depth_m = float(depth_override) if depth_override is not None else None
    angle_deg = float(params.get("angle_deg", 0.0))
    azimuth_deg = float(params.get("azimuth_deg", 0.0))
    subdrill_m = float(params.get("subdrill_m", 1.0))
    diameter_mm = float(params.get("satellite_diameter_mm", params.get("diameter_mm", 152.0)))
    created: list[Hole] = []
    for hole in production:
        for index in range(count):
            bearing = math.radians((azimuth_deg + index * (360.0 / count)) % 360.0)
            x = hole.collar.x + radius * math.sin(bearing)
            y = hole.collar.y + radius * math.cos(bearing)
            if not point_in_polygon((x, y), contour.points_xy):
                continue
            collar, toe = drape_collar(
                x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
            )
            created.append(
                Hole(
                    id=f"SAT-{hole.id}-{index + 1}",
                    row=hole.row,
                    col=index,
                    collar=collar,
                    toe=toe,
                    diameter_mm=diameter_mm,
                    subdrill_m=subdrill_m,
                    kind="satellite",
                    source="generated",
                )
            )
    return created


def _generate_infill_holes(
    holes: list[Hole],
    contour: BlockContour,
    params: dict[str, Any],
    surfaces: object | None,
) -> list[Hole]:
    factor = float(params.get("infill_gap_factor", 1.6))
    production = [h for h in holes if h.enabled and h.kind == "production"]
    by_row: dict[int, list[Hole]] = {}
    for hole in production:
        by_row.setdefault(hole.row, []).append(hole)
    expected_a = float(params.get("spacing_a_m", 5.0))
    threshold = expected_a * factor
    angle_deg = float(params.get("angle_deg", 0.0))
    azimuth_deg = float(params.get("azimuth_deg", 0.0))
    subdrill_m = float(params.get("subdrill_m", 1.0))
    depth_override = params.get("depth_m")
    depth_m = float(depth_override) if depth_override is not None else None
    diameter_mm = float(params.get("diameter_mm", 152.0))
    created: list[Hole] = []
    index = 0
    for row, group in by_row.items():
        ordered = sorted(group, key=lambda h: h.col)
        for left, right in zip(ordered, ordered[1:]):
            gap = math.hypot(right.collar.x - left.collar.x, right.collar.y - left.collar.y)
            if gap < threshold:
                continue
            x = 0.5 * (left.collar.x + right.collar.x)
            y = 0.5 * (left.collar.y + right.collar.y)
            if not point_in_polygon((x, y), contour.points_xy):
                continue
            collar, toe = drape_collar(
                x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
            )
            created.append(
                Hole(
                    id=f"I-{index + 1:02d}",
                    row=row,
                    col=index,
                    collar=collar,
                    toe=toe,
                    diameter_mm=diameter_mm,
                    subdrill_m=subdrill_m,
                    kind="infill",
                    source="generated",
                )
            )
            index += 1
    return created
