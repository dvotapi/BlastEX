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

Здесь же живёт ``check_public_access``: права роли на схему ``public``
проверяются при включении обмена, до первой публикации. Проверяются именно
права, а не удачный ``SELECT``: роль с одним лишь чтением прошла бы пробу и
уронила бы первую же публикацию.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy import Result, TextClause, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from cost.v2.public_sync.mapping import TABLES
from cost.v2.public_sync.push import (
    WRITTEN_TABLES,
    PublicInsert,
    PublicUpdate,
    PublicWritePlan,
)
from cost.v2.public_sync.reader import reason
from cost.v2.repository import PublicLink

__all__ = [
    "PublicAccessError",
    "PublicWriteError",
    "SqlPublicWriter",
    "check_public_access",
]

# Таблицы, строку которых план переиспользует без связи: у `machine_types`
# записи blastex нет, поэтому id уже существующего типа машины ищется по
# имени — по тому самому написанию, которое план взял из журнала.
_NATURAL_KEYS: dict[str, str] = {"machine_types": "name"}


class PublicWriteError(RuntimeError):
    """Журнал не принял запись: публикация откатывается целиком.

    Текст собирается здесь, а не на месте отказа: пользователь должен видеть,
    что не приняла именно чужая схема, а не справочники BlastEX.
    """

    _PREFIX = "Не удалось записать в project1.public: "

    def __init__(self, cause: object) -> None:
        super().__init__(f"{self._PREFIX}{cause}")


class PublicAccessError(PublicWriteError):
    """Роли не хватает прав на схему ``public``: обмен включать нельзя.

    Наследуется от ``PublicWriteError``, чтобы API отвечал на нехватку прав
    тем же кодом, что и на отказ записи: для пользователя это одна и та же
    беда с чужой схемой.
    """

    _PREFIX = "Нет доступа к project1.public: "

    def __init__(self, subject: str, missing: str) -> None:
        # `subject` — уже готовая часть фразы («таблица contracts» или
        # «схема public»): у ошибки уровня схемы нет таблицы, которую можно
        # было бы подставить в общий шаблон.
        super().__init__(
            f"{subject} — {missing}; выполните scripts/grant_public_access.sql"
        )


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
                values[column] = self._parent_id(
                    f"{insert.section or insert.table}/{insert.code}", table, code, inserted
                )
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
            values = dict(update.values)
            # Ссылки в обновлении разрешаются так же, как во вставке: у
            # записи мог смениться тип техники, и строка журнала переезжает
            # на другого родителя.
            for column, table, code in update.foreign_keys:
                values[column] = self._parent_id(
                    f"{update.table}#{update.public_id}", table, code, inserted
                )
            self._update(update, values)
        return links

    # --- Разрешение ссылок --------------------------------------------------

    def _parent_id(
        self,
        owner: str,
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
                f"запись {owner} ссылается на {table}/{code}, "
                "а такой строки в журнале нет."
            )
        return public_id

    def _existing_id(self, table: str, code: str) -> int | None:
        """Строка журнала по естественному ключу — только для `machine_types`.

        Сравнение идёт через ``btrim``: в плане лежит написание журнала без
        крайних пробелов (``push._key``), а в самой строке пробелы могли
        остаться — тип машины журнал заводит руками.
        """

        column = _NATURAL_KEYS.get(table)
        if column is None:
            return None
        statement = text(f'SELECT id FROM public."{table}" WHERE btrim("{column}") = :value')
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

    def _update(self, update: PublicUpdate, values: dict[str, Any]) -> None:
        assignments = ", ".join(f'"{column}" = :{column}' for column in values)
        # Колонки `public_id` в выгружаемых таблицах нет, поэтому имя
        # параметра не столкнётся с именем колонки.
        statement = text(
            f'UPDATE public."{update.table}" SET {assignments} WHERE id = :public_id'
        )
        result = self._execute(statement, {**values, "public_id": update.public_id})
        if result.rowcount == 0:
            raise PublicWriteError(
                f"строка {update.table}#{update.public_id} исчезла из журнала."
            )

    def _execute(self, statement: TextClause, parameters: dict[str, Any]) -> Result[Any]:
        try:
            return self._session.execute(statement, parameters)
        except SQLAlchemyError as exc:
            # Ловится вся ветка ошибок SQLAlchemy: перечислять подклассы
            # значит однажды пропустить незнакомый и уронить публикацию
            # чужой ошибкой вместо понятного отказа журнала.
            raise PublicWriteError(reason(exc)) from exc


# --- Права на схему public --------------------------------------------------

