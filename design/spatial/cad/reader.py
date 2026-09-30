"""Чтение чертежа маркшейдера: все сущности пространства модели.

В отличие от прежнего выбора двух бровок, импорт читает всё, что прислал
маркшейдер: линии (с дугами и сплайнами), точки, условные знаки и подписи.
У каждой сущности — handle, слой, тип, замкнутость, вид Z и цвет, чтобы
роли можно было назначить слою и переопределить у отдельной сущности.

DWG конвертируется `dwg2dxf` в полный DXF: только в нём есть `$INSUNITS` и
таблица слоёв с цветами. Если ezdxf полный вывод не читает, берётся
минимальный DXF (`-m`) с предупреждением.
"""
from __future__ import annotations

import hashlib
import math
import os
import tempfile
from collections import Counter
from dataclasses import dataclass
from itertools import islice

from design.spatial.cad.labels import attach_labels, parse_elevation
from design.spatial.cad.model import (
    CadDrawing,
    CadEntity,
    CadWarning,
    Point,
    ru_number,
)
from design.spatial.cad.units import detect_units
from design.spatial.dwg import DwgConversionError, dwg_to_dxf

__all__ = ["CadReadError", "ReadOptions", "read_cad"]

# Допуск замыкания по разрыву концов, м (§2: допуск по умолчанию 0,5 м).
CLOSURE_TOLERANCE_M = 0.5
# Разрыв больше этой доли длины линии — не замыкание, а незамкнутая линия.
CLOSURE_MAX_GAP_SHARE = 0.05
# Вершины ближе этого расстояния — дубль (съёмка приходит с округлением).
DUPLICATE_TOLERANCE_M = 0.001
# Спрямление дуг и сплайнов: наибольшее отклонение хорды от кривой, м.
CURVE_SAGITTA_M = 0.05
# Вставка блока не больше этого размера — условный знак точки, а не объект.
SIGN_BLOCK_SIZE_M = 5.0
# Пределы одного файла: больше — ошибка с числами, а не молчаливая обрезка.
MAX_ENTITIES = 50_000
MAX_VERTICES = 1_000_000
# Обход с учётом вставок блоков и нечитаемых объектов: MINSERT или блок из
# одних штриховок не должны занимать сервер часами, ничего не добавив.
VISIT_BUDGET_FACTOR = 5
# Handle — ключ хранения (`cad_entities.handle`, до 64 символов). Handle
# вложенных вставок `H/1/2/…` длиннее сжимаются с хэшем — уникальность та же.
MAX_HANDLE_LENGTH = 64

_CURVE_KINDS = frozenset({"ARC", "CIRCLE", "ELLIPSE", "SPLINE"})
_BY_LAYER, _BY_BLOCK = 256, 0


class CadReadError(Exception):
    """Чертёж не удалось прочитать; текст — для пользователя."""


@dataclass(frozen=True)
class ReadOptions:
    scale: float = 1.0
    label_radius_m: float = 3.0
    closure_tolerance_m: float = CLOSURE_TOLERANCE_M


