"""Съёмка старого блока на объекте в PostgreSQL (TASK-014, PR 5а): миграция и круг create/list/delete."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import inspect

from design.survey.site_repository import (
    PostgresSiteSurveyRepository,
    SiteSurveyDuplicateError,
    SiteSurveyNotFoundError,
)
from tests.pg_public import _REPO_ROOT, TEST_DATABASE_URL, public_db, requires_pg  # noqa: F401 — фикстура

pytestmark = requires_pg

ORG = "org-a"
OTHER_ORG = "org-b"
SITE = "KGOK"
POINTS = [{"name": "1-01", "x": 1.5, "y": 2.5, "z": 10.0, "depth_m": 11.0, "line": 2}]


@pytest.fixture()
def repository(public_db):
    created = PostgresSiteSurveyRepository(TEST_DATABASE_URL)
    try:
        yield created
    finally:
        created.engine.dispose()


def _record(**extra):
    return {
        "site_code": SITE, "block_label": "Б-12", "horizon_m": 410.5, "survey_date": "2026-10-01",
        "file_name": "b12.csv", "file_sha256": "a" * 64, "points": POINTS, **extra,
    }


def _alembic(*args: str) -> None:
    env = dict(os.environ, BLASTEX_DATABASE_URL=TEST_DATABASE_URL)
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=_REPO_ROOT, env=env, check=True)


def test_create_list_get_delete_round_trip(repository) -> None:
    created = repository.create(ORG, "mark@example.ru", _record())
    assert created["points"] == POINTS
    assert created["horizon_m"] == 410.5
    assert created["survey_date"] == "2026-10-01"
    assert repository.get(ORG, created["id"]) == created
    assert [item["id"] for item in repository.list(ORG, SITE)] == [created["id"]]
    repository.delete(ORG, created["id"])
    assert repository.list(ORG, SITE) == []


def test_list_is_newest_first_and_scoped(repository) -> None:
    old = repository.create(ORG, "a", _record(survey_date="2026-01-01", file_sha256="1" * 64))
    new = repository.create(ORG, "a", _record(survey_date="2026-09-01", file_sha256="2" * 64))
    repository.create(ORG, "a", _record(site_code="OTHER", file_sha256="3" * 64))
    repository.create(OTHER_ORG, "a", _record(file_sha256="4" * 64))
    assert [item["id"] for item in repository.list(ORG, SITE)] == [new["id"], old["id"]]


def test_same_file_for_same_block_is_rejected(repository) -> None:
    repository.create(ORG, "a", _record())
    with pytest.raises(SiteSurveyDuplicateError):
        repository.create(ORG, "a", _record())
    # Другой блок, другая организация — можно.
    repository.create(ORG, "a", _record(block_label="Б-13"))
    repository.create(OTHER_ORG, "a", _record())


def test_other_organization_cannot_read_or_delete(repository) -> None:
    created = repository.create(ORG, "a", _record())
    with pytest.raises(SiteSurveyNotFoundError):
        repository.get(OTHER_ORG, created["id"])
    with pytest.raises(SiteSurveyNotFoundError):
        repository.delete(OTHER_ORG, created["id"])
    assert repository.get(ORG, created["id"])["id"] == created["id"]


def test_migration_is_reversible(public_db) -> None:
    assert "site_surveys" in inspect(public_db).get_table_names(schema="blastex")
    _alembic("downgrade", "20261113_0016")
    assert "site_surveys" not in inspect(public_db).get_table_names(schema="blastex")
    _alembic("upgrade", "head")
    assert "site_surveys" in inspect(public_db).get_table_names(schema="blastex")
