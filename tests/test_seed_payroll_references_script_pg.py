"""Проверка организации в скрипте сида справочников ФОТ (code review PR #83, пункт 1).

`main()` до вызова `run()` должен только читать, есть ли у организации хоть
одна ревизия справочников — опечатка в `--organization` не должна заводить
новую организацию через `_ensure_defaults`. Без `BLASTEX_TEST_DATABASE_URL`
пропускается, как соседние pg-тесты (см. `tests/pg_public.py`).
"""
from __future__ import annotations

import pytest

from cost.v2.db_repository import PostgresEconomicsRepository
from scripts.seed_payroll_references import organization_exists
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg

ORGANIZATION = "org-seed-script-check"


@pytest.fixture()
def repository(public_db):
    created = PostgresEconomicsRepository(TEST_DATABASE_URL)
    try:
        yield created
    finally:
        created.engine.dispose()


@requires_pg
def test_unknown_organization_does_not_exist_and_creates_no_revision(repository) -> None:
    assert organization_exists(repository, ORGANIZATION) is False

    # Проверка — чтение: повторный вызов тоже не находит организацию, то
    # есть revision №1 для неё не завёлся (в отличие от `get_reference_snapshot`).
    assert organization_exists(repository, ORGANIZATION) is False


@requires_pg
def test_organization_with_a_published_revision_is_found(repository) -> None:
    # `get_reference_snapshot` заводит ревизию №1 — после этого организация известна.
    repository.get_reference_snapshot(ORGANIZATION)

    assert organization_exists(repository, ORGANIZATION) is True
    assert organization_exists(repository, "другая-организация") is False
