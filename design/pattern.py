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
from design.models import (
    FACE_PAIR_ID_SUFFIX,
    FACE_TOE_KIND,
    FRONT_ROW_BASE,
    HOLE_KINDS,
    BlastDomain,
    BlockContour,
    Hole,
    Point3,
    logical_row,
    row_family,
)
from design.toe_line import (
    MIN_CREST_OFFSET_DEFAULT_M,
    TOE_BURDEN_TOLERANCE,
    allowed_floor_burden_m,
    corridor_blocker_pairs,
    crest_geometry,
    floor_point,
    hole_bench_height_m,
    min_crest_offset_m,
    min_floor_burden_m,
    row_steps_m,
    shadow_limits,
    toe_positions,
)

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
# Пара у откоса: устье наклонной на столько ближе к уступу, чем у вертикальной
# первого ряда, по линии столбца, м (решение владельца 22.10.2026).
FACE_PAIR_OFFSET_M = 1.0
# Шаг прохода при поиске упора устья пары (`_collar_reach_m`), м.
COLLAR_REACH_STEP_M = 0.05
# Азимут наклонной пары — к ближайшей точке линии подошвы (по нормали к
# откосу), но не дальше этого от линии столбца (решение владельца 06.11.2026).
FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG = 15.0
# Шаблон раскладки «от тыла» (`layout_anchor`; нет ключа — от бровки):
# `design/back_layout.py`. Только квадратная и прямоугольная сетки.
LAYOUT_ANCHOR_BACK = "back"
LAYOUT_ANCHOR_PATTERNS = ("square", "rectangular")


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
      front_rows_mode         pair | taper — схема первого ряда у откоса (нет ключа — taper при count > 0)
      front_rows_tilt_count   0–2 рядов у откоса с наклоном к откосу (нет ключа — 0)
      front_rows_tilt_deg     угол наклона от вертикали, 0–30° (нет ключа — 15°): у перехода —
                              наибольший; у пары 0 — без наклона, иначе наклон до 30°, наименьший
                              до ЛСП ≈ W (после сдвига устья к кромке)
      grid_shift_along_m      сдвиг узлов решётки вдоль ряда, м (по модулю шага a; нет ключа — 0;
                              ряд вдоль бровки не сдвигается)
      min_crest_offset_m      минимальный отступ устья от кромки (нет ключа — 0,2 м)
      layout_anchor           "back" — шаблон «от тыла» (`design/back_layout.py`; только
                              square/rectangular, нужен тыл); нет ключа — от бровки.
                              Схема первого ряда (`front_rows_mode`, `front_rows_tilt_count`)
                              и ряд вдоль бровки не применяются — их заменяет конец эшелона
      back_offset_m           отступ приконтурного ряда от тыла, м (нет ключа — 0,65·b)
                              У «от тыла» `front_rows_tilt_deg` — верхний предел наклона
                              последней скважины эшелона: берётся наименьший угол до ЛСП ≈ W
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
    grid_shift = float(params.get("grid_shift_along_m", 0.0) or 0.0)
    edge_margin = float(params.get("edge_margin_m", 0.0))
    diameter_mm, subdrill_m, angle_deg, azimuth_deg, depth_override = hole_spec(params, row_azimuth_deg)
    default_kind = _normalize_kind(params.get("default_kind", "production"), "production")
    domain_list = list(domains or [])
    tilt_count, tilt_deg = _front_rows_tilt(params)
    if not contour.free_faces:
        tilt_count = 0
    mode = front_rows_mode(params, tilt_count) if contour.free_faces else None
    if mode == FRONT_ROWS_MODE_TAPER and pattern == "staggered":
        # Шахматка в оптимизатор не входит: столбцы через ряд, и переход
        # разводит ряды 1–2 у подошвы. Сетка — как без ключей (решение 22.10.2026).
        mode = None
    taper = mode == FRONT_ROWS_MODE_TAPER and tilt_count > 0

    verts = ensure_ccw(contour.points_xy)
    if len(verts) < 3 or spacing_a <= 0 or burden_b <= 0:
        return _keep_manual(existing_holes)

    boundary = offset_polygon(verts, edge_margin) if edge_margin > 0 else verts
    row_dir, advance_dir = local_basis(row_azimuth_deg)
    origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)

    if params.get("layout_anchor") == LAYOUT_ANCHOR_BACK and pattern in LAYOUT_ANCHOR_PATTERNS:
        from design.back_layout import back_grid, back_side

        if back_side(contour) is not None:
            return _finish_pattern(
                back_grid(contour, params, boundary, surfaces),
                contour, params, existing_holes, surfaces, boundary, origin, row_dir, advance_dir,
                spacing_a, burden_b, diameter_mm, subdrill_m, angle_deg, azimuth_deg, depth_override,
            )

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
        if grid_shift:
            shift += grid_shift % local_a
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
    # Схема первого ряда работает с основной сеткой: у variable строка
    # `row_params` может дать ряду у откоса другой вид (например, infill) — он
    # остаётся рядом основной сетки. Стенки (буфер, контур, предщель,
    # оконтуривание) и face_toe, заданные строкой, схемой не трогаются
    # (`_front_rows_member`). В `_off_crest`, `_face_pairs` и
    # `_taper_front_rows` уходит только основная сетка.
    lattice_xy: dict[int, tuple[float, float]] = {}
    pair_of: dict[int, int] = {}  # id() пары → id() её вертикальной
    if mode == FRONT_ROWS_MODE_PAIR:
        # Устья основной сетки не ближе `min_crest_offset_m` к кромке — до
        # постановки пар (у пары свой отступ проверяется при постановке).
        def pair_row_burden(hole: Hole) -> float:
            # Шаг b ряда скважины — как у генератора и проверки разрыва
            # (`toe_line._hole_steps`): у сетки по доменам — b домена у устья.
            if pattern == "domain_dependent" and domain_list:
                domain = domain_at(domain_list, Point3(x=hole.collar.x, y=hole.collar.y, z=crest_z))
                if domain is not None and domain.burden_b_m:
                    return float(domain.burden_b_m)
            return row_steps_m(params, pattern, max(logical_row(hole.row), 0), spacing_a, burden_b)[1]

        face_row = holes[:face_row_count]
        holes = _off_crest(holes, contour, min_crest_offset_m(params))
        face_row_count = len(_off_crest(face_row, contour, min_crest_offset_m(params)))
        for partner, pair in _face_pairs(
            holes,
            face_row_count,
            contour,
            boundary,
            advance_dir,
            tilt_deg,
            tilt_floor_burden_target_m(params),
            allowed_floor_burden_m(params),
            min_crest_offset_m(params),
            spacing_a,
            burden_b,
            subdrill_m,
            surfaces,
            depth_override,
            row_burden=pair_row_burden,
        ):
            pair_of[id(pair)] = id(partner)
            holes.append(pair)
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
            spacing_a,
            burden_b,
            subdrill_m,
            surfaces,
            depth_override,
        )
    if mode is not None and mode != FRONT_ROWS_MODE_PAIR:
        # Схема первого ряда задана: устья основной сетки не ближе
        # `min_crest_offset_m` к кромке — после сдвига плавного перехода.
        holes = _off_crest(holes, contour, min_crest_offset_m(params))

    return _finish_pattern(
        holes, contour, params, existing_holes, surfaces, boundary, origin, row_dir, advance_dir,
        spacing_a, burden_b, diameter_mm, subdrill_m, angle_deg, azimuth_deg, depth_override,
        lattice_xy=lattice_xy, pair_of=pair_of,
    )


