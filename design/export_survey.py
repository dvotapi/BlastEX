"""Чертёж скважин паспорта на бурение для маркшейдера (TASK-015, PR 4, спека §4).

`holes_dxf` строит DXF R2010 только из снимка ревизии (`context`), как PDF:
проект при выгрузке не читается. Координаты — в СК объекта без пересчёта:
DXF X — восток (внутренний `x`), Y — север (`y`), Z — отметка, метры
(`$INSUNITS = 6`). Числа в подписях и атрибутах — с точкой, как в чертеже
маркшейдера (решение владельца 10.11.2026); строки `BLX_INFO` — для человека,
с запятой, как в паспорте.

Повторный выпуск той же ревизии даёт те же байты: метаданные ezdxf (даты
создания и правки) фиксируются, GUID чертежа выводятся из снимка
(`$FINGERPRINTGUID` — из проекта и номера паспорта, `$VERSIONGUID` — из всего
снимка и номера ревизии), в `BLX_INFO` — дата паспорта, как в PDF.

Линия подошвы, построенная по углу откоса (`plan.toe_source` не «survey»), —
на своём слое `BLX_TOE_LINE` с пометкой в `BLX_INFO`: на «нижней бровке»
`BLX_CREST_TOE` маркшейдер принял бы её за снятую.

`holes_dwg` переводит DXF в DWG R2000 утилитой LibreDWG `dxf2dwg` и читает
результат обратно `dwg2dxf`: число сущностей слоёв `BLX_*`, тексты, атрибуты
скважин и координаты (устья, забои, вставки, вершины полилиний, концы линий)
должны совпасть, координаты — с допуском 1 мм. Не вышло — отдаётся DXF с предупреждением (§4).
"""
from __future__ import annotations

import hashlib
import io
import logging
import math
import threading
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal

import ezdxf
from ezdxf.enums import MTextEntityAlignment, TextEntityAlignment

from design.mass_blast import canonical_json
from design.reporting.drill import fmt
from design.reporting.drill.layout import block_and_horizon
from design.reporting.drill.plan import hole_circle_mm
from design.spatial.dwg import dwg_to_dxf, dxf_to_dwg

__all__ = [
    "DEFAULT_CIRCLE_MM",
    "DWG_FALLBACK_WARNING",
    "DwgExport",
    "HOLE_ATTRIBUTES",
    "HOLE_LAYERS",
    "holes_dwg",
    "holes_dxf",
]

logger = logging.getLogger(__name__)

# Слой → цвет ACI; тип линии у всех Continuous (§4).
LAYER_COLORS: dict[str, int] = {
    "BLX_CONTOUR": 7,
    "BLX_CREST_TOP": 30,
    "BLX_CREST_TOE": 32,
    "BLX_TOE_LINE": 40,
    "BLX_HOLE": 4,
    "BLX_HOLE_NUM": 7,
    "BLX_HOLE_DEPTH": 8,
    "BLX_FIRST_ROW": 1,
    "BLX_TOE": 6,
    "BLX_INFO": 7,
}
HOLE_LAYERS = tuple(LAYER_COLORS)
HOLE_BLOCK = "BLX_HOLE"
HOLE_ATTRIBUTES = ("NUM", "DEPTH", "ANGLE", "AZIM", "ZCOL", "ZTOE")
# Ø круга, когда в ревизии нет ни диаметра инструмента, ни диаметра скважины
# (ревизия до PR 3), мм.
DEFAULT_CIRCLE_MM = 140.0
TEXT_HEIGHT_M = 0.4
TEXT_GAP_M = 0.15
INFO_HEIGHT_M = 1.0
INFO_GAP_M = 3.0
# Строки DWG R2000 — в кодовой странице чертежа; для русских программ — 1251.
CODEPAGE = "ANSI_1251"
TEXT_FONT = "arial.ttf"

# Нулевой GUID, который ставит `write_fixed_meta_data_for_testing`.
CONST_GUID = "{00000000-0000-0000-0000-000000000000}"

# Фиксация метаданных — глобальная опция ezdxf: построение под замком.
_WRITE_LOCK = threading.Lock()


@contextmanager
def _fixed_metadata() -> Iterator[None]:
    """Даты, GUID и метки ezdxf — постоянные: и при создании, и при записи."""

    with _WRITE_LOCK:
        previous = ezdxf.options.write_fixed_meta_data_for_testing
        ezdxf.options.write_fixed_meta_data_for_testing = True
        try:
            yield
        finally:
            ezdxf.options.write_fixed_meta_data_for_testing = previous


