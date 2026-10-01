"""Контур блока из чертежа: готовый, щелчок внутри, сборка (TASK-013, PR 2).

Каждый способ даёт `ContourDraft`: нормализованное кольцо, ошибки для кнопки
«Построить блок» и участки (`items`). По участкам любой результат можно
дальше править как сборку (§2 «Модель блока и контур»).

- **Готовый** — замкнутая линия; почти замкнутая (разрыв ≤ допуска)
  замыкается сама.
- **Сборка** — участки по порядку. Направление каждого следующего участка
  выбирается по ближайшему концу, первый поворачивается к второму. Разрыв ≤
  допуска сводит концы в их среднюю точку (стык не оставляет ребра в
  сантиметры), больший — замыкающий отрезок.
- **Щелчок внутри** — как штриховка AutoCAD: линии выбранных ролей
  разбиваются в пересечениях, берётся грань с точкой щелчка. Концы ближе
  допуска сводятся, висячие концы соединяются мостом до `bridge_m` — иначе
  контур, присланный кусками с разрывами в метры, не замкнулся бы.

Z контура не используется (§2): это отметка вычерчивания, а не рельеф.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import shapely
import shapely.ops
from shapely.geometry import LineString, Point

from design.spatial.cad.model import CadEntity, CadWarning, ru_number
from design.spatial.cad.reader import CLOSURE_TOLERANCE_M
from design.spatial.cad.rings import XY, LocalFrame, RingIssue, check_ring, normalize_ring
from design.spatial.cad.stitch import StitchedLine

DEFAULT_TOLERANCE_M = CLOSURE_TOLERANCE_M
DEFAULT_BRIDGE_M = 5.0
# Отрезков линий выбранных ролей: больше — уже подложка карьера, а не блок.
MAX_CONTOUR_SEGMENTS = 20_000
# Точка лежит на линии (после узлов shapely), если ближе этого.
_ON_LINE_M = 1e-6

ITEM_KINDS = ("part", "segment", "polyline")


class ContourInputError(ValueError):
    """Запрос контура нельзя выполнить: неизвестный объект, слишком много линий."""


@dataclass
class ContourItem:
    """Участок контура.

    `part` — кусок линии чертежа от `start_m` до `end_m` по её длине в плане;
    `segment` — прямой отрезок `points[0]`–`points[1]`; `polyline` —
    построенная линия (например, тыл блока по бровке). `flip` разворачивает
    участок против направления, выбранного по ближайшему концу.
    """

    kind: str
    handle: str = ""
    start_m: float = 0.0
    end_m: float = 0.0
    points: list[XY] = field(default_factory=list)
    flip: bool = False
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "handle": self.handle,
            "start_m": self.start_m,
            "end_m": self.end_m,
            "points": [list(point) for point in self.points],
            "flip": self.flip,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ContourItem:
        return cls(
            kind=str(data.get("kind", "")),
            handle=str(data.get("handle", "")),
            start_m=float(data.get("start_m", 0.0)),
            end_m=float(data.get("end_m", 0.0)),
            points=[(float(x), float(y)) for x, y, *_ in data.get("points", [])],
            flip=bool(data.get("flip", False)),
            label=str(data.get("label", "")),
        )


@dataclass
class ItemInfo:
    """Участок в собранном контуре: длина, разворот, стык со следующим."""

    kind: str
    handle: str
    layer: str
    length_m: float
    reversed: bool
    gap_to_next_m: float = 0.0
    # `joined` — концы сведены (разрыв ≤ допуска), `closing` — замыкающий отрезок.
    link: str = "joined"


@dataclass
class ContourDraft:
    ring: list[XY] | None
    items: list[ContourItem] = field(default_factory=list)
    item_info: list[ItemInfo] = field(default_factory=list)
    closings: list[tuple[XY, XY]] = field(default_factory=list)
    issues: list[RingIssue] = field(default_factory=list)
    warnings: list[CadWarning] = field(default_factory=list)
    # Блок по бровке: участок бровки, выбранный инженером. Свободная
    # поверхность — только вдоль него, а не вдоль любых бровок у тыла.
    crest_line: list[XY] | None = None

    @property
    def ok(self) -> bool:
        return bool(self.ring) and not self.issues


# --- полилинии в плане ---------------------------------------------------


def line_xy(entity: CadEntity) -> list[XY]:
    """Точки линии в плане; у замкнутой — с возвратом в начало."""

    points = [(float(point[0]), float(point[1])) for point in entity.points]
    if entity.closed and len(points) > 2:
        points.append(points[0])
    return points


def polyline_length(points: Sequence[XY]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def _lerp(a: XY, b: XY, t: float) -> XY:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _mid(a: XY, b: XY) -> XY:
    return _lerp(a, b, 0.5)


def _dedupe(points: Sequence[XY]) -> list[XY]:
    clean: list[XY] = []
    for point in points:
        if not clean or math.dist(clean[-1], point) > 1e-9:
            clean.append(point)
    return clean


def cut_polyline(points: Sequence[XY], from_m: float, to_m: float) -> list[XY]:
    """Кусок полилинии между расстояниями `from_m` и `to_m` от её начала."""

    total = polyline_length(points)
    start, end = sorted((min(max(from_m, 0.0), total), min(max(to_m, 0.0), total)))
    result: list[XY] = []
    walked = 0.0
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        seg_start, seg_end = walked, walked + length
        walked = seg_end
        if seg_end < start:
            continue
        if not result:
            result.append(_lerp(a, b, (start - seg_start) / length) if length else a)
        if seg_end >= end:
            result.append(_lerp(a, b, (end - seg_start) / length) if length else b)
            break
        result.append(b)
    if not result and points:
        result.append(points[-1])
    return _dedupe(result)


def project_on_polyline(points: Sequence[XY], point: XY) -> tuple[float, XY, float]:
    """Ближайшая точка полилинии: расстояние по линии, точка и удаление от неё."""

    best = (0.0, points[0], math.dist(points[0], point))
    walked = 0.0
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        t = 0.0 if not length2 else max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length2))
        foot = (a[0] + dx * t, a[1] + dy * t)
        distance = math.dist(foot, point)
        if distance < best[2]:
            best = (walked + t * math.sqrt(length2), foot, distance)
        walked += math.sqrt(length2)
    return best


def _check_size(lines: Sequence[CadEntity]) -> None:
    count = sum(max(len(item.points) - 1 + (1 if item.closed else 0), 0) for item in lines)
    if count > MAX_CONTOUR_SEGMENTS:
        raise ContourInputError(
            f"Линий выбранных ролей слишком много: {count} отрезков, предел {MAX_CONTOUR_SEGMENTS}. "
            "Снимите лишние роли."
        )


def _usable(lines: Sequence[CadEntity]) -> list[CadEntity]:
    return [item for item in lines if item.geometry_type == "line" and len(item.points) >= 2]


def _points_of(geometry) -> list[Point]:
    """Точки пересечения линий: точки как есть, у наложений — их концы."""

    if geometry.is_empty:
        return []
    kind = geometry.geom_type
    if kind == "Point":
        return [geometry]
    if kind == "LineString":
        coords = list(geometry.coords)
        return [Point(coords[0]), Point(coords[-1])]
    if hasattr(geometry, "geoms"):
        return [point for part in geometry.geoms for point in _points_of(part)]
    return []


# --- разрезы линий -------------------------------------------------------


def split_lines(lines: Sequence[CadEntity]) -> tuple[dict[str, list[float]], list[XY]]:
    """Где линии выбранных ролей пересекаются: места по длине каждой и точки.

    Щелчок по линии в сборке берёт её кусок между соседними разрезами.
    """

    usable = _usable(lines)
    _check_size(usable)
    frame = LocalFrame.of(point for item in usable for point in line_xy(item))
    geoms = [LineString(frame.to_local(line_xy(item))) for item in usable]
    tree = shapely.STRtree(geoms)
    raw: dict[int, list[float]] = {}
    crossings: dict[tuple[float, float], XY] = {}
    left, right = tree.query(geoms, predicate="intersects")
    for i, j in zip(left.tolist(), right.tolist()):
        if i >= j:
            continue
        for point in _points_of(geoms[i].intersection(geoms[j])):
            raw.setdefault(i, []).append(geoms[i].project(point))
            raw.setdefault(j, []).append(geoms[j].project(point))
            world = frame.point_to_world((point.x, point.y))
            crossings.setdefault((round(world[0], 3), round(world[1], 3)), world)

    splits: dict[str, list[float]] = {}
    for index, values in raw.items():
        length = geoms[index].length
        inner = sorted(value for value in values if 1e-6 < value < length - 1e-6)
        merged: list[float] = []
        for value in inner:
            if not merged or value - merged[-1] > 1e-3:
                merged.append(value)
        if merged:
            splits[usable[index].handle] = merged
    return splits, list(crossings.values())


# --- готовый контур и сборка --------------------------------------------


def ready_contour(entity: CadEntity, tolerance_m: float = DEFAULT_TOLERANCE_M) -> ContourDraft:
    if entity.geometry_type != "line" or len(entity.points) < 2:
        raise ContourInputError(f"Объект {entity.handle} — не линия.")
    item = ContourItem(kind="part", handle=entity.handle, start_m=0.0, end_m=entity.length_m)
    points = _dedupe([(float(point[0]), float(point[1])) for point in entity.points])
    if entity.closed:
        ring = normalize_ring(points)
        info = ItemInfo("part", entity.handle, entity.layer, entity.length_m, False)
        return ContourDraft(ring=ring, items=[item], item_info=[info], issues=check_ring(ring))
    gap = math.dist(points[0], points[-1])
    if gap <= tolerance_m and len(points) >= 3:
        return assemble([item], {entity.handle: entity}, tolerance_m)
    return ContourDraft(
        ring=None,
        items=[item],
        issues=[
            RingIssue(
                "not_closed",
                f"Линия {entity.handle} не замкнута: разрыв {ru_number(gap, 2)} м больше допуска "
                f"{ru_number(tolerance_m, 2)} м. Соберите контур из участков или увеличьте допуск.",
                points[-1],
            )
        ],
    )


def assemble(
    items: Sequence[ContourItem], lines: Mapping[str, CadEntity], tolerance_m: float = DEFAULT_TOLERANCE_M
) -> ContourDraft:
    pieces: list[list[XY]] = []
    meta: list[tuple[str, str, str]] = []
    issues: list[RingIssue] = []
    for number, item in enumerate(items, start=1):
        if item.kind == "part":
            entity = lines.get(item.handle)
            if entity is None:
                raise ContourInputError(f"Объекта {item.handle} нет среди линий контура.")
            points = cut_polyline(line_xy(entity), item.start_m, item.end_m)
            layer = entity.layer
        elif item.kind in ("segment", "polyline"):
            if item.kind == "segment" and len(item.points) != 2:
                raise ContourInputError(f"Отрезок {number} задаётся двумя точками.")
            points = _dedupe([(float(x), float(y)) for x, y in item.points])
            layer = ""
        else:
            raise ContourInputError(f"Неизвестный вид участка «{item.kind}».")
        if not points:
            raise ContourInputError(f"Участок {number} пустой.")
        if len(points) < 2:
            issues.append(RingIssue("empty_part", f"Участок {number} нулевой длины — удалите его.", points[0]))
        pieces.append(points)
        meta.append((item.kind, item.handle, layer))

    if not pieces:
        return ContourDraft(
            ring=None,
            issues=[RingIssue("too_few_points", "Добавьте участки контура: щёлкните по линиям на чертеже.")],
        )

    oriented: list[list[XY]] = []
    flags: list[bool] = []
    for index, points in enumerate(pieces):
        if index == 0:
            turn = False
            if len(pieces) > 1:
                following = pieces[1]
                keep = min(math.dist(points[-1], following[0]), math.dist(points[-1], following[-1]))
                flip = min(math.dist(points[0], following[0]), math.dist(points[0], following[-1]))
                turn = flip < keep
        else:
            end = oriented[-1][-1]
            turn = math.dist(end, points[-1]) < math.dist(end, points[0])
        if items[index].flip:
            turn = not turn
        oriented.append(list(reversed(points)) if turn else list(points))
        flags.append(turn)

    chain = list(oriented[0])
    gaps: list[tuple[float, str]] = []
    closings: list[tuple[XY, XY]] = []
    for points in oriented[1:]:
        gap = math.dist(chain[-1], points[0])
        if gap <= tolerance_m:
            chain[-1] = _mid(chain[-1], points[0])
            chain.extend(points[1:])
            gaps.append((gap, "joined"))
        else:
            closings.append((chain[-1], points[0]))
            chain.extend(points)
            gaps.append((gap, "closing"))
    gap = math.dist(chain[-1], chain[0])
    if len(chain) > 1 and gap <= tolerance_m:
        chain[0] = _mid(chain[-1], chain[0])
        chain.pop()
        gaps.append((gap, "joined"))
    else:
        if len(chain) > 1:
            closings.append((chain[-1], chain[0]))
        gaps.append((gap, "closing"))

    infos = [
        ItemInfo(kind, handle, layer, polyline_length(points), flag, gap_value, link)
        for (kind, handle, layer), points, flag, (gap_value, link) in zip(meta, pieces, flags, gaps)
    ]
    ring = normalize_ring(chain)
    return ContourDraft(
        ring=ring,
        items=list(items),
        item_info=infos,
        closings=closings,
        issues=[*issues, *check_ring(ring)],
    )


# --- щелчок внутри -------------------------------------------------------


def _cluster_ends(coords: list[list[XY]], closed: list[bool], tolerance_m: float) -> None:
    """Концы открытых линий ближе допуска сводятся в их среднюю точку."""

    ends = [(line, index) for line in range(len(coords)) if not closed[line] for index in (0, -1)]
    parent = list(range(len(ends)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    cell = max(tolerance_m, 1e-6)
    grid: dict[tuple[int, int], list[int]] = {}
    for number, (line, index) in enumerate(ends):
        x, y = coords[line][index]
        grid.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append(number)
    for number, (line, index) in enumerate(ends):
        x, y = coords[line][index]
        cx, cy = math.floor(x / cell), math.floor(y / cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in grid.get((cx + dx, cy + dy), ()):
                    if other > number and math.dist(coords[line][index], coords[ends[other][0]][ends[other][1]]) <= tolerance_m:
                        parent[find(other)] = find(number)

    groups: dict[int, list[int]] = {}
    for number in range(len(ends)):
        groups.setdefault(find(number), []).append(number)
    for members in groups.values():
        if len(members) < 2:
            continue
        xs = [coords[ends[m][0]][ends[m][1]][0] for m in members]
        ys = [coords[ends[m][0]][ends[m][1]][1] for m in members]
        center = (sum(xs) / len(xs), sum(ys) / len(ys))
        for m in members:
            line, index = ends[m]
            coords[line][index] = center


def _segments(geometry) -> list[LineString]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    return [part for item in getattr(geometry, "geoms", []) for part in _segments(item)]


def _bridges(segments: list[LineString], tolerance_m: float, bridge_m: float) -> list[tuple[XY, XY]]:
    """Мосты: висячий конец — к ближайшему висячему концу не дальше `bridge_m`,
    оставшийся — к ближайшей линии не дальше допуска (недотянутый стык «Т»)."""

    degree: Counter[XY] = Counter()
    for segment in segments:
        coords = list(segment.coords)
        degree[coords[0]] += 1
        degree[coords[-1]] += 1
    dangles = [point for point, count in degree.items() if count == 1]

    pairs = sorted(
        (math.dist(a, b), i, j)
        for i, a in enumerate(dangles)
        for j, b in enumerate(dangles)
        if i < j and math.dist(a, b) <= bridge_m
    ) if len(dangles) <= 2000 else []
    used: set[int] = set()
    bridges: list[tuple[XY, XY]] = []
    for _, i, j in pairs:
        if i in used or j in used:
            continue
        used.update((i, j))
        bridges.append((dangles[i], dangles[j]))

    if len(used) < len(dangles):
        tree = shapely.STRtree(segments)
        for index, point in enumerate(dangles):
            if index in used:
                continue
            probe = Point(point)
            best: tuple[float, XY] | None = None
            for candidate in tree.query(probe.buffer(tolerance_m)).tolist():
                segment = segments[candidate]
                coords = list(segment.coords)
                if coords[0] == point or coords[-1] == point:
                    continue
                distance = segment.distance(probe)
                if distance <= tolerance_m and (best is None or distance < best[0]):
                    foot = segment.interpolate(segment.project(probe))
                    best = (distance, (foot.x, foot.y))
            if best is not None and best[0] > _ON_LINE_M:
                bridges.append((point, best[1]))
    return bridges


def click_contour(
    lines: Sequence[CadEntity],
    point: XY,
    tolerance_m: float = DEFAULT_TOLERANCE_M,
    bridge_m: float = DEFAULT_BRIDGE_M,
) -> ContourDraft:
    usable = _usable(lines)
    _check_size(usable)
    outside = RingIssue(
        "outside",
        "Щелчок не внутри замкнутой области: проверьте роли линий контура или увеличьте мост "
        f"(сейчас {ru_number(bridge_m, 1)} м).",
        point,
    )
    if not usable:
        return ContourDraft(
            ring=None,
            issues=[RingIssue("outside", "Нет линий выбранных ролей — отметьте роли линий для контура.", point)],
        )

    frame = LocalFrame.of([*(p for item in usable for p in line_xy(item)), point])
    coords = [frame.to_local(line_xy(item)) for item in usable]
    closed = [item.closed or math.dist(c[0], c[-1]) <= _ON_LINE_M for item, c in zip(usable, coords)]
    _cluster_ends(coords, closed, tolerance_m)
    snapped = [LineString(c) if len(set(c)) > 1 else None for c in coords]
    noded = _segments(shapely.unary_union([line for line in snapped if line is not None]))
    bridges = _bridges(noded, tolerance_m, bridge_m)
    network = shapely.unary_union([*noded, *(LineString(bridge) for bridge in bridges)])
    faces = list(shapely.polygonize(_segments(network)).geoms)
    probe = Point(frame.to_local([point])[0])
    containing = [face for face in faces if face.covers(probe)]
    if not containing:
        return ContourDraft(ring=None, issues=[outside])
    face = min(containing, key=lambda item: item.area)

    exterior = list(face.exterior.coords)[:-1]
    warnings: list[CadWarning] = []
    if face.interiors:
        warnings.append(
            CadWarning(
                code="inner_rings",
                message="Внутри области есть замкнутые линии — контур взят по внешней границе.",
            )
        )
    boundary = face.exterior
    used_bridges = [
        bridge for bridge in bridges if LineString(bridge).distance(boundary) <= _ON_LINE_M
        and boundary.distance(Point(_mid(*bridge))) <= _ON_LINE_M
    ]
    items = _boundary_items(exterior, usable, snapped, used_bridges, frame, tolerance_m)
    ring = normalize_ring(frame.to_world(exterior))
    return ContourDraft(
        ring=ring,
        items=items,
        closings=[(frame.point_to_world(a), frame.point_to_world(b)) for a, b in used_bridges],
        issues=check_ring(ring),
        warnings=warnings,
    )


def _boundary_items(
    exterior: list[XY],
    usable: Sequence[CadEntity],
    snapped: Sequence[LineString | None],
    bridges: Sequence[tuple[XY, XY]],
    frame: LocalFrame,
    tolerance_m: float,
) -> list[ContourItem]:
    """Граница грани — участками линий чертежа и мостами, чтобы её можно было
    править как сборку. Кусок, который не удаётся честно перевести в участок
    линии (например, через шов замкнутой линии), остаётся построенной линией."""

    bridge_lines = [LineString(bridge) for bridge in bridges]
    count = len(exterior)
    sources: list[tuple[str, int]] = []
    for index in range(count):
        middle = Point(_mid(exterior[index], exterior[(index + 1) % count]))
        source: tuple[str, int] = ("polyline", -1)
        for number, bridge in enumerate(bridge_lines):
            if bridge.distance(middle) <= _ON_LINE_M:
                source = ("bridge", number)
                break
        else:
            best = None
            for number, line in enumerate(snapped):
                if line is None:
                    continue
                distance = line.distance(middle)
                if distance <= _ON_LINE_M and (best is None or distance < best[0]):
                    best = (distance, number)
            if best is not None:
                source = ("line", best[1])
        sources.append(source)

    # Серии рёбер одного источника; начало — на смене источника, чтобы серия не рвалась.
    start = next((index for index in range(count) if sources[index] != sources[index - 1]), 0)
    runs: list[tuple[tuple[str, int], list[XY]]] = []
    for step in range(count):
        index = (start + step) % count
        a, b = exterior[index], exterior[(index + 1) % count]
        if runs and runs[-1][0] == sources[index]:
            runs[-1][1].append(b)
        else:
            runs.append((sources[index], [a, b]))

    items: list[ContourItem] = []
    for (kind, number), points in runs:
        world = frame.to_world(points)
        if kind == "bridge":
            items.append(ContourItem(kind="segment", points=[world[0], world[-1]]))
            continue
        if kind == "line":
            entity = usable[number]
            original = line_xy(entity)
            run_length = polyline_length(world)
            if len(runs) == 1 and entity.closed:
                items.append(ContourItem(kind="part", handle=entity.handle, start_m=0.0, end_m=entity.length_m))
                continue
            start_m = project_on_polyline(original, world[0])[0]
            end_m = project_on_polyline(original, world[-1])[0]
            if abs(abs(end_m - start_m) - run_length) <= 2 * tolerance_m + 0.01 * run_length:
                items.append(
                    ContourItem(kind="part", handle=entity.handle, start_m=min(start_m, end_m), end_m=max(start_m, end_m))
                )
                continue
        items.append(ContourItem(kind="polyline", points=world))
    return items


# --- блок по бровке -------------------------------------------------------

# Изломы бровки сглаживаются (§2 «Блок по бровке»): дрожь съёмки до 5 см
# убирается упрощением, углы — круглыми стыками смещения. Упрощение грубее
# сдвигает тыл внутрь: 0,5 м на дуге R = 100 м дали бы +2 % площади, а
# упрощение самого тыла на 0,2 м — ещё +0,6 %.
CREST_SMOOTHING_M = 0.05
BACK_SIMPLIFY_M = 0.05
MIN_CREST_SPAN_M = 1.0


def _side_of(line: LineString, probe: Point) -> float:
    """Знак стороны точки относительно линии: > 0 — слева по ходу, < 0 — справа."""

    m = line.project(probe)
    a = line.interpolate(max(m - 0.5, 0.0))
    b = line.interpolate(min(m + 0.5, line.length))
    foot = line.interpolate(m)
    return (b.x - a.x) * (probe.y - foot.y) - (b.y - a.y) * (probe.x - foot.x)


def crest_block(
    top: Sequence[StitchedLine],
    bottom: Sequence[StitchedLine],
    lines: Mapping[str, CadEntity],
    start: XY,
    end: XY,
    width_m: float,
    side: str = "auto",
    tolerance_m: float = DEFAULT_TOLERANCE_M,
) -> ContourDraft:
    """Блок по верхней бровке: начало, конец и ширина (§2, способ 4).

    Тыл — смещение участка бровки на ширину в сторону от нижней бровки,
    фланги — по нормали к бровке в концах участка. Результат — обычная
    сборка: участки бровки, два отрезка-фланга и построенный тыл.
    """

    if width_m <= 0:
        raise ContourInputError("Ширина блока должна быть больше нуля.")
    if not top:
        return ContourDraft(
            ring=None,
            issues=[RingIssue("not_on_crest", "Верхней бровки нет — блок по бровке строится только по ней.")],
        )

    best: tuple[float, StitchedLine, float, float] | None = None
    for candidate in top:
        xy = [(point[0], point[1]) for point in candidate.points]
        m_start, _, d_start = project_on_polyline(xy, start)
        m_end, _, d_end = project_on_polyline(xy, end)
        worst = max(d_start, d_end)
        if best is None or worst < best[0]:
            best = (worst, candidate, m_start, m_end)
    assert best is not None
    worst, chain, m_start, m_end = best
    if worst > tolerance_m:
        return ContourDraft(
            ring=None,
            issues=[
                RingIssue(
                    "not_on_crest",
                    "Начало и конец блока должны лежать на одной верхней бровке "
                    f"(не дальше {ru_number(tolerance_m, 2)} м от неё).",
                    start,
                )
            ],
        )
    if abs(m_end - m_start) < MIN_CREST_SPAN_M:
        return ContourDraft(
            ring=None,
            issues=[RingIssue("not_on_crest", "Начало и конец блока на бровке слишком близко.", start)],
        )

    chain_xy = [(point[0], point[1]) for point in chain.points]
    frame = LocalFrame.of(chain_xy)
    sub = cut_polyline(chain_xy, m_start, m_end)
    if m_start > m_end:
        sub.reverse()
    sub_line = LineString(frame.to_local(sub))

    if side == "auto":
        bottoms = [LineString(frame.to_local([(p[0], p[1]) for p in line.points])) for line in bottom]
        if not bottoms:
            return ContourDraft(
                ring=None,
                issues=[
                    RingIssue(
                        "side_required",
                        "Нижней бровки нет — укажите сторону блока: слева или справа по ходу от начала к концу.",
                        start,
                    )
                ],
            )
        union = shapely.unary_union(bottoms)
        votes = 0.0
        for fraction in (0.25, 0.5, 0.75):
            probe = sub_line.interpolate(fraction, normalized=True)
            nearest = shapely.ops.nearest_points(probe, union)[1]
            votes += math.copysign(1.0, _side_of(sub_line, nearest))
        # Блок — по другую сторону бровки от нижней бровки (там откос).
        side = "right" if votes > 0 else "left"
    if side not in ("left", "right"):
        raise ContourInputError(f"Сторона блока «{side}» неизвестна.")

    smooth = sub_line.simplify(CREST_SMOOTHING_M)
    back_geometry = smooth.offset_curve(width_m if side == "left" else -width_m, quad_segs=4, join_style="round")
    if back_geometry.geom_type != "LineString":
        merged = shapely.line_merge(back_geometry)
        back_geometry = max(_segments(merged), key=lambda item: item.length)
    back = list(back_geometry.simplify(BACK_SIMPLIFY_M).coords)
    smooth_start = smooth.coords[0]
    if math.dist(back[-1], smooth_start) < math.dist(back[0], smooth_start):
        back.reverse()
    back_world = frame.to_world(back)

    items = _crest_parts(chain, m_start, m_end)
    items.append(ContourItem(kind="segment", points=[sub[-1], back_world[-1]], label="Фланг"))
    items.append(ContourItem(kind="polyline", points=list(reversed(back_world)), label="Тыл"))
    items.append(ContourItem(kind="segment", points=[back_world[0], sub[0]], label="Фланг"))
    draft = assemble(items, lines, tolerance_m)
    draft.crest_line = sub
    return draft


def _crest_parts(chain: StitchedLine, m_start: float, m_end: float) -> list[ContourItem]:
    """Участок сшитой бровки — участками её фрагментов, от начала к концу блока."""

    low, high = sorted((m_start, m_end))
    items: list[ContourItem] = []
    for part in chain.parts:
        part_low, part_high = part.chain_start_m, part.chain_start_m + part.length_m
        overlap_low, overlap_high = max(low, part_low), min(high, part_high)
        if overlap_high - overlap_low <= 1e-6:
            continue
        a, b = part.entity_m(overlap_low), part.entity_m(overlap_high)
        items.append(ContourItem(kind="part", handle=part.handle, start_m=min(a, b), end_m=max(a, b)))
    if m_start > m_end:
        items.reverse()
    return items