# `USAGE` нужен для любого обращения к объектам схемы: без него запросы прав
# отдельных таблиц ниже либо откажут непонятной ошибкой, либо (если роль
# добирается до public через search_path) само подключение к базе не даст
# столько прочитать. `CREATE` для журнала не нужен, но нужен будущим зеркалам
# разделов — без него включать обмен формально можно, а включать зеркало
# нельзя, и отказ пришёл бы из DDL, а не из понятной пробы прав.
_SCHEMA_ACCESS = text(
    "SELECT has_schema_privilege(current_user, 'public', 'USAGE') AS usage, "
    "has_schema_privilege(current_user, 'public', 'CREATE') AS create_"
)

# Имена таблиц в запросах — параметры, а не части SQL, и приходят они из
# `mapping.TABLES` и `push.WRITTEN_TABLES`, а не от пользователя.
_TABLES_SOURCE = (
    "FROM unnest(CAST(:tables AS text[])) WITH ORDINALITY AS t(table_name, ordinal) "
    "LEFT JOIN pg_class c "
    "ON c.relname = t.table_name AND c.relnamespace = 'public'::regnamespace "
    "ORDER BY t.ordinal"
)


# Команда политики в `pg_policies.cmd`: `FOR ALL` PostgreSQL показывает как
# `ALL`, старые версии — как `*`; такая политика разрешает и чтение, и запись.
_ANY_COMMAND = "'ALL', '*'"
_SELECT_COMMANDS = "'SELECT', " + _ANY_COMMAND
_INSERT_COMMAND = "'INSERT'"
_UPDATE_COMMAND = "'UPDATE'"


def _has_policy(commands: str) -> str:
    """Есть ли у таблицы политика RLS, применимая к роли и этим командам.

    Политика может быть выдана самой роли или ``public``. ``FOR ALL``
    PostgreSQL показывает в ``pg_policies.cmd`` как ``ALL`` (в старых
    версиях — ``*``), поэтому оба написания перечисляются вызывающим.
    """

    return (
        "EXISTS (SELECT 1 FROM pg_policies p "
        "WHERE p.schemaname = 'public' AND p.tablename = t.table_name "
        "AND (p.roles @> ARRAY[current_user]::name[] "
        "OR p.roles @> ARRAY['public']::name[]) "
        f"AND p.cmd IN ({commands}))"
    )


def _policy_allowed(policies: str) -> str:
    """Условие «RLS этой таблицы роли не помешает».

    Таблица без RLS и таблица своего владельца проверку проходят: политика
    им не нужна. Таблицы в ответе может не быть вовсе (``LEFT JOIN`` даст
    NULL) — тогда о правах судит ``has_table_privilege``, а не эта колонка.
    """

    return (
        "COALESCE(NOT c.relrowsecurity "
        "OR pg_get_userbyid(c.relowner) = current_user "
        f"OR {policies}, true) AS policy_allowed"
    )


# Право на чтение и политика RLS, разрешающая чтение. Политика проверяется у
# каждой таблицы снимка, а не только у тех, в которые план пишет: с одним
# лишь GRANT SELECT PostgreSQL молча вернёт ноль строк, снимок окажется
# неполным (у прочих таблиц строки есть, и пустым он не выглядит), а разница
# по ценам или замедлениям пропадёт незаметно.
_READ_ACCESS = text(
    "SELECT t.table_name AS table_name, current_user AS role_name, "
    "has_table_privilege(current_user, format('public.%I', t.table_name), 'SELECT') "
    "AS select_allowed, "
    + _policy_allowed(_has_policy(_SELECT_COMMANDS))
    + " "
    + _TABLES_SOURCE
)

# Право на запись, право на последовательность колонки `id` (без неё INSERT не
# получит следующий номер) и политика RLS, разрешающая запись. Таблица без
# последовательности (`pg_get_serial_sequence` вернёт NULL) проверку
# последовательности проходит; политика на одно чтение записи не спасёт —
# нужна `FOR ALL` либо обе, `FOR INSERT` и `FOR UPDATE`.
_WRITE_ACCESS = text(
    "SELECT t.table_name AS table_name, current_user AS role_name, "
    "has_table_privilege(current_user, format('public.%I', t.table_name), 'INSERT') "
    "AS insert_allowed, "
    "has_table_privilege(current_user, format('public.%I', t.table_name), 'UPDATE') "
    "AS update_allowed, "
    "COALESCE(has_sequence_privilege(current_user, "
    "pg_get_serial_sequence(format('public.%I', t.table_name), 'id'), 'USAGE'), true) "
    "AS sequence_allowed, "
    + _policy_allowed(
        f"({_has_policy(_ANY_COMMAND)} "
        f"OR ({_has_policy(_INSERT_COMMAND)} AND {_has_policy(_UPDATE_COMMAND)}))"
    )
    + " "
    + _TABLES_SOURCE
)