def hole_spec(
    params: dict[str, Any], row_azimuth_deg: float
) -> tuple[float, float, float, float, float | None]:
    """Параметры скважин сетки: диаметр, перебур, угол, азимут (нет ключа —
    азимут рядов) и заданная глубина (`depth_m`, нет ключа — None). Один разбор
    для сетки от бровки и шаблона «от тыла» (`design/back_layout.py`)."""
    depth = params.get("depth_m")
    return (
        float(params.get("diameter_mm", 152.0)),
        float(params.get("subdrill_m", 1.0)),
        float(params.get("angle_deg", 0.0)),
        float(params.get("azimuth_deg", row_azimuth_deg)),
        float(depth) if depth is not None else None,
    )


def _finish_pattern(
    holes: list[Hole],
    contour: BlockContour,
    params: dict[str, Any],
    existing_holes: list[Hole] | None,
    surfaces: object | None,
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
    depth_override: float | None,
    lattice_xy: dict[int, tuple[float, float]] | None = None,
    pair_of: dict[int, int] | None = None,
) -> list[Hole]:
    """Стенки, буфер, стабилизация, сателлиты, вставки и нумерация поверх основной сетки."""
    holes = list(holes)
    lattice_xy = lattice_xy or {}
    pair_of = pair_of or {}
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
    # Пара у откоса — номер своей вертикальной с «T».
    numbered = _keep_manual(existing_holes) + holes
    index_of = {id(h): k for k, h in enumerate(numbered)}
    return number_by_position(
        numbered,
        row_azimuth_deg=float(params.get("row_azimuth_deg", 0.0)),
        positions=[lattice_xy.get(id(h)) for h in numbered] if lattice_xy else None,
        partners=[index_of.get(pair_of[id(h)]) if id(h) in pair_of else None for h in numbered],
    )


def _front_rows_member(hole: Hole) -> bool:
    """Скважина основной сетки, к которой применяется схема первого ряда.

    Любой вид семейства сетки (`row_family` — «grid»), кроме стенок и
    «Наклонной у откоса»: их строка `row_params` задаёт явно, и наклон, пара
    или отступ от кромки их не касаются.
    """
    return row_family(hole.kind) == "grid" and hole.kind != FACE_TOE_KIND


def _off_crest(holes: list[Hole], contour: BlockContour, min_offset: float) -> list[Hole]:
    """Основная сетка (`holes`) без устьев схемы первого ряда ближе `min_offset` к кромке."""
    crest = crest_geometry(contour)
    if crest is None or min_offset <= 0 or not holes:
        return holes
    distances = shapely.distance(shapely.points([(h.collar.x, h.collar.y) for h in holes]), crest)
    return [
        h
        for h, d in zip(holes, distances)
        if not _front_rows_member(h) or d >= min_offset - 1e-9
    ]


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
# у откоса (`_face_pairs`).
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
    directions: list[tuple[float, float]],
    tilt_deg: float,
    target_m: float,
) -> list[float] | None:
    """Наибольший вынос точки оси на уровне подошвы вдоль своего направления
    (`directions[i]` — у каждой скважины), м, по скважинам.

    Вынос t = H·tg α не больше H·tg `tilt_deg`; точка устье + t·directions[i] не
    ближе `target_m` к линии подошвы (та же линия, что у ЛСП, с правилом
    развала) и не за ней. Начальная оценка — по проекции направления на путь к
    ближайшей точке подошвы (точна для прямого участка), затем проверка
    `toe_positions` и, где не прошла, деление пополам. ЛСП вертикальной не
    больше `target_m` — 0. None — линии подошвы нет.

    Это оценка: точка на подошве построенной скважины и её высота уступа
    другие (кровля, подошва TIN), поэтому угол затем проверяется по
    построенной скважине (`_verified_angles`).
    """
    base = toe_positions(contour, collars, heights)
    if base is None:
        return None
    tan_max = math.tan(math.radians(tilt_deg))
    caps: list[float] = []
    for (x, y), height, position, direction in zip(collars, heights, base, directions):
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
        points = [
            (collars[i][0] + directions[i][0] * t, collars[i][1] + directions[i][1] * t) for i, t in zip(indices, shifts)
        ]
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