def _f(value: float, digits: int) -> str:
    return f"{value:.{digits}f}"


def _xyz(point: Mapping[str, Any]) -> tuple[float, float, float]:
    return float(point["x"]), float(point["y"]), float(point["z"])


def _toe(row: Mapping[str, Any]) -> tuple[float, float, float]:
    """Забой из снимка; у ревизии до PR 3 — по длине, углу и азимуту."""

    if row.get("toe"):
        return _xyz(row["toe"])
    x, y, z = _xyz(row["collar"])
    length = float(row["length_m"])
    dip = math.radians(float(row.get("dip_deg") or 90.0))
    azimuth = math.radians(float(row.get("azimuth_deg") or 0.0))
    horizontal = length * math.cos(dip)
    return x + horizontal * math.sin(azimuth), y + horizontal * math.cos(azimuth), z - length * math.sin(dip)


def _guid(*parts: Any) -> str:
    digest = hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).hexdigest()
    return "{" + f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}".upper() + "}"


def _surveyed_toe(plan: Mapping[str, Any]) -> bool:
    return plan.get("toe_source") == "survey"


def _mtext_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _crs_line(crs: Mapping[str, Any] | None) -> str:
    if crs is None:
        return "СК не сохранена в ревизии"
    name = str(crs.get("name") or "").strip()
    epsg = crs.get("epsg")
    heights = str(crs.get("height_system") or "").strip()
    if (not name or name == "local") and not epsg:
        line = "СК не задана (условная)"
    else:
        line = f"СК: {name or 'EPSG'}" + (f" (EPSG {epsg})" if epsg else "")
    return line + (f"; высоты: {heights}" if heights else "; система высот не задана")


def _info_lines(context: Mapping[str, Any], revision_no: int | None) -> list[str]:
    passport = context.get("passport") or {}
    plan = context.get("plan") or {}
    title = f"Паспорт на бурение № {str(passport.get('passport_no') or '').strip() or 'б/н'}"
    if str(passport.get("passport_date") or "").strip():
        title += f" от {fmt.date(str(passport['passport_date']))}"
    if revision_no is not None:
        title += f", ревизия {revision_no}"
    block, horizon = block_and_horizon(passport.get("payload") or {})
    place = ", ".join(part for part in (f"Блок {block}" if block else "", f"горизонт {horizon}" if horizon else "") if part)
    lines = [title, place, _crs_line(context.get("crs")), "Координаты — в СК объекта без пересчёта, метры"]
    if plan.get("crest_toe") and not _surveyed_toe(plan):
        lines.append("Линия подошвы — расчётная по углу откоса (слой BLX_TOE_LINE)")
    lines.append(f"BlastEX, формулы {context.get('formula_version') or '—'}")
    return [line for line in lines if line]


def _new_document():
    doc = ezdxf.new("R2010", units=6)
    doc.encoding = "cp1251"
    doc.header["$DWGCODEPAGE"] = CODEPAGE
    # txt.shx не во всех CAD знает кириллицу: как в чертеже маркшейдера —
    # TrueType Arial (подписи и BLX_INFO берут стиль Standard).
    doc.styles.get("Standard").dxf.font = TEXT_FONT
    for name, color in LAYER_COLORS.items():
        doc.layers.add(name, color=color, linetype="Continuous")
    block = doc.blocks.new(HOLE_BLOCK)
    # Круг Ø 1 м: вставка масштабируется до Ø скважины. Атрибуты невидимы —
    # номер и глубина видны текстом на своих слоях, без двойных надписей.
    block.add_circle((0.0, 0.0), 0.5, dxfattribs={"layer": "0", "color": 0})
    for index, tag in enumerate(HOLE_ATTRIBUTES):
        block.add_attdef(
            tag, (0.6, -0.6 * index), dxfattribs={"height": TEXT_HEIGHT_M, "flags": 1, "layer": HOLE_BLOCK}
        )
    return doc


def _polyline(msp, points: Sequence[Sequence[float]], layer: str, closed: bool) -> None:
    if len(points) >= 2:
        msp.add_lwpolyline([(float(p[0]), float(p[1])) for p in points], close=closed, dxfattribs={"layer": layer})


