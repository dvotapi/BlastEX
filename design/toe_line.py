"""Линия подошвы откоса: от неё считается ЛСП первого ряда скважин.

Если у контура есть съёмка нижней бровки (`cad.bottom`, контур не правили) —
берутся рёбра её кольца, не касающиеся вершин верхнего контура (тыл и фланги
кольцо делит с контуром, продления флангов начинаются в его вершинах); иначе
линия строится смещением верхней бровки наружу на проекцию откоса в плане.
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

# Допуск к проектной линии сопротивления по подошве (W): ЛСП до W + 3% — норма.
TOE_BURDEN_TOLERANCE = 0.03

Polyline = list[tuple[float, float]]


@dataclass(frozen=True)
class ToeLine:
    polylines: list[Polyline]
    source: str  # "survey" — по съёмке нижней бровки, "built" — построена от верхней


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


def toe_line(contour: BlockContour) -> ToeLine | None:
    """Линия подошвы вдоль свободных поверхностей; None, если их нет."""
    free = _free_polylines(contour)
    if not free:
        return None
    ring = drawing_bottom(contour)
    if ring is not None:
        polylines = _survey(ring, contour.points_xy)
        if polylines:
            return ToeLine(polylines=polylines, source="survey")
    return ToeLine(polylines=_built(contour, free, slope_offset_m(contour.bench)), source="built")


@dataclass(frozen=True)
class FloorBurden:
    hole_id: str
    value_m: float  # ЛСП: расстояние в плане от точки оси на уровне подошвы до линии подошвы
    allowed_m: float | None  # W + 3%; None, если W не задана
    excess: bool


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


def _corridor_half_width_m(pattern_params: dict | None) -> float:
    """Половина шага по ряду: a, без него — W, без обоих — `DEFAULT_CORRIDOR_STEP_M`."""
    params = pattern_params or {}
    for key in ("spacing_a_m", "burden_b_m"):
        try:
            step = float(params.get(key) or 0.0)
        except (TypeError, ValueError):
            step = 0.0
        if step > 0:
            return step / 2.0
    return DEFAULT_CORRIDOR_STEP_M / 2.0


def floor_burdens(design: BlastDesign) -> dict[str, FloorBurden]:
    """ЛСП включённых рядовых скважин, стоящих у откоса.

    ЛСП — расстояние в плане от точки оси на уровне подошвы до ближайшей точки
    линии подошвы. Скважина стоит у откоса, если в коридоре между этими двумя
    точками нет другой включённой скважины сетки (`row_family == "grid"`, в том
    числе ручной), которая ближе к подошве: расстояние соседа до отрезка меньше
    a/2 и его ЛСП меньше. Номер ряда не важен — так первый ряд находится и у
    фланговых свободных поверхностей, и у рядов поперёк бровки.
    """
    toe = toe_line(design.contour)
    if toe is None:
        return {}
    lines = [LineString(poly) for poly in toe.polylines if len(poly) >= 2]
    if not lines:
        return {}
    toe_geom = MultiLineString(lines)
    allowed = allowed_floor_burden_m(design.pattern_params)
    half = _corridor_half_width_m(design.pattern_params)
    grid = [h for h in design.holes if h.enabled and row_family(h.kind) == "grid"]
    if not grid:
        return {}
    points = shapely.points([floor_point(h) for h in grid])
    values = shapely.distance(points, toe_geom)
    tree = shapely.STRtree(points)
    result: dict[str, FloorBurden] = {}
    for i, hole in enumerate(grid):
        if hole.kind != "production":
            continue
        value = float(values[i])
        if value > 0:
            corridor = LineString([points[i], nearest_points(toe_geom, points[i])[0]])
            near = tree.query(corridor, predicate="dwithin", distance=half)
            if any(
                j != i and values[j] < value and shapely.distance(points[j], corridor) < half
                for j in (int(k) for k in near)
            ):
                continue
        result[hole.id] = FloorBurden(
            hole_id=hole.id,
            value_m=value,
            allowed_m=allowed,
            excess=allowed is not None and value > allowed,
        )
    return result