def read_cad(data: bytes, filename: str = "", options: ReadOptions | None = None) -> CadDrawing:
    """Читает DXF или DWG и возвращает все сущности пространства модели."""

    options = options or ReadOptions()
    if not data or not data.strip():
        raise CadReadError("Файл пустой. Загрузите чертёж DXF или DWG.")

    source_format = "dxf"
    minimal = False
    if _is_dwg(data, filename):
        source_format = "dwg"
        doc, minimal = _load_dwg(data, filename or "drawing.dwg")
    else:
        doc = _load_dxf(data)

    collector = _Collector(doc, options)
    collector.collect()
    entities = collector.entities
    if not entities:
        if collector.skipped:
            listed = ", ".join(f"{kind} × {count}" for kind, count in sorted(collector.skipped.items()))
            raise CadReadError(f"В чертеже нет объектов, которые читает импорт: {listed}.")
        raise CadReadError("В чертеже нет объектов: пространство модели пустое.")

    attach_labels(entities, options.label_radius_m)

    insunits = None if minimal else _header_int(doc, "$INSUNITS")
    extent = _extent(entities)
    suggested_scale, unit_warnings = detect_units(insunits, extent)
    if options.scale != 1.0:
        # Масштаб уже применён — предлагать его снова незачем.
        suggested_scale = None
        unit_warnings = [
            CadWarning(
                code="units_scaled",
                message=f"Координаты умножены на {ru_number(options.scale, 3)}.",
                level="info",
            )
        ]

    warnings: list[CadWarning] = []
    if minimal:
        warnings.append(
            CadWarning(
                code="minimal_dxf",
                message=(
                    "DWG прочитан в упрощённом виде: единицы и цвета слоёв из файла недоступны. "
                    "Геометрия, слои и отметки прочитаны полностью."
                ),
            )
        )
    warnings.extend(unit_warnings)
    warnings.extend(collector.notes())

    layers = {name: collector.layer_colors.get(name) for name in sorted({item.layer for item in entities})}
    return CadDrawing(
        entities=entities,
        layers=layers,
        insunits=insunits,
        extent=extent,
        source_format=source_format,
        minimal_dxf=minimal,
        warnings=warnings,
        suggested_scale=suggested_scale,
    )


# --- файл ---------------------------------------------------------------


def _is_dwg(data: bytes, filename: str) -> bool:
    if filename.lower().endswith(".dwg"):
        return True
    return data[:2] == b"AC" and b"SECTION" not in data[:512]


def _looks_like_dxf(data: bytes) -> bool:
    head = data[:4096]
    return head.startswith(b"AutoCAD Binary DXF") or b"SECTION" in head


def _load_dwg(data: bytes, filename: str):
    try:
        full = dwg_to_dxf(data, filename, minimal=False)
    except DwgConversionError as exc:
        raise CadReadError(str(exc)) from exc
    try:
        return _load_dxf(full), False
    except CadReadError:
        pass
    try:
        reduced = dwg_to_dxf(data, filename, minimal=True)
    except DwgConversionError as exc:
        raise CadReadError(str(exc)) from exc
    return _load_dxf(reduced), True


def _load_dxf(data: bytes):
    """Читает DXF из байтов; битый ASCII-чертёж — через режим восстановления."""

    import ezdxf
    from ezdxf import recover

    if not _looks_like_dxf(data):
        raise CadReadError("Не удалось прочитать DXF: файл не похож на чертёж DXF или DWG.")
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as handle:
        handle.write(data)
        path = handle.name
    try:
        try:
            doc = ezdxf.readfile(path)
        except Exception:
            doc, _auditor = recover.readfile(path)
    except Exception as exc:  # ezdxf поднимает свои классы ошибок на любой мусор
        raise CadReadError(f"Не удалось прочитать DXF: {exc}") from exc
    finally:
        os.unlink(path)
    if not len(doc.modelspace()):
        raise CadReadError("В чертеже нет объектов: пространство модели пустое.")
    return doc


def _header_int(doc, name: str) -> int | None:
    try:
        value = doc.header.get(name)
    except Exception:
        return None
    return int(value) if value is not None else None


def _hex(rgb) -> str:
    red, green, blue = (int(value) for value in rgb)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _extent(entities: list[CadEntity]) -> tuple[float, float, float, float] | None:
    xs = [point[0] for item in entities for point in item.points]
    ys = [point[1] for item in entities for point in item.points]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


# --- обход пространства модели -----------------------------------------


