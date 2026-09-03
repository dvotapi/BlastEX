# Единые справочники, PR 2: импорт и экспорт справочников файлом

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Опубликованную ревизию справочников можно скачать файлом xlsx или JSON, а файл того же формата — загрузить в черновик страницы «Справочники» и опубликовать обычным путём.

**Architecture:** Модуль `cost/v2/reference_files.py` строит книгу xlsx по JSON-схемам разделов (лист на раздел, строка ключей, строка подписей, данные) и разбирает её обратно в `ReferenceItem`; JSON-формат — тот же объект, что отдаёт `GET /economics/references/snapshot`. Два маршрута в `api/routers/economics.py`: экспорт ревизии файлом и импорт файла в разделы черновика без записи в базу. Фронт добавляет три кнопки в панель публикации и подменяет разделы черновика содержимым файла; дальше действует существующий путь проверка → различия → публикация.

**Tech Stack:** Python 3.12, FastAPI (UploadFile, python-multipart), openpyxl 3.1, Pydantic 2; React 19 + TypeScript + Vite + vitest.

**Spec:** `Docs/specs/2026-09-03-unified-references-design.md`, §8 (формат, API, интерфейс), §3 (модуль `cost/v2/reference_files.py`), §11 (тесты round-trip), §12 пункт 2.

## Global Constraints

- Ветка `feat/references-file-io` создаётся от `feat/unified-references` (PR 1 ещё не слит; спецификация и планы лежат там). PR открывается на базу `feat/unified-references`; после слияния PR 1 база меняется на `main`.
- Поля payload описываются только схемами `cost/v2/schemas/`; экспорт и импорт узнают состав колонок из `section_json_schema(section)`, а не из кода по разделам (CLAUDE.md). Поля с `x-internal` (`legacy_ref`) в файл не выгружаются.
- Импорт ничего не пишет в базу: ответ — разделы в формате `validate`; публикация остаётся единственной точкой записи (спецификация §3, §8).
- Формат xlsx (спецификация §8): лист на раздел, имя листа — ключ раздела; строка 1 — ключи полей (`code`, `name`, `is_active`, `valid_from`, `valid_to`, `comment`, затем поля схемы); строка 2 — русские подписи; данные с третьей строки; ссылки — кодами; булевы — `да`/`нет`; даты — датами Excel; списки и вложенные модели — JSON-строкой в ячейке. Импорт читает ключи из строки 1 и не зависит от подписей; неизвестный лист или колонка — ошибка с именем листа и колонки.
- Формат JSON — объект `GET /economics/references/snapshot` (`revision_id`, `published_at`, `published_by`, `sections`).
- Интерфейс не хранит собственных знаний о полях разделов: кнопки и слияние черновика работают с разделами как с непрозрачными списками записей.
- Тексты интерфейса, комментарии, коммиты — на русском; коммиты завершаются `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; в `git add` только файлы задачи (в каталоге есть посторонние untracked-файлы с суффиксами « 2»/« 3»).
- Python-тесты: `.venv/bin/python -m pytest -q`; фронт: `cd frontend && npx tsc -b && npm test`.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `cost/v2/reference_files.py` (создать) | колонки раздела по схеме; `export_xlsx`, `export_json`; `import_file` (xlsx/JSON) → разделы `ReferenceItem`; `ReferenceFileError` |
| `api/schemas/economics.py` (изменить) | `ReferenceImportResponse` |
| `api/routers/economics.py` (изменить) | `GET /references/export`, `POST /references/import` |
| `frontend/src/api/endpoints.ts` (изменить) | `exportReferences`, `importReferences` |
| `frontend/src/types/economics.ts` (изменить) | `ReferenceImportResult` |
| `frontend/src/pages/references/importDraft.ts` (создать) | чистая функция слияния разделов файла в черновик |
| `frontend/src/pages/references/PublishBar.tsx` (изменить) | кнопки «Экспорт xlsx», «Экспорт JSON», «Импорт файла» |
| `frontend/src/pages/references/ReferencesPage.tsx` (изменить) | обработчики экспорта и импорта |
| `README.md` (изменить) | раздел об импорте и экспорте, строка таблицы API |
| `tests/test_reference_files.py`, `tests/test_api_reference_files.py`, `frontend/src/pages/references/importDraft.test.ts` (создать) | тесты |

---

### Task 0: Ветка

- [ ] **Step 1: Создать ветку от PR 1**

```bash
git checkout feat/unified-references && git checkout -b feat/references-file-io
```

Проверить: `git branch --show-current` → `feat/references-file-io`; `git log --oneline -1` → `cf4d9c1 refactor: убраны мёртвая ветка патча снапшота ...`.

---

### Task 1: Экспорт xlsx и JSON

**Files:**
- Create: `cost/v2/reference_files.py`
- Test: `tests/test_reference_files.py`

**Interfaces:**
- Consumes: `cost.v2.schemas.section_json_schema(section)`, `SECTION_SCHEMAS`; `cost.v2.references.REFERENCE_SECTION_DEFINITIONS`; `cost.v2.models.ReferenceSnapshot`, `ReferenceItem`.
- Produces:
  - `FIXED_COLUMNS: tuple[Column, ...]` и `Column(key, title, kind)` с `kind ∈ {"text", "bool", "date", "decimal", "json"}`;
  - `section_columns(section: str) -> list[Column]` — фиксированные колонки + поля схемы без `x-internal`;
  - `exportable_sections() -> list[str]` — разделы со схемой в порядке `REFERENCE_SECTION_DEFINITIONS`, без `deprecated`;
  - `export_xlsx(snapshot: ReferenceSnapshot) -> bytes`;
  - `export_json(snapshot: ReferenceSnapshot) -> dict[str, Any]` (объект снимка без каталогов);
  - `XLSX_MEDIA_TYPE` = `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_reference_files.py`:

```python
"""Экспорт и импорт справочников файлом (спецификация §8)."""
from __future__ import annotations

