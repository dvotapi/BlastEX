"""Настройки листа расчёта по объекту в репозитории PostgreSQL.

In-memory репозиторий проверяется в
``tests/test_repository_organization_isolation.py``; здесь тот же контракт
проверяется на реальной базе — таблице ``blastex.calc_object_inputs`` с
первичным ключом по паре (организация, объект работ).

Без ``BLASTEX_TEST_DATABASE_URL`` тесты пропускаются, но модуль обязан
импортироваться: фикстура ``public_db`` уже применила миграции Alembic.
"""
from __future__ import annotations

import time

import pytest

from cost.v2.db_repository import PostgresEconomicsRepository
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg

ORG = "org-calc-inputs"
USER = "editor@example.ru"


@pytest.fixture()
def repository(public_db):
    """Репозиторий поверх базы, уже приведённой фикстурой к схеме из миграций."""

    created = PostgresEconomicsRepository(TEST_DATABASE_URL)
    try:
        yield created
    finally:
        created.engine.dispose()


@requires_pg
def test_calc_inputs_round_trip(repository) -> None:
    assert repository.get_calc_inputs(ORG, "Карьер А") is None

    saved = repository.save_calc_inputs(ORG, USER, "Карьер А", {"bench_height_m": 12})

    assert saved.work_object_name == "Карьер А"
    assert saved.inputs == {"bench_height_m": 12}
    assert saved.updated_at is not None

    fetched = repository.get_calc_inputs(ORG, "Карьер А")
    assert fetched == saved
    assert repository.get_calc_inputs("другая-организация", "Карьер А") is None


@requires_pg
def test_calc_inputs_overwrite_bumps_updated_at(repository) -> None:
    first = repository.save_calc_inputs(ORG, USER, "Карьер Б", {"bench_height_m": 12})

    # Секундная задержка — надёжнее сравнения `>=` внутри той же секунды:
    # `updated_at` обрезан до целых секунд (`replace(microsecond=0)`).
    time.sleep(1.1)

    second = repository.save_calc_inputs(ORG, USER, "Карьер Б", {"bench_height_m": 18})

    assert second.inputs == {"bench_height_m": 18}
    assert second.updated_at > first.updated_at
    assert repository.get_calc_inputs(ORG, "Карьер Б").inputs == {"bench_height_m": 18}
