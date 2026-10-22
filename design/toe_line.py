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

from design.geometry import drawing_bottom, local_basis
from design.models import FACE_TOE_KIND, BenchSurface, BlastDesign, BlockContour, Hole, face_pair_partner_id, logical_row, row_family

# Вершина кольца нижней бровки ближе этого к вершине верхнего контура — общая с ним, м.
SHARED_VERTEX_TOLERANCE_M = 0.01

# Положе этого угла откоса (от горизонтали) смещение подошвы не считается: при
# угле у нуля проекция откоса уходит в сотни метров.
MIN_FACE_ANGLE_DEG = 30.0

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

# Минимальный отступ устья от кромки (верхней бровки) по умолчанию, м:
# `pattern_params.min_crest_offset_m` (решение владельца 22.10.2026).
MIN_CREST_OFFSET_DEFAULT_M = 1.0

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
class FloorRowGap:
    """Разрыв у подошвы между скважиной и рядом впереди неё (к откосу)."""

    hole_id: str
    value_m: float  # продвижение соседа впереди вдоль коридора, на уровне подошвы
    allowed_m: float  # шаг + 3 %
    excess: bool  # все соседи впереди дальше своего допуска
    # С каким шагом сравнивалось: "a" (по ряду), "b" (соседний ряд), "2b" (через ряд)
    # или "grid" — проекция решётки на коридор (косой ряд, дуга).
    step: str = "b"


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


# Сетки, у которых шаг рядов b задаётся отдельно от a (`design/pattern.py`);
# остальное, включая отсутствие ключа `pattern`, — квадратная сетка, b = a.
_OWN_BURDEN_PATTERNS = ("rectangular", "staggered", "variable", "domain_dependent")


# Шаг a квадратной сетки без `spacing_a_m` — как в `generate_pattern`, м.
DEFAULT_SQUARE_SPACING_M = 5.0


def _is_square(params: dict) -> bool:
    """Квадратная ли сетка — так же, как в `generate_pattern` (нет ключа или неизвестный вид — квадратная)."""
    return str(params.get("pattern", "square")) not in _OWN_BURDEN_PATTERNS


def _positive(params: dict, key: str) -> float | None:
    """Положительное конечное число из `params[key]`; иначе None."""
    try:
        value = float(params.get(key))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def grid_steps_m(pattern_params: dict | None) -> tuple[float, float]:
    """Шаги сетки (a, b) так же, как их берёт `generate_pattern`.

    a — `spacing_a_m`, без него `DEFAULT_SQUARE_SPACING_M`; b — у квадратной
    сетки a, у остальных `burden_b_m`, без него a. Одна функция для W
    (`design_burden_m`), коридора «закрыт соседом» (`shadow_limits`) и
    допусков разрыва у подошвы.
    """
    params = pattern_params or {}
    a = _positive(params, "spacing_a_m") or DEFAULT_SQUARE_SPACING_M
    b = a if _is_square(params) else _positive(params, "burden_b_m") or a
    return a, b


def design_burden_m(pattern_params: dict | None) -> float | None:
    """Проектная W — шаг b (`grid_steps_m`); None — не задана.

    Задана: у квадратной сетки — введён `spacing_a_m` или `burden_b_m` (без
    шага генератор строит сетку с a по умолчанию), у остальных — `burden_b_m`.
    """
    params = pattern_params or {}
    keys = ("spacing_a_m", "burden_b_m") if _is_square(params) else ("burden_b_m",)
    if not any(_positive(params, key) for key in keys):
        return None
    return grid_steps_m(params)[1]


def allowed_floor_burden_m(pattern_params: dict | None) -> float | None:
    """Допустимая ЛСП сверху: W · (1 + 3%)."""
    w = design_burden_m(pattern_params)
    return w * (1.0 + TOE_BURDEN_TOLERANCE) if w is not None else None


def min_floor_burden_m(pattern_params: dict | None) -> float | None:
    """Допустимая ЛСП снизу: `FLOOR_BURDEN_MIN_RATIO` · W."""
    w = design_burden_m(pattern_params)
    return w * FLOOR_BURDEN_MIN_RATIO if w is not None else None


def min_crest_offset_m(pattern_params: dict | None) -> float:
    """Минимальный отступ устья от кромки: `min_crest_offset_m`, без него (или
    при неверном значении) — `MIN_CREST_OFFSET_DEFAULT_M`; не меньше 0."""
    raw = (pattern_params or {}).get("min_crest_offset_m")
    try:
        value = float(raw) if raw not in (None, "") else MIN_CREST_OFFSET_DEFAULT_M
    except (TypeError, ValueError):
        return MIN_CREST_OFFSET_DEFAULT_M
    return max(0.0, value) if math.isfinite(value) else MIN_CREST_OFFSET_DEFAULT_M


