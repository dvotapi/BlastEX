"""Исполнение плана выгрузки в журнал — без базы.

Здесь проверяется то, что писатель решает сам: каким SQL он ищет строку
родителя, которой нет ни во вставках плана, ни в связях, и как он проверяет
права роли перед включением обмена. Поведение на живой базе — в
``test_public_sync_push_pg.py``.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from cost.v2.public_sync.mapping import TABLES
from cost.v2.public_sync.push import (
    PublicInsert,
    PublicUpdate,
    PublicWritePlan,
    WRITTEN_TABLES,
)
from cost.v2.public_sync.writer import (
    PublicAccessError,
    PublicWriteError,
    SqlPublicWriter,
    check_public_access,
)


class RecordingSession:
    """Сессия-заглушка: запоминает операторы и отдаёт заготовленные id."""

    def __init__(self, *, scalar: Any = None, insert_id: int = 100) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._scalar = scalar
        self._insert_id = insert_id

    def execute(self, statement: Any, parameters: Any = None) -> Any:
        self.calls.append((str(statement), parameters))
        return SimpleNamespace(
            scalar=lambda: self._scalar,
            scalar_one=lambda: self._insert_id,
            rowcount=1,
        )


class FailingSession:
    """Сессия, у которой любой оператор кончается отказом базы."""

    def execute(self, statement: Any, parameters: Any = None) -> Any:
        raise SQLAlchemyError("нет прав на public.equipment_models")


MODEL = PublicInsert(
    table="equipment_models",
    values={"model_name": "DM45", "brand": "Epiroc"},
    section="equipment_types",
    code="DM45",
    depends_on=(("machine_types", "Буровая установка"),),
    foreign_keys=(("machine_type_id", "machine_types", "Буровая установка"),),
)


def test_parent_is_looked_up_by_trimmed_name() -> None:
    # План кладёт написание типа машины без крайних пробелов, а в журнале
    # его заводили руками: сравнение должно совпадать с `_machine_type_key`,
    # иначе писатель не найдёт строку и уронит публикацию.
    session = RecordingSession(scalar=7)

    links = SqlPublicWriter(session).apply(PublicWritePlan(inserts=(MODEL,)))

    select_sql, select_parameters = session.calls[0]
    assert 'WHERE btrim("name") = :value' in select_sql
    assert select_parameters == {"value": "Буровая установка"}
    insert_sql, insert_parameters = session.calls[1]
    assert 'INSERT INTO public."equipment_models"' in insert_sql
    assert insert_parameters["machine_type_id"] == 7
    assert [(link.section, link.code, link.public_id) for link in links] == [
        ("equipment_types", "DM45", 100)
    ]


def test_missing_parent_stops_the_publication() -> None:
    session = RecordingSession(scalar=None)

    with pytest.raises(PublicWriteError) as failure:
        SqlPublicWriter(session).apply(PublicWritePlan(inserts=(MODEL,)))

    assert "project1.public" in str(failure.value)


def test_any_database_failure_becomes_a_write_error() -> None:
    # Отказ приходит подклассом `SQLAlchemyError` — перечислять их поимённо
    # значит однажды пропустить незнакомый и уронить публикацию чужой ошибкой.
    with pytest.raises(PublicWriteError):
        SqlPublicWriter(FailingSession()).apply(
            PublicWritePlan(
                inserts=(
                    PublicInsert(
                        table="equipment_models",
                        values={"model_name": "DM45", "brand": "Epiroc"},
                        section="equipment_types",
                        code="DM45",
                    ),
                )
            )
        )


# --- Ссылки в обновлениях ----------------------------------------------------

RETYPED_MODEL = PublicUpdate(
    table="equipment_models",
    public_id=5,
    values={"brand": "Epiroc"},
    depends_on=(("machine_types", "Экскаватор"),),
    foreign_keys=(("machine_type_id", "machine_types", "Экскаватор"),),
)


def test_update_resolves_its_foreign_key_like_an_insert() -> None:
    session = RecordingSession(scalar=7)

    SqlPublicWriter(session).apply(PublicWritePlan(updates=(RETYPED_MODEL,)))

    select_sql, select_parameters = session.calls[0]
    assert 'WHERE btrim("name") = :value' in select_sql
    assert select_parameters == {"value": "Экскаватор"}
    update_sql, update_parameters = session.calls[1]
    assert '"machine_type_id" = :machine_type_id' in update_sql
    assert update_parameters["machine_type_id"] == 7
    assert update_parameters["public_id"] == 5


def test_update_takes_the_id_of_a_row_inserted_by_the_same_plan() -> None:
    # Тип машины заводится этой же публикацией: id известен только из
    # `RETURNING`, и обновление модели должно взять его оттуда.
    session = RecordingSession(scalar=None, insert_id=42)
    machine_type = PublicInsert(
        table="machine_types", values={"name": "Погрузчик"}, section="", code="Погрузчик"
    )
    update = PublicUpdate(
        table="equipment_models",
        public_id=5,
        values={},
        depends_on=(("machine_types", "Погрузчик"),),
        foreign_keys=(("machine_type_id", "machine_types", "Погрузчик"),),
    )

    SqlPublicWriter(session).apply(
        PublicWritePlan(inserts=(machine_type,), updates=(update,))
    )

    update_sql, update_parameters = session.calls[-1]
    assert 'SET "machine_type_id" = :machine_type_id WHERE id = :public_id' in update_sql
    assert update_parameters == {"machine_type_id": 42, "public_id": 5}


def test_update_without_a_parent_stops_the_publication() -> None:
    session = RecordingSession(scalar=None)

    with pytest.raises(PublicWriteError):
        SqlPublicWriter(session).apply(PublicWritePlan(updates=(RETYPED_MODEL,)))


# --- Права на схему public ---------------------------------------------------


class AccessSession:
    """Сессия, отвечающая на проверку прав заготовленными строками.

    Первый запрос ``check_public_access`` — проба схемы, без параметров:
    у него нет ``tables``, поэтому отвечаем на него отдельно, заготовкой
    из ключа ``schema`` (``usage`` и ``create_``, по умолчанию — есть оба
    права).
    """

    def __init__(self, **overrides: dict[str, Any]) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._schema = overrides.pop("schema", {})
        self._overrides = overrides

    def execute(self, statement: Any, parameters: Any = None) -> Any:
        self.calls.append((str(statement), parameters))
        if parameters is None:
            row = {"usage": True, "create_": True, **self._schema}
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: row))
        rows = [self._row(table) for table in parameters["tables"]]
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))

    def _row(self, table: str) -> dict[str, Any]:
        allowed = {
            "table_name": table,
            "role_name": "blastex",
            "select_allowed": True,
            "insert_allowed": True,
            "update_allowed": True,
            "sequence_allowed": True,
            "policy_allowed": True,
        }
        allowed.update(self._overrides.get(table, {}))
        return allowed


def test_access_check_asks_about_every_table_it_touches() -> None:
    session = AccessSession()

    check_public_access(session)

    # Первой идёт проба самой схемы — без неё пробы таблиц ничего не значат.
    schema_sql, schema_parameters = session.calls[0]
    assert "has_schema_privilege(current_user, 'public', 'USAGE')" in schema_sql
    assert "has_schema_privilege(current_user, 'public', 'CREATE')" in schema_sql
    assert schema_parameters is None
    read_sql, read_parameters = session.calls[1]
    assert "has_table_privilege(current_user" in read_sql
    assert read_parameters["tables"] == list(TABLES)
    # Политика RLS спрашивается у каждой таблицы, а не только у тех, в
    # которые план пишет: без политики PostgreSQL молча вернёт ноль строк.
    # Читающей таблице довольно политики на чтение, пишущей нужна на запись.
    assert "pg_policies" in read_sql
    assert "'SELECT', 'ALL', '*'" in read_sql
    write_sql, write_parameters = session.calls[2]
    assert "pg_get_serial_sequence" in write_sql
    assert "pg_policies" in write_sql
    assert "'SELECT'" not in write_sql
    assert "'INSERT'" in write_sql and "'UPDATE'" in write_sql
    assert write_parameters["tables"] == list(WRITTEN_TABLES)


def test_missing_schema_usage_stops_before_table_checks() -> None:
    # Развёртывание настроено частично: права на таблицы и политики RLS уже
    # выданы, а USAGE на саму схему отозван. Обе пробы таблиц спрашивают
    # только has_table_privilege и политики — без этой пробы включение
    # прошло бы, а первая же публикация упала бы отказом SELECT.
    session = AccessSession(schema={"usage": False})

    with pytest.raises(PublicAccessError) as failure:
        check_public_access(session)

    assert str(failure.value) == (
        "Нет доступа к project1.public: схема public — нет права USAGE; "
        "выполните scripts/grant_public_access.sql"
    )
    assert len(session.calls) == 1


def test_missing_schema_create_mentions_mirrors() -> None:
    # CREATE журналу не нужен, но нужен будущим зеркалам разделов: без него
    # обмен включить можно, а зеркало — нет, и жалоба должна это объяснять.
    session = AccessSession(schema={"create_": False})

    with pytest.raises(PublicAccessError) as failure:
        check_public_access(session)

    assert str(failure.value) == (
        "Нет доступа к project1.public: схема public — "
        "нет права CREATE (нужно для зеркал разделов); "
        "выполните scripts/grant_public_access.sql"
    )
    assert len(session.calls) == 1


def test_missing_select_names_the_table_and_the_grant_script() -> None:
    session = AccessSession(contracts={"select_allowed": False})

    with pytest.raises(PublicAccessError) as failure:
        check_public_access(session)

    assert str(failure.value) == (
        "Нет доступа к project1.public: таблица contracts — нет права SELECT; "
        "выполните scripts/grant_public_access.sql"
    )


@pytest.mark.parametrize(
    ("column", "missing"),
    [
        ("insert_allowed", "нет права INSERT"),
        ("update_allowed", "нет права UPDATE"),
        ("sequence_allowed", "нет права USAGE на последовательность колонки id"),
        ("policy_allowed", "нет политики RLS для роли blastex"),
    ],
)
def test_every_write_privilege_is_required(column: str, missing: str) -> None:
    session = AccessSession(counterparties={column: False})

    with pytest.raises(PublicAccessError) as failure:
        check_public_access(session)

    assert f"таблица counterparties — {missing}" in str(failure.value)


def test_read_only_table_without_policy_is_refused() -> None:
    # Права SELECT выданы, а политики RLS нет: PostgreSQL молча вернёт ноль
    # строк, снимок журнала окажется неполным, и разница по ценам или
    # замедлениям пропала бы незаметно — обмен включать нельзя.
    session = AccessSession(delay_series={"policy_allowed": False})

    with pytest.raises(PublicAccessError) as failure:
        check_public_access(session)

    assert str(failure.value) == (
        "Нет доступа к project1.public: таблица delay_series — "
        "нет политики RLS для роли blastex; "
        "выполните scripts/grant_public_access.sql"
    )


def test_access_check_is_a_write_error_for_the_publication() -> None:
    # Отказ прав должен ловиться там же, где и отказ записи: включение обмена
    # и публикация показывают его одним текстом.
    assert issubclass(PublicAccessError, PublicWriteError)


def test_database_failure_of_the_access_check_becomes_a_write_error() -> None:
    with pytest.raises(PublicWriteError):
        check_public_access(FailingSession())