# Шаг уменьшения угла, когда построенная скважина не проходит проверку ЛСП, °.
TILT_VERIFY_STEP_DEG = 0.25


def _tilt_holds(contour: BlockContour, holes: list[Hole], target_m: float) -> list[bool]:
    """ЛСП построенных скважин не меньше `target_m` и низ не за подошвой.

    Та же оценка, что у `floor_checks`: точка оси на уровне подошвы и высота
    уступа по оси скважины (у съёмки — с правилом развала по этой высоте).
    """
    if not holes:
        return []
    block_h = contour.bench.height_m
    found = toe_positions(
        contour, [floor_point(h) for h in holes], [hole_bench_height_m(h, block_h) for h in holes]
    )
    if found is None:
        return [True] * len(holes)
    return [not p.beyond and p.distance_m >= target_m - 1e-7 for p in found]


def _verified_angles(
    angles: list[float], passes: Callable[[list[int], list[float]], list[bool]]
) -> list[float]:
    """Углы, при которых построенные скважины проходят `passes`; 0 — ни один.

    Предел `_tilt_caps_m` — оценка по точке устье + H·tg α с высотой у устья, а
    ЛСП скважины — по её точке на подошве и её высоте уступа (кровля, подошва
    TIN). Линия подошвы рвётся (съёмка ↔ развал по высоте уступа), и оценка
    у разрыва может пройти, а скважина — нет. Угол, не прошедший проверку,
    уменьшается шагами `TILT_VERIFY_STEP_DEG` до первого проходящего, затем
    уточняется делением пополам между ним и непрошедшим. `passes(ключи, углы)` —
    пакетом.
    """
    result = list(angles)
    todo = [k for k, angle in enumerate(result) if angle > 1e-9]
    if not todo:
        return result
    high = {k: result[k] for k, ok in zip(todo, passes(todo, [result[k] for k in todo])) if not ok}
    low: dict[int, float] = {}
    pending = list(high)
    while pending:
        for k in [k for k in pending if high[k] - TILT_VERIFY_STEP_DEG <= 1e-9]:
            result[k] = 0.0
            del high[k]
        live = [k for k in pending if k in high]
        trial = [high[k] - TILT_VERIFY_STEP_DEG for k in live]
        pending = []
        for k, angle, ok in zip(live, trial, passes(live, trial)):
            if ok:
                low[k] = angle
            else:
                high[k] = angle
                pending.append(k)
    # Деление пополам: low проходит, high — нет.
    bisect = list(low)
    for _ in range(40):
        if not bisect:
            break
        mids = [0.5 * (low[k] + high[k]) for k in bisect]
        for k, mid, ok in zip(bisect, mids, passes(bisect, mids)):
            if ok:
                low[k] = mid
            else:
                high[k] = mid
        bisect = [k for k in bisect if high[k] - low[k] > 1e-9]
    for k, angle in low.items():
        result[k] = angle
    return result


def _clamped_direction(base: tuple[float, float], wanted: tuple[float, float], max_deg: float) -> tuple[float, float]:
    """Единичный `wanted`, повёрнутый к `base` так, чтобы угол между ними был не
    больше `max_deg`; нулевой `wanted` или смотрящий назад — `base`."""
    norm = math.hypot(*wanted)
    if norm < 1e-12:
        return base
    wx, wy = wanted[0] / norm, wanted[1] / norm
    cross = base[0] * wy - base[1] * wx
    dot = base[0] * wx + base[1] * wy
    if dot <= 0:
        return base
    angle = math.atan2(cross, dot)
    limit = math.radians(max_deg)
    if abs(angle) <= limit:
        return (wx, wy)
    turn = math.copysign(limit, angle)
    c, s = math.cos(turn), math.sin(turn)
    return (base[0] * c - base[1] * s, base[0] * s + base[1] * c)


def _floor_burdens_of(contour: BlockContour, holes: list[Hole]) -> list[float]:
    """ЛСП построенных скважин (по точке оси на подошве и своей высоте уступа)."""
    block_h = contour.bench.height_m
    found = toe_positions(contour, [floor_point(h) for h in holes], [hole_bench_height_m(h, block_h) for h in holes])
    return [p.distance_m for p in found] if found else [0.0] * len(holes)


