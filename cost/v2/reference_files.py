"""Справочники файлом: книга xlsx (лист на раздел) и JSON-снимок.

Состав колонок берётся из JSON-схемы раздела, поэтому новый раздел или поле
попадают в файл без правок здесь. Модуль не знает ни об API, ни об
интерфейсе: принимает и возвращает `ReferenceSnapshot` / `ReferenceItem`.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from openpyxl import Workbook, load_workbook

from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import REFERENCE_SECTION_DEFINITIONS
from cost.v2.schemas import SECTION_SCHEMAS, section_json_schema

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
JSON_MEDIA_TYPE = "application/json"

TRUE_WORDS = frozenset({"да", "true", "1", "yes", "истина"})
FALSE_WORDS = frozenset({"нет", "false", "0", "no", "ложь"})


class ReferenceFileError(ValueError):
    """Файл не разобран: сообщение называет лист, строку и колонку."""


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    kind: str  # text | bool | date | decimal | json


FIXED_COLUMNS: tuple[Column, ...] = (
    Column("code", "Код", "text"),
    Column("name", "Наименование", "text"),
    Column("is_active", "Активна", "bool"),
    Column("valid_from", "Действует с", "date"),
    Column("valid_to", "Действует по", "date"),
    Column("comment", "Комментарий", "text"),
)
_FIXED_KEYS = {column.key for column in FIXED_COLUMNS}


def exportable_sections() -> list[str]:
    """Разделы со схемой в порядке каталога; устаревшие в файл не идут."""

    return [
        code
        for code, meta in REFERENCE_SECTION_DEFINITIONS.items()
        if code in SECTION_SCHEMAS and not meta.get("deprecated", False)
    ]


def section_columns(section: str) -> list[Column]:
    schema = section_json_schema(section)
    columns = list(FIXED_COLUMNS)
    for key, prop in schema.get("properties", {}).items():
        if prop.get("x-internal") or key in _FIXED_KEYS:
            continue
        columns.append(Column(key, _title(key, prop), _kind(prop)))
    return columns


def _title(key: str, prop: Mapping[str, Any]) -> str:
    title = str(prop.get("title") or prop.get("description") or key)
    unit = prop.get("x-unit")
    return f"{title}, {unit}" if unit else title


def _types(prop: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()
    if "type" in prop:
        found.add(str(prop["type"]))
    for variant in prop.get("anyOf", ()):
        if "type" in variant:
            found.add(str(variant["type"]))
        if "$ref" in variant or "items" in variant:
            found.add("object")
    if "$ref" in prop or "items" in prop:
        found.add("object")
    return found


def _kind(prop: Mapping[str, Any]) -> str:
    if "x-ref" in prop or "enum" in prop:
        return "text"
    types = _types(prop)
    if "boolean" in types:
        return "bool"
    if "array" in types or "object" in types:
        return "json"
    if "number" in types or "integer" in types:
        return "decimal"
    if prop.get("format") == "date":
        return "date"
    return "text"


# --- Экспорт ----------------------------------------------------------------


def export_xlsx(snapshot: ReferenceSnapshot) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for section in exportable_sections():
        sheet = book.create_sheet(section)
        columns = section_columns(section)
        sheet.append([column.key for column in columns])
        sheet.append([column.title for column in columns])
        for item in snapshot.sections.get(section, ()):
            sheet.append([_cell(column, _item_value(item, column.key)) for column in columns])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def export_json(snapshot: ReferenceSnapshot) -> dict[str, Any]:
    return snapshot.to_dict()


def _item_value(item: ReferenceItem, key: str) -> Any:
    if key in _FIXED_KEYS:
        return getattr(item, key)
    return item.payload.get(key)


def _cell(column: Column, value: Any) -> Any:
    if value is None or value == "":
        return None
    if column.kind == "bool":
        return "да" if bool(value) else "нет"
    if column.kind == "date":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if column.kind == "decimal":
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            return str(value)
        return int(number) if number == number.to_integral_value() else float(number)
    if column.kind == "json":
        if value in ([], {}):
            return None
        return json.dumps(value, ensure_ascii=False)
    return str(value)
