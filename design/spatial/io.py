"""Импорт съёмки уступа: XYZ, CSV, DXF (точки и полилинии), GeoJSON."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from statistics import median
from typing import Iterable

from design.models import Point3

SUPPORTED_FORMATS = ("xyz", "csv", "dxf", "geojson")


class SurveyImportError(ValueError):
    """Файл съёмки не удалось разобрать."""


@dataclass
class BenchDxfImport:
    """Named 3D crest/toe polylines extracted from an ASCII DXF drawing."""

    crest: list[Point3]
    toe: list[Point3]
    crest_layer: str
    toe_layer: str

    @property
    def contour(self) -> list[Point3]:
        return _clean_polyline([*self.crest, *reversed(self.toe)])

    @property
    def crest_z_m(self) -> float:
        return float(median(point.z for point in self.crest))

    @property
    def toe_z_m(self) -> float:
        return float(median(point.z for point in self.toe))


@dataclass
class SurveyImport:
    points: list[Point3]
    polylines: list[list[Point3]]
    source_format: str
    source_name: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.points and not self.polylines


def detect_format(filename: str = "", content: str = "") -> str:
    name = (filename or "").lower()
    if name.endswith(".xyz") or name.endswith(".txt"):
        return "xyz"
    if name.endswith(".csv"):
        return "csv"
    if name.endswith(".dxf"):
        return "dxf"
    if name.endswith(".geojson") or name.endswith(".json"):
        return "geojson"
    stripped = (content or "").lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "geojson"
    head = stripped[:4000]
    if "SECTION" in head or re.match(r"^\s*0\s*\n", stripped):
        return "dxf"
    first = next((line for line in stripped.splitlines() if line.strip()), "")
    if "," in first and not _looks_like_xyz_row(first):
        return "csv"
    return "xyz"


def import_survey(
    content: str,
    *,
    filename: str = "",
    format: str | None = None,
) -> SurveyImport:
    """Разбирает текстовую съёмку. Бинарный DXF отвергается явно."""
    if not content or not content.strip():
        raise SurveyImportError("Файл съёмки пуст.")
    if "\x00" in content[:200]:
        raise SurveyImportError("Бинарный DXF не поддерживается — сохраните чертёж в ASCII DXF.")
    fmt = (format or detect_format(filename, content)).lower()
    if fmt == "txt":
        fmt = "xyz"
    if fmt == "json":
        fmt = "geojson"
    if fmt not in SUPPORTED_FORMATS:
        raise SurveyImportError(f"Формат «{fmt}» не поддерживается. Допустимы: XYZ, CSV, DXF, GeoJSON.")
    if fmt == "xyz":
        points, lines = _parse_xyz(content)
    elif fmt == "csv":
        points, lines = _parse_csv(content)
    elif fmt == "dxf":
        points, lines = _parse_dxf(content)
    else:
        points, lines = _parse_geojson(content)
    if not points and not lines:
        raise SurveyImportError("В файле нет точек или полилиний с координатами.")
    return SurveyImport(
        points=_dedup_points(points),
        polylines=lines,
        source_format=fmt,
        source_name=filename,
    )


def build_bench_from_polylines(
    crest: list[Point3],
    toe: list[Point3],
    crest_layer: str = "",
    toe_layer: str = "",
) -> BenchDxfImport:
    """Собирает уступ из двух явно указанных бровок.

    Проверки те же, что и при автоматическом импорте: инженер выбирает линии
    руками, но ошибиться местами верх/низ или взять незамкнутую мелочь может
    так же легко, поэтому геометрия проверяется одинаково.
    """

    result = BenchDxfImport(
        crest=_clean_polyline(crest), toe=_clean_polyline(toe),
        crest_layer=crest_layer, toe_layer=toe_layer,
    )
    if len(result.crest) < 2 or len(result.toe) < 2:
        raise SurveyImportError("Каждая бровка должна содержать минимум две разные точки.")
    if len(result.contour) < 3 or abs(_polygon_area(result.contour)) < 0.01:
        raise SurveyImportError("Выбранные бровки не образуют площадь блока в плане.")
    if result.crest_z_m <= result.toe_z_m:
        raise SurveyImportError(
            "Отметка верхней бровки должна быть выше нижней — возможно, линии перепутаны местами."
        )
    return result


def import_bench_dxf(content: str) -> BenchDxfImport:
    """Extract the crest and toe polylines of a surveyed block from ASCII DXF.

    DXF drawings often include labels and survey points.  This importer uses
    only 3D/LW polylines with an explicit engineering layer name; it therefore
    never silently turns arbitrary text or point clouds into a blast contour.
    """

    if not content or not content.strip() or "\x00" in content[:200]:
        raise SurveyImportError("Для импорта блока нужен непустой ASCII DXF.")
    records = _dxf_layered_polylines(content)
    crest_candidates = [(layer, points) for layer, points in records if _is_crest_layer(layer)]
    toe_candidates = [(layer, points) for layer, points in records if _is_toe_layer(layer)]
    if not crest_candidates or not toe_candidates:
        available = ", ".join(sorted({layer for layer, _ in records if layer})) or "нет"
        raise SurveyImportError(
            "Не найдены слои верхней и нижней бровки. "
            f"Ожидались имена с «верх/crest/top» и «ниж/toe/floor/подошв»; найдены: {available}."
        )
    crest_layer, crest = max(crest_candidates, key=lambda item: len(item[1]))
    toe_layer, toe = max(toe_candidates, key=lambda item: len(item[1]))
    result = BenchDxfImport(crest=_clean_polyline(crest), toe=_clean_polyline(toe), crest_layer=crest_layer, toe_layer=toe_layer)
    if len(result.crest) < 2 or len(result.toe) < 2 or len(result.contour) < 3:
        raise SurveyImportError("Бровки должны содержать минимум по две разные точки.")
    if abs(_polygon_area(result.contour)) < 0.01:
        raise SurveyImportError("Бровки не образуют площадь блока в плане. Проверьте порядок точек в DXF.")
    if result.crest_z_m <= result.toe_z_m:
        raise SurveyImportError("Отметка верхней бровки должна быть выше нижней. Проверьте выбранные слои.")
    return result


def _looks_like_xyz_row(line: str) -> bool:
    parts = re.split(r"[\s,;]+", line.strip())
    if len(parts) < 3:
        return False
    try:
        float(parts[0].replace(",", "."))
        float(parts[1].replace(",", "."))
        float(parts[2].replace(",", "."))
    except ValueError:
        return False
    return True


def _parse_number(raw: str) -> float:
    return float(raw.strip().replace(" ", "").replace(",", "."))


def _dedup_points(points: Iterable[Point3]) -> list[Point3]:
    seen: dict[tuple[int, int, int], Point3] = {}
    for point in points:
        key = (round(point.x * 1e4), round(point.y * 1e4), round(point.z * 1e4))
        seen[key] = point
    return list(seen.values())


def _parse_xyz(content: str) -> tuple[list[Point3], list[list[Point3]]]:
    points: list[Point3] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if not _looks_like_xyz_row(line):
            continue
        parts = re.split(r"[\s,;]+", line)
        points.append(Point3(x=_parse_number(parts[0]), y=_parse_number(parts[1]), z=_parse_number(parts[2])))
    return points, []


_X_NAMES = {"x", "east", "easting", "east_m", "x_m", "lon", "longitude"}
_Y_NAMES = {"y", "north", "northing", "north_m", "y_m", "lat", "latitude"}
_Z_NAMES = {"z", "elev", "elevation", "height", "z_m", "rl", "level", "h"}


def _parse_csv(content: str) -> tuple[list[Point3], list[list[Point3]]]:
    sample = "\n".join(content.splitlines()[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t ")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(content), dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [], []
    header = [cell.strip().lower() for cell in rows[0]]
    xi = yi = zi = None
    if any(name in _X_NAMES or name in _Y_NAMES or name in _Z_NAMES for name in header):
        for i, name in enumerate(header):
            if xi is None and name in _X_NAMES:
                xi = i
            elif yi is None and name in _Y_NAMES:
                yi = i
            elif zi is None and name in _Z_NAMES:
                zi = i
        data_rows = rows[1:]
    else:
        xi, yi, zi = 0, 1, 2 if len(rows[0]) >= 3 else None
        data_rows = rows
        # Если первая строка не числа — это заголовок без известных имён.
        try:
            _parse_number(rows[0][0])
            _parse_number(rows[0][1])
        except (ValueError, IndexError):
            data_rows = rows[1:]
    if xi is None or yi is None:
        raise SurveyImportError("В CSV не найдены колонки X/Y (или easting/northing).")
    points: list[Point3] = []
    for row in data_rows:
        if max(xi, yi, zi or 0) >= len(row):
            continue
        try:
            x = _parse_number(row[xi])
            y = _parse_number(row[yi])
            z = _parse_number(row[zi]) if zi is not None and zi < len(row) and row[zi].strip() else 0.0
        except ValueError:
            continue
        points.append(Point3(x=x, y=y, z=z))
    return points, []


def _dxf_groups(content: str) -> list[tuple[int, str]]:
    lines = [line.rstrip("\r") for line in content.splitlines()]
    groups: list[tuple[int, str]] = []
    i = 0
    while i + 1 < len(lines):
        code_raw = lines[i].strip()
        value = lines[i + 1]
        try:
            code = int(code_raw)
        except ValueError:
            i += 1
            continue
        groups.append((code, value))
        i += 2
    return groups


def _dxf_layered_polylines(content: str) -> list[tuple[str, list[Point3]]]:
    """Read POLYLINE/LWPOLYLINE entities and preserve their layer names."""

    groups = _dxf_groups(content)
    in_entities = False
    entity = ""
    layer = ""
    records: list[tuple[str, list[Point3]]] = []
    poly_points: list[Point3] = []
    vertex: dict[int, str] = {}
    lw_points: list[Point3] = []
    lw_elevation = 0.0

    def flush_vertex() -> None:
        nonlocal vertex
        point = _point_from_dxf(vertex, 10, 20, 30)
        if point is not None:
            poly_points.append(point)
        vertex = {}

    def flush_poly() -> None:
        nonlocal poly_points, lw_points, lw_elevation
        points = poly_points if poly_points else [
            Point3(point.x, point.y, point.z if point.z else lw_elevation) for point in lw_points
        ]
        if len(points) >= 2:
            records.append((layer, _clean_polyline(points)))
        poly_points, lw_points, lw_elevation = [], [], 0.0

    for code, raw in groups:
        value = raw.strip()
        if code == 0:
            name = value.upper()
            if name == "SECTION":
                entity = "SECTION"
                continue
            if name == "ENDSEC":
                if entity in {"POLYLINE", "LWPOLYLINE"}:
                    flush_poly()
                in_entities, entity = False, ""
                continue
            if not in_entities:
                entity = name
                continue
            if entity == "VERTEX":
                flush_vertex()
            if name == "SEQEND":
                if entity in {"VERTEX", "POLYLINE"}:
                    flush_poly()
                entity = ""
                continue
            if entity == "LWPOLYLINE":
                flush_poly()
            entity = name
            if name in {"POLYLINE", "LWPOLYLINE"}:
                layer, poly_points, lw_points, lw_elevation = "", [], [], 0.0
            continue
        if code == 2 and entity == "SECTION" and value.upper() == "ENTITIES":
            in_entities, entity = True, ""
            continue
        if not in_entities:
            continue
        if code == 8 and entity in {"POLYLINE", "LWPOLYLINE"}:
            layer = value
        elif entity == "VERTEX" and code in {10, 20, 30}:
            vertex[code] = value
        elif entity == "LWPOLYLINE":
            if code == 10:
                lw_points.append(Point3(_safe_float(value), 0.0, 0.0))
            elif code == 20 and lw_points:
                point = lw_points[-1]
                lw_points[-1] = Point3(point.x, _safe_float(value), point.z)
            elif code == 30 and lw_points:
                point = lw_points[-1]
                lw_points[-1] = Point3(point.x, point.y, _safe_float(value))
            elif code == 38:
                lw_elevation = _safe_float(value)
    if entity == "VERTEX":
        flush_vertex()
    if entity in {"POLYLINE", "LWPOLYLINE", "VERTEX"}:
        flush_poly()
    return records


def _clean_polyline(points: Iterable[Point3]) -> list[Point3]:
    clean: list[Point3] = []
    for point in points:
        if not clean or (abs(clean[-1].x - point.x) > 1e-7 or abs(clean[-1].y - point.y) > 1e-7):
            clean.append(Point3(point.x, point.y, point.z))
    if len(clean) > 2 and abs(clean[0].x - clean[-1].x) < 1e-7 and abs(clean[0].y - clean[-1].y) < 1e-7:
        clean.pop()
    return clean


def _polygon_area(points: list[Point3]) -> float:
    return 0.5 * sum(point.x * points[(index + 1) % len(points)].y - point.y * points[(index + 1) % len(points)].x for index, point in enumerate(points))


def _is_crest_layer(layer: str) -> bool:
    value = layer.casefold()
    return any(token in value for token in ("верх", "crest", "top"))


def _is_toe_layer(layer: str) -> bool:
    value = layer.casefold()
    return any(token in value for token in ("ниж", "toe", "floor", "подошв"))


def _parse_dxf(content: str) -> tuple[list[Point3], list[list[Point3]]]:
    groups = _dxf_groups(content)
    if not groups:
        raise SurveyImportError("Не удалось прочитать группы ASCII DXF.")
    points: list[Point3] = []
    polylines: list[list[Point3]] = []
    in_entities = False
    entity = ""
    fields: dict[int, str] = {}
    lw_points: list[Point3] = []
    lw_elev = 0.0
    lw_closed = False
    current_poly: list[Point3] = []
    in_poly = False

    def flush_simple() -> None:
        nonlocal entity, fields
        if entity == "POINT":
            point = _point_from_dxf(fields, 10, 20, 30)
            if point:
                points.append(point)
        elif entity == "LINE":
            a = _point_from_dxf(fields, 10, 20, 30)
            b = _point_from_dxf(fields, 11, 21, 31)
            if a and b:
                polylines.append([a, b])
                points.extend([a, b])
        entity = ""
        fields = {}

    def flush_lw() -> None:
        nonlocal lw_points, lw_elev, lw_closed
        if lw_points:
            line = [
                Point3(x=p.x, y=p.y, z=p.z if p.z else lw_elev) for p in lw_points
            ]
            if lw_closed and len(line) >= 2 and (line[0].x, line[0].y) != (line[-1].x, line[-1].y):
                line.append(Point3(x=line[0].x, y=line[0].y, z=line[0].z))
            polylines.append(line)
            points.extend(line)
        lw_points = []
        lw_elev = 0.0
        lw_closed = False

    def flush_poly() -> None:
        nonlocal current_poly, in_poly
        if current_poly:
            polylines.append(list(current_poly))
            points.extend(current_poly)
        current_poly = []
        in_poly = False

    for code, value in groups:
        if code == 0:
            name = value.strip().upper()
            if name == "SECTION":
                flush_simple()
                entity = "SECTION"
                continue
            if name == "ENDSEC":
                flush_simple()
                flush_lw()
                flush_poly()
                in_entities = False
                continue
            if in_entities:
                if entity == "LWPOLYLINE":
                    flush_lw()
                elif entity in {"POINT", "LINE"}:
                    flush_simple()
                if name == "SEQEND":
                    flush_poly()
                    entity = ""
                    continue
                entity = name
                fields = {}
                if name == "POLYLINE":
                    in_poly = True
                    current_poly = []
                continue
            entity = name
            continue
        if code == 2 and entity == "SECTION" and value.strip().upper() == "ENTITIES":
            in_entities = True
            entity = ""
            continue
        if not in_entities:
            continue
        if entity == "LWPOLYLINE":
            if code == 10:
                lw_points.append(Point3(x=_safe_float(value), y=0.0, z=0.0))
            elif code == 20 and lw_points:
                last = lw_points[-1]
                lw_points[-1] = Point3(x=last.x, y=_safe_float(value), z=last.z)
            elif code == 30 and lw_points:
                last = lw_points[-1]
                lw_points[-1] = Point3(x=last.x, y=last.y, z=_safe_float(value))
            elif code == 38:
                lw_elev = _safe_float(value)
            elif code == 70:
                try:
                    lw_closed = bool(int(float(value.strip() or "0")) & 1)
                except ValueError:
                    lw_closed = False
            continue
        if entity == "VERTEX" and in_poly:
            if code in {10, 20, 30}:
                fields[code] = value
            if code == 30:
                point = _point_from_dxf(fields, 10, 20, 30)
                if point:
                    current_poly.append(point)
                fields = {}
            continue
        if code in {10, 20, 30, 11, 21, 31}:
            fields[code] = value

    if entity == "LWPOLYLINE":
        flush_lw()
    elif entity in {"POINT", "LINE"}:
        flush_simple()
    if in_poly:
        flush_poly()
    return points, polylines


def _safe_float(raw: str) -> float:
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError:
        return 0.0


def _point_from_dxf(fields: dict[int, str], x_code: int, y_code: int, z_code: int) -> Point3 | None:
    if x_code not in fields or y_code not in fields:
        return None
    return Point3(
        x=_safe_float(fields[x_code]),
        y=_safe_float(fields[y_code]),
        z=_safe_float(fields.get(z_code, "0")),
    )


def _parse_geojson(content: str) -> tuple[list[Point3], list[list[Point3]]]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SurveyImportError(f"Некорректный GeoJSON: {exc}") from exc
    points: list[Point3] = []
    polylines: list[list[Point3]] = []

    def walk(geom: object) -> None:
        if not isinstance(geom, dict):
            return
        gtype = str(geom.get("type") or "")
        if gtype == "Feature":
            walk(geom.get("geometry"))
            return
        if gtype == "FeatureCollection":
            for feature in geom.get("features", []):
                walk(feature)
            return
        if gtype == "GeometryCollection":
            for child in geom.get("geometries", []):
                walk(child)
            return
        coords = geom.get("coordinates")
        if gtype == "Point":
            point = _coord_point(coords)
            if point:
                points.append(point)
        elif gtype == "MultiPoint":
            for item in coords or []:
                point = _coord_point(item)
                if point:
                    points.append(point)
        elif gtype == "LineString":
            line = [_coord_point(item) for item in coords or []]
            line_ok = [p for p in line if p]
            if line_ok:
                polylines.append(line_ok)
                points.extend(line_ok)
        elif gtype == "MultiLineString":
            for part in coords or []:
                walk({"type": "LineString", "coordinates": part})
        elif gtype == "Polygon":
            rings = coords or []
            if rings:
                walk({"type": "LineString", "coordinates": rings[0]})
        elif gtype == "MultiPolygon":
            for polygon in coords or []:
                walk({"type": "Polygon", "coordinates": polygon})

    walk(data)
    return points, polylines


def _coord_point(coords: object) -> Point3 | None:
    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
        return None
    try:
        x = float(coords[0])
        y = float(coords[1])
        z = float(coords[2]) if len(coords) > 2 else 0.0
    except (TypeError, ValueError):
        return None
    return Point3(x=x, y=y, z=z)