def _raised_angles(
    contour: BlockContour,
    candidates: list[tuple[int, tuple[float, float], float]],
    angles: list[float],
    own_h: list[float],
    directions: list[tuple[float, float]],
    tilted: Callable[[int, float], Hole],
    holds: Callable[[list[int], list[float]], list[bool]],
    target_m: float,
    allowed_m: float,
) -> list[float]:
    """Угол пары, у которой ЛСП больше `allowed_m`: наименьший до
    `FRONT_ROWS_TILT_MAX_DEG`, при котором ЛСП ≤ `allowed_m`, но не больше
    наибольшего, при котором ЛСП ≥ `target_m` и забой не за подошвой
    (решение владельца 06.11.2026: не хватает ЛСП — поднимать угол).

    Деление пополам — пакетом по всем таким парам (один `toe_positions` на
    шаг). Итог проверяется `holds`: у скачка съёмка ↔ развал ЛСП немонотонна,
    и угол, не прошедший нижнюю границу, заменяется наибольшим допустимым.
    """

    def lsp(keys: list[int], values: list[float]) -> list[float]:
        return _floor_burdens_of(contour, [tilted(k, a) for k, a in zip(keys, values)])

    keys = list(range(len(candidates)))
    over = [k for k, value in zip(keys, lsp(keys, [angles[k] for k in keys])) if value > allowed_m + 1e-9]
    if not over:
        return angles
    caps = _tilt_caps_m(
        contour, [candidates[k][1] for k in over], [own_h[k] for k in over], [directions[k] for k in over],
        FRONT_ROWS_TILT_MAX_DEG, target_m,
    ) or [0.0] * len(over)
    ceiling = [
        math.degrees(math.atan(cap / own_h[k])) if cap > 1e-12 and own_h[k] > 0 else 0.0
        for k, cap in zip(over, caps)
    ]
    ceiling = _verified_angles(ceiling, lambda ks, vs: holds([over[i] for i in ks], vs))
    result = list(angles)
    top = {k: c for k, c in zip(over, ceiling) if c > angles[k] + 1e-9}
    if not top:
        return result
    live = list(top)
    at_top = lsp(live, [top[k] for k in live])
    low: dict[int, float] = {}
    high: dict[int, float] = {}
    for k, value in zip(live, at_top):
        if value > allowed_m + 1e-9:
            result[k] = top[k]  # и 30° не хватает — наибольший допустимый
        else:
            low[k], high[k] = angles[k], top[k]
    todo = list(low)
    for _ in range(40):
        if not todo:
            break
        mids = [0.5 * (low[k] + high[k]) for k in todo]
        for k, mid, value in zip(todo, mids, lsp(todo, mids)):
            if value > allowed_m:
                low[k] = mid
            else:
                high[k] = mid
        todo = [k for k in todo if high[k] - low[k] > 1e-6]
    found = list(high)
    for k, ok in zip(found, holds(found, [high[k] for k in found])):
        result[k] = high[k] if ok else top[k]
    return result


def _smallest_angles(
    contour: BlockContour,
    keys: list[int],
    ceiling: dict[int, float],
    tilted: Callable[[int, float], Hole],
    holds: Callable[[list[int], list[float]], list[bool]],
    goal_m: float,
) -> dict[int, float]:
    """Наименьший угол в [0, `ceiling[k]`], при котором ЛСП пары ≤ `goal_m`
    (решение владельца 06.11.2026: наклон — наименьший, до ЛСП ≈ W).

    Не хватает и `ceiling` — он сам. Деление пополам — пакетом (один
    `toe_positions` на шаг); итог проверяется `holds`: у скачка съёмка ↔
    развал ЛСП немонотонна, и угол, не прошедший нижнюю границу, заменяется
    наибольшим допустимым.
    """

    def lsp(ks: list[int], values: list[float]) -> list[float]:
        return _floor_burdens_of(contour, [tilted(k, a) for k, a in zip(ks, values)])

    result: dict[int, float] = {}
    live = [k for k in keys if ceiling[k] > 1e-9]
    for k in keys:
        if ceiling[k] <= 1e-9:
            result[k] = 0.0
    low: dict[int, float] = {}
    high: dict[int, float] = {}
    for k, value in zip(live, lsp(live, [ceiling[k] for k in live])):
        if value > goal_m + 1e-9:
            result[k] = ceiling[k]
        else:
            low[k], high[k] = 0.0, ceiling[k]
    todo = list(low)
    for _ in range(40):
        if not todo:
            break
        mids = [0.5 * (low[k] + high[k]) for k in todo]
        for k, mid, value in zip(todo, mids, lsp(todo, mids)):
            if value > goal_m:
                low[k] = mid
            else:
                high[k] = mid
        todo = [k for k in todo if high[k] - low[k] > 1e-6]
    found = list(high)
    for k, ok in zip(found, holds(found, [high[k] for k in found])):
        result[k] = high[k] if ok else ceiling[k]
    return result


def _collar_reach_m(
    starts: list[tuple[float, float]],
    direction: tuple[float, float],
    boundary: list[tuple[float, float]],
    crest,
    min_crest_m: float,
    limits_m: list[float],
) -> list[float]:
    """Наибольший сдвиг устья вдоль `direction` в [0, `limits_m[k]`], при
    котором устье на всём пути внутри контура и не ближе `min_crest_m` к
    кромке (пакетом)."""
    if not starts:
        return []
    # Допуск 1 мкм: узел на самом краю контура (x = −1e-16) — внутри, как у `point_in_polygon`.
    polygon = shapely.Polygon(boundary).buffer(1e-6)
    xs = np.asarray([p[0] for p in starts], dtype=float)
    ys = np.asarray([p[1] for p in starts], dtype=float)
    limits = np.asarray(limits_m, dtype=float)

    def ok(bx: np.ndarray, by: np.ndarray, t: np.ndarray) -> np.ndarray:
        px, py = bx + direction[0] * t, by + direction[1] * t
        return shapely.intersects_xy(polygon, px, py) & (
            shapely.distance(shapely.points(px, py), crest) >= min_crest_m - 1e-9
        )

    # У вогнутого контура годный упор не значит, что годен каждый меньший
    # сдвиг: первый негодный ищется проходом шагом `COLLAR_REACH_STEP_M`, затем
    # делением пополам между ним и последним годным — весь [0, итог] годен.
    count = int(np.ceil(float(limits.max(initial=0.0)) / COLLAR_REACH_STEP_M)) + 1
    fractions = np.linspace(0.0, 1.0, max(count, 2))
    samples = limits[:, None] * fractions[None, :]
    width = samples.shape[1]
    good = ok(np.repeat(xs, width), np.repeat(ys, width), samples.ravel()).reshape(samples.shape)
    bad_any = ~good.all(axis=1)
    first_bad = np.where(bad_any, np.argmin(good, axis=1), samples.shape[1])
    result = limits.copy()
    rows = np.nonzero(bad_any)[0]
    if rows.size:
        low = np.where(first_bad[rows] > 0, samples[rows, np.maximum(first_bad[rows] - 1, 0)], 0.0)
        high = samples[rows, first_bad[rows]]
        start_ok = first_bad[rows] > 0
        for _ in range(40):
            mid = 0.5 * (low + high)
            fine = ok(xs[rows], ys[rows], mid)
            low = np.where(fine, mid, low)
            high = np.where(fine, high, mid)
        result[rows] = np.where(start_ok, low, 0.0)
    return [float(v) for v in result]