# Ключи, с которыми проверяется отступ устья от кромки (`crest_offset_checked`).
CREST_OFFSET_KEYS = ("min_crest_offset_m", "front_rows_mode", "front_rows_tilt_count", "front_rows_tilt_deg")


def crest_offset_checked(pattern_params: dict | None) -> bool:
    """Проверять ли отступ устья от кромки: задан `min_crest_offset_m` или ключ
    схемы первого ряда (решение 22.10.2026 — старые паспорта без ключей не
    засыпаются предупреждениями).

    Шахматную сетку плавный переход не меняет (`generate_pattern`), поэтому у
    неё ключи перехода проверку не включают — только `min_crest_offset_m` или
    пара у откоса.
    """
    params = pattern_params or {}
    if not any(params.get(key) not in (None, "") for key in CREST_OFFSET_KEYS):
        return False
    if params.get("min_crest_offset_m") not in (None, ""):
        return True
    if str(params.get("front_rows_mode") or "").strip().lower() == "pair":
        return True
    return str(params.get("pattern", "square")) != "staggered"


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
    """ЛСП включённых скважин основной сетки и пар у откоса, стоящих у откоса.

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
    burdens, beyond, _gaps = floor_checks(design, with_gaps=False)
    return burdens, beyond


def floor_row_gaps(design: BlastDesign) -> dict[str, FloorRowGap]:
    """Разрывы между рядами у подошвы (см. `floor_checks`); пусто, если b не задан."""
    return floor_checks(design)[2]


def floor_checks(
    design: BlastDesign, *, with_gaps: bool = True
) -> tuple[dict[str, FloorBurden], list[str], dict[str, FloorRowGap]]:
    """ЛСП, скважины за подошвой и разрывы между рядами у подошвы за один расчёт.

    Разрыв у подошвы — у скважины основной сетки (рядовые и `default_kind`),
    перед которой в её коридоре к подошве стоит другая скважина основной
    сетки: наименьшее продвижение такого соседа вдоль коридора (та же
    проверка «впереди», что у ЛСП, — `corridor_blocker_pairs`, по точкам на
    подошве). Это расстояние до ряда впереди у подошвы: у шахматной сетки
    сосед стоит наискосок, но продвигается на b. Пары у откоса и стенки не
    считаются ни скважиной, ни соседом: вертикальная за парой — ряд 1, у неё
    разрыва нет. Допуск — b + 3 % (b — `design_burden_m`, у квадратной
    сетки a), а для соседа своего ряда решётки — a + 3 % (`_row_gaps`); без b
    разрывы не считаются.
    """
    grid = [h for h in design.holes if h.enabled and row_family(h.kind) == "grid"]
    if not grid:
        return {}, [], {}
    block_h = design.contour.bench.height_m
    xy = [floor_point(h) for h in grid]
    positions = toe_positions(design.contour, xy, [hole_bench_height_m(h, block_h) for h in grid])
    if positions is None:
        return {}, [], {}
    beyond = [hole.id for hole, position in zip(grid, positions) if position.beyond]
    allowed = allowed_floor_burden_m(design.pattern_params)
    minimum = min_floor_burden_m(design.pattern_params)
    a, b = grid_steps_m(design.pattern_params)
    min_advance, reach = shadow_limits(a, b)
    points = shapely.points(xy)
    tree = shapely.STRtree(points)
    # ЛСП — у скважин основной сетки (рядовые и вид `default_kind`) и у пар у
    # откоса; вертикальная за своей парой закрыта всегда — даже если пара
    # вертикальная и стоит впереди меньше чем на 0,4·min(a, b).
    measured = {"production", FACE_TOE_KIND}
    default_kind = str((design.pattern_params or {}).get("default_kind") or "").strip().lower()
    if default_kind:
        measured.add(default_kind)
    paired = {partner for hole in grid if (partner := face_pair_partner_id(hole)) is not None}
    result: dict[str, FloorBurden] = {}
    for i, hole in enumerate(grid):
        if hole.kind not in measured or hole.id in paired:
            continue
        position = positions[i]
        value = position.distance_m
        if value > 0 and not position.beyond:
            target = shapely.Point(position.toe_point)
            # Пара у откоса закрывает только свою вертикальную (`paired`), не соседей.
            blockers = corridor_blockers(i, value, points, target, tree, min_advance, reach)
            if next((j for j in blockers if grid[j].kind != FACE_TOE_KIND), None) is not None:
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
    gaps: dict[str, FloorRowGap] = {}
    if with_gaps and allowed is not None:
        main_kinds = measured - {FACE_TOE_KIND}
        main = [grid[i] for i in range(len(grid)) if grid[i].kind in main_kinds]
        index = [i for i in range(len(grid)) if grid[i].kind in main_kinds]
        steps = _hole_steps(design, main, b)
        if steps is not None:
            gaps = _row_gaps(
                [hole.id for hole in main],
                [xy[i] for i in index],
                [(hole.collar.x, hole.collar.y) for hole in main],
                [positions[i] for i in index],
                steps,
                _row_azimuth_deg(design.pattern_params),
                min_advance,
                reach,
                a,
            )
    return result, beyond, gaps


def row_steps_m(params: dict, pattern: str, row_index: int, a: float, b: float) -> tuple[float, float]:
    """Шаги (a, b) ряда решётки `row_index` переменной сетки: строка `row_params`
    (за последней — последняя), неверные значения — общие шаги. Одно правило
    с генератором (`design/pattern.py::_row_config`); b ряда — шаг до следующего.
    """
    row_params = params.get("row_params") or []
    override: dict = {}
    if pattern == "variable" and isinstance(row_params, list) and row_params:
        if 0 <= row_index < len(row_params) and isinstance(row_params[row_index], dict):
            override = row_params[row_index]
        elif isinstance(row_params[-1], dict):
            override = row_params[-1]
    return _positive(override, "spacing_a_m") or a, _positive(override, "burden_b_m") or b


def _hole_steps(design: BlastDesign, holes: list[Hole], b: float):
    """Ряд решётки и шаг b (до следующего ряда) у каждой скважины основной сетки.

    Переменная сетка — шаг ряда (`row_steps_m`, ряды впереди первого — строка
    0); сетка по доменам — b домена у устья (как у генератора: только
    заданный доменом); без доменов у такой сетки шаг неизвестен — None,
    разрыв не проверяется.
    """
    params = design.pattern_params or {}
    pattern = str(params.get("pattern", "square"))
    rows = np.asarray([logical_row(h.row) for h in holes], dtype=np.int64)
    steps_b = np.full(len(holes), b)
    if pattern == "variable":
        for k, row in enumerate(rows.tolist()):
            steps_b[k] = row_steps_m(params, pattern, max(row, 0), b, b)[1]
    elif pattern == "domain_dependent":
        if not design.domains:
            return None
        from design.geology import domain_at
        from design.models import Point3

        crest_z = design.contour.bench.crest_z_m
        for k, hole in enumerate(holes):
            domain = domain_at(design.domains, Point3(x=hole.collar.x, y=hole.collar.y, z=crest_z))
            if domain is not None and domain.burden_b_m:
                steps_b[k] = domain.burden_b_m
    return rows, steps_b


def _row_azimuth_deg(pattern_params: dict | None) -> float:
    """Азимут рядов сетки (`row_azimuth_deg`, как у генератора; без него 0°)."""
    try:
        value = float((pattern_params or {}).get("row_azimuth_deg") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _row_gaps(
    ids: list[str],
    xy: list[tuple[float, float]],
    collars_xy: list[tuple[float, float]],
    positions: list[ToePosition],
    steps,
    row_azimuth_deg: float,
    min_advance: float,
    reach: float,
    step_a: float | None = None,
) -> dict[str, FloorRowGap]:
    """Разрыв у подошвы для точек основной сетки (см. `floor_checks`), пакетом.

    Как у ранга ряда (`design/pattern.py::front_row_ranks`): сначала начало
    коридора у всех, весь коридор — только у тех, кому там соседа не нашлось.

    Для каждой пары «сосед j впереди i в коридоре к подошве» допуск — её
    продвижение в правильной решётке, плюс 3 %: вектор решётки от i к j
    вдоль ряда берётся по устьям (наклон и сдвиг плавного перехода идут
    вдоль столбца и его не меняют), поперёк ряда — |Δряд|·b (`steps`: b ряда,
    что ближе к началу решётки; у соседа своего ряда — 0), и проецируется на
    направление коридора. Так сосед своего ряда сравнивается с a (ряды
    поперёк бровки, фланговая грань), сосед другого ряда прямо впереди — с
    b, наискосок — с проекцией решётки (косые ряды, дуга), а сдвинутая к
    тылу у подошвы скважина даёт продвижение больше допуска. Пары, где в
    решётке j не впереди i (продвижение решётки меньше порога «впереди»), не
    считаются. Разрыв — если каждый сосед впереди дальше своего допуска
    (наименьшее отношение продвижения к допуску больше 1); в ответе — пара с
    наименьшим отношением, при равенстве — своего ряда.
    """
    if not ids:
        return {}
    rows, steps_b = steps
    points = shapely.points(xy)
    tree = shapely.STRtree(points)
    targets = shapely.points([p.toe_point for p in positions])
    values = np.asarray([p.distance_m for p in positions], dtype=float)
    eligible = [i for i, p in enumerate(positions) if p.distance_m > 0 and not p.beyond]
    near = min_advance + 2.0 * reach
    near_i, near_j = corridor_blocker_pairs(eligible, points, targets, values, tree, min_advance, reach, near)
    found = set(near_i.tolist())
    far = [i for i in eligible if i not in found and values[i] > near]
    far_i, far_j = corridor_blocker_pairs(far, points, targets, values, tree, min_advance, reach)
    i = np.concatenate([near_i, far_i])
    j = np.concatenate([near_j, far_j])
    if i.size == 0:
        return {}
    xs, ys = shapely.get_x(points), shapely.get_y(points)
    tx, ty = shapely.get_x(targets), shapely.get_y(targets)
    # Направление коридора i и продвижение соседа j — как в `corridor_blocker_pairs`.
    dx, dy = (tx[i] - xs[i]) / values[i], (ty[i] - ys[i]) / values[i]
    advance = (xs[j] - xs[i]) * dx + (ys[j] - ys[i]) * dy
    # Вектор решётки i → j: вдоль ряда — по устьям, поперёк — ±b (свой ряд — 0).
    (rx, ry), (ax, ay) = local_basis(row_azimuth_deg)
    collars = np.asarray(collars_xy, dtype=float)
    cx, cy = collars[j, 0] - collars[i, 0], collars[j, 1] - collars[i, 1]
    along = cx * rx + cy * ry
    across = cx * ax + cy * ay
    same = rows[i] == rows[j]
    step_b = np.where(rows[i] < rows[j], steps_b[i], steps_b[j])
    # Через ряд (наклонённый ряд ушёл вперёд соседнего) — |Δряд|·b.
    lattice_across = np.where(same, 0.0, np.sign(across) * np.abs(rows[j] - rows[i]) * step_b)
    expected = along * (rx * dx + ry * dy) + lattice_across * (ax * dx + ay * dy)
    # Пара считается, только если и в решётке j впереди i (иначе это сосед
    # сбоку, ушедший вперёд наклоном, а не ряд впереди).
    ahead = expected >= min_advance
    # Подпись допуска: чистый шаг (a, b, k·b), если допуск с ним совпадает
    # (коридор вдоль столбца или ряда), иначе — проекция решётки, «шаг сетки».
    # Подпись — `step_a` (a паспорта), у переменной сетки с другим a ряда — «шаг сетки».
    rows_apart = np.abs(rows[j] - rows[i])
    cols_apart = np.rint(np.abs(along) / step_a).astype(np.int64) if step_a else np.zeros_like(rows_apart)
    pure = np.where(same, cols_apart * (step_a or 0.0), rows_apart * step_b)
    exact = (pure > 0) & (np.abs(expected - pure) <= 0.01 * pure)
    count = np.where(same, cols_apart, rows_apart)
    letter = np.where(same, "a", "b")
    labels = np.where(
        ~exact, "grid", np.where(count == 1, letter, np.char.add(count.astype(str), letter))
    )
    i, j, same, advance, expected, labels = i[ahead], j[ahead], same[ahead], advance[ahead], expected[ahead], labels[ahead]
    if i.size == 0:
        return {}
    allowed = expected * (1.0 + TOE_BURDEN_TOLERANCE)
    ratio = advance / allowed
    # При равных отношениях в ответ — сосед своего ряда (сравнение с a).
    order = np.lexsort((~same, np.round(ratio, 9), i))
    first = order[np.r_[True, i[order][1:] != i[order][:-1]]]
    return {
        ids[k]: FloorRowGap(
            hole_id=ids[k],
            value_m=float(advance[p]),
            allowed_m=float(allowed[p]),
            excess=bool(ratio[p] > 1.0 + 1e-9),
            step=str(labels[p]),
        )
        for p in first.tolist()
        for k in (int(i[p]),)
    }


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
    a, _ = grid_steps_m(design.pattern_params)
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
