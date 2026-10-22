"""Линия подошвы откоса: от неё считается ЛСП первого ряда скважин.

Если у контура есть съёмка нижней бровки (`cad.bottom`, контур не правили) —
берутся рёбра её кольца, не касающиеся вершин верхнего контура (тыл и фланги
кольцо делит с контуром, продления флангов начинаются в его вершинах); иначе
линия строится смещением верхней бровки наружу на проекцию откоса в плане
(«подошва по углу»).

Съёмка с развалом (решение 21.10.2026, блок №66): если ближайшая к скважине
точка съёмки лежит от верхней бровки дальше `SURVEY_SPOIL_WIDTH_FACTOR · H`,
там не откос, а развал или берма — ЛСП этой скважины считается по углу
откоса: расстояние от точки оси на уровне подошвы до верхней бровки плюс
H · tan(90° − угол). H — высота уступа по оси скважины (`Hole.bench_height_m`,
без неё — высота блока). Угол 90° и круче здесь — «угол не задан» (умолчание
сервера у старых паспортов): берётся 15° от вертикали (75° от горизонтали),
иначе подошва по углу совпала бы с бровкой и ЛСП занизилась бы.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import nearest_points

from design.geometry import drawing_bottom
from design.models import BenchSurface, BlastDesign, BlockContour, Hole, row_family

# Вершина кольца нижней бровки ближе этого к вершине верхнего контура — общая с ним, м.
SHARED_VERTEX_TOLERANCE_M = 0.01

# Положе этого угла откоса (от горизонтали) смещение подошвы не считается: при
# угле у нуля проекция откоса уходит в сотни метров.
MIN_FACE_ANGLE_DEG = 30.0

# Шаг сетки по ряду, когда в параметрах нет ни a, ни W, м.
DEFAULT_CORRIDOR_STEP_M = 4.0

# Сосед закрывает скважину от откоса, если продвинут к подошве вдоль её коридора
# хотя бы на эту долю min(a, b) и отступает вбок не дальше этой доли max(a, b).
SHADOW_ADVANCE_RATIO = 0.4
SHADOW_REACH_RATIO = 1.05

# Съёмка подошвы дальше этой доли высоты уступа от верхней бровки (откос положе
# 45° от вертикали) — развал или берма, а не откос: ЛСП считается по углу.
SURVEY_SPOIL_WIDTH_FACTOR = 1.0

# Угол откоса (от горизонтали) для подошвы по углу вместо развала, когда угол
# блока не задан (90° — умолчание сервера): 15° от вертикали.
SPOIL_DEFAULT_FACE_ANGLE_DEG = 75.0

# Источник линии подошвы у скважины: съёмка нижней бровки или построение по углу.
TOE_SOURCE_SURVEY = "survey"
TOE_SOURCE_ANGLE = "angle"

# Допуск к проектной линии сопротивления по подошве (W): ЛСП до W + 3% — норма.
TOE_BURDEN_TOLERANCE = 0.03
# Нижняя граница ЛСП (решение владельца 22.10.2026): не меньше 0,8·W.
# Допустимый коридор ЛСП — от 0,8·W до W + 3 %.
FLOOR_BURDEN_MIN_RATIO = 0.8

Polyline = list[tuple[float, float]]


@dataclass(frozen=True)
class ToeLine:
    polylines: list[Polyline]
    source: str  # "survey" — по съёмке нижней бровки, "angle" — от верхней бровки по углу откоса


def _offset_m(height_m: float, face_angle_deg: float) -> float:
    """H · tan(90° − угол); угол от горизонтали, не положе `MIN_FACE_ANGLE_DEG`."""
    angle = min(90.0, max(MIN_FACE_ANGLE_DEG, face_angle_deg))
    return max(0.0, height_m * math.tan(math.radians(90.0 - angle)))


def slope_offset_m(bench: BenchSurface) -> float:
    """Смещение подошвы от верхней бровки в плане: H · tan(90° − угол откоса).

    Угол откоса — от горизонтали, не положе `MIN_FACE_ANGLE_DEG`.
    """
    return _offset_m(bench.height_m, bench.face_angle_deg)


def spoil_face_angle_deg(bench: BenchSurface) -> float:
    """Угол откоса для подошвы по углу там, где съёмка — развал.

    90° и круче — «угол не задан» (умолчание сервера у паспортов, сохранённых до
    правки импорта): берётся `SPOIL_DEFAULT_FACE_ANGLE_DEG`. Без съёмки угол
    блока используется как есть.
    """
    angle = bench.face_angle_deg
    return angle if angle < 90.0 else SPOIL_DEFAULT_FACE_ANGLE_DEG


def _free_polylines(contour: BlockContour) -> list[Polyline]:
    pts = contour.points_xy
    lines = []
    for face in contour.free_faces:
        line = [pts[i] for i in face if 0 <= i < len(pts)]
        if len(line) >= 2:
            lines.append(line)
    return lines


def _built(contour: BlockContour, free: list[Polyline], offset: float) -> list[Polyline]:
    if offset <= 0:
        return [list(line) for line in free]
    polygon = Polygon(contour.points_xy)
    result: list[Polyline] = []
    for line in free:
        base = LineString(line)
        best = None
        for sign in (offset, -offset):
            shifted = base.offset_curve(sign)
            if shifted.is_empty:
                continue
            geoms = list(shifted.geoms) if hasattr(shifted, "geoms") else [shifted]
            if not polygon.contains(geoms[0].interpolate(0.5, normalized=True)):
                best = geoms
                break
        if best is None:
            best = [base]
        result.extend([(float(x), float(y)) for x, y in g.coords] for g in best)
    return result


def _survey(ring: list[tuple[float, float]], top: list[tuple[float, float]]) -> list[Polyline]:
    """Рёбра кольца нижней бровки, ни один конец которых не совпадает с вершиной контура.

    Тыл и фланги кольцо делит с верхним контуром, продление фланга до подошвы
    начинается в вершине контура — остаются только рёбра по самой нижней бровке.
    Соседние рёбра склеиваются в полилинии.
    """
    n = len(ring)
    shared = [False] * n
    if top:
        tree = shapely.STRtree(shapely.points(top))
        hits = tree.query(shapely.points(ring), predicate="dwithin", distance=SHARED_VERTEX_TOLERANCE_M)
        for i in set(int(k) for k in hits[0]):
            shared[i] = True
    selected = [not shared[i] and not shared[(i + 1) % n] for i in range(n)]
    if not any(selected):
        return []
    if all(selected):
        return [list(ring) + [ring[0]]]
    # Начинаем обход с ребра после первого невыбранного, чтобы серии не рвались на стыке кольца.
    start = (selected.index(False) + 1) % n
    polylines: list[Polyline] = []
    current: Polyline = []
    for k in range(n):
        i = (start + k) % n
        if selected[i]:
            if not current:
                current = [ring[i]]
            current.append(ring[(i + 1) % n])
        elif current:
            polylines.append(current)
            current = []
    if current:
        polylines.append(current)
    return polylines


def angle_toe_line(contour: BlockContour, face_angle_deg: float | None = None) -> ToeLine | None:
    """Линия подошвы по углу откоса блока; None, если свободных поверхностей нет.

    `face_angle_deg` — угол вместо угла блока (подошва по углу вместо развала).
    """
    free = _free_polylines(contour)
    if not free:
        return None
    angle = contour.bench.face_angle_deg if face_angle_deg is None else face_angle_deg
    offset = _offset_m(contour.bench.height_m, angle)
    return ToeLine(polylines=_built(contour, free, offset), source=TOE_SOURCE_ANGLE)


def toe_line(contour: BlockContour) -> ToeLine | None:
    """Линия подошвы вдоль свободных поверхностей; None, если их нет.

    Съёмка, если она есть, — целиком: проверку на развал делает `floor_burdens`
    по каждой скважине.
    """
    free = _free_polylines(contour)
    if not free:
        return None
    ring = drawing_bottom(contour)
    if ring is not None:
        polylines = _survey(ring, contour.points_xy)
        if polylines:
            return ToeLine(polylines=polylines, source=TOE_SOURCE_SURVEY)
    return angle_toe_line(contour)


def _geometry(line: ToeLine | None) -> MultiLineString | None:
    if line is None:
        return None
    parts = [LineString(poly) for poly in line.polylines if len(poly) >= 2]
    return MultiLineString(parts) if parts else None


@dataclass(frozen=True)
class FloorBurden:
    hole_id: str
    value_m: float  # ЛСП: расстояние в плане от точки оси на уровне подошвы до линии подошвы
    allowed_m: float | None  # W + 3%; None, если W не задана
    excess: bool  # ЛСП больше W + 3% или точка за линией подошвы — не «в допуске»
    toe_source: str = TOE_SOURCE_SURVEY  # "survey" — съёмка, "angle" — подошва по углу
    beyond_toe: bool = False  # точка на подошве за нижней бровкой: скважина выходит в откос
    min_m: float | None = None  # 0,8·W; None, если W не задана
    short: bool = False  # ЛСП меньше 0,8·W (W задана, скважина не за подошвой)


@dataclass(frozen=True)
class ToePosition:
    """Положение точки на уровне подошвы относительно линии подошвы (для ЛСП)."""

    distance_m: float  # расстояние в плане до линии подошвы, без знака
    source: str  # "survey" или "angle" — по какой линии считано (правило развала)
    toe_point: tuple[float, float]  # точка подошвы, к которой идёт коридор
    beyond: bool  # точка за линией подошвы, со стороны откоса


def floor_point(hole: Hole) -> tuple[float, float]:
    """Точка оси на уровне подошвы уступа: забой минус перебор вдоль оси, в плане."""
    dx = hole.toe.x - hole.collar.x
    dy = hole.toe.y - hole.collar.y
    dz = hole.toe.z - hole.collar.z
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 0:
        return (hole.toe.x, hole.toe.y)
    k = hole.subdrill_m / length
    return (hole.toe.x - dx * k, hole.toe.y - dy * k)


def design_burden_m(pattern_params: dict | None) -> float | None:
    """Проектная W: `burden_b_m`; у квадратной сетки без него — шаг; None — не задана."""
    params = pattern_params or {}
    w = params.get("burden_b_m")
    if not w and params.get("pattern") == "square":
        w = params.get("spacing_a_m")
    try:
        w = float(w)
    except (TypeError, ValueError):
        return None
    return w if math.isfinite(w) and w > 0 else None


def allowed_floor_burden_m(pattern_params: dict | None) -> float | None:
    """Допустимая ЛСП сверху: W · (1 + 3%)."""
    w = design_burden_m(pattern_params)
    return w * (1.0 + TOE_BURDEN_TOLERANCE) if w is not None else None


def min_floor_burden_m(pattern_params: dict | None) -> float | None:
    """Допустимая ЛСП снизу: `FLOOR_BURDEN_MIN_RATIO` · W."""
    w = design_burden_m(pattern_params)
    return w * FLOOR_BURDEN_MIN_RATIO if w is not None else None


def _grid_steps_m(pattern_params: dict | None) -> tuple[float, float]:
    """Шаги сетки (a, b): a — `spacing_a_m`, без него W, без обоих
    `DEFAULT_CORRIDOR_STEP_M`; b — `burden_b_m`, без него a."""
    params = pattern_params or {}

    def step(key: str) -> float:
        try:
            value = float(params.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return value if value > 0 else 0.0

    a = step("spacing_a_m") or step("burden_b_m") or DEFAULT_CORRIDOR_STEP_M
    b = step("burden_b_m") or a
    return a, b


def shadow_limits(a: float, b: float) -> tuple[float, float]:
    """Коридор «закрыт соседом»: минимальное продвижение и предельный отступ вбок, м."""
    return SHADOW_ADVANCE_RATIO * min(a, b), SHADOW_REACH_RATIO * max(a, b)


def corridor_blockers(
    i: int,
    value: float,
    points,
    target,
    tree: shapely.STRtree,
    min_advance: float,
    reach: float,
    query_length: float | None = None,
):
    """Соседи, закрывающие точку i на пути к точке `target` (подошва или бровка).

    `query_length` — искать только в начале коридора, не дальше этого от
    точки i: найденные — настоящие закрывающие, но пустой ответ ничего не
    доказывает (дальше по коридору сосед может быть).

    d — единичный вектор от точки i к `target`, `value` — расстояние до неё; для
    соседа j продвижение — проекция (p_j − p_i) на d, отступ вбок — модуль
    перпендикулярной составляющей. Сосед закрывает i, если продвижение не меньше
    `min_advance` и меньше `value`, а отступ не больше `reach`. Такой сосед
    лежит не дальше `reach` от отрезка «точка i → target», поэтому запрос к
    индексу его не пропустит. Одна и та же проверка — у ЛСП (`floor_burdens`,
    по точкам на подошве) и у ранга ряда наклона (`design/pattern.py`, по устьям).
    """
    px, py = points[i].x, points[i].y
    dx, dy = (target.x - px) / value, (target.y - py) / value
    if query_length is not None and query_length < value:
        corridor = LineString([(px, py), (px + dx * query_length, py + dy * query_length)])
    else:
        corridor = LineString([points[i], target])
    for k in tree.query(corridor, predicate="dwithin", distance=reach):
        j = int(k)
        if j == i:
            continue
        vx, vy = points[j].x - px, points[j].y - py
        advance = vx * dx + vy * dy
        lateral = abs(vx * dy - vy * dx)
        if min_advance <= advance < value and lateral <= reach:
            yield j


def corridor_blocker_pairs(
    indices,
    points,
    targets,
    values,
    tree: shapely.STRtree,
    min_advance: float,
    reach: float,
    query_length: float | None = None,
):
    """Пакетный `corridor_blockers` для точек `indices`: пары (i, j) «j закрывает i».

    Та же проверка, что у `corridor_blockers`, но запрос к индексу и отбор —
    одним вызовом на все точки (numpy). `query_length` — как там: ищется
    только начало коридора.
    """
    idx = np.asarray(indices, dtype=np.int64)
    if idx.size == 0:
        return idx, idx
    xs, ys = shapely.get_x(points), shapely.get_y(points)
    tx, ty = shapely.get_x(targets[idx]), shapely.get_y(targets[idx])
    vals = np.asarray(values, dtype=float)[idx]
    dx, dy = (tx - xs[idx]) / vals, (ty - ys[idx]) / vals
    lengths = vals if query_length is None else np.minimum(vals, query_length)
    ex, ey = xs[idx] + dx * lengths, ys[idx] + dy * lengths
    # Запрос — по габариту коридора с полосой `reach`: отбор ниже точный, а
    # габарит дешевле проверки расстояния до отрезка.
    boxes = shapely.box(
        np.minimum(xs[idx], ex) - reach,
        np.minimum(ys[idx], ey) - reach,
        np.maximum(xs[idx], ex) + reach,
        np.maximum(ys[idx], ey) + reach,
    )
    pos, j = tree.query(boxes)
    i = idx[pos]
    vx, vy = xs[j] - xs[i], ys[j] - ys[i]
    advance = vx * dx[pos] + vy * dy[pos]
    lateral = np.abs(vx * dy[pos] - vy * dx[pos])
    keep = (j != i) & (advance >= min_advance) & (advance < vals[pos]) & (lateral <= reach)
    return i[keep], j[keep]


def crest_geometry(contour: BlockContour) -> MultiLineString | None:
    """Верхняя бровка — свободные поверхности контура; None, если их нет."""
    lines = _free_polylines(contour)
    return MultiLineString([LineString(line) for line in lines]) if lines else None


def _valid_polygon(ring):
    """Полигон кольца; самопересечённое кольцо чинится `make_valid`.

    Если починка дала набор с линиями или точками (GeometryCollection), берётся
    наибольший полигон: у набора нет границы, и «за подошвой» молча не
    находилось бы.
    """
    polygon = Polygon(ring)
    if polygon.is_valid:
        return polygon
    fixed = shapely.make_valid(polygon)
    if fixed.geom_type in ("Polygon", "MultiPolygon"):
        return fixed
    parts = [g for g in shapely.get_parts(fixed) if g.geom_type in ("Polygon", "MultiPolygon")]
    polygons = [q for g in parts for q in shapely.get_parts(g)]
    return max(polygons, key=lambda q: q.area) if polygons else polygon


def toe_positions(
    contour: BlockContour, points_xy: list[tuple[float, float]], heights_m: list[float]
) -> list[ToePosition] | None:
    """Расстояние до линии подошвы для точек на уровне подошвы; None — подошвы нет.

    Та же линия, что у ЛСП: съёмка нижней бровки с правилом развала (по высоте
    уступа `heights_m` у каждой точки) или подошва по углу. «За подошвой» —
    точка вне верхнего контура, ближайший край которого — свободная
    поверхность (со стороны откоса, а не за тылом или флангом), и при этом:
    у съёмки — вне кольца нижней бровки, у подошвы по углу — дальше смещения
    H · tan(90° − угол) от бровки.
    """
    toe = toe_line(contour)
    toe_geom = _geometry(toe)
    if toe is None or toe_geom is None or not points_xy:
        return None
    points = shapely.points(points_xy)
    values = [float(v) for v in shapely.distance(points, toe_geom)]
    sources = [toe.source] * len(points_xy)
    nearest = shapely.get_point(shapely.shortest_line(toe_geom, points), 0)
    toe_points: list = list(nearest)
    crest_geom = crest_geometry(contour)
    top = _valid_polygon(contour.points_xy)
    xs, ys = shapely.get_x(points), shapely.get_y(points)
    inside = shapely.contains_xy(top, xs, ys)
    crest_d = shapely.distance(points, crest_geom)
    # Сторона откоса: ближайший край верхнего контура — свободная поверхность.
    face_side = crest_d <= shapely.distance(points, top.boundary) + 1e-6
    if toe.source == TOE_SOURCE_SURVEY:
        bottom = _valid_polygon(drawing_bottom(contour))
        beyond = [bool(not inside[i] and face_side[i] and not bottom.covers(points[i])) for i in range(len(points))]
        _spoil_to_angle(contour, heights_m, points, toe_geom, crest_geom, inside, crest_d, values, sources, toe_points)
        # Развал: подошва по углу с высотой уступа у точки.
        angle = spoil_face_angle_deg(contour.bench)
        for i in range(len(points)):
            if sources[i] == TOE_SOURCE_ANGLE:
                offset = _offset_m(heights_m[i], angle)
                beyond[i] = bool(not inside[i] and face_side[i] and crest_d[i] > offset + 1e-9)
    else:
        offset = _offset_m(contour.bench.height_m, contour.bench.face_angle_deg)
        beyond = [bool(not inside[i] and face_side[i] and crest_d[i] > offset + 1e-9) for i in range(len(points))]
    return [
        ToePosition(
            distance_m=values[i],
            source=sources[i],
            toe_point=(float(toe_points[i].x), float(toe_points[i].y)),
            beyond=beyond[i],
        )
        for i in range(len(points_xy))
    ]


def floor_burdens(design: BlastDesign) -> dict[str, FloorBurden]:
    """ЛСП включённых рядовых скважин, стоящих у откоса.

    ЛСП — расстояние в плане от точки оси на уровне подошвы p_i до ближайшей
    точки линии подошвы t_i. Пусть d — единичный вектор от p_i к t_i. Скважину i
    закрывает от откоса другая включённая скважина сетки j (`row_family ==
    "grid"`, в том числе ручная), если одновременно:

    1. продвижение j к подошве (p_j − p_i)·d не меньше 0,4·min(a, b) и меньше
       ЛСП_i — j стоит впереди i, между ней и подошвой;
    2. отступ j вбок от направления d не больше 1,05·max(a, b).

    Закрытая скважина ЛСП не получает. Продвижение берётся вдоль коридора i, а
    не разностью ЛСП: у фланга сосед может быть ближе к фронтальной подошве, но
    стоять сбоку от пути к фланговой. Отступ до max(a, b) нужен шахматной сетке:
    сосед предыдущего ряда стоит в a/2 (ряды вдоль бровки) или в b (ряды
    поперёк бровки) сбоку. Номер ряда не важен — так первый ряд находится и у
    фланговых свободных поверхностей, и у рядов поперёк бровки.

    Точка за линией подошвы (скважина выходит в откос) коридора к подошве не
    имеет: такая скважина попадает в ответ всегда, с `beyond_toe` и
    `excess=True` — ЛСП без знака там не «в допуске», а расстояние с другой
    стороны линии.
    """
    return floor_report(design)[0]


def floor_report(design: BlastDesign) -> tuple[dict[str, FloorBurden], list[str]]:
    """ЛСП (`floor_burdens`) и скважины за подошвой (`holes_beyond_toe`) за один расчёт.

    Положение относительно линии подошвы считается один раз для всех
    включённых скважин сетки.
    """
    grid = [h for h in design.holes if h.enabled and row_family(h.kind) == "grid"]
    if not grid:
        return {}, []
    block_h = design.contour.bench.height_m
    xy = [floor_point(h) for h in grid]
    positions = toe_positions(design.contour, xy, [hole_bench_height_m(h, block_h) for h in grid])
    if positions is None:
        return {}, []
    beyond = [hole.id for hole, position in zip(grid, positions) if position.beyond]
    allowed = allowed_floor_burden_m(design.pattern_params)
    minimum = min_floor_burden_m(design.pattern_params)
    a, b = _grid_steps_m(design.pattern_params)
    min_advance, reach = shadow_limits(a, b)
    points = shapely.points(xy)
    tree = shapely.STRtree(points)
    result: dict[str, FloorBurden] = {}
    for i, hole in enumerate(grid):
        if hole.kind != "production":
            continue
        position = positions[i]
        value = position.distance_m
        if value > 0 and not position.beyond:
            target = shapely.Point(position.toe_point)
            if next(corridor_blockers(i, value, points, target, tree, min_advance, reach), None) is not None:
                continue
        result[hole.id] = FloorBurden(
            hole_id=hole.id,
            value_m=value,
            allowed_m=allowed,
            excess=position.beyond or (allowed is not None and value > allowed),
            toe_source=position.source,
            beyond_toe=position.beyond,
            min_m=minimum,
            # Допуск 1 мкм: наклон, ограниченный ровно до 0,8·W, даёт ЛСП на ошибку округления меньше.
            short=minimum is not None and not position.beyond and value < minimum - 1e-6,
        )
    return result, beyond


def holes_beyond_toe(design: BlastDesign) -> list[str]:
    """Включённые скважины сетки (в том числе ручные), чья точка на подошве за линией подошвы."""
    return floor_report(design)[1]


def hole_bench_height_m(hole: Hole, block_height_m: float) -> float:
    """Высота уступа у скважины: по её оси, без неё — высота блока."""
    own = hole.bench_height_m
    return own if own > 0 else block_height_m


def _spoil_to_angle(
    contour: BlockContour, heights, points, toe_geom, crest_geom, inside, crest_d, values, sources, toe_points
) -> None:
    """Точки, у которых съёмка подошвы — развал, переводятся на подошву по углу.

    Развал: ближайшая к точке p_i точка съёмки дальше `SURVEY_SPOIL_WIDTH_FACTOR · H_i`
    от верхней бровки, H_i — высота уступа у скважины. ЛСП по углу —
    d(p_i, бровка) + H_i · tan(90° − угол): для точки внутри блока это ровно
    расстояние до бровки, смещённой наружу на проекцию откоса (у смещённой
    кривой с круглыми стыками расстояния складываются). Точка за бровкой
    (наклонная скважина) — |смещение − d|. Угол — `spoil_face_angle_deg`.
    """
    angle = spoil_face_angle_deg(contour.bench)
    nearest_survey = shapely.get_point(shapely.shortest_line(toe_geom, points), 0)
    survey_gap = shapely.distance(nearest_survey, crest_geom)
    fallback_geom = None
    for i in range(len(points)):
        height = heights[i]
        if height <= 0 or survey_gap[i] <= SURVEY_SPOIL_WIDTH_FACTOR * height:
            continue
        offset = _offset_m(height, angle)
        d = float(crest_d[i])
        values[i] = d + offset if inside[i] else abs(offset - d)
        sources[i] = TOE_SOURCE_ANGLE
        px, py = points[i].x, points[i].y
        if d > 1e-9:
            c = nearest_points(crest_geom, points[i])[0]
            ux, uy = (c.x - px) / d, (c.y - py) / d
            if not inside[i] and offset >= d:
                ux, uy = -ux, -uy  # точка за бровкой, подошва ещё дальше от блока
            toe_points[i] = shapely.Point(px + ux * values[i], py + uy * values[i])
        else:
            # Точка на самой бровке: направление — к линии по углу блока.
            if fallback_geom is None:
                fallback_geom = _geometry(angle_toe_line(contour, angle))
            if fallback_geom is not None:
                toe_points[i] = nearest_points(fallback_geom, points[i])[0]


def spoil_angle_toe_lines(design: BlastDesign, burdens: dict[str, FloorBurden]) -> list[Polyline]:
    """Куски подошвы по углу у скважин, чья ЛСП считана по ней вместо съёмки-развала.

    Для плана: у каждой такой скважины — своя линия по углу
    (`spoil_face_angle_deg`), смещённая от бровки на H_i · tan(90° − угол) с
    высотой уступа H_i у этой скважины, как в ЛСП, в пределах ±a/2 от ближайшей
    к скважине точки (a — шаг сетки). Куски не сливаются: у скважин разной
    высоты они лежат на разном удалении от бровки. Пусто, если съёмки нет
    (тогда нарисованная подошва и есть линия по углу) или все скважины по съёмке.
    """
    ids = {hid for hid, fb in burdens.items() if fb.toe_source == TOE_SOURCE_ANGLE}
    contour = design.contour
    toe = toe_line(contour)
    if not ids or toe is None or toe.source != TOE_SOURCE_SURVEY:
        return []
    free = _free_polylines(contour)
    angle = spoil_face_angle_deg(contour.bench)
    block_h = contour.bench.height_m
    a, _ = _grid_steps_m(design.pattern_params)
    # Линия по углу для каждой встретившейся высоты: смещение одно на высоту.
    by_offset: dict[float, MultiLineString | None] = {}
    result: list[Polyline] = []
    for hole in design.holes:
        if hole.id not in ids:
            continue
        offset = round(_offset_m(hole_bench_height_m(hole, block_h), angle), 9)
        if offset not in by_offset:
            by_offset[offset] = _geometry(ToeLine(polylines=_built(contour, free, offset), source=TOE_SOURCE_ANGLE))
        geom = by_offset[offset]
        if geom is None:
            continue
        anchor = nearest_points(geom, shapely.Point(floor_point(hole)))[0]
        pieces = [g for g in shapely.get_parts(geom.intersection(anchor.buffer(a / 2.0))) if g.geom_type == "LineString"]
        if not pieces:
            continue
        # Пересечение с кругом может задеть и соседний изгиб — берётся кусок у скважины.
        piece = min(pieces, key=lambda g: g.distance(anchor))
        if len(piece.coords) >= 2:
            result.append([(float(x), float(y)) for x, y in piece.coords])
    return result