def face_tilts(
    contour: BlockContour,
    holes: list[Hole],
    collars_xy: list[tuple[float, float]],
    base_direction: tuple[float, float],
    tilt_deg: float,
    target_m: float,
    allowed_m: float,
    subdrill_m: float,
    surfaces: object | None,
    depth_override: float | None,
) -> list[tuple[float, float]]:
    """Наклон к откосу: (угол от вертикали, азимут) для каждого устья `collars_xy`.

    `holes[k]` — скважина, из которой строится наклонная с устьем в
    `collars_xy[k]` (устье и забой заменяются, остальное — её). Азимут — к
    ближайшей точке линии подошвы от устья, не дальше
    `FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG` от `base_direction` (линия столбца к
    откосу). Угол — наибольший ≤ `tilt_deg`, при котором ЛСП не меньше
    `target_m` и низ не за подошвой (`_tilt_caps_m` по устью и своей высоте
    уступа, проверка построенной скважины — `_verified_angles`); если ЛСП с
    осью, перенесённой из `holes[k]` в новое устье, не больше `allowed_m` —
    0. При 0 < `tilt_deg` < 30° угол поднимается до 30°, пока ЛСП > `allowed_m`
    (`_raised_angles`). Общий помощник пары у откоса и конца эшелона шаблона
    «от тыла».
    """
    if not holes:
        return []
    block_h = contour.bench.height_m
    heights = [hole_bench_height_m(h, block_h) for h in holes]
    candidates = [(k, xy, height) for k, (xy, height) in enumerate(zip(collars_xy, heights))]
    # ЛСП с осью исходной скважины — по её точке на подошве, перенесённой в новое устье.
    shifts = [(x - h.collar.x, y - h.collar.y) for h, (x, y) in zip(holes, collars_xy)]
    plain = toe_positions(
        contour,
        [(fx + dx, fy + dy) for (fx, fy), (dx, dy) in zip((floor_point(h) for h in holes), shifts)],
        heights,
    ) or []

    # Наклон — к ближайшей точке линии подошвы от устья, не дальше
    # `FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG` от линии столбца.
    toward = toe_positions(contour, list(collars_xy), heights) or []
    directions = [
        _clamped_direction(base_direction, (p.toe_point[0] - xy[0], p.toe_point[1] - xy[1]), FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG)
        for xy, p in zip(collars_xy, toward)
    ] or [base_direction] * len(holes)
    azimuths = [math.degrees(math.atan2(d[0], d[1])) % 360.0 for d in directions]

    def tilted(k: int, angle: float) -> Hole:
        x, y = collars_xy[k]
        collar, toe = drape_collar(x, y, angle, azimuths[k], subdrill_m, contour, surfaces, depth_override)
        return replace(holes[k], collar=collar, toe=toe)

    # Предел угла — по новому устью (своя отметка кровли и своя высота
    # уступа), затем проверка построенной скважины (`_verified_angles`).
    own_h = [hole_bench_height_m(tilted(k, 0.0), block_h) for k in range(len(holes))]
    caps = _tilt_caps_m(contour, list(collars_xy), own_h, directions, tilt_deg, target_m) or [0.0] * len(holes)
    angles = [
        math.degrees(math.atan(cap / h)) if position.distance_m > allowed_m and cap > 1e-12 and h > 0 else 0.0
        for position, cap, h in zip(plain, caps, own_h)
    ] or [0.0] * len(holes)

    def holds(keys: list[int], values: list[float]) -> list[bool]:
        return _tilt_holds(contour, [tilted(k, a) for k, a in zip(keys, values)], target_m)

    angles = _verified_angles(angles, holds)
    if 0.0 < tilt_deg < FRONT_ROWS_TILT_MAX_DEG:
        angles = _raised_angles(contour, candidates, angles, own_h, directions, tilted, holds, target_m, allowed_m)
    return list(zip(angles, azimuths))


