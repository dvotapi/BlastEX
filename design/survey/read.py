"""Чтение файла исполнительной съёмки маркшейдера.

Чистый модуль: байты файла → точки. Ничего не знает о проекте и сопоставлении.
Координаты — как у `Point3`: x — восток, y — север. Описание точки в файле
выноса («R1 L10.7») глубиной не считается: глубину даёт только таблица съёмки.
"""

from __future__ import annotations

import csv
import hashlib
import heapq
import io
import math
import re
from dataclasses import dataclass, field
from typing import Any

SURVEY_FORMATS = ("PNEZD_CSV", "PENZD_CSV", "PNEZ_TXT", "DXF_POINTS", "TABLE")

# Подпись точки в DXF выноса стоит со сдвигом (+0,15; +0,15) — ищем с запасом.
LABEL_RADIUS_M = 0.6

# Пределы входа: съёмка блока — сотни точек; всё, что больше, — не съёмка.
MAX_SURVEY_BYTES = 20 * 1024 * 1024
MAX_SURVEY_ROWS = 50_000
MAX_COLUMNS = 64
MAX_LABELS_PER_CELL = 50  # подписей в квадрате со стороной LABEL_RADIUS_M
LABEL_CANDIDATES = 4  # ближайших подписей на точку
MAX_UNPACKED_BYTES = 200 * 1024 * 1024  # xlsx в распакованном виде

COLUMN_KEYS = ("name", "east", "north", "z", "depth", "angle", "azimuth", "wet", "water")

# Псевдонимы заголовков (в нижнем регистре, без пробелов по краям). Порядок
# ключей — порядок проверки: «уровень воды» раньше «вода».
_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("№", "номер", "скв", "скважина", "point", "name", "точка", "id"),
    "east": ("e", "восток", "easting", "east"),
    "north": ("n", "север", "northing", "north"),
    "z": ("z", "h", "отметка", "elevation", "высота"),
    "depth": ("глубина", "depth", "l"),
    "angle": ("угол", "angle", "dip"),
    "azimuth": ("азимут", "azimuth", "az"),
    "water": ("уровень воды", "water", "water_depth"),
    "wet": ("вода", "обводн", "обводнена", "обводнённая", "wet"),
}
_XY = {"x": "north", "y": "east"}  # по-русски X — север, Y — восток
# «Поменять»: восток и север переставлены (таблица с колонками востока и севера, профили, DXF).
SWAPPED_TEXT = "Колонки востока и севера переставлены по запросу."
_TRUE = {"да", "1", "+", "wet", "true", "yes", "y", "д"}
_FALSE = {"нет", "0", "false", "no", "n", "н"}


class SurveyReadError(ValueError):
    """Файл съёмки не прочитан; текст — для пользователя. У таблицы — её
    заголовки (`headers`): по ним колонки выбираются вручную."""

    def __init__(self, message: str, headers: list[str] | None = None) -> None:
        super().__init__(message)
        self.headers = list(headers or [])