# Жалоба, которой нужно имя роли, несёт `{role}`: подставляется `current_user`
# из ответа базы — администратор должен видеть, какой именно роли не хватило
# политики, а не искать её в конфигурации приложения.
_MISSING_POLICY = "нет политики RLS для роли {role}"

# Колонка ответа → чего не хватает роли. Порядок задаёт порядок жалоб: сначала
# сами права, потом последовательность и политика.
_READ_CHECKS: tuple[tuple[str, str], ...] = (
    ("select_allowed", "нет права SELECT"),
    ("policy_allowed", _MISSING_POLICY),
)

_WRITE_CHECKS: tuple[tuple[str, str], ...] = (
    ("insert_allowed", "нет права INSERT"),
    ("update_allowed", "нет права UPDATE"),
    ("sequence_allowed", "нет права USAGE на последовательность колонки id"),
    ("policy_allowed", _MISSING_POLICY),
)


def check_public_access(session: Session) -> None:
    """Проверяет права роли на схему ``public`` перед включением обмена.

    Проверяются права, а не удачное чтение: роль с одним лишь ``SELECT`` или
    без политики RLS прошла бы пробу чтением и уронила бы первую публикацию
    ответом 502. Читаются все таблицы ``mapping.TABLES``, пишутся только
    ``push.WRITTEN_TABLES`` — с них и спрашивается больше. Политика RLS нужна
    и читаемым таблицам: без неё PostgreSQL не откажет, а вернёт ноль строк,
    и обмен молча разошёлся бы с журналом.

    Первая же нехватка — ``PublicAccessError`` с именем таблицы и права:
    администратору нужно знать, что именно не выдал скрипт, а не список из
    тринадцати строк. Перед таблицами проверяется сама схема: без ``USAGE``
    последующие пробы либо ничего не значат, либо ничего не увидят, а без
    ``CREATE`` пройдёт эта проба, но зеркало раздела включить не удастся.
    """

    _check_schema_access(session)
    _require(_access_rows(session, _READ_ACCESS, TABLES), _READ_CHECKS)
    _require(_access_rows(session, _WRITE_ACCESS, WRITTEN_TABLES), _WRITE_CHECKS)


def _check_schema_access(session: Session) -> None:
    """Проверяет ``USAGE`` и ``CREATE`` роли на саму схему ``public``.

    Ставится перед пробами отдельных таблиц: развёртывание бывает
    настроено частично — права на таблицы и политики RLS уже выданы, а
    ``USAGE`` на схему отозван или не выдавался. Обе пробы таблиц тогда
    молча проходят (они спрашивают только ``has_table_privilege`` и
    политики), обмен включается, а первая же публикация падает отказом
    ``SELECT`` с 502 вместо понятного отказа на включении.
    """

    try:
        row = session.execute(_SCHEMA_ACCESS).mappings().one()
    except SQLAlchemyError as exc:
        raise PublicWriteError(reason(exc)) from exc
    if not row["usage"]:
        raise PublicAccessError("схема public", "нет права USAGE")
    if not row["create_"]:
        raise PublicAccessError(
            "схема public", "нет права CREATE (нужно для зеркал разделов)"
        )


def _require(
    rows: Sequence[Mapping[str, Any]], checks: tuple[tuple[str, str], ...]
) -> None:
    """Отказывает на первой же нехватке: таблица за таблицей, право за правом.

    Текст жалобы проходит через ``format``: имя роли нужно только политике
    (``_MISSING_POLICY``), а остальные жалобы фигурных скобок не содержат и
    от подстановки не меняются.
    """

    for row in rows:
        for column, missing in checks:
            if not row[column]:
                raise PublicAccessError(
                    f"таблица {row['table_name']}",
                    missing.format(role=row["role_name"]),
                )


def _access_rows(
    session: Session, statement: TextClause, tables: Sequence[str]
) -> Sequence[Mapping[str, Any]]:
    try:
        result = session.execute(statement, {"tables": list(tables)})
    except SQLAlchemyError as exc:
        # Нет таблицы, нет схемы, нет соединения — тот же отказ, что и при
        # записи: обмен не включается, флаги откатываются.
        raise PublicWriteError(reason(exc)) from exc
    return result.mappings().all()