def _face_pairs(
    grid: list[Hole],
    face_row_count: int,
    contour: BlockContour,
    boundary: list[tuple[float, float]],
    advance_dir: tuple[float, float],
    tilt_deg: float,
    target_m: float,
    allowed_m: float | None,
    min_crest_m: float,
    spacing_a: float,
    burden_b: float,
    subdrill_m: float,
    surfaces: object | None,
    depth_override: float | None,
    row_burden: Callable[[Hole], float] | None = None,
) -> list[tuple[Hole, Hole]]:
    """Пара у откоса: (вертикальная, наклонная у откоса) для скважин ранга 1.

    `row_burden(hole)` — шаг b ряда скважины (у переменной сетки свой у ряда);
    без него — `burden_b`. От него — предел разрыва у подошвы b + 3 %.

    Пара ставится к скважине основной сетки (`grid` — только она;
    `_front_rows_member`) ранга 1
    (`front_row_ranks`), у которой ЛСП больше допустимой `allowed_m` (W + 3 %).
    Устье пары — ближе к откосу по линии столбца (−`advance_dir`), без
    смещения вдоль ряда: сдвиг не меньше `FACE_PAIR_OFFSET_M`, наименьший, при
    котором ЛСП вертикальной пары ≤ W, но не дальше упора в `min_crest_m` от
    кромки и в разрыв у подошвы с вертикальной b + 3 %. Если и у упора ЛСП
    больше W, а `tilt_deg` > 0, — наклон к откосу (азимут к ближайшей точке
    подошвы, не дальше 15° от столбца): наименьший угол до ЛСП ≈ W, не больше
    30°, ЛСП не меньше `target_m`, разрыв у подошвы — те же b + 3 %
    (`_smallest_angles`, проверка построенной пары — `_verified_angles`;
    решение владельца 06.11.2026). Пара не ставится, если устье и при сдвиге
    1 м вне контура (`boundary`) или ближе `min_crest_m` к кромке. Без W
    (`allowed_m` None) пар нет: сравнивать не с чем. Вертикальная остаётся
    на месте. Номер пары — номер вертикальной с «T», ряд и столбец — её.
    """
    if allowed_m is None or not grid:
        return []
    crest = crest_geometry(contour)
    if crest is None:
        return []
    direction = (-advance_dir[0], -advance_dir[1])
    block_h = contour.bench.height_m
    collars = [(h.collar.x, h.collar.y) for h in grid]
    ranks = front_row_ranks(collars, contour, spacing_a, burden_b, forced_first=face_row_count)
    picked = [i for i in range(len(grid)) if ranks[i] == 1 and _front_rows_member(grid[i])]
    if not picked:
        return []
    heights = [hole_bench_height_m(grid[i], block_h) for i in picked]
    own = toe_positions(contour, [floor_point(grid[i]) for i in picked], heights) or []

    # Сдвиг устья пары к кромке вдоль столбца: от `FACE_PAIR_OFFSET_M` до упора
    # в отступ от кромки и в разрыв у подошвы между парой и её вертикальной
    # (не больше b + 3 %). Наименьший сдвиг, при котором ЛСП вертикальной
    # пары ≤ W; не хватает — наибольший, и дальше наклон (решение владельца
    # 06.11.2026: ближе к кромке вместо наклона).
    goal_m = allowed_m / (1.0 + TOE_BURDEN_TOLERANCE)
    over = [(i, h) for i, h, p in zip(picked, heights, own) if not p.beyond and p.distance_m > allowed_m]
    gap_of = {
        i: (row_burden(grid[i]) if row_burden is not None else burden_b) * (1.0 + TOE_BURDEN_TOLERANCE)
        for i, _ in over
    }
    reach = _collar_reach_m(
        [collars[i] for i, _ in over], direction, boundary, crest, min_crest_m, [gap_of[i] for i, _ in over]
    )
    pending = [(i, h, r) for (i, h), r in zip(over, reach) if r >= FACE_PAIR_OFFSET_M - 1e-9]
    if not pending:
        return []

    def plain_pair(i: int, x: float, y: float) -> Hole:
        """Пара без наклона с устьем (x, y): ось вертикальной `grid[i]`."""
        hole = grid[i]
        if surfaces is None:
            # Ось вертикальной на плоском уступе — перенос.
            collar = Point3(x=x, y=y, z=hole.collar.z)
            toe = Point3(x=x + (hole.toe.x - hole.collar.x), y=y + (hole.toe.y - hole.collar.y), z=hole.toe.z)
        else:
            dx, dy, dz = hole.toe.x - hole.collar.x, hole.toe.y - hole.collar.y, hole.toe.z - hole.collar.z
            angle = math.degrees(math.atan2(math.hypot(dx, dy), -dz)) if dz < 0 else 0.0
            own_azimuth = math.degrees(math.atan2(dx, dy)) % 360.0 if (dx or dy) else 0.0
            collar, toe = drape_collar(x, y, angle, own_azimuth, subdrill_m, contour, surfaces, depth_override)
        return replace(hole, collar=collar, toe=toe)

    def vertical_lsp(items: list[tuple[int, float]], shifts: list[float]) -> list[float]:
        """ЛСП пары без наклона на сдвиге — по её собственной оси и высоте
        уступа (у наклонной подошвы и смены съёмки на развал своя); низ за
        подошвой — −inf (нижняя граница не пройдена)."""
        built = [
            plain_pair(i, collars[i][0] + direction[0] * t, collars[i][1] + direction[1] * t)
            for (i, _), t in zip(items, shifts)
        ]
        found = toe_positions(
            contour, [floor_point(h) for h in built], [hole_bench_height_m(h, block_h) for h in built]
        ) or []
        if not found:
            return [0.0] * len(items)
        return [-math.inf if p.beyond else p.distance_m for p in found]

    # Пара не ближе 1 м к вертикальной: если уже при этом сдвиге ЛСП меньше
    # нижней границы `target_m`, пара перегрузила бы откос — её нет.
    at_start = vertical_lsp([(i, h) for i, h, _ in pending], [FACE_PAIR_OFFSET_M] * len(pending))
    kept = [k for k, value in enumerate(at_start) if value >= target_m - 1e-9]
    pending = [pending[k] for k in kept]
    at_start = [at_start[k] for k in kept]
    if not pending:
        return []
    shifts = [FACE_PAIR_OFFSET_M] * len(pending)
    at_reach = vertical_lsp([(i, h) for i, h, _ in pending], [r for _, _, r in pending])
    low = {k: FACE_PAIR_OFFSET_M for k in range(len(pending))}
    high = {}
    for k, ((_, _, r), first, last) in enumerate(zip(pending, at_start, at_reach)):
        if first <= goal_m:
            del low[k]
        elif last > goal_m:
            shifts[k] = r
            del low[k]
        else:
            high[k] = r
    todo = list(low)
    for _ in range(40):
        if not todo:
            break
        mids = [0.5 * (low[k] + high[k]) for k in todo]
        for k, mid, value in zip(todo, mids, vertical_lsp([pending[k][:2] for k in todo], mids)):
            if value > goal_m:
                low[k] = mid
            else:
                high[k] = mid
        todo = [k for k in todo if high[k] - low[k] > 1e-6]
    for k, value in high.items():
        shifts[k] = value

    candidates: list[tuple[int, tuple[float, float], float]] = [
        (i, (collars[i][0] + direction[0] * t, collars[i][1] + direction[1] * t), h)
        for (i, h, _), t in zip(pending, shifts)
    ]
    plain_lsp = vertical_lsp([(i, h) for i, h, _ in pending], shifts)

    # Наклон — к ближайшей точке линии подошвы от устья пары, не дальше
    # `FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG` от линии столбца.
    toward = toe_positions(contour, [xy for _, xy, _ in candidates], [h for _, _, h in candidates]) or []
    directions = [
        _clamped_direction(direction, (p.toe_point[0] - xy[0], p.toe_point[1] - xy[1]), FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG)
        for (_, xy, _), p in zip(candidates, toward)
    ] or [direction] * len(candidates)
    azimuths = [math.degrees(math.atan2(d[0], d[1])) % 360.0 for d in directions]

    def tilted(k: int, angle: float) -> Hole:
        i, (x, y), _ = candidates[k]
        collar, toe = drape_collar(x, y, angle, azimuths[k], subdrill_m, contour, surfaces, depth_override)
        return replace(grid[i], collar=collar, toe=toe)

    # Наклон — только если и у кромки ЛСП вертикальной пары больше W, и только
    # при `tilt_deg` > 0: наименьший угол до ЛСП ≈ W, не больше 30°, ЛСП не
    # меньше `target_m`, разрыв у подошвы с вертикальной не больше b + 3 %.
    own_h = [hole_bench_height_m(tilted(k, 0.0), block_h) for k in range(len(candidates))]
    need = [k for k, value in enumerate(plain_lsp) if value > goal_m + 1e-9] if tilt_deg > 0.0 else []
    angles = [0.0] * len(candidates)

    def holds(keys: list[int], values: list[float]) -> list[bool]:
        return _tilt_holds(contour, [tilted(k, a) for k, a in zip(keys, values)], target_m)

    if need:
        caps = _tilt_caps_m(
            contour, [candidates[k][1] for k in need], [own_h[k] for k in need], [directions[k] for k in need],
            FRONT_ROWS_TILT_MAX_DEG, target_m,
        ) or [0.0] * len(need)
        ceiling_list = []
        for k, cap in zip(need, caps):
            along = directions[k][0] * direction[0] + directions[k][1] * direction[1]
            room = (gap_of[candidates[k][0]] - shifts[k]) / along if along > 1e-9 else 0.0
            reach_t = max(0.0, min(cap, room))
            ceiling_list.append(math.degrees(math.atan(reach_t / own_h[k])) if reach_t > 1e-12 and own_h[k] > 0 else 0.0)
        ceiling_list = _verified_angles(ceiling_list, lambda ks, vs: holds([need[i] for i in ks], vs))
        chosen = _smallest_angles(contour, need, dict(zip(need, ceiling_list)), tilted, holds, goal_m)
        for k, angle in chosen.items():
            angles[k] = angle

    # Пара без наклона: ЛСП вдоль сдвига может быть немонотонной (смена
    # съёмки на развал) — итог проверяется, не прошла нижнюю границу — пары нет.
    plain_keys = [k for k, angle in enumerate(angles) if angle <= 1e-9]
    plain_ok = dict(zip(plain_keys, _tilt_holds(contour, [plain_pair(candidates[k][0], *candidates[k][1]) for k in plain_keys], target_m)))
    result: list[tuple[Hole, Hole]] = []
    for k, ((i, (x, y), _height), angle) in enumerate(zip(candidates, angles)):
        hole = grid[i]
        if angle > 1e-9:
            collar, toe = drape_collar(x, y, angle, azimuths[k], subdrill_m, contour, surfaces, depth_override)
        elif not plain_ok[k]:
            continue
        else:
            built = plain_pair(i, x, y)
            collar, toe = built.collar, built.toe
        pair = replace(
            hole,
            id=hole.id + FACE_PAIR_ID_SUFFIX,
            collar=collar,
            toe=toe,
            kind=FACE_TOE_KIND,
            source="generated",
            manual=[],
        )
        result.append((hole, pair))
    return result


