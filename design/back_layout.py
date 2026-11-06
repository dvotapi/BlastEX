"""Шаблон раскладки «от тыла» (`pattern_params.layout_anchor = "back"`).

Владелец раскладывает блок от тыла: приконтурный ряд — параллельно линии
отрыва (наиболее длинной несвободной стороне контура) на 0,5–0,8·b от неё,
эшелоны (столбцы) — перпендикулярно ей к свободной поверхности с шагом b, у
бровки каждый эшелон заканчивается по ЛСП: ничего, наклон к откосу или
скважина на остатке. Сетка одна, прямоугольная; на дуге тыла приконтурный ряд
выходит лесенкой. Подробности — `Docs/FRONT_ROWS_TILT.md`, «Шаблон «от тыла»».
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any

import shapely

from design.geometry import drape_collar, local_basis, point_in_polygon, polygon_centroid, polygon_signed_area
from design.models import BlockContour, Hole, main_grid_kind
from design.toe_line import (
    TOE_BURDEN_TOLERANCE,
    allowed_floor_burden_m,
    crest_geometry,
    design_burden_m,
    floor_point,
    grid_steps_m,
    hole_bench_height_m,
    min_crest_offset_m,
    min_floor_burden_m,
    shadow_limits,
    toe_positions,
)

Point2 = tuple[float, float]

# Излом между соседними несвободными рёбрами больше этого делит стороны
# контура; дуга из мелких рёбер остаётся одной стороной, °.
BACK_SPLIT_TURN_DEG = 45.0
# Отступ приконтурного ряда от тыла — доля шага b: без ключа `back_offset_m`
# 0,65·b, допустимый диапазон 0,5–0,8·b (решение владельца 06.11.2026).
BACK_OFFSET_DEFAULT_RATIO = 0.65
BACK_OFFSET_RANGE = (0.5, 0.8)
# Точность делений пополам, где каждый шаг — запрос к линии подошвы: шаг
# остатка, м, и угол наклона, °. Перебор (PR 3) зовёт генератор сотни раз.
BISECT_TOLERANCE_M = 1e-4
BISECT_TOLERANCE_DEG = 1e-3
# Скважина на остатке — не ближе этого к последней регулярной своего эшелона
# (станок), м; и не ближе порога «впереди» у ЛСП (`toe_line.shadow_limits`:
# 0,4·min(a, b)) — иначе проверка ЛСП не считает последнюю закрытой.
REMAINDER_MIN_STEP_M = 1.0


def _free_edge_indices(contour: BlockContour) -> set[int]:
    """Номера свободных рёбер кольца: ребро k — от вершины k к k + 1 (по модулю n)."""
    n = len(contour.vertices)
    free: set[int] = set()
    for chain in contour.free_faces:
        for i, j in zip(chain, chain[1:]):
            if not (0 <= i < n and 0 <= j < n):
                continue
            if j == (i + 1) % n:
                free.add(i)
            elif i == (j + 1) % n:
                free.add(j)
    return free


def _turn_deg(a: Point2, b: Point2) -> float:
    """Угол между направлениями двух рёбер, °."""
    cross = a[0] * b[1] - a[1] * b[0]
    dot = a[0] * b[0] + a[1] * b[1]
    return abs(math.degrees(math.atan2(cross, dot)))


def back_side(contour: BlockContour) -> list[Point2] | None:
    """Тыл блока — вершины наиболее длинной несвободной стороны по обходу контура.

    Сторона — серия подряд идущих несвободных рёбер, излом между соседними
    больше `BACK_SPLIT_TURN_DEG` её делит. Длина стороны — сумма длин рёбер.
    None — несвободных рёбер нет (или у контура меньше трёх вершин).
    """
    pts = contour.points_xy
    n = len(pts)
    if n < 3:
        return None
    free = _free_edge_indices(contour)
    vectors = [(pts[(k + 1) % n][0] - pts[k][0], pts[(k + 1) % n][1] - pts[k][1]) for k in range(n)]
    lengths = [math.hypot(*v) for v in vectors]
    edges = [k for k in range(n) if k not in free and lengths[k] > 1e-9]
    if not edges:
        return None

    def joins(prev: int, nxt: int) -> bool:
        # Между рёбрами допускаются только вырожденные несвободные (повтор вершины).
        k = (prev + 1) % n
        while k != nxt:
            if k in free or lengths[k] > 1e-9:
                return False
            k = (k + 1) % n
        return _turn_deg(vectors[prev], vectors[nxt]) <= BACK_SPLIT_TURN_DEG

    # Начало обхода — ребро, которое не продолжает предыдущее: так серия,
    # проходящая через вершину 0, не рвётся. Замкнутая серия (всё кольцо
    # без изломов) начинается с первого ребра.
    start = next(
        (pos for pos, k in enumerate(edges) if not joins(edges[pos - 1], k) or len(edges) == 1),
        0,
    )
    ordered = edges[start:] + edges[:start]
    sides: list[list[int]] = []
    for k in ordered:
        if sides and joins(sides[-1][-1], k):
            sides[-1].append(k)
        else:
            sides.append([k])
    best = max(sides, key=lambda side: sum(lengths[k] for k in side))
    return [pts[best[0]]] + [pts[(k + 1) % n] for k in best]


def back_azimuth_deg(contour: BlockContour) -> float | None:
    """Азимут хорды тыла в [0, 180): 0° = +Y, по часовой (как `geometry.crest_azimuth_deg`)."""
    side = back_side(contour)
    if side is None:
        return None
    dx, dy = side[-1][0] - side[0][0], side[-1][1] - side[0][1]
    if math.hypot(dx, dy) < 1e-9:
        return None
    return (math.degrees(math.atan2(dx, dy)) % 180.0) % 180.0


def back_offset_m(params: dict[str, Any], burden_b: float) -> float:
    """Отступ приконтурного ряда от тыла: `back_offset_m`, без него (или при
    неверном, не положительном значении) — `BACK_OFFSET_DEFAULT_RATIO`·b."""
    raw = (params or {}).get("back_offset_m")
    try:
        value = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        value = None
    if value is None or not math.isfinite(value) or value <= 0:
        return BACK_OFFSET_DEFAULT_RATIO * burden_b
    return value


@dataclass
class BackColumn:
    """Эшелон (столбец) решётки от тыла.

    `nodes` — регулярные узлы от тыла к бровке с шагом b; `rows` — номер ряда
    решётки у каждого узла (один на всю сетку: узлы на одной линии ряда — один
    номер; здесь от тыла, ряд у тыла — 0; `back_grid` перенумеровывает от
    откоса — `_face_rows`); `index` — номер столбца решётки по оси ряда.
    """

    index: int
    nodes: list[Point2] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)


def _toward_face(contour: BlockContour, back: list[Point2], advance: Point2) -> Point2:
    """`advance` или обратное ему — направление от тыла к свободной поверхности
    (без неё — к центру масс контура)."""
    mid = (0.5 * (back[0][0] + back[-1][0]), 0.5 * (back[0][1] + back[-1][1]))
    pts = contour.points_xy
    free = sorted({i for chain in contour.free_faces for i in chain if 0 <= i < len(pts)})
    if free:
        target = (sum(pts[i][0] for i in free) / len(free), sum(pts[i][1] for i in free) / len(free))
    else:
        target = polygon_centroid(pts)
    dot = (target[0] - mid[0]) * advance[0] + (target[1] - mid[1]) * advance[1]
    return advance if dot >= 0 else (-advance[0], -advance[1])


def back_frame(contour: BlockContour, row_azimuth_deg: float) -> tuple[Point2, Point2]:
    """Направление ряда и направление от тыла к бровке (`local_basis` с
    развёрнутым к свободной поверхности продвижением); без тыла — как есть."""
    row_dir, advance = local_basis(row_azimuth_deg)
    back = back_side(contour)
    return row_dir, (_toward_face(contour, back, advance) if back is not None else advance)


def back_columns(
    contour: BlockContour,
    boundary: list[Point2],
    row_azimuth_deg: float,
    spacing_a: float,
    burden_b: float,
    back_offset: float,
    shift_along: float,
) -> list[BackColumn]:
    """Эшелоны решётки от тыла: узлы каждого от приконтурного ряда к бровке.

    Решётка одна: ряды — по `row_azimuth_deg` (`local_basis`), столбцы
    перпендикулярно; начало по v — хорда тыла, сдвинутая к бровке на
    `back_offset`, по u — середина хорды плюс `shift_along` (по модулю a).
    Первый узел эшелона — узел решётки внутри `boundary`, расстояние которого
    до тыла в `BACK_OFFSET_RANGE`·b, ближайший по эшелону к линии отступа (тыл,
    смещённый внутрь на `back_offset`); такого нет — узел, ближайший к
    диапазону (при равенстве — дальше от тыла). Расстояние до тыла — до
    ломаной тыла, если эшелон её пересекает, иначе — по эшелону от входа в
    контур. Дальше — узлы внутри `boundary` с шагом b к бровке. Пустые эшелоны
    не возвращаются; без тыла — пусто.
    """
    back = back_side(contour)
    if back is None or spacing_a <= 0 or burden_b <= 0 or len(boundary) < 3:
        return []
    row_dir, advance = back_frame(contour, row_azimuth_deg)
    origin = (0.5 * (back[0][0] + back[-1][0]), 0.5 * (back[0][1] + back[-1][1]))

    def world(u: float, v: float) -> Point2:
        return (origin[0] + u * row_dir[0] + v * advance[0], origin[1] + u * row_dir[1] + v * advance[1])

    def local(p: Point2) -> tuple[float, float]:
        dx, dy = p[0] - origin[0], p[1] - origin[1]
        return dx * row_dir[0] + dy * row_dir[1], dx * advance[0] + dy * advance[1]

    ring = list(boundary) + [boundary[0]]
    outline = shapely.LineString(ring)
    back_line = shapely.LineString(back)
    # Тыл, смещённый внутрь: внутренность кольца против часовой — слева от обхода.
    ccw = polygon_signed_area(contour.points_xy) > 0
    offset_line = shapely.offset_curve(back_line, back_offset if ccw else -back_offset)
    uv = [local(p) for p in boundary]
    u_lo, u_hi = min(u for u, _ in uv), max(u for u, _ in uv)
    v_lo, v_hi = min(v for _, v in uv), max(v for _, v in uv)
    lo_range, hi_range = BACK_OFFSET_RANGE[0] * burden_b, BACK_OFFSET_RANGE[1] * burden_b
    phase = shift_along % spacing_a
    k_lo = math.floor((u_lo - phase) / spacing_a)
    k_hi = math.ceil((u_hi - phase) / spacing_a)
    j_lo = math.floor((v_lo - back_offset) / burden_b) - 1
    j_hi = math.ceil((v_hi - back_offset) / burden_b) + 1

    def crossings(geom: object, u: float) -> list[float]:
        line = shapely.LineString([world(u, v_lo - burden_b), world(u, v_hi + burden_b)])
        hit = shapely.intersection(line, geom)
        pts = [q for q in shapely.get_coordinates(hit)] if not hit.is_empty else []
        return sorted(local((float(q[0]), float(q[1])))[1] for q in pts)

    columns: list[BackColumn] = []
    for k in range(k_lo, k_hi + 1):
        u = phase + k * spacing_a
        inside = [
            j for j in range(j_lo, j_hi + 1) if point_in_polygon(world(u, back_offset + j * burden_b), boundary)
        ]
        if not inside:
            continue
        crosses_back = bool(crossings(back_line, u))
        if crosses_back:
            nodes = [world(u, back_offset + j * burden_b) for j in inside]
            dist = [float(d) for d in shapely.distance(shapely.points(nodes), back_line)]
        else:
            entry = crossings(outline, u)
            start = entry[0] if entry else v_lo
            dist = [back_offset + j * burden_b - start for j in inside]
        target_hits = crossings(offset_line, u) if crosses_back else []
        target = target_hits[0] if target_hits else None

        def gap(n: int) -> float:
            return max(lo_range - dist[n], dist[n] - hi_range, 0.0)

        def key(n: int) -> tuple[float, float]:
            if gap(n) > 0:
                return (gap(n), -dist[n])
            v = back_offset + inside[n] * burden_b
            return (0.0, abs(v - target) if target is not None else abs(dist[n] - back_offset))

        first = min(range(len(inside)), key=key)
        picked = inside[first:]
        columns.append(
            BackColumn(index=k, nodes=[world(u, back_offset + j * burden_b) for j in picked], rows=list(picked))
        )
    if columns:
        base = min(r for col in columns for r in col.rows)
        for col in columns:
            col.rows = [r - base for r in col.rows]
    return columns


def _float(params: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(params.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _known_floor_burdens(contour: BlockContour, holes: list[Hole]) -> list[tuple[float, bool]] | None:
    """(ЛСП, за подошвой) построенных скважин: точка оси на подошве и своя высота
    уступа; None — линии подошвы нет (ЛСП неизвестна, а не 0)."""
    if not holes:
        return []
    block_h = contour.bench.height_m
    found = toe_positions(contour, [floor_point(h) for h in holes], [hole_bench_height_m(h, block_h) for h in holes])
    return [(p.distance_m, p.beyond) for p in found] if found else None


def _floor_burdens(contour: BlockContour, holes: list[Hole]) -> list[tuple[float, bool]]:
    """`_known_floor_burdens` там, где линия подошвы уже есть (`back_grid` её
    проверил): без неё — (0, не за подошвой)."""
    return _known_floor_burdens(contour, holes) or [(0.0, False)] * len(holes)


def back_grid(
    contour: BlockContour,
    params: dict[str, Any],
    boundary: list[Point2],
    surfaces: object | None = None,
) -> list[Hole]:
    """Основная сетка шаблона «от тыла»: эшелоны `back_columns` и конец каждого у бровки.

    Регулярные узлы — скважины вида основной сетки (`default_kind`), `row` —
    ряд решётки от откоса (передний — 0, `_face_rows`), `col` — столбец; угол и азимут — `angle_deg`/`azimuth_deg`,
    как у прежней сетки. Устья ближе `min_crest_offset_m` к бровке и низ за
    подошвой убираются. С W (`allowed_floor_burden_m`) — конец эшелона по
    последней регулярной (решение владельца 06.11.2026):

    1. Регулярные с конца, у которых ЛСП меньше 0,8·W, убираются.
    2. ЛСП последней ≤ W + 3 % — ничего.
    3. Иначе наклон к откосу (`pattern.face_tilts`: азимут к подошве ≤ 15° от
       столбца, угол `front_rows_tilt_deg`, при недоборе — до 30°), но не
       больше угла, при котором точка оси на подошве уходит от предыдущей
       скважины эшелона дальше b + 3 % (`floor_row_gap_excess` — анти-цель
       спецификации), и из допустимых — наименьший, при котором ЛСП ≈ W
       (`_least_angle_to`); ЛСП вошла в допуск — наклонённая.
    4. Иначе — вертикальная на остатке: на линии эшелона ближе к бровке, ЛСП ≈ W
       (не меньше 0,8·W), устье не ближе отступа к бровке, не ближе
       max(`REMAINDER_MIN_STEP_M`, 0,4·min(a, b)) к последней и ближе b; член основной сетки
       (ряд — на один впереди последней, столбец — её). Вертикальная не
       помещается, а наклон не выключен (`front_rows_tilt_deg` > 0) — остаток
       с устьем как можно ближе к бровке (не ближе 1 м к последней) и
       наименьшим наклоном к откосу, при котором у подошвы он впереди
       последней не меньше 0,4·min(a, b), ЛСП в коридоре и разрыв ≤ b + 3 %
       (`_tilted_remainder`).
    5. Места для остатка нет — последняя с наклоном из п. 3 (наибольшим
       допустимым), ЛСП покажет проверка. Остаток, у которого проверка видит
       разрыв у подошвы (вне решётки у угла блока), заменяется тем же.
    """
    from design.pattern import _front_rows_tilt, _grid_id, face_tilts, hole_spec, tilt_floor_burden_target_m

    spacing_a, burden_b = grid_steps_m(params)
    row_azimuth = _float(params, "row_azimuth_deg", 0.0)
    columns = back_columns(
        contour,
        boundary,
        row_azimuth,
        spacing_a,
        burden_b,
        back_offset_m(params, burden_b),
        _float(params, "grid_shift_along_m", 0.0),
    )
    if not columns:
        return []
    kind = main_grid_kind(params)
    diameter_mm, subdrill_m, angle_deg, azimuth_deg, depth_override = hole_spec(params, row_azimuth)

    def make(x: float, y: float, row: int, col: int, angle: float, azimuth: float) -> Hole:
        collar, toe = drape_collar(x, y, angle, azimuth, subdrill_m, contour, surfaces, depth_override)
        return Hole(
            id=_grid_id(kind, row, col),
            row=row,
            col=col,
            collar=collar,
            toe=toe,
            diameter_mm=diameter_mm,
            subdrill_m=subdrill_m,
            kind=kind,
            source="generated",
        )

    col_base = min(col.index for col in columns)
    echelons = [
        [make(x, y, row, col.index - col_base, angle_deg, azimuth_deg) for (x, y), row in zip(col.nodes, col.rows)]
        for col in columns
    ]
    crest = crest_geometry(contour)
    if crest is None:
        return _face_rows([h for echelon in echelons for h in echelon])
    min_crest = min_crest_offset_m(params)

    def off_crest(holes: list[Hole]) -> list[bool]:
        if not holes:
            return []
        dist = shapely.distance(shapely.points([(h.collar.x, h.collar.y) for h in holes]), crest)
        return [float(d) >= min_crest - 1e-9 for d in dist]

    flat = [h for echelon in echelons for h in echelon]
    burdens = _known_floor_burdens(contour, flat)
    keep = {
        id(h) for h, ok, (_, beyond) in zip(flat, off_crest(flat), burdens or [(0.0, False)] * len(flat))
        if ok and not beyond
    }
    echelons = [[h for h in echelon if id(h) in keep] for echelon in echelons]

    allowed = allowed_floor_burden_m(params)
    w = design_burden_m(params)
    lower = min_floor_burden_m(params)
    # Без линии подошвы ЛСП неизвестна: конец эшелона не считается, решётка — как есть.
    if allowed is None or w is None or lower is None or (flat and burdens is None):
        return _face_rows([h for echelon in echelons for h in echelon])

    # 1. С конца — регулярные с ЛСП меньше 0,8·W.
    # Пакетом: ЛСП всех последних за один запрос, повтор — только где убрали.
    todo = [k for k, echelon in enumerate(echelons) if echelon]
    while todo:
        values = _floor_burdens(contour, [echelons[k][-1] for k in todo])
        short = [k for k, (lsp, _) in zip(todo, values) if lsp < lower - 1e-9]
        for k in short:
            echelons[k].pop()
        todo = [k for k in short if echelons[k]]
    ends = [k for k, echelon in enumerate(echelons) if echelon]
    lasts = [echelons[k][-1] for k in ends]
    over = [k for k, (lsp, _) in zip(ends, _floor_burdens(contour, lasts)) if lsp > allowed + 1e-9]
    if not over:
        return _face_rows([h for echelon in echelons for h in echelon])

    # 3. Наклон к откосу — пакетом по всем таким эшелонам.
    _, advance = back_frame(contour, row_azimuth)
    _, tilt_deg = _front_rows_tilt(params)
    target = tilt_floor_burden_target_m(params)
    over_holes = [echelons[k][-1] for k in over]
    tilts = face_tilts(
        contour,
        over_holes,
        [(h.collar.x, h.collar.y) for h in over_holes],
        advance,
        tilt_deg,
        target,
        allowed,
        subdrill_m,
        surfaces,
        depth_override,
    )
    gap_limit = burden_b * (1.0 + TOE_BURDEN_TOLERANCE)
    # Коридоры ЛСП последних и предыдущих — двумя запросами на все эшелоны.
    prevs = [echelons[k][-2] if len(echelons[k]) > 1 else None for k in over]
    prev_corridors = _corridors(contour, prevs)
    last_corridors = dict(zip(over, _corridors(contour, over_holes)))
    tilted: dict[int, Hole] = {}
    for k, h, (angle, azimuth), prev, prev_corridor in zip(over, over_holes, tilts, prevs, prev_corridors):
        if angle <= 1e-9:
            continue
        angle = _gap_limited_angle(contour, h, prev, prev_corridor, angle, azimuth, advance, burden_b, make)
        if angle > 1e-9:
            angle = _least_angle_to(contour, h, angle, azimuth, w, make)
        if angle > 1e-9:
            tilted[k] = make(h.collar.x, h.collar.y, h.row, h.col, angle, azimuth)
    fixed = {
        k for k, (lsp, beyond) in zip(tilted, _floor_burdens(contour, list(tilted.values())))
        if lsp <= allowed + 1e-9 and not beyond
    }
    remainders: dict[int, Hole] = {}
    for k in over:
        if k in fixed:
            echelons[k][-1] = tilted[k]
            continue
        last = echelons[k][-1]
        # «Впереди» у ЛСП — по пути от точки последней на подошве к ближайшей
        # точке линии подошвы (`toe_line.corridor_blockers`), а не по столбцу.
        shadow = shadow_limits(spacing_a, burden_b)[0]
        corridor = last_corridors[k]
        along = advance[0] * corridor[0] + advance[1] * corridor[1]
        if along < 0.1:
            extra = None
        else:
            min_step = max(REMAINDER_MIN_STEP_M, shadow / along)
            extra = _remainder(contour, boundary, crest, last, advance, burden_b, min_step, w, lower, min_crest, make)
        over_tolerance = False
        if extra is not None:
            over_tolerance = _floor_burdens(contour, [extra])[0][0] > allowed + 1e-9
        if (extra is None or over_tolerance) and tilt_deg > 0 and along >= 0.1:
            # Вертикальный не помещается или и на наибольшем шаге ЛСП > W + 3 % —
            # наклонный в допуске лучше; нет его — остаётся вертикальный.
            extra = _tilted_remainder(
                contour, boundary, crest, last, advance, corridor, burden_b, shadow, lower, allowed, gap_limit,
                min_crest, make,
            ) or extra
        if extra is not None:
            echelons[k].append(extra)
            remainders[k] = extra
        elif k in tilted:
            # 5. Места для остатка нет — наклон с наибольшим допустимым углом.
            echelons[k][-1] = tilted[k]
    if remainders:
        # Остаток стоит вне решётки (шаг меньше b), а проверка разрыва у подошвы
        # ждёт |Δряд|·b: где коридор к подошве идёт вбок (угол блока), она видит
        # у остатка разрыв до соседнего столбца. Такой остаток убирается, у
        # последней — наклон из п. 3, как при нехватке места (п. 5).
        # Остаток бывает и соседом впереди у скважины другого столбца: тогда
        # убираются остатки рядом с ней (в пределах коридора), до трёх проходов.
        reach = 1.05 * max(spacing_a, burden_b) + burden_b
        for _ in range(3):
            flat = [h for echelon in echelons for h in echelon]
            regular = [h for h in flat if all(h is not extra for extra in remainders.values())]
            numbered = _face_rows(flat, regular)
            checked = _gap_excess_ids(contour, params, numbered)
            flagged = {h.id for h, n in zip(flat, numbered) if n.id in checked}
            if not flagged:
                break
            by_id = {h.id: h for h in flat}
            drop = [
                k
                for k, extra in remainders.items()
                if extra.id in flagged
                or any(
                    math.hypot(by_id[f].collar.x - extra.collar.x, by_id[f].collar.y - extra.collar.y) <= reach
                    for f in flagged
                    if f in by_id
                )
            ]
            if not drop:
                break
            for k in drop:
                echelons[k].pop()
                if k in tilted:
                    echelons[k][-1] = tilted[k]
                del remainders[k]
    flat = [h for echelon in echelons for h in echelon]
    return _face_rows(flat, [h for h in flat if all(h is not extra for extra in remainders.values())])


def _face_rows(holes: list[Hole], regular: list[Hole] | None = None) -> list[Hole]:
    """Ряды — от откоса, как у всего конвейера (нумерация, тайминг, монтаж,
    стабилизация, «ряд позади»): передний ряд регулярных узлов (`regular`, по
    умолчанию все) — 0, к тылу номера растут. Внутри `back_grid` ряды идут от
    тыла (остаток — `last.row + 1`); остаток впереди ряда 0 получает ряд
    впереди первого (`FRONT_ROW_BASE − 1`, как у раскладки от бровки). Номера
    скважин — по новым рядам."""
    from design.models import FRONT_ROW_BASE
    from design.pattern import _grid_id

    if not holes:
        return []
    top = max(h.row for h in (regular if regular else holes))
    result = []
    for h in holes:
        row = top - h.row
        if row < 0:
            row = FRONT_ROW_BASE + row
        result.append(replace(h, row=row, id=_grid_id(h.kind, row, h.col)))
    return result


def _gap_excess_ids(contour: BlockContour, params: dict[str, Any], holes: list[Hole]) -> set[str]:
    """Номера скважин с разрывом у подошвы (`floor_row_gap_excess`), как его видит `validate`."""
    from design.models import BlastDesign
    from design.toe_line import floor_checks

    design = BlastDesign(design_id="back_layout", contour=contour, holes=holes, pattern_params=params)
    _, _, gaps = floor_checks(design, with_gaps=True)
    return {hole_id for hole_id, gap in gaps.items() if gap.excess}


def _corridors(contour: BlockContour, holes: list[Hole | None]) -> list[Point2]:
    """Единичное направление от точки оси на подошве к ближайшей точке линии
    подошвы (коридор ЛСП) у каждой скважины — одним запросом; (0, 0) — линии
    нет, точка на ней или скважины нет (None)."""
    present = [h for h in holes if h is not None]
    if not present:
        return [(0.0, 0.0)] * len(holes)
    floors = [floor_point(h) for h in present]
    found = toe_positions(contour, floors, [hole_bench_height_m(h, contour.bench.height_m) for h in present]) or []
    by_id: dict[int, Point2] = {}
    for h, (fx, fy), position in zip(present, floors, found):
        dx, dy = position.toe_point[0] - fx, position.toe_point[1] - fy
        norm = math.hypot(dx, dy)
        by_id[id(h)] = (dx / norm, dy / norm) if norm > 1e-9 else (0.0, 0.0)
    return [by_id.get(id(h), (0.0, 0.0)) if h is not None else (0.0, 0.0) for h in holes]


def _bisect(lo: float, hi: float, keep_low: Any, tolerance: float) -> tuple[float, float]:
    """Деление пополам [lo, hi] до ширины `tolerance`: `keep_low(mid)` — mid
    становится нижней границей, иначе верхней. Каждый шаг строит скважину
    (а часто и запрос к линии подошвы), поэтому точность — константы модуля."""
    while hi - lo > tolerance:
        mid = 0.5 * (lo + hi)
        if keep_low(mid):
            lo = mid
        else:
            hi = mid
    return lo, hi


def _max_step(
    last: Hole, advance: Point2, low: float, burden_b: float, boundary: list[Point2], crest: object, min_crest: float
) -> float | None:
    """Наибольший шаг t ∈ [`low`, b) от устья `last` по `advance`, при котором
    устье внутри `boundary` и не ближе `min_crest` к бровке; None — и `low` не годится."""
    x0, y0 = last.collar.x, last.collar.y

    def placeable(t: float) -> bool:
        x, y = x0 + advance[0] * t, y0 + advance[1] * t
        if not point_in_polygon((x, y), boundary):
            return False
        return float(shapely.distance(shapely.Point(x, y), crest)) >= min_crest - 1e-9

    if low >= burden_b or not placeable(low):
        return None
    high = burden_b - 1e-6
    if placeable(high):
        return high
    return _bisect(low, high, placeable, BISECT_TOLERANCE_M)[0]


def _least_angle_to(contour: BlockContour, hole: Hole, angle: float, azimuth: float, w: float, make: Any) -> float:
    """Наименьший угол ≤ `angle`, при котором ЛСП наклонённой `hole` не больше
    `w` (ЛСП ≈ W; решение владельца 06.11.2026 — как у пары, наклон не больше
    нужного). ЛСП и при `angle` больше `w` — `angle`."""

    def lsp(value: float) -> float:
        found, beyond = _floor_burdens(contour, [make(hole.collar.x, hole.collar.y, hole.row, hole.col, value, azimuth)])[0]
        return math.inf if beyond else found

    if lsp(angle) > w:
        return angle
    # lsp(0) > w ≥ lsp(angle)
    return _bisect(0.0, angle, lambda a: lsp(a) > w, BISECT_TOLERANCE_DEG)[1]


def _gap_limited_angle(
    contour: BlockContour,
    hole: Hole,
    prev: Hole | None,
    corridor: Point2,
    angle: float,
    azimuth: float,
    advance: Point2,
    burden_b: float,
    make: Any,
) -> float:
    """Наибольший угол ≤ `angle`, при котором наклонённая `hole` не даёт у
    предыдущей скважины эшелона `prev` разрыва у подошвы (`floor_row_gap_excess`,
    анти-цель спецификации). Как у проверки (`toe_line._row_gaps`): продвижение
    точки `hole` на подошве от точки `prev` по коридору `prev` к подошве (`corridor`) — не
    больше (1 + 3 %) решёточного шага b, спроецированного на этот коридор; и
    расстояние между точками на подошве — не больше b + 3 %. Шаг — |Δряд|·b:
    у эшелона, вышедшего из контура и вошедшего снова, предыдущая может стоять
    через пропущенные узлы. Без предыдущей — `angle`."""
    if prev is None:
        return angle
    step = burden_b * max(1, abs(hole.row - prev.row))
    expected = step * (advance[0] * corridor[0] + advance[1] * corridor[1])
    limit_along = expected * (1.0 + TOE_BURDEN_TOLERANCE) - 1e-6
    limit_gap = step * (1.0 + TOE_BURDEN_TOLERANCE) - 1e-6
    px, py = floor_point(prev)

    def fits(value: float) -> bool:
        fx, fy = floor_point(make(hole.collar.x, hole.collar.y, hole.row, hole.col, value, azimuth))
        along = (fx - px) * corridor[0] + (fy - py) * corridor[1]
        return math.hypot(fx - px, fy - py) <= limit_gap and (expected <= 0 or along <= limit_along)

    if fits(angle):
        return angle
    if not fits(0.0):
        return 0.0
    return _bisect(0.0, angle, fits, BISECT_TOLERANCE_DEG)[0]


def _remainder(
    contour: BlockContour,
    boundary: list[Point2],
    crest: object,
    last: Hole,
    advance: Point2,
    burden_b: float,
    min_step: float,
    w: float,
    lower: float,
    min_crest: float,
    make: Any,
) -> Hole | None:
    """Вертикальная на остатке за `last` по линии эшелона (`advance`) или None.

    Шаг t от последней — в [`min_step`, b): устье внутри
    `boundary` и не ближе `min_crest` к бровке. ЛСП убывает с t: берётся t с
    ЛСП = W (деление пополам), а если и у наибольшего t ЛСП больше W — оно;
    ЛСП при наименьшем t меньше 0,8·W — места нет.
    """
    x0, y0 = last.collar.x, last.collar.y

    def at(t: float) -> Hole:
        return make(x0 + advance[0] * t, y0 + advance[1] * t, last.row + 1, last.col, 0.0, 0.0)

    def lsp(t: float) -> float:
        value, beyond = _floor_burdens(contour, [at(t)])[0]
        return -1.0 if beyond else value

    low = min_step
    # Наибольший допустимый шаг: устье в контуре и не ближе отступа к бровке.
    high = _max_step(last, advance, low, burden_b, boundary, crest, min_crest)
    if high is None:
        return None
    low_lsp = lsp(low)
    if low_lsp < lower - 1e-9:
        return None
    if lsp(high) >= w:
        return at(high)
    if low_lsp < w:
        return at(low)
    # lsp(low) ≥ W > lsp(high); каждое деление — запрос к линии подошвы.
    return at(_bisect(low, high, lambda t: lsp(t) >= w, BISECT_TOLERANCE_M)[0])


def _tilted_remainder(
    contour: BlockContour,
    boundary: list[Point2],
    crest: object,
    last: Hole,
    advance: Point2,
    corridor: Point2,
    burden_b: float,
    shadow: float,
    lower: float,
    allowed: float,
    gap_limit: float,
    min_crest: float,
    make: Any,
) -> Hole | None:
    """Наклонная на остатке за `last` или None.

    Устье — на линии эшелона на наибольшем шаге t ∈ [`REMAINDER_MIN_STEP_M`, b),
    при котором оно внутри `boundary` и не ближе `min_crest` к бровке. Азимут —
    к ближайшей точке линии подошвы, не дальше 15° от столбца (как у пары).
    Угол — наименьший до 30° (деления пополам), при котором
    точка на подошве впереди точки `last` по коридору ЛСП `corridor` не меньше `shadow`, не
    дальше `gap_limit`, ЛСП в [`lower`; `allowed`] и низ не за подошвой.
    """
    from design.pattern import FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG, FRONT_ROWS_TILT_MAX_DEG, _clamped_direction

    t = _max_step(last, advance, REMAINDER_MIN_STEP_M, burden_b, boundary, crest, min_crest)
    if t is None:
        return None
    x, y = last.collar.x + advance[0] * t, last.collar.y + advance[1] * t
    base_floor = floor_point(last)
    height = hole_bench_height_m(make(x, y, last.row + 1, last.col, 0.0, 0.0), contour.bench.height_m)
    toward = toe_positions(contour, [(x, y)], [height])
    if not toward:
        return None
    direction = _clamped_direction(
        advance,
        (toward[0].toe_point[0] - x, toward[0].toe_point[1] - y),
        FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG,
    )
    azimuth = math.degrees(math.atan2(direction[0], direction[1])) % 360.0

    def ahead_of(angle: float) -> tuple[Hole, float, float]:
        hole = make(x, y, last.row + 1, last.col, angle, azimuth)
        fx, fy = floor_point(hole)
        ahead = (fx - base_floor[0]) * corridor[0] + (fy - base_floor[1]) * corridor[1]
        return hole, ahead, math.hypot(fx - base_floor[0], fy - base_floor[1])

    def lsp(angle: float) -> float:
        found, beyond = _floor_burdens(contour, [ahead_of(angle)[0]])[0]
        return -1.0 if beyond else found

    def least_ok(lo: float, hi: float, ok: Any) -> float:
        """Наименьший угол в (lo, hi], при котором `ok` (ok(lo) — нет, ok(hi) — да)."""
        return _bisect(lo, hi, lambda a: not ok(a), BISECT_TOLERANCE_DEG)[1]

    top = FRONT_ROWS_TILT_MAX_DEG
    # Наименьший угол, при котором остаток у подошвы впереди на `shadow`
    # (продвижение растёт с углом; без запросов к линии подошвы).
    if ahead_of(0.0)[1] >= shadow:
        least = 0.0
    elif ahead_of(top)[1] < shadow:
        return None
    else:
        least = least_ok(0.0, top, lambda a: ahead_of(a)[1] >= shadow)
    # Наибольший угол, при котором разрыв у подошвы до последней ≤ b + 3 %.
    if ahead_of(least)[2] > gap_limit + 1e-9:
        return None
    most = top
    if ahead_of(top)[2] > gap_limit + 1e-9:
        # Разрыв при least в допуске, при top — нет.
        most = _bisect(least, top, lambda a: ahead_of(a)[2] <= gap_limit, BISECT_TOLERANCE_DEG)[0]
    first = lsp(least)
    if first < lower - 1e-9:
        return None
    if first > allowed + 1e-9:
        # Наименьший угол до ЛСП ≤ W + 3 %: ЛСП убывает с углом; не хватает и при
        # наибольшем — места нет.
        if lsp(most) > allowed + 1e-9:
            return None
        least = least_ok(least, most, lambda a: 0.0 <= lsp(a) <= allowed)
    hole, _, gap = ahead_of(least)
    value, beyond = _floor_burdens(contour, [hole])[0]
    if beyond or not lower - 1e-9 <= value <= allowed + 1e-9 or gap > gap_limit + 1e-9:
        return None
    return hole