def holes_dxf(context: Mapping[str, Any], *, revision_no: int | None = None) -> bytes:
    """DXF R2010 скважин ревизии: слои `BLX_*` §4, байты повторяются."""

    with _fixed_metadata():
        text = _build(context, revision_no)
    # Тестовая опция ezdxf ставит всем чертежам нулевые GUID: подменяем их на
    # выведенные из снимка — CAD и PDM различают чертежи по ним.
    passport = context.get("passport") or {}
    for name, guid in (
        ("$FINGERPRINTGUID", _guid("fingerprint", context.get("design_id"), passport.get("passport_no"))),
        ("$VERSIONGUID", _guid("version", context, revision_no)),
    ):
        tag = f"{name}\n  2\n{CONST_GUID}\n"
        assert text.count(tag) == 1, name
        text = text.replace(tag, f"{name}\n  2\n{guid}\n")
    return text.encode("utf-8")


def _build(context: Mapping[str, Any], revision_no: int | None) -> str:
    doc = _new_document()
    msp = doc.modelspace()
    plan = context.get("plan") or {}
    summary = context.get("summary") or {}
    _polyline(msp, plan.get("contour") or [], "BLX_CONTOUR", closed=True)
    for line in plan.get("crest_top") or []:
        _polyline(msp, line, "BLX_CREST_TOP", closed=False)
    toe_layer = "BLX_CREST_TOE" if _surveyed_toe(plan) else "BLX_TOE_LINE"
    for line in plan.get("crest_toe") or []:
        _polyline(msp, line, toe_layer, closed=False)

    xs = [float(p[0]) for p in plan.get("contour") or []]
    ys = [float(p[1]) for p in plan.get("contour") or []]
    for row in context.get("holes") or []:
        collar = _xyz(row["collar"])
        toe = _toe(row)
        xs.append(collar[0])
        ys.append(collar[1])
        diameter_m = (hole_circle_mm(summary, row) or DEFAULT_CIRCLE_MM) / 1000.0
        radius = diameter_m / 2
        inclined = row.get("azimuth_deg") is not None
        number = str(row["number"])
        depth = _f(float(row["length_m"]), 1)

        msp.add_point(collar, dxfattribs={"layer": "BLX_HOLE"})
        ref = msp.add_blockref(
            HOLE_BLOCK, collar, dxfattribs={"layer": "BLX_HOLE", "xscale": diameter_m, "yscale": diameter_m, "zscale": diameter_m}
        )
        ref.add_auto_attribs(
            {
                "NUM": number,
                "DEPTH": depth,
                "ANGLE": _f(float(row["dip_deg"]), 0) if inclined else "",
                "AZIM": _f(float(row["azimuth_deg"]), 0) if inclined else "",
                "ZCOL": _f(collar[2], 2),
                "ZTOE": _f(toe[2], 2),
            }
        )
        for attrib in ref.attribs:
            attrib.dxf.layer = "BLX_HOLE"
            attrib.is_invisible = True
        msp.add_text(number, height=TEXT_HEIGHT_M, dxfattribs={"layer": "BLX_HOLE_NUM"}).set_placement(
            (collar[0], collar[1] + radius + TEXT_GAP_M, collar[2]), align=TextEntityAlignment.BOTTOM_CENTER
        )
        msp.add_text(depth, height=TEXT_HEIGHT_M, dxfattribs={"layer": "BLX_HOLE_DEPTH"}).set_placement(
            (collar[0], collar[1] - radius - TEXT_GAP_M, collar[2]), align=TextEntityAlignment.TOP_CENTER
        )
        if row.get("first_row"):
            msp.add_circle(collar, radius, dxfattribs={"layer": "BLX_FIRST_ROW"})
        if inclined:
            msp.add_line(collar, toe, dxfattribs={"layer": "BLX_TOE"})
            msp.add_point(toe, dxfattribs={"layer": "BLX_TOE"})

    info = msp.add_mtext(
        "\\P".join(_mtext_escape(line) for line in _info_lines(context, revision_no)),
        dxfattribs={"layer": "BLX_INFO", "char_height": INFO_HEIGHT_M},
    )
    if xs:
        info.set_location((min(xs), max(ys) + INFO_GAP_M + INFO_HEIGHT_M * 6), attachment_point=MTextEntityAlignment.TOP_LEFT)

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue()


DWG_FALLBACK_WARNING = "DWG не сформирован, используйте DXF (открывается в AutoCAD / nanoCAD)."
# Допуск сверки координат после обратного чтения DWG, м.
DWG_TOLERANCE_M = 0.001
# Сущности, которые сверяются по слоям `BLX_*`. ATTRIB не считаются: `dwg2dxf`
# выводит их и отдельно от вставок (значения сверяются по вставкам).
_CHECKED_TYPES = ("POINT", "INSERT", "TEXT", "MTEXT", "CIRCLE", "LINE", "LWPOLYLINE")
# DWG R2000 начинается с версии формата.
DWG_SIGNATURE = b"AC1015"


