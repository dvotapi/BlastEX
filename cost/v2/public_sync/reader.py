"""Чтение таблиц схемы ``public`` (журнал буровых работ project1).

Читается только то, что перечислено в ``TABLES``, и только на чтение: в
``public`` этот модуль ничего не пишет. Схема принадлежит другой системе,
поэтому её недоступность (нет таблицы, нет прав, база не отвечает) — это не
поломка приложения, а сообщение пользователю: ``PublicUnavailable`` ловится
на уровне API и показывается плашкой, страница «Справочники» продолжает
работать.
"""
from __future__ import annotations

from typing import Protocol

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from cost.v2.public_sync.mapping import TABLES, PublicRow, PublicSnapshot

__all__ = [
    "PublicReader",
    "PublicUnavailable",
    "SqlPublicReader",
    "StaticPublicReader",
    "reason",
]


class PublicUnavailable(RuntimeError):
    """Схема ``public`` недоступна: нет таблицы, прав или соединения."""


class PublicReader(Protocol):
    def read(self) -> PublicSnapshot: ...


class SqlPublicReader:
    """Читает таблицы ``public`` из той же базы, где живёт схема blastex.

    Обычно читатель получает ``Engine`` и открывает соединение сам. Выгрузке
    при публикации нужно другое: она читает и пишет журнал внутри транзакции
    ревизии, поэтому получает уже открытое соединение
    (``SqlPublicReader.from_connection``). Со вторым соединением снимок не
    увидел бы изменений этой транзакции, а RLS-контекст был бы чужим.
    """

    def __init__(
        self, engine: Engine | None = None, connection: Connection | None = None
    ) -> None:
        if (engine is None) == (connection is None):
            raise ValueError("Читателю нужен ровно один источник: engine или connection.")
        self._engine = engine
        self._connection = connection

    @classmethod
    def from_connection(cls, connection: Connection) -> "SqlPublicReader":
        return cls(connection=connection)

    def read(self) -> PublicSnapshot:
        try:
            if self._connection is not None:
                return self._read(self._connection)
            assert self._engine is not None
            with self._engine.connect() as connection:
                return self._read(connection)
        except (ProgrammingError, OperationalError, DBAPIError) as exc:
            raise PublicUnavailable(
                f"Схема public недоступна: {reason(exc)}"
            ) from exc

    @staticmethod
    def _read(connection: Connection) -> PublicSnapshot:
        rows: dict[str, tuple[PublicRow, ...]] = {}
        for table in TABLES:
            # Имя таблицы берётся из константы TABLES, а не от
            # пользователя, поэтому подстановка в SQL безопасна.
            result = connection.execute(text(f'SELECT * FROM public."{table}"'))
            # Порядок строк задаётся здесь, а не ORDER BY: снимок
            # должен быть одинаковым от запроса к запросу, иначе
            # разница с черновиком «прыгает» между вызовами.
            rows[table] = tuple(
                sorted(
                    (
                        PublicRow(table, int(mapping["id"]), dict(mapping))
                        for mapping in result.mappings()
                    ),
                    key=lambda row: row.id,
                )
            )
        return PublicSnapshot(rows=rows)


class StaticPublicReader:
    """Готовый снимок вместо базы — для тестов и API без доступа к journal."""

    def __init__(self, snapshot: PublicSnapshot) -> None:
        self._snapshot = snapshot

    def read(self) -> PublicSnapshot:
        return self._snapshot


def reason(exc: Exception) -> str:
    """Первая строка сообщения драйвера: остальное — SQL и трассировка.

    Общая для чтения и записи журнала: ``writer`` объясняет отказ теми же
    словами драйвера.
    """

    original = getattr(exc, "orig", None) or exc
    text_value = str(original).strip()
    return text_value.splitlines()[0] if text_value else exc.__class__.__name__