@dataclass
class SurveyedPoint:
    name: str
    x: float
    y: float
    z: float | None = None
    depth_m: float | None = None
    angle_deg: float | None = None
    azimuth_deg: float | None = None
    wet: bool | None = None
    water_depth_m: float | None = None
    line: int = 0

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "x": self.x, "y": self.y, "line": self.line}
        for key in ("z", "depth_m", "angle_deg", "azimuth_deg", "wet", "water_depth_m"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurveyedPoint":
        return cls(
            name=str(data["name"]),
            x=float(data["x"]),
            y=float(data["y"]),
            z=data.get("z"),
            depth_m=data.get("depth_m"),
            angle_deg=data.get("angle_deg"),
            azimuth_deg=data.get("azimuth_deg"),
            wet=data.get("wet"),
            water_depth_m=data.get("water_depth_m"),
            line=int(data.get("line", 0)),
        )


@dataclass
class SurveyFile:
    points: list[SurveyedPoint]
    format: str
    columns: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    sha256: str = ""
    # Заголовки колонок таблицы (формат TABLE); у профилей — пусто.
    headers: list[str] = field(default_factory=list)


def read_survey(
    data: bytes,
    filename: str,
    *,
    format: str | None = None,  # noqa: A002 — имя параметра задано контрактом
    columns: dict[str, str] | None = None,
    swap_xy: bool | None = None,
) -> SurveyFile:
    if not data or not data.strip():
        raise SurveyReadError("Файл съёмки пустой.")
    if len(data) > MAX_SURVEY_BYTES:
        raise SurveyReadError(f"Файл съёмки больше {MAX_SURVEY_BYTES // (1024 * 1024)} МБ.")
    if format is not None and format not in SURVEY_FORMATS:
        raise SurveyReadError(f"Формат «{format}» не поддерживается.")
    fmt = format or _detect_format(data, filename)
    warnings: list[str] = []
    used: dict[str, str] = {}
    headers: list[str] = []
    if fmt == "DXF_POINTS":
        points = _read_dxf(data, filename, warnings)
    elif fmt == "TABLE":
        points = _read_table(data, filename, columns, swap_xy, warnings, used, headers)
    else:
        points = _read_profile(_decode(data), fmt, warnings)
    if swap_xy and fmt != "TABLE" and points:
        # У таблицы перестановка — в колонках (`_map_columns`), у профилей и DXF — в точках.
        for point in points:
            point.x, point.y = point.y, point.x
        warnings.append(SWAPPED_TEXT)
    if not points:
        raise SurveyReadError("В файле нет ни одной точки съёмки: координаты не прочитаны как числа.")
    return SurveyFile(points, fmt, used, warnings, hashlib.sha256(data).hexdigest(), headers)


# --- определение формата и декодирование -----------------------------------


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace").lstrip("﻿")


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _detect_format(data: bytes, filename: str) -> str:
    ext = _extension(filename)
    if ext == "dxf":
        return "DXF_POINTS"
    if ext in ("xlsx", "xlsm"):
        return "TABLE"
    named = _profile_in_name(filename)
    if named:
        return named
    text = _decode(data)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    # Заголовок — таблица при любом расширении и разделителе (таб, пробелы).
    if _has_header(first):
        return "TABLE"
    if ext == "txt" and "," not in text and ";" not in text:
        return "PNEZ_TXT"
    return "PNEZD_CSV"


# Профили выноса, которые BlastEX пишет в имя файла (`drilling_passport_service._stakeout`).
_NAMED_PROFILES = ("PENZD_CSV", "PNEZD_CSV", "PNEZ_TXT")


def _profile_in_name(filename: str) -> str | None:
    upper = filename.upper()
    return next((code for code in _NAMED_PROFILES if code in upper), None)


def _has_header(line: str) -> bool:
    """Первая строка — заголовок, если в ней нет двух чисел подряд за именем."""

    cells = _split(line, _delimiter(line, spaces=True))
    return not (len(cells) >= 3 and _number(cells[1], False) is not None and _number(cells[2], False) is not None)


_SPACES = " "  # разделитель таблицы — пробелы (подряд), когда нет «;», таба и «,»


def _delimiter(line: str, *, spaces: bool = False) -> str:
    for delim in (";", "\t"):
        if delim in line:
            return delim
    if spaces and "," not in line:
        return _SPACES
    return ","


def _split(line: str, delim: str) -> list[str]:
    if delim == _SPACES:
        return line.split()
    return next(csv.reader([line], delimiter=delim, skipinitialspace=True), [])


_QUOTED_DECIMAL = re.compile(r"^[+-]?\d+,\d+$")


def _too_many_rows() -> SurveyReadError:
    return SurveyReadError(f"В файле больше {MAX_SURVEY_ROWS} строк — это не съёмка блока.")


def _number(raw: Any, decimal_comma: bool) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if math.isfinite(raw) else None
    text = str(raw).strip().replace("\xa0", "").replace(" ", "")
    # Запятая внутри ячейки (после разбора CSV — значит в кавычках) — десятичная.
    if decimal_comma or _QUOTED_DECIMAL.match(text):
        text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


# --- профили выноса (без заголовков колонок) --------------------------------


def _read_profile(text: str, fmt: str, warnings: list[str]) -> list[SurveyedPoint]:
    points: list[SurveyedPoint] = []
    seen_first = False
    skipped: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if number > MAX_SURVEY_ROWS:
            raise _too_many_rows()
        if not line.strip():
            continue
        first = not seen_first
        seen_first = True
        if fmt == "PNEZ_TXT":
            cells, comma = line.split(), False
        else:
            delim = _delimiter(line)
            cells, comma = _split(line, delim), delim != ","
        a = _number(cells[1], comma) if len(cells) > 1 else None
        b = _number(cells[2], comma) if len(cells) > 2 else None
        if a is None or b is None:
            if not first:  # первая строка — «Point,Northing,...»: молча
                skipped.append(number)
            continue
        north, east = (b, a) if fmt == "PENZD_CSV" else (a, b)
        z = _number(cells[3], comma) if len(cells) > 3 else None
        points.append(SurveyedPoint(cells[0].strip(), east, north, z, line=number))
    if skipped:
        warnings.append(f"Строки без координат пропущены: {_listed(skipped)}.")
    return points


def _listed(numbers: list[int], limit: int = 10) -> str:
    text = ", ".join(str(n) for n in numbers[:limit])
    return text + (f" и ещё {len(numbers) - limit}" if len(numbers) > limit else "")


# --- DXF --------------------------------------------------------------------


def _read_dxf(data: bytes, filename: str, warnings: list[str]) -> list[SurveyedPoint]:
    from design.spatial.cad.reader import CadReadError, read_cad

    try:
        drawing = read_cad(data, filename or "survey.dxf")
    except CadReadError as exc:
        raise SurveyReadError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — битый DXF: любой отказ ezdxf
        raise SurveyReadError("Файл DXF не прочитан.") from exc
    marks = [e for e in drawing.entities if e.kind == "POINT" and e.points]
    labels = [e for e in drawing.entities if e.kind in ("TEXT", "MTEXT") and e.points and e.text]
    if len(marks) > MAX_SURVEY_ROWS or len(labels) > MAX_SURVEY_ROWS:
        raise _too_many_rows()
    # Подписи — в сетку с ячейкой в радиус поиска: пары только из соседних ячеек.
    grid: dict[tuple[int, int], list[int]] = {}
    for j, t in enumerate(labels):
        cell = (math.floor(t.points[0][0] / LABEL_RADIUS_M), math.floor(t.points[0][1] / LABEL_RADIUS_M))
        grid.setdefault(cell, []).append(j)
    if any(len(js) > MAX_LABELS_PER_CELL for js in grid.values()):
        raise SurveyReadError(
            f"Слишком много подписей в одном месте чертежа (больше {MAX_LABELS_PER_CELL} на {LABEL_RADIUS_M} м)."
        )
    pairs: list[tuple[float, int, int]] = []
    for i, m in enumerate(marks):
        near: list[tuple[float, int, int]] = []
        cx, cy = math.floor(m.points[0][0] / LABEL_RADIUS_M), math.floor(m.points[0][1] / LABEL_RADIUS_M)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((cx + dx, cy + dy), ()):
                    t = labels[j]
                    d = math.hypot(m.points[0][0] - t.points[0][0], m.points[0][1] - t.points[0][1])
                    if d <= LABEL_RADIUS_M:
                        near.append((d, i, j))
        pairs.extend(heapq.nsmallest(LABEL_CANDIDATES, near))
    pairs.sort()
    named: dict[int, int] = {}
    used: set[int] = set()
    for distance, i, j in pairs:
        if distance > LABEL_RADIUS_M:
            break
        if i not in named and j not in used:
            named[i] = j
            used.add(j)
    nameless = 0
    points: list[SurveyedPoint] = []
    for i, mark in enumerate(marks):
        if i not in named:
            nameless += 1
            continue
        x, y, z = mark.points[0]
        points.append(SurveyedPoint(labels[named[i]].text.strip(), x, y, z, line=i + 1))
    if nameless:
        warnings.append(f"Точек без подписи рядом (до {LABEL_RADIUS_M} м): {nameless} — пропущены.")
    return points


# --- таблица (CSV/TXT с заголовком: «;», таб, «,» или пробелы; XLSX) -------


def _read_table(
    data: bytes,
    filename: str,
    explicit: dict[str, str] | None,
    swap_xy: bool | None,
    warnings: list[str],
    used: dict[str, str],
    headers: list[str],
) -> list[SurveyedPoint]:
    if _extension(filename) in ("xlsx", "xlsm"):
        header, rows, comma = _xlsx_rows(data)
    else:
        header, rows, comma = _text_rows(_decode(data), warnings)
    if not header:
        raise SurveyReadError("В таблице нет строки заголовков.")
    # Непустые заголовки — как в файле: по ним колонку выбирают вручную.
    headers.extend(title for title in header if title.strip())
    disabled: set[str] = set()
    try:
        mapping = _map_columns(header, explicit or {}, swap_xy, warnings, disabled)
    except SurveyReadError as exc:
        raise SurveyReadError(str(exc), headers) from None
    for key, label in _REQUIRED_LABELS.items():
        if key not in mapping:
            raise SurveyReadError(f"В таблице не найдена колонка «{label}». Укажите её вручную.", headers)
    used.update({key: header[idx] for key, idx in mapping.items()})
    # Выключенные роли — пустой строкой: клиент пришлёт их так же при новом чтении.
    used.update({key: "" for key in disabled})
    points: list[SurveyedPoint] = []
    bad: list[int] = []
    bad_depth: list[int] = []
    bad_water: list[int] = []
    for number, row in rows:

        def cell(key: str) -> Any:
            idx = mapping.get(key)
            return row[idx] if idx is not None and idx < len(row) else None

        name = "" if cell("name") is None else _cell_text(cell("name"))
        east, north = _number(cell("east"), comma), _number(cell("north"), comma)
        if not name and east is None and north is None:
            continue
        if not name or east is None or north is None:
            bad.append(number)
            continue
        # Глубина ≤ 0 и уровень воды < 0 — не замер: забой выше устья дал бы
        # скважину «пробуренной» на модуль числа.
        depth = _number(cell("depth"), comma)
        if depth is not None and depth <= 0:
            bad_depth.append(number)
            depth = None
        water = _number(cell("water"), comma)
        if water is not None and water < 0:
            bad_water.append(number)
            water = None
        points.append(
            SurveyedPoint(
                name,
                east,
                north,
                _number(cell("z"), comma),
                depth,
                _number(cell("angle"), comma),
                _number(cell("azimuth"), comma),
                _flag(cell("wet")) if "wet" in mapping else None,
                water,
                line=number,
            )
        )
    if bad:
        warnings.append(f"Строки без номера или координат пропущены: {_listed(bad)}.")
    if bad_depth:
        warnings.append(f"Глубина не больше нуля не прочитана (глубина не замерена) в строках {_listed(bad_depth)}.")
    if bad_water:
        warnings.append(f"Уровень воды меньше нуля не прочитан в строках {_listed(bad_water)}.")
    return points


def _cell_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _text_rows(text: str, warnings: list[str]) -> tuple[list[str], list[tuple[int, list[Any]]], bool]:
    all_lines = text.splitlines()
    if len(all_lines) > MAX_SURVEY_ROWS + 1:
        raise _too_many_rows()
    lines = [(n, ln) for n, ln in enumerate(all_lines, start=1) if ln.strip()]
    if not lines:
        return [], [], False
    delim = _delimiter(lines[0][1], spaces=True)
    header = [c.strip() for c in _split(lines[0][1], delim)]
    if len(header) > MAX_COLUMNS:
        raise SurveyReadError(f"В таблице больше {MAX_COLUMNS} колонок.")
    rows = [(n, _split(ln, delim)) for n, ln in lines[1:]]
    if delim == _SPACES:
        # Через пробелы пустую ячейку и название из двух слов не отличить — не молча.
        ragged = [n for n, cells in rows if len(cells) != len(header)]
        if ragged:
            warnings.append(
                "Таблица через пробелы: в строках "
                f"{_listed(ragged)} число значений не совпадает с заголовком — проверьте колонки "
                "(названия колонок — одним словом, пустые ячейки не допускаются)."
            )
    return header, rows, delim != ","


def _xlsx_rows(data: bytes) -> tuple[list[str], list[tuple[int, list[Any]]], bool]:
    try:
        import zipfile

        import openpyxl

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            unpacked = sum(item.file_size for item in archive.infolist())
        if unpacked > MAX_UNPACKED_BYTES:
            raise SurveyReadError("Книга Excel слишком велика.")
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet = book.worksheets[0]
        grid = []
        for n, row in enumerate(sheet.iter_rows(max_col=MAX_COLUMNS, values_only=True), start=1):
            if n > MAX_SURVEY_ROWS + 1:
                raise _too_many_rows()
            grid.append((n, list(row)))
    except SurveyReadError:
        raise
    except Exception as exc:  # noqa: BLE001 — не книга Excel
        raise SurveyReadError("Файл Excel не прочитан.") from exc
    grid = [(n, row) for n, row in grid if any(c is not None and str(c).strip() for c in row)]
    if not grid:
        return [], [], False
    header = ["" if c is None else str(c).strip() for c in grid[0][1]]
    # Числа в книге — числа; строки с запятой («12,4») разберёт десятичная запятая.
    return header, grid[1:], True


_REQUIRED_LABELS = {"name": "номер скважины", "east": "восток", "north": "север"}


def _map_columns(
    header: list[str],
    explicit: dict[str, str],
    swap_xy: bool | None,
    warnings: list[str],
    disabled: set[str],
) -> dict[str, int]:
    """Колонки по ролям. Явный выбор главнее псевдонимов; пустая строка —
    роль выключена (`disabled`): колонка не ищется по псевдониму, значения нет."""

    lowered = [h.strip().lower() for h in header]
    mapping: dict[str, int] = {}
    for key, title in explicit.items():
        if key not in COLUMN_KEYS:
            raise SurveyReadError(f"Неизвестная колонка «{key}».")
        if title == "":
            if key in _REQUIRED_LABELS:
                raise SurveyReadError(
                    f"Колонку «{_REQUIRED_LABELS[key]}» нельзя отключить: без неё точку не прочитать. Выберите её."
                )
            disabled.add(key)
            continue
        if title not in header:
            raise SurveyReadError(f"В файле нет колонки «{title}».")
        mapping[key] = header.index(title)
    for key, aliases in _ALIASES.items():
        if key in mapping or key in disabled:
            continue
        for idx, title in enumerate(lowered):
            if title in aliases and idx not in mapping.values():
                mapping[key] = idx
                break
    if "east" not in mapping and "north" not in mapping:
        xi = lowered.index("x") if "x" in lowered else None
        yi = lowered.index("y") if "y" in lowered else None
        if xi is not None and yi is not None:
            mapping["north"], mapping["east"] = xi, yi
            if swap_xy:
                mapping["north"], mapping["east"] = yi, xi
                warnings.append("Колонки X/Y переставлены по запросу: X — восток, Y — север.")
            else:
                warnings.append("Колонки X/Y прочитаны как X — север, Y — восток (как в маркшейдерской практике).")
    elif swap_xy and "east" in mapping and "north" in mapping:
        mapping["east"], mapping["north"] = mapping["north"], mapping["east"]
        warnings.append(SWAPPED_TEXT)
    return mapping