# Столбец сетки для плавного перехода: устья с проекцией на ось ряда в
# пределах этой доли шага a — один столбец (у шахматки соседний столбец — в
# полшага, он свой; у variable с разным a по рядам совпадают лишь общие узлы).
TAPER_COLUMN_TOLERANCE_RATIO = 0.1
# Разрыв участка ряда: соседние по ряду устья дальше этого числа шагов ряда.
TAPER_SEGMENT_GAP_RATIO = 1.5


# Плавный переход: устья соседних рангов в столбце не ближе этого, м (как
# шаг пары у откоса — 1 м) — угол участка ограничивается, иначе вертикальная
# за наклонной встаёт вплотную или впереди неё и скважины пересекаются в
# массиве (решение 22.10.2026).
MIN_COLLAR_ROW_GAP_M = 1.0


def taper_tan_limit(tilt_count: int, burden_b: float, height_m: float) -> float:
    """Наибольший tg α₁, при котором устья соседних рангов в столбце не ближе 1 м.

    Сдвиг между рангами не больше b − `MIN_COLLAR_ROW_GAP_M` (b — шаг рядов
    решётки, H — высота уступа блока). count = 1: H·tg α₁ ≤ b − 1;
    count = 2: H·(tg α₁ − tg(α₁/2)) ≤ b − 1 и H·tg(α₁/2) ≤ b − 1 — обе части
    растут с углом, предел — делением пополам.
    """
    if height_m <= 0:
        return math.inf
    k = max(0.0, burden_b - MIN_COLLAR_ROW_GAP_M) / height_m
    if tilt_count < 2 or k <= 0.0:
        return k

    def fits(alpha: float) -> bool:
        tan_full, tan_half = math.tan(alpha), math.tan(0.5 * alpha)
        return tan_full - tan_half <= k + 1e-12 and tan_half <= k + 1e-12

    low, high = 0.0, math.radians(89.0)
    for _ in range(60):
        mid = 0.5 * (low + high)
        if fits(mid):
            low = mid
        else:
            high = mid
    return math.tan(low)


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
    блока): у подошвы между соседями столбца — шаг сетки. `grid` — только
    основная сетка; наклоняются скважины `_front_rows_member` (не стенки и
    не face_toe из `row_params`), сдвигаются все скважины столбца.

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
    row_gap: dict[int, float] = {}
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
        # Шаг рядов в столбце у устьев (ранги 1→2 и 2→3) — для предела угла.
        chain = ([anchor] if face_row_count else []) + ordered[: 3 - (1 if face_row_count else 0)]
        toward = [collars[i, 0] * direction[0] + collars[i, 1] * direction[1] for i in chain]
        steps = [a - b for a, b in zip(toward, toward[1:])][:tilt_count]
        if steps:
            row_gap[anchor] = min(row_gap.get(anchor, math.inf), *steps)

    first = [rank[i] == 1 and _front_rows_member(grid[i]) for i in range(len(grid))]
    picked = [i for i in range(len(grid)) if first[i]]
    tan_first = [0.0] * len(grid)
    if picked:
        heights = [grid[i].bench_height_m for i in picked]
        caps = _tilt_caps_m(
            contour, [tuple(collars[i]) for i in picked], heights, [direction] * len(picked), tilt_deg, target_m
        )
        if caps is not None:
            tan_of = {i: (cap / height if height > 0 else 0.0) for i, cap, height in zip(picked, caps, heights)}
            # Угол участка — наименьший из допустимых по его скважинам и не
            # больше предела по зазору устьев между рангами.
            # Шаг b — наименьший шаг рядов у устьев в столбцах участка (у
            # variable он свой у ряда), без соседей в столбце — шаг паспорта.
            segments = _row_segments(grid, collars, direction, first, spacing_a)
            values = []
            for segment in segments:
                step_b = min((row_gap[i] for i in segment if i in row_gap), default=burden_b)
                limit = taper_tan_limit(tilt_count, step_b, contour.bench.height_m)
                values.append(math.degrees(math.atan(min(min(tan_of[i] for i in segment), limit))))

            # Проверка построенных скважин участка (`_verified_angles`): угол
            # участка уменьшается, пока ЛСП хоть одной меньше `target_m`.
            def segment_holds(keys: list[int], angles: list[float]) -> list[bool]:
                built: list[Hole] = []
                owner: list[int] = []
                for n, (k, angle) in enumerate(zip(keys, angles)):
                    for i in segments[k]:
                        x, y = float(collars[i, 0]), float(collars[i, 1])
                        collar, toe = drape_collar(x, y, angle, azimuth, subdrill_m, contour, surfaces, depth_override)
                        built.append(replace(grid[i], collar=collar, toe=toe))
                        owner.append(n)
                ok = [True] * len(keys)
                for n, holds in zip(owner, _tilt_holds(contour, built, target_m)):
                    ok[n] = ok[n] and holds
                return ok

            for segment, angle in zip(segments, _verified_angles(values, segment_holds)):
                for i in segment:
                    tan_first[i] = math.tan(math.radians(angle))

    height = contour.bench.height_m
    tan_1s = np.zeros(len(grid))
    tan_ks = np.zeros(len(grid))
    for i in range(len(grid)):
        if rank[i] == 0:
            continue
        tan_1 = tan_first[head[i]] if head[i] >= 0 else 0.0
        if rank[i] == 1:
            tan_k = tan_first[i]
        elif rank[i] == 2 and tilt_count >= 2 and _front_rows_member(grid[i]):
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
    # Шаги ряда — одно правило с проверкой разрыва у подошвы (`toe_line.row_steps_m`).
    local_a, local_b = row_steps_m(params, pattern, row_index, spacing_a, burden_b)
    shift_ratio = float(override.get("shift_ratio", row_shift_ratio))
    kind = _normalize_kind(override.get("kind", default_kind), default_kind)
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
