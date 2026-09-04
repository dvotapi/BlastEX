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

from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

from cost.v2.public_sync.mapping import TABLES, PublicRow, PublicSnapshot

__all__ = ["PublicReader", "PublicUnavailable", "SqlPublicReader", "StaticPublicReader"]


class PublicUnavailable(RuntimeError):
    """Схема ``public`` недоступна: нет таблицы, прав или соединения."""


class PublicReader(Protocol):
    def read(self) -> PublicSnapshot: ...


class SqlPublicReader:
    """Читает таблицы ``public`` из той же базы, где живёт схема blastex."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read(self) -> PublicSnapshot:
        rows: dict[str, tuple[PublicRow, ...]] = {}
        try:
            with self._engine.connect() as connection:
                for table in TABLES:
                    # Имя таблицы берётся из константы TABLES, а не от
                    # пользователя, поэтому подстановка в SQL безопасна.
                    result = connection.execute(
                        text(f'SELECT * FROM public."{table}"')
                    )
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
        except (ProgrammingError, OperationalError, DBAPIError) as exc:
            raise PublicUnavailable(
                f"Схема public недоступна: {_reason(exc)}"
            ) from exc
        return PublicSnapshot(rows=rows)


class StaticPublicReader:
    """Готовый снимок вместо базы — для тестов и API без доступа к journal."""

    def __init__(self, snapshot: PublicSnapshot) -> None:
        self._snapshot = snapshot

    def read(self) -> PublicSnapshot:
        return self._snapshot


def _reason(exc: Exception) -> str:
    """Первая строка сообщения драйвера: остальное — SQL и трассировка."""

    original = getattr(exc, "orig", None) or exc
    text_value = str(original).strip()
    return text_value.splitlines()[0] if text_value else exc.__class__.__name__
