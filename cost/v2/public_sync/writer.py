"""Исполнение плана выгрузки в схеме ``public`` (журнал project1).

Единственное место пакета, которое пишет в чужую схему. Своей транзакции
писатель не открывает и ничего не коммитит: он выполняет план в переданной
сессии — той же, в которой публикуется ревизия. Иначе журнал мог бы получить
строки от ревизии, которой в blastex нет, а откат публикации оставил бы их
сиротами.

Что писать, решает ``push``: имена таблиц и колонок приходят из его констант,
а не от пользователя, поэтому подставляются в SQL напрямую; значения всегда
идут именованными параметрами.

Любой отказ базы (нарушенный уникальный ключ, ``NOT NULL``, потерянные права)
превращается в ``PublicWriteError``. Он вылетает из транзакции публикации и
откатывает её целиком: ревизия, связи и строки журнала либо появляются
вместе, либо не появляются вовсе.
"""
from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import Result, TextClause, text
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from cost.v2.public_sync.push import PublicInsert, PublicUpdate, PublicWritePlan
from cost.v2.public_sync.reader import reason
from cost.v2.repository import PublicLink

__all__ = ["PublicWriteError", "SqlPublicWriter"]

# Таблицы, строку которых план переиспользует без связи: у `machine_types`
# записи blastex нет, поэтому id уже существующего типа машины ищется по
# имени — по тому самому написанию, которое план взял из журнала.
_NATURAL_KEYS: dict[str, str] = {"machine_types": "name"}


class PublicWriteError(RuntimeError):
    """Журнал не принял запись: публикация откатывается целиком.

    Текст собирается здесь, а не на месте отказа: пользователь должен видеть,
    что не приняла именно чужая схема, а не справочники BlastEX.
    """

    def __init__(self, cause: object) -> None:
        super().__init__(f"Не удалось записать в project1.public: {cause}")


class SqlPublicWriter:
    """Выполняет план выгрузки в переданной сессии.

    Связи организации нужны для разрешения ссылок: родитель мог быть выгружен
    прошлой публикацией, и тогда его id известен только из связи.
    """

    def __init__(self, session: Session, links: Sequence[PublicLink] = ()) -> None:
        self._session = session
        self._linked = {(link.public_table, link.code): link.public_id for link in links}

    def apply(self, plan: PublicWritePlan) -> list[PublicLink]:
        """Вставляет и обновляет строки журнала, возвращая новые связи.

        Вставки идут в порядке плана — он топологический, поэтому id родителя
        уже известен к моменту вставки ребёнка. Связь возвращается только для
        записей blastex: у вспомогательной строки ``machine_types`` раздел
        пуст, связывать её не с чем.
        """

        inserted: dict[tuple[str, str], int] = {}
        links: list[PublicLink] = []
        for insert in plan.inserts:
            values = dict(insert.values)
            for column, table, code in insert.foreign_keys:
                values[column] = self._parent_id(insert, table, code, inserted)
            public_id = self._insert(insert.table, values)
            inserted[(insert.table, insert.code)] = public_id
            if insert.section:
                links.append(
                    PublicLink(
                        section=insert.section,
                        code=insert.code,
                        public_table=insert.table,
                        public_id=public_id,
                    )
                )
        for update in plan.updates:
            self._update(update)
        return links

    # --- Разрешение ссылок --------------------------------------------------

    def _parent_id(
        self,
        insert: PublicInsert,
        table: str,
        code: str,
        inserted: dict[tuple[str, str], int],
    ) -> int:
        public_id = inserted.get((table, code))
        if public_id is None:
            public_id = self._linked.get((table, code))
        if public_id is None:
            public_id = self._existing_id(table, code)
        if public_id is None:
            raise PublicWriteError(
                f"запись {insert.section or insert.table}/{insert.code} "
                f"ссылается на {table}/{code}, а такой строки в журнале нет."
            )
        return public_id

    def _existing_id(self, table: str, code: str) -> int | None:
        """Строка журнала по естественному ключу — только для `machine_types`."""

        column = _NATURAL_KEYS.get(table)
        if column is None:
            return None
        statement = text(f'SELECT id FROM public."{table}" WHERE "{column}" = :value')
        public_id = self._execute(statement, {"value": code}).scalar()
        return None if public_id is None else int(public_id)

    # --- Операторы ----------------------------------------------------------

    def _insert(self, table: str, values: dict[str, Any]) -> int:
        columns = ", ".join(f'"{column}"' for column in values)
        parameters = ", ".join(f":{column}" for column in values)
        statement = text(
            f'INSERT INTO public."{table}" ({columns}) '
            f"VALUES ({parameters}) RETURNING id"
        )
        # Значения psycopg 3 принимает как есть: Decimal, date, bool, строку и
        # None — приводить их к JSON или тексту не нужно.
        return int(self._execute(statement, values).scalar_one())

    def _update(self, update: PublicUpdate) -> None:
        assignments = ", ".join(f'"{column}" = :{column}' for column in update.values)
        # Колонки `public_id` в выгружаемых таблицах нет, поэтому имя
        # параметра не столкнётся с именем колонки.
        statement = text(
            f'UPDATE public."{update.table}" SET {assignments} WHERE id = :public_id'
        )
        result = self._execute(
            statement, {**update.values, "public_id": update.public_id}
        )
        if result.rowcount == 0:
            raise PublicWriteError(
                f"строка {update.table}#{update.public_id} исчезла из журнала."
            )

    def _execute(self, statement: TextClause, parameters: dict[str, Any]) -> Result[Any]:
        try:
            return self._session.execute(statement, parameters)
        except (IntegrityError, ProgrammingError, OperationalError, DBAPIError) as exc:
            raise PublicWriteError(reason(exc)) from exc
