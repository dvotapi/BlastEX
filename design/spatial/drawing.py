"""Разбор чертежа блока на полилинии.

Штатный импорт (`io.import_bench_dxf`) сам угадывает бровки по именам слоёв и
работает только с ASCII DXF. Здесь задача другая: показать инженеру всё, что
есть в чертеже, и дать выбрать бровки руками. Поэтому чтение отдано ezdxf —
он понимает ASCII и бинарный DXF, дуги, сплайны и вставки блоков, — а DWG
предварительно прогоняется через внешний конвертер.
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field

from design.models import Point3
from design.spatial.dwg import DwgConversionError, dwg_to_dxf

__all__ = ["DrawingError", "DrawingPolyline", "DrawingScan", "read_drawing"]

# Сколько объектов и точек отдаём в интерфейс: чертёж карьера легко содержит
# десятки тысяч примитивов, но выбирать бровки инженер будет из десятков.
MAX_POLYLINES = 400
MAX_POINTS_PER_POLYLINE = 2000
MIN_POINTS = 2
# Допуск склейки отрезков LINE в цепочку, м. Съёмка приходит с округлением,
# поэтому «тот же узел» — это не строгое равенство координат.
CHAIN_TOLERANCE_M = 0.01
# Спрямление дуг и сплайнов: максимальное отклонение хорды от кривой, м.
CURVE_SAGITTA_M = 0.05

POLYLINE_TYPES = frozenset({"LWPOLYLINE", "POLYLINE", "SPLINE", "ARC", "CIRCLE", "ELLIPSE"})


class DrawingError(Exception):
    """Чертёж не удалось разобрать."""


@dataclass
class DrawingPolyline:
    """Одна линия чертежа в мировых координатах."""

    id: str
    layer: str
    points: list[Point3]
    closed: bool
    entity: str = ""

    @property
    def length_m(self) -> float:
        total = 0.0
        for a, b in zip(self.points, self.points[1:]):
            total += math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
        if self.closed and len(self.points) > 2:
            a, b = self.points[-1], self.points[0]
            total += math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
        return total

    @property
    def z_min(self) -> float:
        return min(point.z for point in self.points)

    @property
    def z_max(self) -> float:
        return max(point.z for point in self.points)

    @property
    def area_m2(self) -> float:
        """Площадь в плане для замкнутой линии, иначе 0."""

        if not self.closed or len(self.points) < 3:
            return 0.0
        total = 0.0
        for a, b in zip(self.points, [*self.points[1:], self.points[0]]):
            total += a.x * b.y - b.x * a.y
        return abs(total) / 2


@dataclass
class DrawingScan:
    polylines: list[DrawingPolyline] = field(default_factory=list)
    source_format: str = "dxf"
    source_name: str = ""
    converted_from: str = ""
    truncated: bool = False


def read_drawing(data: bytes, filename: str = "") -> DrawingScan:
    """Читает DXF или DWG и возвращает найденные полилинии."""

    if not data or not data.strip():
        raise DrawingError("Файл пустой. Загрузите чертёж DXF или DWG.")

    converted_from = ""
    if _is_dwg(data, filename):
        try:
            data = dwg_to_dxf(data, filename or "drawing.dwg")
        except DwgConversionError as exc:
            raise DrawingError(str(exc)) from exc
        converted_from = "dwg"

    doc = _read_dxf(data)
    records = _collect(doc)
    lines = [item for item in records if item.entity == "LINE"]
    others = [item for item in records if item.entity != "LINE"]
    polylines = others + _join_line_chains(lines)
    if not polylines:
        raise DrawingError(
            "В чертеже нет полилиний. Нужны бровки как LWPOLYLINE / 3D-полилиния "
            "или как цепочка отрезков; текст и точки контуром не считаются."
        )

    polylines.sort(key=lambda item: item.length_m, reverse=True)
    truncated = len(polylines) > MAX_POLYLINES
    return DrawingScan(
        polylines=polylines[:MAX_POLYLINES],
        source_format="dxf",
        source_name=filename,
        converted_from=converted_from,
        truncated=truncated,
    )


def _is_dwg(data: bytes, filename: str) -> bool:
    if filename.lower().endswith(".dwg"):
        return True
    # Сигнатура DWG: "AC" + версия в первых байтах, при этом это не DXF-тег.
    return data[:2] == b"AC" and b"SECTION" not in data[:512]


def _read_dxf(data: bytes):
    """Читает DXF из байтов.

    `readfile` понимает и ASCII, и бинарный DXF, но требует файл; `recover`
    вытягивает битые ASCII-чертежи, которых в реальных выгрузках хватает.
    """

    import ezdxf
    from ezdxf import recover

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as handle:
        handle.write(data)
        path = handle.name
    try:
        try:
            return ezdxf.readfile(path)
        except Exception:
            doc, _auditor = recover.readfile(path)
            return doc
    except Exception as exc:  # ezdxf поднимает свои классы ошибок на любой мусор
        raise DrawingError(f"Не удалось прочитать DXF: {exc}") from exc
    finally:
        os.unlink(path)


def _collect(doc) -> list[DrawingPolyline]:
    records: list[DrawingPolyline] = []
    for entity in doc.modelspace():
        _append_entity(entity, records)
    return records


def _append_entity(entity, records: list[DrawingPolyline]) -> None:
    kind = entity.dxftype()
    if kind == "INSERT":
        # Вставка блока: разворачиваем в мировые координаты, иначе бровка,
        # начерченная внутри блока, потеряется или уедет на нулевую точку.
        try:
            for virtual in entity.virtual_entities():
                _append_entity(virtual, records)
        except Exception:  # повреждённая вставка не должна ронять весь импорт
            return
        return

    if kind == "LINE":
        start, end = entity.dxf.start, entity.dxf.end
        _push(records, entity, [_point(start), _point(end)], closed=False)
        return

    if kind not in POLYLINE_TYPES:
        return

    points, closed = _entity_points(entity, kind)
    _push(records, entity, points, closed)


def _entity_points(entity, kind: str) -> tuple[list[Point3], bool]:
    if kind == "LWPOLYLINE":
        return [_point(v) for v in entity.vertices_in_wcs()], bool(entity.closed)
    if kind == "POLYLINE":
        return [_point(v.dxf.location) for v in entity.vertices], bool(entity.is_closed)
    if kind == "SPLINE":
        return [_point(v) for v in entity.flattening(CURVE_SAGITTA_M)], bool(entity.closed)
    # ARC / CIRCLE / ELLIPSE
    return [_point(v) for v in entity.flattening(CURVE_SAGITTA_M)], kind in {"CIRCLE", "ELLIPSE"}


def _push(records: list[DrawingPolyline], entity, points: list[Point3], closed: bool) -> None:
    cleaned = _dedup(points)
    if len(cleaned) < MIN_POINTS:
        return
    if len(cleaned) > MAX_POINTS_PER_POLYLINE:
        cleaned = _decimate(cleaned, MAX_POINTS_PER_POLYLINE)
    records.append(DrawingPolyline(
        id=f"e{len(records) + 1}",
        layer=str(entity.dxf.layer or ""),
        points=cleaned,
        closed=closed,
        entity=entity.dxftype(),
    ))


def _point(value) -> Point3:
    x, y, z = float(value[0]), float(value[1]), float(value[2]) if len(value) > 2 else 0.0
    return Point3(x=x, y=y, z=z)


def _dedup(points: list[Point3]) -> list[Point3]:
    result: list[Point3] = []
    for point in points:
        if result and _same(result[-1], point):
            continue
        result.append(point)
    # Замкнутая линия часто дублирует первую точку в конце — она не нужна.
    if len(result) > 2 and _same(result[0], result[-1]):
        result.pop()
    return result


def _same(a: Point3, b: Point3) -> bool:
    return abs(a.x - b.x) <= CHAIN_TOLERANCE_M and abs(a.y - b.y) <= CHAIN_TOLERANCE_M and abs(a.z - b.z) <= CHAIN_TOLERANCE_M


def _decimate(points: list[Point3], limit: int) -> list[Point3]:
    step = len(points) / limit
    kept = [points[int(i * step)] for i in range(limit - 1)]
    kept.append(points[-1])
    return kept


def _join_line_chains(lines: list[DrawingPolyline]) -> list[DrawingPolyline]:
    """Склеивает отрезки LINE одного слоя в непрерывные цепочки.

    Съёмку нередко отдают россыпью отрезков; без склейки инженер получил бы
    список из сотен двухточечных «полилиний», в котором бровку не найти.
    """

    by_layer: dict[str, list[DrawingPolyline]] = {}
    for line in lines:
        by_layer.setdefault(line.layer, []).append(line)

    chains: list[DrawingPolyline] = []
    for layer, items in by_layer.items():
        pending = [list(item.points) for item in items]
        while pending:
            chain = pending.pop(0)
            merged = True
            while merged:
                merged = False
                for index, candidate in enumerate(pending):
                    if _same(chain[-1], candidate[0]):
                        chain.extend(candidate[1:])
                    elif _same(chain[-1], candidate[-1]):
                        chain.extend(list(reversed(candidate))[1:])
                    elif _same(chain[0], candidate[-1]):
                        chain[:0] = candidate[:-1]
                    elif _same(chain[0], candidate[0]):
                        chain[:0] = list(reversed(candidate))[:-1]
                    else:
                        continue
                    pending.pop(index)
                    merged = True
                    break
            closed = len(chain) > 3 and _same(chain[0], chain[-1])
            if closed:
                chain.pop()
            chains.append(DrawingPolyline(
                id=f"c{len(chains) + 1}",
                layer=layer,
                points=chain,
                closed=closed,
                entity="LINE",
            ))
    return chains