import io
import json
from datetime import date

import pytest
from openpyxl import load_workbook

from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import default_reference_snapshot
from cost.v2.schemas import SECTION_SCHEMAS


def _snapshot(**sections) -> ReferenceSnapshot:
    base = dict(default_reference_snapshot().sections)
    base.update({key: tuple(items) for key, items in sections.items()})
    return ReferenceSnapshot(revision_id="REV-FILE", sections=base, published_by="tester")


def _site() -> ReferenceItem:
    return ReferenceItem(
        code="SITE_A",
        name="Карьер А",
        payload={"mobilization_km": "220", "is_watered": True, "customer_code": "CP_1"},
        valid_from=date(2026, 1, 1),
        comment="тест",
    )


def _crew() -> ReferenceItem:
    return ReferenceItem(
        code="CREW_1",
        name="Бригада",
        payload={"package_code": "PKG_DRILL", "members": [{"position_code": "POS_DRILLER", "headcount": "2"}]},
    )


class TestColumns:
    def test_fixed_columns_come_first_and_internal_fields_are_hidden(self):
        from cost.v2.reference_files import FIXED_COLUMNS, section_columns

        columns = section_columns("sites")
        assert [c.key for c in columns[: len(FIXED_COLUMNS)]] == [
            "code", "name", "is_active", "valid_from", "valid_to", "comment",
        ]
        keys = [c.key for c in columns]
        assert "legacy_ref" not in keys
        assert "mobilization_km" in keys and "is_watered" in keys and "customer_code" in keys

    def test_kinds_follow_the_schema(self):
        from cost.v2.reference_files import section_columns

        kinds = {c.key: c.kind for c in section_columns("sites")}
        assert kinds["mobilization_km"] == "decimal"
        assert kinds["is_watered"] == "bool"
        assert kinds["customer_code"] == "text"
        assert kinds["valid_from"] == "date"
        crew = {c.key: c.kind for c in section_columns("crew_templates")}
        assert crew["members"] == "json"
        materials = {c.key: c.kind for c in section_columns("materials")}
        assert materials["storage_class"] == "text"

    def test_titles_carry_units(self):
        from cost.v2.reference_files import section_columns

        titles = {c.key: c.title for c in section_columns("sites")}
        assert titles["mobilization_km"] == "Плечо мобилизации, км"
        assert titles["code"] == "Код"

    def test_every_schema_section_is_exportable(self):
        from cost.v2.reference_files import exportable_sections

        assert set(exportable_sections()) == set(SECTION_SCHEMAS)
        assert all(len(name) <= 31 for name in exportable_sections())


