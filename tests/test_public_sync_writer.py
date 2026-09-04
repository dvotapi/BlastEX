"""Исполнение плана выгрузки в журнал — без базы.

Здесь проверяется то, что писатель решает сам: каким SQL он ищет строку
родителя, которой нет ни во вставках плана, ни в связях. Поведение на живой
базе — в ``test_public_sync_push_pg.py``.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from cost.v2.public_sync.push import PublicInsert, PublicWritePlan
from cost.v2.public_sync.writer import PublicWriteError, SqlPublicWriter


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
