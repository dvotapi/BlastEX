"""Паспорт на бурение в PostgreSQL: ревизии неизменяемы, миграция обратима (TASK-015, PR 1).

Тесты включаются переменной ``BLASTEX_TEST_DATABASE_URL`` (фикстура
``public_db`` применяет миграции Alembic), без неё пропускаются.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import inspect, select

from cost.v2.db_repository import AuditLogRow
from design.drilling_passport_repository import (
    DrillingPassportConflictError,
    DrillingPassportNotFoundError,
    PostgresDrillingPassportRepository,
)
from tests.pg_public import _REPO_ROOT, TEST_DATABASE_URL, public_db, requires_pg  # noqa: F401 — фикстура

pytestmark = requires_pg

ORG = "org-a"
AUTHOR = "designer@example.ru"
TABLES = {"drilling_passports", "drilling_passport_revisions"}
CONTEXT = {"formula_version": "drill-v1", "design_id": "block-66", "design_revision": 3, "design_sha256": "d" * 64}


@pytest.fixture()
def repository(public_db):
    created = PostgresDrillingPassportRepository(TEST_DATABASE_URL)
    try:
        yield created
    finally:
        created.engine.dispose()


def _draft(repository):
    return repository.create_passport(ORG, AUTHOR, "block-66", "66-26/Б", "2026-11-09", {"block": "66"})


def test_revision_is_appended_and_draft_version_moves(repository) -> None:
    passport = _draft(repository)
    first = repository.create_revision(ORG, AUTHOR, passport["id"], passport["version"], None, CONTEXT, "a" * 64)
    assert first["revision_no"] == 1
    assert first["design_revision"] == 3
    after = repository.get_passport(ORG, passport["id"])
    assert after["current_revision_id"] == first["id"]
    assert after["version"] == passport["version"] + 1

    second = repository.create_revision(ORG, AUTHOR, passport["id"], after["version"], None, CONTEXT, "a" * 64)
    assert second["revision_no"] == 2
    assert second["previous_revision_id"] == first["id"]
    # Первая ревизия не изменилась.
    assert repository.get_revision(ORG, first["id"]) == first

    with repository.session_factory() as session:
        actions = session.scalars(
            select(AuditLogRow.action).where(AuditLogRow.entity_type == "drilling_passport")
        ).all()
    assert "CREATE_DRILLING_PASSPORT_REVISION" in actions


def test_stale_version_and_foreign_org_are_refused(repository) -> None:
    passport = _draft(repository)
    with pytest.raises(DrillingPassportConflictError):
        repository.update_passport(ORG, AUTHOR, passport["id"], "66-26/Б", "2026-11-09", {}, passport["version"] + 5)
    with pytest.raises(DrillingPassportNotFoundError):
        repository.get_passport("org-b", passport["id"])
    revision = repository.create_revision(ORG, AUTHOR, passport["id"], passport["version"], None, CONTEXT, "b" * 64)
    with pytest.raises(DrillingPassportNotFoundError):
        repository.get_revision("org-b", revision["id"])


def _alembic(*args: str) -> None:
    env = dict(os.environ)
    env["BLASTEX_DATABASE_URL"] = TEST_DATABASE_URL
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=_REPO_ROOT, env=env, check=True)


def test_migration_is_reversible(public_db) -> None:
    def tables() -> set[str]:
        return TABLES & set(inspect(public_db).get_table_names(schema="blastex"))

    assert tables() == TABLES
    _alembic("downgrade", "20261003_0012")
    assert tables() == set()
    _alembic("upgrade", "20261109_0013")
    assert tables() == TABLES