class TestExport:
    def test_xlsx_has_a_sheet_per_section_with_keys_titles_and_rows(self):
        from cost.v2.reference_files import export_xlsx

        book = load_workbook(io.BytesIO(export_xlsx(_snapshot(sites=[_site()], crew_templates=[_crew()]))))
        assert "sites" in book.sheetnames and "crew_templates" in book.sheetnames
        sheet = book["sites"]
        keys = [cell.value for cell in sheet[1]]
        titles = [cell.value for cell in sheet[2]]
        assert keys[:6] == ["code", "name", "is_active", "valid_from", "valid_to", "comment"]
        assert titles[:2] == ["Код", "Наименование"]
        row = {key: cell.value for key, cell in zip(keys, sheet[3])}
        assert row["code"] == "SITE_A"
        assert row["name"] == "Карьер А"
        assert row["is_active"] == "да"
        assert row["is_watered"] == "да"
        assert row["valid_from"] == date(2026, 1, 1) or getattr(row["valid_from"], "date", lambda: None)() == date(2026, 1, 1)
        assert row["mobilization_km"] == 220
        assert row["customer_code"] == "CP_1"
        assert row["comment"] == "тест"
        crew = book["crew_templates"]
        crew_keys = [cell.value for cell in crew[1]]
        crew_row = {key: cell.value for key, cell in zip(crew_keys, crew[3])}
        assert json.loads(crew_row["members"]) == [{"position_code": "POS_DRILLER", "headcount": "2"}]

    def test_empty_section_still_has_header_rows(self):
        from cost.v2.reference_files import export_xlsx

        book = load_workbook(io.BytesIO(export_xlsx(_snapshot())))
        sheet = book["sites"]
        assert sheet.max_row == 2
        assert sheet["A1"].value == "code"

    def test_json_export_is_the_snapshot_object(self):
        from cost.v2.reference_files import export_json

        payload = export_json(_snapshot(sites=[_site()]))
        assert payload["revision_id"] == "REV-FILE"
        assert payload["published_by"] == "tester"
        assert payload["sections"]["sites"][0]["code"] == "SITE_A"
        assert payload["sections"]["sites"][0]["valid_from"] == "2026-01-01"
        assert "section_catalog" not in payload
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_reference_files.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'cost.v2.reference_files'`.

- [ ] **Step 3: Написать модуль экспорта**

Создать `cost/v2/reference_files.py`:

```python
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
```

- [ ] **Step 4: Прогнать тесты экспорта**

Run: `.venv/bin/python -m pytest tests/test_reference_files.py -q`
Expected: PASS всех тестов классов `TestColumns` и `TestExport`. Если `test_titles_carry_units` падает: проверить `title` поля `mobilization_km` в `cost/v2/schemas/organization.py` («Плечо мобилизации») и `x-unit` «км».

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/reference_files.py tests/test_reference_files.py
git commit -m "feat(cost): экспорт справочников в xlsx и JSON по схемам разделов

Лист на раздел, строка ключей и строка подписей с единицами, булевы
«да/нет», даты датами, вложенные модели JSON-строкой.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Импорт xlsx и JSON

**Files:**
- Modify: `cost/v2/reference_files.py`
- Test: `tests/test_reference_files.py`

**Interfaces:**
- Produces: `import_file(name: str, data: bytes) -> dict[str, list[ReferenceItem]]` — по расширению `.xlsx` или `.json`; `import_xlsx(data: bytes) -> dict[str, list[ReferenceItem]]`; `import_json(data: bytes) -> dict[str, list[ReferenceItem]]`; ошибки — `ReferenceFileError` с русским сообщением.
- Правила xlsx: пустые листы (только заголовки) дают пустой раздел; строки без `code` и `name` пропускаются целиком, если все ячейки пусты, иначе ошибка «нет кода»; пустая ячейка payload — поле не задаётся (действует умолчание схемы); числа — строкой нормализованного `Decimal` (`"220"`, `"0.85"`); `source` = `Импорт xlsx`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/test_reference_files.py`:

```python
class TestImport:
    def test_xlsx_round_trip_restores_items(self):
        from cost.v2.reference_files import export_xlsx, import_xlsx

        sections = import_xlsx(export_xlsx(_snapshot(sites=[_site()], crew_templates=[_crew()])))
        site = sections["sites"][0]
        assert site.code == "SITE_A" and site.name == "Карьер А"
        assert site.is_active is True
        assert site.valid_from == date(2026, 1, 1) and site.valid_to is None
        assert site.comment == "тест"
        assert site.source == "Импорт xlsx"
        assert site.payload["mobilization_km"] == "220"
        assert site.payload["is_watered"] is True
        assert site.payload["customer_code"] == "CP_1"
        assert "legacy_ref" not in site.payload
        assert "distance_from_base_km" not in site.payload
        crew = sections["crew_templates"][0]
        assert crew.payload["members"] == [{"position_code": "POS_DRILLER", "headcount": "2"}]
        assert sections["rocks"] == []

    def test_round_trip_of_the_default_snapshot_validates(self):
        from cost.v2.reference_files import export_xlsx, import_xlsx
        from cost.v2.references import has_validation_errors, validate_reference_sections

        snapshot = default_reference_snapshot()
        sections = import_xlsx(export_xlsx(snapshot))
        assert not has_validation_errors(validate_reference_sections(sections))
        assert {i.code for i in sections["units"]} == {i.code for i in snapshot.sections["units"]}
        assert [i.code for i in sections["operations"]] == [i.code for i in snapshot.sections["operations"]]

    def test_unknown_sheet_and_column_are_reported_by_name(self):
        from cost.v2.reference_files import ReferenceFileError, export_xlsx, import_xlsx

        book = load_workbook(io.BytesIO(export_xlsx(_snapshot())))
        book.create_sheet("прочее").append(["code", "name"])
        with pytest.raises(ReferenceFileError, match="лист «прочее»"):
            import_xlsx(_bytes(book))

        book = load_workbook(io.BytesIO(export_xlsx(_snapshot())))
        book["sites"].cell(row=1, column=book["sites"].max_column + 1, value="mobilisation")
        with pytest.raises(ReferenceFileError, match="колонка «mobilisation».*лист «sites»"):
            import_xlsx(_bytes(book))

    def test_bad_boolean_names_sheet_row_and_column(self):
        from cost.v2.reference_files import ReferenceFileError, export_xlsx, import_xlsx

        book = load_workbook(io.BytesIO(export_xlsx(_snapshot(sites=[_site()]))))
        sheet = book["sites"]
        keys = [cell.value for cell in sheet[1]]
        sheet.cell(row=3, column=keys.index("is_watered") + 1, value="возможно")
        with pytest.raises(ReferenceFileError, match="лист «sites», строка 3, колонка «is_watered»"):
            import_xlsx(_bytes(book))

    def test_row_without_code_is_an_error_but_blank_rows_are_skipped(self):
        from cost.v2.reference_files import ReferenceFileError, export_xlsx, import_xlsx

        book = load_workbook(io.BytesIO(export_xlsx(_snapshot(sites=[_site()]))))
        sheet = book["sites"]
        sheet.append([None] * sheet.max_column)
        assert len(import_xlsx(_bytes(book))["sites"]) == 1
        sheet.append([None, "Без кода"])
        with pytest.raises(ReferenceFileError, match="строка 5.*нет кода"):
            import_xlsx(_bytes(book))

    def test_json_import_reads_snapshot_object(self):
        from cost.v2.reference_files import ReferenceFileError, export_json, import_json

        payload = export_json(_snapshot(sites=[_site()]))
        sections = import_json(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        assert sections["sites"][0].code == "SITE_A"
        assert sections["sites"][0].valid_from == date(2026, 1, 1)
        with pytest.raises(ReferenceFileError, match="раздел «other»"):
            import_json(json.dumps({"sections": {"other": []}}).encode("utf-8"))
        with pytest.raises(ReferenceFileError, match="sections"):
            import_json(b"{}")
        with pytest.raises(ReferenceFileError, match="JSON"):
            import_json(b"not json")

    def test_import_file_dispatches_by_extension(self):
        from cost.v2.reference_files import ReferenceFileError, export_json, export_xlsx, import_file

        assert "sites" in import_file("refs.XLSX", export_xlsx(_snapshot()))
        assert "sites" in import_file("refs.json", json.dumps(export_json(_snapshot())).encode("utf-8"))
        with pytest.raises(ReferenceFileError, match="xlsx или JSON"):
            import_file("refs.csv", b"")


def _bytes(book) -> bytes:
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_reference_files.py -q -k Import`
Expected: FAIL, `ImportError: cannot import name 'import_xlsx'`.