class _Collector:
    def __init__(self, doc, options: ReadOptions) -> None:
        self.doc = doc
        self.options = options
        self.entities: list[CadEntity] = []
        self.skipped: Counter[str] = Counter()
        self.degenerate = 0
        self.duplicates = 0
        self.vertex_total = 0
        self.visited = 0
        self._handles: Counter[str] = Counter()
        self.layer_colors = self._layer_colors()

    def collect(self) -> None:
        for entity in self.doc.modelspace():
            self._append(entity, handle=str(entity.dxf.handle), layer=None, block_color=None)

    def _bounded(self, vertices) -> list:
        """Вершины кривой, но не больше остатка предела: окружность радиусом
        10¹⁰ м не должна успеть занять гигабайты до проверки."""

        remaining = MAX_VERTICES - self.vertex_total
        taken = list(islice(vertices, remaining + 2))
        if len(taken) > remaining + 1:
            raise CadReadError(
                f"В чертеже больше {MAX_VERTICES} вершин — это предел одного файла. "
                "Оставьте в файле блок и ближайшую ситуацию."
            )
        return taken

    @property
    def sagitta(self) -> float:
        """Допуск спрямления в единицах чертежа: после масштаба он — CURVE_SAGITTA_M."""

        return CURVE_SAGITTA_M / self.options.scale

    def notes(self) -> list[CadWarning]:
        notes: list[CadWarning] = []
        if self.skipped:
            listed = ", ".join(f"{kind} × {count}" for kind, count in sorted(self.skipped.items()))
            notes.append(CadWarning(code="skipped", message=f"Не читаются: {listed}.", level="info"))
        if self.duplicates:
            notes.append(
                CadWarning(
                    code="duplicate_handles",
                    message=(
                        f"У {self.duplicates} объектов handle повторял чужой — к нему добавлен "
                        "суффикс «~2», «~3»…"
                    ),
                    level="info",
                )
            )
        if self.degenerate:
            notes.append(
                CadWarning(
                    code="degenerate",
                    message=f"Пропущено линий нулевой длины: {self.degenerate}.",
                    level="info",
                )
            )
        return notes

    def _add(self, entity: CadEntity) -> None:
        """Добавляет сущность с уникальным handle — он ключ хранения.

        Пределы файла проверяются здесь, по ходу чтения: раскрытие огромного
        блока не должно успеть съесть память до проверки.
        """

        if len(self.entities) >= MAX_ENTITIES:
            raise CadReadError(
                f"В чертеже больше {MAX_ENTITIES} объектов — это предел одного файла. "
                "Оставьте в файле блок и ближайшую ситуацию."
            )
        self.vertex_total += entity.vertex_count
        if self.vertex_total > MAX_VERTICES:
            raise CadReadError(
                f"В чертеже больше {MAX_VERTICES} вершин — это предел одного файла. "
                "Оставьте в файле блок и ближайшую ситуацию."
            )

        entity.handle = _compact_handle(entity.handle)
        self._handles[entity.handle] += 1
        seen = self._handles[entity.handle]
        if seen > 1:
            self.duplicates += 1
            entity.handle = _compact_handle(f"{entity.handle}~{seen}")
            self._handles[entity.handle] += 1
        self.entities.append(entity)

    def _layer_colors(self) -> dict[str, str | None]:
        from ezdxf import colors

        result: dict[str, str | None] = {}
        for layer in self.doc.layers:
            rgb = layer.rgb
            if rgb is None:
                aci = abs(int(layer.dxf.get("color", 7) or 7))
                rgb = colors.aci2rgb(aci) if 0 < aci < 256 else None
            result[str(layer.dxf.name)] = _hex(rgb) if rgb is not None else None
        return result

    def _color(self, entity, layer: str, block_color: str | None) -> str | None:
        from ezdxf import colors

        if entity.dxf.hasattr("true_color"):
            return _hex(colors.int2rgb(entity.dxf.true_color))
        aci = int(entity.dxf.get("color", _BY_LAYER))
        if aci == _BY_BLOCK and block_color is not None:
            return block_color
        if aci in (_BY_LAYER, _BY_BLOCK):
            return self.layer_colors.get(layer)
        return _hex(colors.aci2rgb(aci)) if 0 < aci < 256 else None

    def _append(self, entity, *, handle: str, layer: str | None, block_color: str | None) -> None:
        self.visited += 1
        if self.visited > MAX_ENTITIES * VISIT_BUDGET_FACTOR:
            raise CadReadError(
                f"В чертеже с учётом вставок блоков больше {MAX_ENTITIES * VISIT_BUDGET_FACTOR} "
                "объектов — это предел одного файла. Оставьте в файле блок и ближайшую ситуацию."
            )
        try:
            self._append_entity(entity, handle=handle, layer=layer, block_color=block_color)
        except CadReadError:
            raise
        except Exception:  # одна битая сущность не должна ронять весь чертёж
            self.skipped[f"{entity.dxftype()} (повреждён)"] += 1

    def _append_entity(self, entity, *, handle: str, layer: str | None, block_color: str | None) -> None:
        kind = entity.dxftype()
        own_layer = str(entity.dxf.get("layer", "0") or "0")
        # Слой «0» внутри блока берёт слой вставки — как в AutoCAD.
        layer_name = layer if layer is not None and own_layer == "0" else own_layer
        color = self._color(entity, layer_name, block_color)

        if kind == "INSERT":
            self._insert(entity, handle, layer_name, color)
            return
        if kind == "POINT":
            self._push_point(handle, layer_name, "POINT", entity.dxf.location, color)
            return
        if kind in ("TEXT", "MTEXT"):
            self._text(entity, kind, handle, layer_name, color)
            return
        if kind in ("LWPOLYLINE", "POLYLINE", "LINE") or kind in _CURVE_KINDS:
            self._line(entity, kind, handle, layer_name, color)
            return
        self.skipped[kind] += 1

    # --- линии ----------------------------------------------------------

    def _line(self, entity, kind: str, handle: str, layer: str, color: str | None) -> None:
        from ezdxf import path as ezpath

        closed_flag = False
        if kind == "POLYLINE":
            if entity.is_poly_face_mesh or entity.is_polygon_mesh:
                self.skipped["POLYLINE (сеть)"] += 1
                return
            closed_flag = bool(entity.is_closed)
            if entity.is_3d_polyline:
                kind = "POLYLINE3D"
                raw = self._bounded(entity_vertex.dxf.location for entity_vertex in entity.vertices)
            else:
                kind = "POLYLINE2D"
                raw = self._bounded(ezpath.make_path(entity).flattening(self.sagitta))
        elif kind == "LINE":
            raw = [entity.dxf.start, entity.dxf.end]
        else:
            if kind == "LWPOLYLINE":
                closed_flag = bool(entity.closed)
            elif kind == "CIRCLE":
                closed_flag = True
            elif kind == "ELLIPSE":
                span = abs(float(entity.dxf.end_param) - float(entity.dxf.start_param))
                closed_flag = math.isclose(span, math.tau, abs_tol=1e-6) or span < 1e-9
            elif kind == "SPLINE":
                closed_flag = bool(entity.closed)
            raw = self._bounded(ezpath.make_path(entity).flattening(self.sagitta))

        points = _dedup([self._scaled(value) for value in raw])
        closed, by_gap = False, False
        if len(points) >= 4 and _near(points[0], points[-1]) and _distinct(points) >= 3:
            points.pop()
            closed, by_gap = True, not closed_flag
        elif closed_flag and _distinct(points) >= 3:
            closed = True
        if len(points) < 2:
            self.degenerate += 1
            return
        line = CadEntity(
            handle=handle, layer=layer, kind=kind, points=points, closed=closed, closed_by_gap=by_gap, color=color
        )
        if not line.closed and _distinct(points) >= 3:
            gap = math.dist(points[0][:2], points[-1][:2])
            if gap <= self.options.closure_tolerance_m and gap <= CLOSURE_MAX_GAP_SHARE * line.length_m:
                line.closed = True
                line.closed_by_gap = True
        self._add(line)

    # --- точки, знаки, подписи -----------------------------------------

    def _push_point(self, handle: str, layer: str, kind: str, location, color: str | None, text: str = "") -> CadEntity:
        point = CadEntity(
            handle=handle, layer=layer, kind=kind, points=[self._scaled(location)], text=text, color=color
        )
        self._add(point)
        return point

    def _text(self, entity, kind: str, handle: str, layer: str, color: str | None) -> None:
        if kind == "TEXT":
            location = entity.ocs().to_wcs(entity.dxf.insert)
            text = str(entity.dxf.get("text", "") or "")
            height = float(entity.dxf.get("height", 0.0) or 0.0)
        else:
            location = entity.dxf.insert
            text = entity.plain_text()
            height = float(entity.dxf.get("char_height", 0.0) or 0.0)
        label = CadEntity(
            handle=handle,
            layer=layer,
            kind=kind,
            points=[self._scaled(location)],
            text=text.strip(),
            text_height=height * self.options.scale,
            color=color,
        )
        self._add(label)

    def _insert(self, entity, handle: str, layer: str, color: str | None) -> None:
        if entity.mcount > MAX_ENTITIES:
            raise CadReadError(
                f"Массив блоков «{entity.dxf.name}» из {entity.mcount} копий — больше предела "
                f"{MAX_ENTITIES} объектов одного файла."
            )
        if entity.mcount > 1:
            # MINSERT — массив копий блока: каждая копия как отдельная вставка.
            for index, single in enumerate(entity.multi_insert(), start=1):
                self._insert(single, f"{handle}/{index}", layer, color)
            return
        attributes = [str(attrib.dxf.get("text", "") or "") for attrib in entity.attribs]
        if attributes or self._block_size(entity) * self.options.scale <= SIGN_BLOCK_SIZE_M:
            location = entity.ocs().to_wcs(entity.dxf.insert)
            label = next((text for text in attributes if parse_elevation(text) is not None), "")
            sign = self._push_point(handle, layer, "INSERT", location, color, text=label)
            x, y, z = sign.points[0]
            if label and abs(z) <= 1e-9:
                sign.points = [(x, y, float(parse_elevation(label)))]
                sign.z_from_label = True
            return
        try:
            virtuals = list(entity.virtual_entities())
        except Exception:  # повреждённая вставка не должна ронять весь импорт
            self.skipped["INSERT (повреждён)"] += 1
            return
        for index, virtual in enumerate(virtuals, start=1):
            self._append(virtual, handle=f"{handle}/{index}", layer=layer, block_color=color)

    def _block_size(self, entity) -> float:
        from ezdxf import bbox

        block = entity.block()
        if block is None:
            return 0.0
        try:
            extents = bbox.extents(block)
        except Exception:
            return 0.0
        if not extents.has_data:
            return 0.0
        scale = max(abs(float(entity.dxf.get("xscale", 1.0))), abs(float(entity.dxf.get("yscale", 1.0))))
        return max(extents.size.x, extents.size.y) * scale

    def _scaled(self, value) -> Point:
        scale = self.options.scale
        z = float(value[2]) if len(value) > 2 else 0.0
        return (float(value[0]) * scale, float(value[1]) * scale, z * scale)


def _near(a: Point, b: Point) -> bool:
    return math.dist(a, b) <= DUPLICATE_TOLERANCE_M


def _compact_handle(handle: str) -> str:
    if len(handle) <= MAX_HANDLE_LENGTH:
        return handle
    digest = hashlib.sha1(handle.encode("utf-8")).hexdigest()[:12]
    return f"{handle[:40]}…{digest}"


def _distinct(points: list[Point]) -> int:
    """Сколько различных вершин в плане: линия A–B–A замкнутой не бывает."""

    return len({(round(x, 3), round(y, 3)) for x, y, _ in points})


def _dedup(points: list[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if result and _near(result[-1], point):
            continue
        result.append(point)
    return result
