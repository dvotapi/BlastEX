"""Слои проекта МВ в PostgreSQL (TASK-018, PR 2): создание, версии, «устарел», ревизии.

Включаются переменной ``BLASTEX_TEST_DATABASE_URL`` (фикстура ``public_db``
применяет миграции Alembic, в том числе 0014), без неё пропускаются.
"""
from __future__ import annotations

import pytest

from design.mass_blast_repository import MassBlastConflictError, MassBlastNotFoundError
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg  # noqa: F401 — фикстура
from tests.test_mass_blast_repository_pg import (  # noqa: F401 — фикстура
    AUTHOR,
    ORG,
    _approve_project,
    _released,
    repository,
)

pytestmark = requires_pg

APPROVED = {"approved", "executed", "closed"}


def _approved(repository):
    project, revision = _released(repository)
    for role, actor in (("blast_manager", "manager@example.ru"), ("explosives_supervisor", "supervisor@example.ru")):
        repository.approve_revision(ORG, actor, revision["id"], role, "approved", "")
    return _approve_project(repository, project), revision


def _create(repository, project, revision, kind="NARYAD", single=False):
    return repository.create_layer(
        ORG, AUTHOR, project["id"], kind=kind, project_revision_id=revision["id"], allowed_statuses=APPROVED,
        single=single, seed={"kind": kind, "blocks": []}, payload={"number": "1"},
    )


def test_layer_lifecycle(repository) -> None:
    project, revision = _approved(repository)
    layer = _create(repository, project, revision)
    assert layer["status"] == "draft" and layer["version"] == 1 and layer["stale"] is False

    updated = repository.update_layer(ORG, AUTHOR, layer["id"], expected_version=1, payload={"number": "2"})
    assert updated["payload"] == {"number": "2"} and updated["version"] == 2
    with pytest.raises(MassBlastConflictError):
        repository.update_layer(ORG, AUTHOR, layer["id"], expected_version=1, payload={"number": "3"})

    issued = repository.create_layer_revision(ORG, AUTHOR, layer["id"], expected_version=2, context={"a": 1}, content_sha256="d" * 64)
    assert issued["revision_no"] == 1 and issued["project_revision_id"] == revision["id"]
    again = repository.create_layer_revision(ORG, AUTHOR, layer["id"], expected_version=3, context={"a": 2}, content_sha256="e" * 64)
    assert again["revision_no"] == 2
    current = repository.get_layer(ORG, layer["id"])
    assert current["status"] == "issued" and current["current_revision_id"] == again["id"]
    assert [item["id"] for item in repository.list_layers(ORG, project["id"])] == [layer["id"]]


def test_layer_needs_the_status_and_the_current_revision(repository) -> None:
    project, revision = _released(repository)  # in_review
    with pytest.raises(MassBlastConflictError):
        _create(repository, repository.get_project(ORG, project["id"]), revision)


def test_single_kind_and_foreign_organization(repository) -> None:
    project, revision = _approved(repository)
    layer = _create(repository, project, revision, kind="READINESS_ACT", single=True)
    with pytest.raises(MassBlastConflictError):
        _create(repository, project, revision, kind="READINESS_ACT", single=True)
    with pytest.raises(MassBlastNotFoundError):
        repository.get_layer("org-b", layer["id"])


def test_refresh_moves_the_layer_to_the_new_revision(repository) -> None:
    project, revision = _approved(repository)
    layer = _create(repository, project, revision)
    refreshed = repository.update_layer(
        ORG, AUTHOR, layer["id"], expected_version=1, seed={"kind": "NARYAD", "blocks": [1]}, project_revision_id=revision["id"],
    )
    assert refreshed["seed"]["blocks"] == [1] and refreshed["payload"] == {"number": "1"}