- [ ] **Step 3: Написать импорт**

Дописать в конец `cost/v2/reference_files.py`:

```python
# --- Импорт -----------------------------------------------------------------


def import_file(name: str, data: bytes) -> dict[str, list[ReferenceItem]]:
    lowered = name.lower()
    if lowered.endswith(".xlsx"):
        return import_xlsx(data)
    if lowered.endswith(".json"):
        return import_json(data)
    raise ReferenceFileError("Поддерживаются файлы xlsx или JSON.")


def import_json(data: bytes) -> dict[str, list[ReferenceItem]]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceFileError(f"Файл не является корректным JSON: {exc}") from exc
    raw_sections = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(raw_sections, dict):
        raise ReferenceFileError("В JSON нет объекта «sections» с разделами.")
    known = set(exportable_sections())
    sections: dict[str, list[ReferenceItem]] = {}
    for section, rows in raw_sections.items():
        if section not in known:
            raise ReferenceFileError(f"Неизвестный раздел «{section}».")
        if not isinstance(rows, list):
            raise ReferenceFileError(f"Раздел «{section}» должен быть списком записей.")
        sections[section] = [ReferenceItem.from_dict(row) for row in rows]
    return sections


def import_xlsx(data: bytes) -> dict[str, list[ReferenceItem]]:
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl бросает разные классы для битых файлов
        raise ReferenceFileError(f"Файл не открывается как книга xlsx: {exc}") from exc
    known = set(exportable_sections())
    sections: dict[str, list[ReferenceItem]] = {}
    for sheet in book.worksheets:
        section = sheet.title
        if section not in known:
            raise ReferenceFileError(f"Неизвестный лист «{section}»: такого раздела нет.")
        columns = {column.key: column for column in section_columns(section)}
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            sections[section] = []
            continue
        keys: list[str | None] = [str(key).strip() if key not in (None, "") else None for key in header]
        for key in keys:
            if key is not None and key not in columns:
                raise ReferenceFileError(f"Неизвестная колонка «{key}» на листе «{section}».")
        next(rows, None)  # строка подписей
        items: list[ReferenceItem] = []
        for row_no, values in enumerate(rows, start=3):
            cells = {key: value for key, value in zip(keys, values) if key is not None}
            if all(value in (None, "") for value in cells.values()):
                continue
            items.append(_item_from_cells(section, row_no, cells, columns))
        sections[section] = items
    return sections


def _item_from_cells(
    section: str,
    row_no: int,
    cells: Mapping[str, Any],
    columns: Mapping[str, Column],
) -> ReferenceItem:
    def parse(key: str) -> Any:
        return _parse(section, row_no, columns[key], cells.get(key))

    code = parse("code") if "code" in cells else None
    if not code:
        raise ReferenceFileError(f"Лист «{section}», строка {row_no}: нет кода записи.")
    name = parse("name") if "name" in cells else None
    if not name:
        raise ReferenceFileError(f"Лист «{section}», строка {row_no}: нет наименования записи.")
    is_active = parse("is_active") if "is_active" in cells else None
    payload: dict[str, Any] = {}
    for key in cells:
        if key in _FIXED_KEYS:
            continue
        value = parse(key)
        if value is not None:
            payload[key] = value
    return ReferenceItem(
        code=str(code),
        name=str(name),
        payload=payload,
        is_active=True if is_active is None else bool(is_active),
        valid_from=parse("valid_from") if "valid_from" in cells else None,
        valid_to=parse("valid_to") if "valid_to" in cells else None,
        source="Импорт xlsx",
        comment=str(parse("comment") or "") if "comment" in cells else "",
    )


def _parse(section: str, row_no: int, column: Column, value: Any) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    where = f"лист «{section}», строка {row_no}, колонка «{column.key}»"
    if column.kind == "bool":
        if isinstance(value, bool):
            return value
        word = str(value).strip().lower()
        if word in TRUE_WORDS:
            return True
        if word in FALSE_WORDS:
            return False
        raise ReferenceFileError(f"{where}: ожидается «да» или «нет», получено «{value}».")
    if column.kind == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError as exc:
            raise ReferenceFileError(f"{where}: ожидается дата, получено «{value}».") from exc
    if column.kind == "decimal":
        try:
            number = Decimal(str(value).strip().replace(",", "."))
        except InvalidOperation as exc:
            raise ReferenceFileError(f"{where}: ожидается число, получено «{value}».") from exc
        return format(number.normalize(), "f")
    if column.kind == "json":
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(str(value))
        except json.JSONDecodeError as exc:
            raise ReferenceFileError(f"{where}: ожидается JSON, получено «{value}».") from exc
    return str(value).strip()
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_reference_files.py -q`
Expected: PASS. Если `test_round_trip_of_the_default_snapshot_validates` падает на числах системных записей (`factor_to_base: 1` → `"1"`), это допустимо схемой (`Decimal` принимает строку); если падает на `required`-полях, которые в файле пусты — посмотреть сообщение и убедиться, что такое поле не пустое в самом снимке.

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/reference_files.py tests/test_reference_files.py
git commit -m "feat(cost): импорт справочников из xlsx и JSON с проверкой листов и колонок

