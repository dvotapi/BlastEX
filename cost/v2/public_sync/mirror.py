"""Зеркала разделов справочников в схеме ``public``.

У части разделов (породы, нормативы, ставки) аналога в журнале project1 нет:
сопоставлять их не с чем, а видеть их из журнала нужно. Для таких разделов
администратор включает «зеркало» — таблицу ``public.blastex_<раздел>``,
которую приложение само создаёт по схеме раздела и при каждой публикации
приводит к опубликованной ревизии.

Зеркало — производная от схемы раздела, а не отдельное описание таблицы:
колонки, их типы и подписи выводятся из pydantic-модели и её JSON Schema
(``cost/v2/schemas``). Новое поле в схеме доезжает до уже созданной таблицы
само — весь DDL идемпотентный и выполняется перед каждой выгрузкой.

Своей транзакции модуль не открывает и ничего не коммитит: и DDL, и строки
идут в переданной сессии — той же, в которой публикуется ревизия. Иначе
журнал получил бы таблицу с данными ревизии, которой в blastex нет.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from types import UnionType
from typing import Any, Literal, Sequence, Union, get_args, get_origin

from sqlalchemy import text
from sqlalchemy.orm import Session

from cost.v2.models import ReferenceItem
from cost.v2.public_sync.settings import mirrorable_sections
from cost.v2.schemas import SECTION_SCHEMAS, section_json_schema

__all__ = [
    "MirrorColumn",
    "RECORD_COLUMNS",
    "create_table_sql",
    "ensure_mirror",
    "mirror_columns",
    "mirror_table_name",
    "mirror_value",
    "sync_mirror",
]

# Общий префикс таблиц-зеркал: по нему в чужой схеме видно, чьи это строки.
TABLE_PREFIX = "blastex_"

# Роль приложения и имя политики RLS. Таблица в общей схеме закрывается от
# остальных ролей журнала: писать и читать её должно только приложение.
MIRROR_ROLE = "blastex"
MIRROR_POLICY = "blastex_full_access"


@dataclass(frozen=True)
class MirrorColumn:
    """Колонка зеркала: имя, тип PostgreSQL и подпись для журнала.

    Типы колонок по схеме раздела — ``numeric``, ``boolean``, ``text``,
    ``date`` и ``jsonb``; у служебных колонок записи (``RECORD_COLUMNS``)
    добавляется ``timestamptz``.
    """

    name: str
    sql_type: str
    comment: str


# Поля самой записи справочника — одинаковые у всех разделов. Порядок задаёт
# порядок колонок таблицы, поэтому меняется только вместе с ним.
RECORD_COLUMNS: tuple[MirrorColumn, ...] = (
    MirrorColumn("code", "text", "Код записи в справочнике BlastEX"),
    MirrorColumn("name", "text", "Наименование"),
    MirrorColumn("is_active", "boolean", "Запись действует"),
    MirrorColumn("valid_from", "date", "Действует с"),
    MirrorColumn("valid_to", "date", "Действует по"),
    MirrorColumn("source", "text", "Источник записи"),
    MirrorColumn("comment", "text", "Комментарий"),
    MirrorColumn("revision_id", "text", "Ревизия справочников, которой выгружена строка"),
    MirrorColumn("synced_at", "timestamptz", "Момент выгрузки"),
)

_RECORD_NAMES = frozenset(column.name for column in RECORD_COLUMNS)

# Ограничения служебных колонок. Код записи — ключ зеркала: по нему идёт
# обновление строки при повторной выгрузке.
_RECORD_CONSTRAINTS: dict[str, str] = {
    "code": "PRIMARY KEY",
    "name": "NOT NULL DEFAULT ''",
    "is_active": "NOT NULL DEFAULT true",
}

# Аннотация поля схемы → тип колонки. Ключи сравниваются точно, поэтому
# `bool` не попадает в `numeric` вслед за `int`, чьим подклассом он является.
_SCALAR_SQL_TYPES: dict[Any, str] = {
    Decimal: "numeric",
    int: "numeric",
    float: "numeric",
    bool: "boolean",
    str: "text",
    date: "date",
}


def mirror_table_name(section: str) -> str:
    """Имя таблицы-зеркала раздела.

    Здесь же проверяется сам раздел: имя таблицы подставляется в SQL
    напрямую, поэтому оно должно собираться только из известного списка
    ``mirrorable_sections()``. Раздел, выгружаемый прямым сопоставлением
    таблиц (``sites``), и вовсе неизвестное имя — ошибка.
    """

    if section not in mirrorable_sections():
        raise ValueError(f"У раздела «{section}» нет зеркала в схеме public.")
    return f"{TABLE_PREFIX}{section}"


def mirror_columns(section: str) -> list[MirrorColumn]:
    """Колонки зеркала: поля записи, затем поля payload в порядке схемы.

    Служебные поля схемы (``x-internal``, например ключ строки в источнике
    импорта) в журнал не выгружаются: читателю журнала они ничего не говорят.
    """

    return list(_mirror_columns(section))


@lru_cache(maxsize=None)
def _mirror_columns(section: str) -> tuple[MirrorColumn, ...]:
    """Колонки раздела. Схема статична, поэтому считаются один раз."""

    mirror_table_name(section)
    model = SECTION_SCHEMAS[section]
    properties = section_json_schema(section).get("properties") or {}
    columns = list(RECORD_COLUMNS)
    for name, field in model.model_fields.items():
        node = properties.get(name) or {}
        if node.get("x-internal"):
            continue
        columns.append(
            MirrorColumn(
                name=name,
                sql_type=_sql_type(field.annotation),
                comment=_column_comment(name, node),
            )
        )
    return tuple(columns)


def _column_comment(name: str, node: dict[str, Any]) -> str:
    """Подпись колонки: `title` из JSON Schema уже разрешён по-русски."""

    return str(node.get("title") or node.get("description") or name)


def _sql_type(annotation: Any) -> str:
    """Тип колонки по аннотации поля схемы.

    Незнакомая аннотация уезжает в ``jsonb``: зеркало не должно падать из-за
    типа, которого не было в схемах на момент написания модуля.
    """

    if hasattr(annotation, "__metadata__"):  # Annotated[тип, ...]
        return _sql_type(get_args(annotation)[0])
    origin = get_origin(annotation)
    if origin is Literal:
        # Перечисление вариантов — это текст: варианты в схемах строковые.
        return "text"
    if origin in (Union, UnionType):
        variants = [argument for argument in get_args(annotation) if argument is not type(None)]
        return _sql_type(variants[0]) if len(variants) == 1 else "jsonb"
    if origin in (list, tuple, set, frozenset, dict):
        return "jsonb"
    return _SCALAR_SQL_TYPES.get(annotation, "jsonb")


def create_table_sql(section: str) -> list[str]:
    """Идемпотентный DDL зеркала: от пустой базы и от уже созданной таблицы.

    Операторы выполняются перед каждой выгрузкой, поэтому ни один из них не
    должен спорить с уже существующей таблицей: колонка, добавленная в схему
    раздела позже, доезжает отдельным ``ADD COLUMN IF NOT EXISTS``, а политика
    RLS создаётся только если её ещё нет — ``CREATE POLICY`` не знает
    ``IF NOT EXISTS``.

    В SQL подставляются только имя раздела, проверенное ``mirror_table_name``,
    и имена с типами колонок из схемы: пользовательских строк здесь нет.
    """

    table = mirror_table_name(section)
    columns = mirror_columns(section)
    definitions = ", ".join(
        " ".join(
            part
            for part in (f'"{column.name}"', column.sql_type, _RECORD_CONSTRAINTS.get(column.name, ""))
            if part
        )
        for column in RECORD_COLUMNS
    )
    statements = [f'CREATE TABLE IF NOT EXISTS public."{table}" ({definitions})']
    statements.extend(
        f'ALTER TABLE public."{table}" ADD COLUMN IF NOT EXISTS "{column.name}" {column.sql_type}'
        for column in columns
        if column.name not in _RECORD_NAMES
    )
    statements.extend(
        f'COMMENT ON COLUMN public."{table}"."{column.name}" IS \'{_quoted(column.comment)}\''
        for column in columns
    )
    statements.append(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
    statements.append(
        "DO $$ BEGIN\n"
        "    IF NOT EXISTS (\n"
        "        SELECT 1 FROM pg_policies\n"
        f"        WHERE schemaname = 'public' AND tablename = '{table}'\n"
        f"          AND policyname = '{MIRROR_POLICY}'\n"
        "    ) THEN\n"
        f'        CREATE POLICY "{MIRROR_POLICY}" ON public."{table}"\n'
        f"            FOR ALL TO {MIRROR_ROLE} USING (true) WITH CHECK (true);\n"
        "    END IF;\n"
        "END $$;"
    )
    return statements


def _quoted(value: str) -> str:
    """Строковый литерал SQL: подписи наши, но кавычку экранируем всё равно."""

    return value.replace("'", "''")


def ensure_mirror(session: Session, section: str) -> None:
    """Приводит таблицу зеркала к текущей схеме раздела."""

    for statement in create_table_sql(section):
        session.execute(text(statement))


def sync_mirror(
    session: Session,
    section: str,
    revision_id: str,
    items: Sequence[ReferenceItem],
    now: datetime,
) -> tuple[int, int]:
    """Приводит зеркало к ревизии, возвращая ``(записано, деактивировано)``.

    Выгружаются все записи ревизии, включая неактивные: зеркало показывает
    справочник целиком, а не только то, чем сейчас пользуются. Строка,
    которой в ревизии больше нет, из таблицы не удаляется — журнал мог
    сослаться на неё раньше, — а помечается недействующей.
    """

    table = mirror_table_name(section)
    columns = mirror_columns(section)
    rows = [_mirror_row(columns, item, revision_id, now) for item in items]
    if rows:
        session.execute(text(_insert_sql(table, columns)), rows)
    result = session.execute(
        text(
            f'UPDATE public."{table}" SET "is_active" = false, "revision_id" = :revision_id, '
            f'"synced_at" = :synced_at WHERE "code" <> ALL(CAST(:codes AS text[]))'
        ),
        {
            "revision_id": revision_id,
            "synced_at": now,
            # Приведение к `text[]` обязательно: у пустого списка драйверу
            # неоткуда взять тип массива, и сравнение не разобралось бы.
            "codes": [item.code for item in items],
        },
    )
    return len(rows), int(result.rowcount or 0)


def _insert_sql(table: str, columns: Sequence[MirrorColumn]) -> str:
    names = ", ".join(f'"{column.name}"' for column in columns)
    values = ", ".join(_placeholder(column) for column in columns)
    assignments = ", ".join(
        f'"{column.name}" = EXCLUDED."{column.name}"'
        for column in columns
        if column.name != "code"
    )
    return (
        f'INSERT INTO public."{table}" ({names}) VALUES ({values}) '
        f'ON CONFLICT ("code") DO UPDATE SET {assignments}'
    )


def _placeholder(column: MirrorColumn) -> str:
    # JSON приходит строкой: без явного приведения он попал бы в jsonb-колонку
    # как текст, и вставка упала бы на несовпадении типов.
    if column.sql_type == "jsonb":
        return f"CAST(:{column.name} AS jsonb)"
    return f":{column.name}"


def _mirror_row(
    columns: Sequence[MirrorColumn],
    item: ReferenceItem,
    revision_id: str,
    now: datetime,
) -> dict[str, Any]:
    """Значения одной строки зеркала: поля записи плюс поля payload."""

    record: dict[str, Any] = {
        "code": item.code,
        "name": item.name,
        "is_active": item.is_active,
        "valid_from": item.valid_from,
        "valid_to": item.valid_to,
        "source": item.source,
        "comment": item.comment,
        "revision_id": revision_id,
        "synced_at": now,
    }
    return {
        column.name: mirror_value(
            column, record[column.name] if column.name in record else item.payload.get(column.name)
        )
        for column in columns
    }


def mirror_value(column: MirrorColumn, value: Any) -> Any:
    """Значение payload в виде, который примет колонка зеркала.

    Payload прошёл валидацию схемой, но хранится как JSON: число там бывает
    строкой, дата — строкой ISO, а незаполненное поле — пустой строкой.
    Значение, которое не удаётся привести к типу колонки, становится
    ``NULL``: зеркало показывает то, что разобрано, и не роняет публикацию.
    """

    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if column.sql_type == "numeric":
        return _numeric(value)
    if column.sql_type == "boolean":
        if isinstance(value, bool):
            return value
        # Признак из импорта приходит строкой: «false» — это ложь, а не
        # просто непустая строка.
        return str(value).strip().lower() not in {"false", "0", "нет", "no"}
    if column.sql_type == "date":
        return _date(value)
    if column.sql_type == "jsonb":
        return json.dumps(value, ensure_ascii=False, default=str)
    if column.sql_type == "text":
        return value if isinstance(value, str) else str(value)
    return value


def _numeric(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