@dataclass(frozen=True)
class DwgExport:
    """Результат выгрузки DWG: DWG или, при отказе, исходный DXF с предупреждением."""

    data: bytes
    format: Literal["dwg", "dxf"]
    warning: str | None = None


@dataclass
class _Signature:
    counts: Counter
    texts: Counter
    attribs: dict[str, tuple[str, ...]]
    # (тип, слой) → точки: устья и забои (POINT), вставки (INSERT), вершины
    # полилиний (LWPOLYLINE), концы линий (LINE).
    points: dict[tuple[str, str], list[tuple[float, float, float]]]


def _text(value: str) -> str:
    """Строка с байтами, разрезанными посреди буквы UTF-8, — снова буквами."""

    return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _signature(dxf: bytes) -> _Signature:
    """Что сверяется после обратного чтения: число сущностей, тексты, атрибуты, точки."""

    # `dwg2dxf` пишет UTF-8 при любой `$DWGCODEPAGE` (ezdxf — тоже, R2010) и
    # концы строк CRLF: `newline=None` переводит их, иначе пустое бинарное поле
    # (группа 310) читается как «\r» и разбор падает. Длинный MTEXT он режет
    # на куски по 250 байт и может разрезать букву: `surrogateescape` хранит
    # такие байты, `_text` склеивает их обратно.
    doc = ezdxf.read(io.StringIO(dxf.decode("utf-8", "surrogateescape"), newline=None))
    result = _Signature(Counter(), Counter(), {}, {})
    for entity in doc.modelspace():
        kind, layer = entity.dxftype(), entity.dxf.get("layer", "")
        if kind not in _CHECKED_TYPES or not layer.startswith("BLX_"):
            continue
        result.counts[(kind, layer)] += 1
        if kind == "TEXT":
            result.texts[(layer, _text(entity.dxf.text))] += 1
        elif kind == "MTEXT":
            result.texts[(layer, _text(entity.text))] += 1
        points = result.points.setdefault((kind, layer), [])
        if kind == "POINT":
            points.append(tuple(entity.dxf.location))
        elif kind == "INSERT":
            points.append(tuple(entity.dxf.insert))
            if layer == "BLX_HOLE":
                result.attribs[_text(entity.get_attrib_text("NUM") or "")] = tuple(
                    _text(attrib.dxf.text) for attrib in entity.attribs
                )
        elif kind == "LWPOLYLINE":
            elevation = entity.dxf.elevation
            points.extend((x, y, elevation) for x, y in entity.get_points("xy"))
        elif kind == "LINE":
            points.extend((tuple(entity.dxf.start), tuple(entity.dxf.end)))
    return result


def _same_points(a: list[tuple[float, float, float]], b: list[tuple[float, float, float]]) -> bool:
    return len(a) == len(b) and all(
        abs(p - q) <= DWG_TOLERANCE_M for left, right in zip(sorted(a), sorted(b)) for p, q in zip(left, right)
    )


def _same_drawing(expected: bytes, actual: bytes) -> bool:
    want, got = _signature(expected), _signature(actual)
    return (
        want.counts == got.counts
        and want.texts == got.texts
        and want.attribs == got.attribs
        and want.points.keys() == got.points.keys()
        and all(_same_points(points, got.points[key]) for key, points in want.points.items())
    )


def holes_dwg(dxf: bytes) -> DwgExport:
    """DWG R2000 из DXF `holes_dxf` со сверкой обратным чтением; отказ — DXF."""

    try:
        dwg = dxf_to_dwg(dxf)
        same = dwg.startswith(DWG_SIGNATURE) and _same_drawing(dxf, dwg_to_dxf(dwg, "holes.dwg"))
    except Exception:  # noqa: BLE001 — любой отказ утилит или чтения даёт DXF
        logger.warning("DWG скважин не сформирован, отдаётся DXF", exc_info=True)
        return DwgExport(dxf, "dxf", DWG_FALLBACK_WARNING)
    if not same:
        logger.warning("DWG скважин не совпал с DXF при обратном чтении, отдаётся DXF")
        return DwgExport(dxf, "dxf", DWG_FALLBACK_WARNING)
    return DwgExport(dwg, "dwg")
