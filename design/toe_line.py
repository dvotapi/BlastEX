"""Линия подошвы откоса: от неё считается ЛСП первого ряда скважин.

Если у контура есть съёмка нижней бровки (`cad.bottom`, контур не правили) —
берутся рёбра её кольца, не касающиеся вершин верхнего контура (тыл и фланги
кольцо делит с контуром, продления флангов начинаются в его вершинах); иначе
линия строится смещением верхней бровки наружу на проекцию откоса в плане
(«подошва по углу»).

Съёмка с развалом (решение 21.10.2026, блок №66): если ближайшая к скважине
точка съёмки лежит от верхней бровки дальше `SURVEY_SPOIL_WIDTH_FACTOR · H`,
там не откос, а развал или берма — ЛСП этой скважины считается по линии,
построенной по углу откоса блока.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

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

# Источник линии подошвы у скважины: съёмка нижней бровки или построение по углу.
TOE_SOURCE_SURVEY = "survey"
TOE_SOURCE_ANGLE = "angle"

# Допуск к проектной линии сопротивления по подошве (W): ЛСП до W + 3% — норма.
TOE_BURDEN_TOLERANCE = 0.03

Polyline = list[tuple[float, float]]


@dataclass(frozen=True)
class ToeLine:
    polylines: list[Polyline]
    source: str  # "survey" — по съёмке нижней бровки, "angle" — от верхней бровки по углу откоса


def slope_offset_m(bench: BenchSurface) -> float:
    """Смещение подошвы от верхней бровки в плане: H · tan(90° − угол откоса).

    Угол откоса — от горизонтали, не положе `MIN_FACE_ANGLE_DEG`.
    """
    angle = min(90.0, max(MIN_FACE_ANGLE_DEG, bench.face_angle_deg))
    return max(0.0, bench.height_m * math.tan(math.radians(90.0 - angle)))


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


def angle_toe_line(contour: BlockContour) -> ToeLine | None:
    """Линия подошвы по углу откоса блока; None, если свободных поверхностей нет."""
    free = _free_polylines(contour)
    if not free:
        return None
    return ToeLine(polylines=_built(contour, free, slope_offset_m(contour.bench)), source=TOE_SOURCE_ANGLE)


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
    excess: bool
    toe_source: str = TOE_SOURCE_SURVEY  # "survey" — съёмка, "angle" — подошва по углу


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


def allowed_floor_burden_m(pattern_params: dict | None) -> float | None:
    """Допустимая ЛСП: W · (1 + 3%). W — `burden_b_m`; у квадратной сетки без него — шаг."""
    params = pattern_params or {}
    w = params.get("burden_b_m")
    if not w and params.get("pattern") == "square":
        w = params.get("spacing_a_m")
    try:
        w = float(w)
    except (TypeError, ValueError):
        return None
    return w * (1.0 + TOE_BURDEN_TOLERANCE) if w > 0 else None


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


def _shadowed(
    i: int,
    value: float,
    points,
    toe_point,
    tree: shapely.STRtree,
    min_advance: float,
    reach: float,
) -> bool:
    """Закрыта ли скважина i соседом сетки на пути к ближайшей точке подошвы.

    d — единичный вектор от точки i к ближайшей точке линии подошвы; для соседа
    j продвижение — проекция (p_j − p_i) на d, отступ вбок — модуль
    перпендикулярной составляющей. Такой сосед лежит не дальше `reach` от
    отрезка «точка i → подошва», поэтому запрос к индексу его не пропустит.
    """
    px, py = points[i].x, points[i].y
    dx, dy = (toe_point.x - px) / value, (toe_point.y - py) / value
    corridor = LineString([points[i], toe_point])
    for k in tree.query(corridor, predicate="dwithin", distance=reach):
        j = int(k)
        if j == i:
            continue
        vx, vy = points[j].x - px, points[j].y - py
        advance = vx * dx + vy * dy
        lateral = abs(vx * dy - vy * dx)
        if min_advance <= advance < value and lateral <= reach:
            return True
    return False


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
    """
    toe = toe_line(design.contour)
    if toe is None:
        return {}
    toe_geom = _geometry(toe)
    if toe_geom is None:
        return {}
    angle_geom = toe_geom if toe.source == TOE_SOURCE_ANGLE else _geometry(angle_toe_line(design.contour))
    crest_geom = MultiLineString([LineString(line) for line in _free_polylines(design.contour)])
    allowed = allowed_floor_burden_m(design.pattern_params)
    a, b = _grid_steps_m(design.pattern_params)
    min_advance = SHADOW_ADVANCE_RATIO * min(a, b)
    reach = SHADOW_REACH_RATIO * max(a, b)
    grid = [h for h in design.holes if h.enabled and row_family(h.kind) == "grid"]
    if not grid:
        return {}
    points = shapely.points([floor_point(h) for h in grid])
    # Линия подошвы каждой скважины: съёмка, а там, где ближайшая точка съёмки
    # дальше k·H от верхней бровки (развал, берма), — построенная по углу.
    geoms = [toe_geom] * len(grid)
    sources = [toe.source] * len(grid)
    spoil_width = SURVEY_SPOIL_WIDTH_FACTOR * design.contour.bench.height_m
    if toe.source == TOE_SOURCE_SURVEY and angle_geom is not None and spoil_width > 0:
        nearest = shapely.get_point(shapely.shortest_line(toe_geom, points), 0)
        spoil = shapely.distance(nearest, crest_geom) > spoil_width
        for i in range(len(grid)):
            if spoil[i]:
                geoms[i] = angle_geom
                sources[i] = TOE_SOURCE_ANGLE
    values = shapely.distance(points, geoms)
    tree = shapely.STRtree(points)
    result: dict[str, FloorBurden] = {}
    for i, hole in enumerate(grid):
        if hole.kind != "production":
            continue
        value = float(values[i])
        if value > 0:
            toe_point = nearest_points(geoms[i], points[i])[0]
            if _shadowed(i, value, points, toe_point, tree, min_advance, reach):
                continue
        result[hole.id] = FloorBurden(
            hole_id=hole.id,
            value_m=value,
            allowed_m=allowed,
            excess=allowed is not None and value > allowed,
            toe_source=sources[i],
        )
    return result
