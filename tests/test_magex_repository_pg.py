"""Версии выписки MagEX и исполнение в PostgreSQL (TASK-018 PR 7, миграция 0015).

Включаются переменной ``BLASTEX_TEST_DATABASE_URL``, без неё пропускаются.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from design.mass_blast_repository import MassBlastConflictError
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg  # noqa: F401 — фикстура
from tests.test_mass_blast_layers_pg import _approved, _create
from tests.test_mass_blast_repository_pg import AUTHOR, ORG, repository  # noqa: F401 — фикстура

pytestmark = requires_pg


def _build(token: str = "a.b.c"):
    return lambda ver: (f"{token}{ver}", "kid-1", "f" * 64)


def test_versions_grow_and_pending_is_superseded(repository) -> None:
    project, revision = _approved(repository)
    layer = _create(repository, project, revision)
    first = repository.create_magex_version(ORG, AUTHOR, layer["id"], _build())
    assert first["ver"] == 1 and first["status"] == "SENDING" and first["jws"] == "a.b.c1"
    repository.update_magex_version(first["id"], status="PENDING", attempts=1,
                                    next_attempt_at=datetime(2026, 10, 14, 5, tzinfo=timezone.utc))
    second = repository.create_magex_version(ORG, AUTHOR, layer["id"], _build())
    assert second["ver"] == 2
    statuses = [(item["ver"], item["status"]) for item in repository.list_magex_versions(ORG, layer["id"])]
    assert statuses == [(1, "SUPERSEDED"), (2, "SENDING")]
    with pytest.raises(ValueError):
        repository.update_magex_version(second["id"], jws="x")


def test_queue_claims_due_versions_once(repository) -> None:
    project, revision = _approved(repository)
    layer = _create(repository, project, revision)
    version = repository.create_magex_version(ORG, AUTHOR, layer["id"], _build())
    now = datetime(2026, 10, 14, 5, tzinfo=timezone.utc)
    repository.update_magex_version(version["id"], status="PENDING", next_attempt_at=now - timedelta(seconds=1))
    claimed = repository.claim_due_magex_versions(now, lease_s=120)
    assert [item["id"] for item in claimed] == [version["id"]]
    assert repository.claim_due_magex_versions(now, lease_s=120) == []
    assert [item["id"] for item in repository.claim_due_magex_versions(now + timedelta(seconds=121), lease_s=120)] == [version["id"]]


def test_discarded_revision_restores_the_layer(repository) -> None:
    project, revision = _approved(repository)
    layer = _create(repository, project, revision)
    first = repository.create_layer_revision(ORG, AUTHOR, layer["id"], expected_version=1, context={"a": 1}, content_sha256="d" * 64)
    second = repository.create_layer_revision(ORG, AUTHOR, layer["id"], expected_version=2, context={"a": 2}, content_sha256="e" * 64)
    version = repository.create_magex_version(ORG, AUTHOR, layer["id"], _build())
    repository.update_magex_version(version["id"], layer_revision_id=second["id"])
    restored = repository.discard_layer_revision(ORG, AUTHOR, layer["id"], second["id"])
    assert restored["current_revision_id"] == first["id"] and restored["status"] == "issued"
    assert repository.list_magex_versions(ORG, layer["id"])[0]["layer_revision_id"] is None
    assert repository.magex_version_for_revision(ORG, second["id"]) is None
    with pytest.raises(MassBlastConflictError):
        repository.update_layer(ORG, AUTHOR, layer["id"], expected_version=restored["version"] - 1, payload={})


def test_execution_and_keys_in_use(repository) -> None:
    project, revision = _approved(repository)
    layer = _create(repository, project, revision)
    assert repository.magex_execution(ORG, layer["id"]) is None
    version = repository.create_magex_version(ORG, AUTHOR, layer["id"], _build())
    repository.update_magex_version(version["id"], status="ACCEPTED")
    repository.save_magex_execution(ORG, layer["id"], {"status": "issued", "lines": []})
    assert repository.magex_execution(ORG, layer["id"])["status"] == "issued"
    assert repository.magex_keys_in_use(ORG) == [{"kid": "kid-1", "open_naryads": 1}]
    repository.save_magex_execution(ORG, layer["id"], {"status": "closed", "lines": []})
    assert repository.magex_keys_in_use(ORG) == []
    assert repository.magex_execution("other", layer["id"]) is None