Неизвестный лист или колонка, неверные булевы, даты, числа и JSON
называют лист, строку и колонку; пустые ячейки оставляют умолчания схемы.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: API экспорта и импорта

**Files:**
- Modify: `api/schemas/economics.py` (после `ReferenceValidationResponse`)
- Modify: `api/routers/economics.py` (после `get_reference_revision`)
- Modify: `README.md` (таблица API и раздел о справочниках)
- Test: `tests/test_api_reference_files.py`

**Interfaces:**
- `GET /api/v1/economics/references/export?format=xlsx|json&revision_id=` — `require_internal_access`; ответ файлом: xlsx с `Content-Disposition: attachment; filename="references-<8 символов ревизии>.xlsx"`, JSON — объект `export_json` с тем же заголовком и расширением `.json`; неизвестный `format` → 422.
- `POST /api/v1/economics/references/import` — `require_reference_editor`, multipart-поле `file`; ответ `ReferenceImportResponse(file_name, counts, sections)`; `ReferenceFileError` → 422 `{"detail": {"message": ...}}`; ничего не пишется.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_api_reference_files.py`:

```python
"""`GET /economics/references/export` и `POST /economics/references/import`."""
from __future__ import annotations

import io
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.routers import economics
from api.security import SESSION_COOKIE, create_session_token
from api.services.economics_service import get_economics_repository
from cost.v2.models import ReferenceItem
from cost.v2.repository import InMemoryEconomicsRepository


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(economics.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


def _publish_site(repository: InMemoryEconomicsRepository) -> str:
    current = repository.get_reference_snapshot("default")
    sections = dict(current.sections)
    sections["sites"] = (ReferenceItem("SITE_X", "Карьер X", {"mobilization_km": "15"}),)
    return repository.publish_references("default", "tester", current.revision_id, sections, "test").revision_id


def test_export_xlsx_returns_a_workbook_attachment(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    revision = _publish_site(repository)
    response = client.get("/api/v1/economics/references/export?format=xlsx")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert response.headers["content-disposition"] == f'attachment; filename="references-{revision[:8]}.xlsx"'
    book = load_workbook(io.BytesIO(response.content))
    assert book["sites"]["A3"].value == "SITE_X"


def test_export_json_matches_snapshot_and_accepts_revision_id(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    first = repository.get_reference_snapshot("default").revision_id
    second = _publish_site(repository)
    latest = client.get("/api/v1/economics/references/export?format=json")
    assert latest.status_code == 200
    assert latest.headers["content-disposition"].endswith(f'references-{second[:8]}.json"')
    assert latest.json()["sections"]["sites"][0]["code"] == "SITE_X"
    old = client.get(f"/api/v1/economics/references/export?format=json&revision_id={first}")
    assert old.json()["revision_id"] == first
    assert old.json()["sections"]["sites"] == []


def test_export_rejects_unknown_format(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    assert client.get("/api/v1/economics/references/export?format=csv").status_code == 422


def test_import_xlsx_returns_sections_without_writing(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    exported = client.get("/api/v1/economics/references/export?format=xlsx").content
    before = repository.get_reference_snapshot("default").revision_id
    response = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.xlsx", exported, "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["file_name"] == "refs.xlsx"
    assert body["counts"]["units"] > 0
    assert body["sections"]["units"][0]["source"] == "Импорт xlsx"
    assert repository.get_reference_snapshot("default").revision_id == before


def test_import_json_and_bad_file(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    snapshot = client.get("/api/v1/economics/references/export?format=json").json()
    ok = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.json", json.dumps(snapshot).encode("utf-8"), "application/json")},
    )
    assert ok.status_code == 200
    bad = client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.json", b"not json", "application/json")},
    )
    assert bad.status_code == 422
    assert "JSON" in bad.json()["detail"]["message"]


def test_user_cannot_import(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    token = create_session_token("user@example.ru", "user", "default", int(time.time()) + 3600)
    user_client = TestClient(client.app)
    user_client.cookies.set(SESSION_COOKIE, token)
    response = user_client.post(
        "/api/v1/economics/references/import",
        files={"file": ("refs.json", b"{}", "application/json")},
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_api_reference_files.py -q`
Expected: FAIL, статус 404 на новых маршрутах.

- [ ] **Step 3: Схема ответа**

В `api/schemas/economics.py` после `ReferenceValidationResponse` добавить:

```python
class ReferenceImportResponse(BaseModel):
    """Разделы, разобранные из файла: ничего не записано, черновик заменяет их у себя."""

    file_name: str
    counts: dict[str, int] = Field(default_factory=dict)
    sections: dict[str, list[ReferenceItemSchema]]
```

- [ ] **Step 4: Маршруты**

В `api/routers/economics.py`:
- дополнить импорты: `from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status`, `from fastapi.responses import JSONResponse, Response`; `ReferenceImportResponse` из `api.schemas.economics`; `from cost.v2.reference_files import XLSX_MEDIA_TYPE, ReferenceFileError, export_json, export_xlsx, import_file`;
- после `get_reference_revision` добавить:

```python
@router.get("/references/export")
def export_references(
    format: str = "xlsx",
    revision_id: str | None = None,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> Response:
    """Опубликованная ревизия файлом: книга xlsx (лист на раздел) или JSON-снимок."""

    if format not in {"xlsx", "json"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Формат экспорта: xlsx или json.",
        )
    organization_id, _ = _identity(session)
    try:
        snapshot = repository.get_reference_snapshot(organization_id, revision_id)
    except Exception as exc:
        raise repository_error(exc) from exc
    file_name = f"references-{snapshot.revision_id[:8]}.{format}"
    disposition = f'attachment; filename="{file_name}"'
    if format == "json":
        return JSONResponse(export_json(snapshot), headers={"Content-Disposition": disposition})
    return Response(
        export_xlsx(snapshot),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": disposition},
    )


@router.post("/references/import", response_model=ReferenceImportResponse)
async def import_references(
    file: UploadFile = File(...),
    _session: dict[str, object] = Depends(require_reference_editor),
) -> ReferenceImportResponse:
    """Файл → разделы черновика. В базу ничего не пишется: дальше проверка и публикация."""

    data = await file.read()
    try:
        sections = import_file(file.filename or "", data)
    except ReferenceFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc)},
        ) from exc
    return ReferenceImportResponse(
        file_name=file.filename or "",
        counts={section: len(items) for section, items in sections.items()},
        sections={
            section: [ReferenceItemSchema.model_validate(item.to_dict()) for item in items]
            for section, items in sections.items()
        },
    )
```

Проверить, что `ReferenceItemSchema` импортирован в роутере (`grep -n "ReferenceItemSchema" api/routers/economics.py`); если нет — добавить в импорт из `api.schemas.economics`.

- [ ] **Step 5: README**

В таблице API (строка `| GET/POST | /economics/references/* | ...`) дополнить описание: «Снапшот, валидация, публикация, история ревизий, экспорт файлом (`export?format=xlsx|json`) и импорт файла (`import`) Cost V2». В раздел о странице «Справочники» (около строки 324) добавить абзац:

```
Справочники можно скачать файлом («Экспорт xlsx», «Экспорт JSON») и загрузить
обратно («Импорт файла»): xlsx — лист на раздел, первая строка — ключи полей,
вторая — подписи, данные с третьей; ссылки кодами, булевы «да»/«нет», списки
JSON-строкой. Импорт заменяет в черновике разделы из файла, остальные не
трогает; в базу попадает только публикация после проверки.
```

- [ ] **Step 6: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_api_reference_files.py tests/test_api_economics.py tests/test_api_reference_schema.py -q`
Expected: PASS.

- [ ] **Step 7: Коммит**

```bash
git add api/schemas/economics.py api/routers/economics.py README.md tests/test_api_reference_files.py
git commit -m "feat(api): экспорт ревизии справочников файлом и импорт файла в черновик

GET /economics/references/export отдаёт xlsx или JSON, POST
/economics/references/import разбирает файл в разделы без записи в базу.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Кнопки на странице «Справочники»

**Files:**
- Modify: `frontend/src/types/economics.ts`, `frontend/src/api/endpoints.ts` (блок `economics`)
- Create: `frontend/src/pages/references/importDraft.ts`, `frontend/src/pages/references/importDraft.test.ts`
- Modify: `frontend/src/pages/references/PublishBar.tsx`, `frontend/src/pages/references/ReferencesPage.tsx`

**Interfaces:**
- `api.economics.exportReferences(format: "xlsx" | "json", revisionId?: string): Promise<void>` — скачивает файл (шаблон `exportCsv` в `endpoints.ts`);
- `api.economics.importReferences(file: File): Promise<ReferenceImportResult>` через `postFile`;
- `mergeImportedSections(draft, imported, makeRowId) -> { draft, replaced: string[] }` в `importDraft.ts`;
- `PublishBar` получает `onExportXlsx`, `onExportJson`, `onImport(file: File)`.

- [ ] **Step 1: Тест функции слияния**

Создать `frontend/src/pages/references/importDraft.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { mergeImportedSections } from "./importDraft";
import type { EconomicsReferenceItem } from "../../types/economics";

function item(code: string): EconomicsReferenceItem {
  return { code, name: code, payload: {}, is_active: true, valid_from: null, valid_to: null, source: "", comment: "", revision: 1 };
}

describe("mergeImportedSections", () => {
  it("заменяет разделы из файла и не трогает остальные", () => {
    let n = 0;
    const draft = {
      sites: [{ ...item("OLD"), row_id: "r1" }],
      rocks: [{ ...item("ROCK"), row_id: "r2" }],
    };
    const result = mergeImportedSections(draft, { sites: [item("NEW_A"), item("NEW_B")] }, () => `id-${++n}`);
    expect(result.replaced).toEqual(["sites"]);
    expect(result.draft.sites.map((row) => row.code)).toEqual(["NEW_A", "NEW_B"]);
    expect(result.draft.sites.map((row) => row.row_id)).toEqual(["id-1", "id-2"]);
    expect(result.draft.rocks).toBe(draft.rocks);
  });

  it("пустой раздел файла очищает раздел черновика", () => {
    const draft = { sites: [{ ...item("OLD"), row_id: "r1" }] };
    const result = mergeImportedSections(draft, { sites: [] }, () => "x");
    expect(result.draft.sites).toEqual([]);
    expect(result.replaced).toEqual(["sites"]);
  });
});
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && npx vitest run src/pages/references/importDraft.test.ts`
Expected: FAIL, модуль не найден.

- [ ] **Step 3: Функция слияния, типы, эндпоинты**

Создать `frontend/src/pages/references/importDraft.ts`:

```ts
import type { EconomicsReferenceItem } from "../../types/economics";
import type { DraftItem } from "./RecordForm";

export type DraftSections = Record<string, DraftItem[]>;

/**
 * Разделы из файла заменяют одноимённые разделы черновика целиком; разделы,
 * которых в файле нет, остаются как были. Страница не знает полей записей —
 * только код и состав разделов.
 */
export function mergeImportedSections(
  draft: DraftSections,
  imported: Record<string, EconomicsReferenceItem[]>,
  makeRowId: () => string,
): { draft: DraftSections; replaced: string[] } {
  const next: DraftSections = { ...draft };
  const replaced: string[] = [];
  for (const [section, items] of Object.entries(imported)) {
    next[section] = items.map((item) => ({ ...item, row_id: makeRowId() }));
    replaced.push(section);
  }
  return { draft: next, replaced };
}
```

В `frontend/src/types/economics.ts` после `ReferenceValidation` добавить:

```ts
export type ReferenceImportResult = {
  file_name: string;
  counts: Record<string, number>;
  sections: Record<string, EconomicsReferenceItem[]>;
};
```

В `frontend/src/api/endpoints.ts` в блок `economics` после `revisions` добавить (и импортировать тип `ReferenceImportResult` из `../types/economics`; `postFile` уже импортирован из `./client`):

```ts
    exportReferences: async (format: "xlsx" | "json", revisionId?: string) => {
      const query = new URLSearchParams({ format });
      if (revisionId) query.set("revision_id", revisionId);
      const response = await fetch(`${V1}/economics/references/export?${query}`, { credentials: "include" });
      if (!response.ok) throw new Error("Не удалось экспортировать справочники.");
      const disposition = response.headers.get("content-disposition") ?? "";
      const match = /filename="([^"]+)"/.exec(disposition);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = match?.[1] ?? `references.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    },
    importReferences: (file: File) =>
      postFile<ReferenceImportResult>(`${V1}/economics/references/import`, file),
```

- [ ] **Step 4: Панель публикации**

В `frontend/src/pages/references/PublishBar.tsx` добавить пропсы `onExportXlsx: () => void`, `onExportJson: () => void`, `onImport: (file: File) => void` (в деструктуризацию и в тип), импортировать `useRef` из `react`, и перед `<input value={comment} ...>` вставить:

```tsx
      <input
        ref={fileInput}
        type="file"
        accept=".xlsx,.json"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onImport(file);
          event.target.value = "";
        }}
      />
      <button type="button" className="ref-ghost-button" onClick={onExportXlsx} disabled={busy}>
        Экспорт xlsx
      </button>
      <button type="button" className="ref-ghost-button" onClick={onExportJson} disabled={busy}>
        Экспорт JSON
      </button>
      <button
        type="button"
        className="ref-ghost-button"
        onClick={() => fileInput.current?.click()}
        disabled={!canEdit || busy}
      >
        Импорт файла
      </button>
```

где в начале компонента `const fileInput = useRef<HTMLInputElement>(null);`.

- [ ] **Step 5: Обработчики на странице**

В `frontend/src/pages/references/ReferencesPage.tsx`:
- импортировать `mergeImportedSections` из `./importDraft`; заменить локальный тип `DraftSections` на импорт из `./importDraft`, если он объявлен идентично (иначе оставить локальный и привести типы);
- после функции `discard()` добавить:

```tsx
  async function exportReferences(format: "xlsx" | "json") {
    setBusy(true);
    setError("");
    try {
      await api.economics.exportReferences(format, snapshot?.revision_id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось экспортировать справочники.");
    } finally {
      setBusy(false);
    }
  }

  async function importReferences(file: File) {
    if (!canEdit) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.economics.importReferences(file);
      const merged = mergeImportedSections(draft, result.sections, rowId);
      setDraft(merged.draft);
      // Новые для опубликованной ревизии записи помечаем как новые: список и
      // форма показывают их так же, как добавленные вручную.
      setNewRows((current) => {
        const next = new Set(current);
        for (const section of merged.replaced) {
          for (const row of merged.draft[section] ?? []) {
            if (!publishedByCode.has(`${section}::${row.code}`)) next.add(row.row_id);
          }
        }
        return next;
      });
      setSelectedRow("");
      setIssues([]);
      if (merged.replaced.length && !merged.replaced.includes(activeSection)) setActiveSection(merged.replaced[0]);
      const validation = await api.economics.validateReferences(toSections(merged.draft));
      setIssues(validation.issues);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось загрузить файл.");
    } finally {
      setBusy(false);
    }
  }
```

- в `<PublishBar ...>` добавить `onExportXlsx={() => void exportReferences("xlsx")}`, `onExportJson={() => void exportReferences("json")}`, `onImport={(file) => void importReferences(file)}`.

Проверить, что `publishedByCode` (строка ~132) объявлен выше обработчика и является `Map` с ключами `section::code`; `rowId` — функция модуля (строка ~22).

- [ ] **Step 6: Сборка и тесты**

Run: `cd frontend && npx tsc -b && npm test`
Expected: `tsc` чисто; vitest PASS (включая новый тест).

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/types/economics.ts frontend/src/api/endpoints.ts frontend/src/pages/references/importDraft.ts frontend/src/pages/references/importDraft.test.ts frontend/src/pages/references/PublishBar.tsx frontend/src/pages/references/ReferencesPage.tsx
git commit -m "feat(frontend): экспорт и импорт справочников файлом на странице «Справочники»

Кнопки «Экспорт xlsx», «Экспорт JSON», «Импорт файла»; файл заменяет
разделы черновика, дальше обычная проверка и публикация.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Проверка в браузере

- [ ] **Step 1: Запустить API и фронт**

Конфигурации `api-cost-v2` и `frontend` из `.claude/launch.json` через Browser pane; вход `admin@example.ru` / `admin123`.

- [ ] **Step 2: Проверить сценарий**

1. «Справочники» → «Экспорт xlsx»: скачивается `references-<8 символов>.xlsx`; открыть через openpyxl в терминале и убедиться, что лист `sites` содержит 10 объектов и строку подписей.
2. «Экспорт JSON»: скачивается `.json` с `revision_id` текущей ревизии.
3. Изменить в скачанном xlsx у одного объекта `mobilization_km` (через openpyxl в терминале, сохранить как новый файл), «Импорт файла» → в разделе «Карьеры и объекты» строка помечена изменённой, проверка без ошибок, «Опубликовать ревизию N» создаёт ревизию; после перезагрузки значение на месте.
4. Импортировать файл с неизвестной колонкой: сообщение об ошибке с именем листа и колонки, черновик не изменён.
5. Импортировать JSON, скачанный в п. 2, поверх черновика: различий нет, кнопка публикации неактивна.

Через `read_console_messages` и `preview_logs` убедиться, что ошибок нет. Скриншоты панели с новыми кнопками и сообщения об ошибке импорта.

- [ ] **Step 3: Полный прогон**

```bash
.venv/bin/python -m pytest -q && cd frontend && npx tsc -b && npm test && cd ..
```

Expected: PASS. Правки по итогам проверки — отдельным коммитом `fix(...)` с объяснением. PR открывается на базу `feat/unified-references` с заголовком «Единые справочники, PR 2: импорт и экспорт справочников файлом».

---

## Самопроверка плана

- Спецификация §8: формат xlsx (Task 1–2), JSON (Task 1–2), API (Task 3), интерфейс и правило «импорт заменяет разделы из файла» (Task 4), round-trip и ошибки с именами (Task 2), проверка в браузере (Task 5).
- §3: модуль `cost/v2/reference_files.py` не знает об интерфейсе (Task 1–2), всё для фронта через `api/` (Task 3).
- Типы: `Column`, `FIXED_COLUMNS`, `section_columns`, `exportable_sections`, `export_xlsx`, `export_json`, `import_file`, `import_xlsx`, `import_json`, `ReferenceFileError`, `XLSX_MEDIA_TYPE` (Task 1–2) используются в Task 3 с теми же именами; `ReferenceImportResponse` (Task 3) ↔ `ReferenceImportResult` (Task 4) с одинаковыми полями `file_name`, `counts`, `sections`; `mergeImportedSections` (Task 4) вызывается с `(draft, result.sections, rowId)`.
