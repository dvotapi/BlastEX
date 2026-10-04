"""Согласование ревизии массового взрыва подписывает только назначенная учётка.

Хранилище проектов живёт только в PostgreSQL: тесты включаются переменной
``BLASTEX_TEST_DATABASE_URL`` (фикстура ``public_db`` применяет миграции
Alembic), без неё они пропускаются.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from cost.v2.db_repository import ReferenceRevisionRow
from design.mass_blast_repository import (
    MassBlastApprovalRow,
    MassBlastConflictError,
    MassBlastForbiddenError,
    PostgresMassBlastRepository,
)
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg  # noqa: F401 — фикстура

pytestmark = requires_pg

ORG = "org-a"
AUTHOR = "designer@example.ru"
MANAGER = "manager@example.ru"
SUPERVISOR = "supervisor@example.ru"
REFERENCE_REVISION = "11111111-1111-1111-1111-111111111111"


@pytest.fixture()
def repository(public_db):
    created = PostgresMassBlastRepository(TEST_DATABASE_URL)
    with created.session_factory() as session, session.begin():
        session.add(ReferenceRevisionRow(
            id=REFERENCE_REVISION, organization_id=ORG, sequence_no=1,
            published_at=datetime(2026, 10, 1, tzinfo=timezone.utc), published_by=AUTHOR, comment="",
        ))
    try:
        yield created
    finally:
        created.engine.dispose()


def _responsibilities(manager: str | None = MANAGER, supervisor: str | None = SUPERVISOR) -> list[dict[str, str]]:
    items = [
        {"role_code": "blast_manager", "employee_code": "Иванов", "position_name": "Руководитель взрывных работ"},
        {"role_code": "explosives_supervisor", "employee_code": "Петров", "position_name": "Ответственный за ВМ"},
    ]
    for item, email in zip(items, (manager, supervisor)):
        if email is not None:
            item["account_email"] = email
    return items


def _released(repository: PostgresMassBlastRepository, responsibilities: list[dict[str, str]] | None = None):
    responsibilities = _responsibilities() if responsibilities is None else responsibilities
    payload = {
        "name": "Массовый взрыв №1", "site_code": "SITE-1", "object_name": "Карьер", "blast_date": "2026-10-10",
        "responsibilities": responsibilities,
    }
    project = repository.create_project(ORG, AUTHOR, payload)
    revision = repository.create_revision(
        ORG, AUTHOR, project["id"], project["version"], REFERENCE_REVISION,
        {"responsibilities": responsibilities}, [], "formula-test", "template-test", "c" * 64,
    )
    return repository.get_project(ORG, project["id"]), revision


def _approve_project(repository: PostgresMassBlastRepository, project: dict) -> dict:
    current = repository.get_project(ORG, project["id"])
    return repository.transition_project(ORG, AUTHOR, project["id"], "approved", current["version"], "")


def test_assigned_account_approves_its_role(repository) -> None:
    _, revision = _released(repository)

    approval = repository.approve_revision(ORG, MANAGER, revision["id"], "blast_manager", "approved", "")

    assert approval["actor"] == MANAGER
    assert approval["role_code"] == "blast_manager"


@pytest.mark.parametrize("actor", [SUPERVISOR, AUTHOR])
def test_other_account_cannot_approve_a_role(repository, actor: str) -> None:
    _, revision = _released(repository)

    with pytest.raises(MassBlastForbiddenError, match=MANAGER):
        repository.approve_revision(ORG, actor, revision["id"], "blast_manager", "approved", "")


def test_role_absent_from_revision_is_refused(repository) -> None:
    _, revision = _released(repository)

    with pytest.raises(MassBlastConflictError, match="chief_engineer"):
        repository.approve_revision(ORG, MANAGER, revision["id"], "chief_engineer", "approved", "")


def test_revision_released_without_accounts_must_be_released_again(repository) -> None:
    _, revision = _released(repository, _responsibilities(manager=None, supervisor=None))

    with pytest.raises(MassBlastConflictError, match="черновик"):
        repository.approve_revision(ORG, MANAGER, revision["id"], "blast_manager", "approved", "")


def test_revision_with_one_account_on_two_roles_cannot_be_approved(repository) -> None:
    project, revision = _released(repository, _responsibilities(manager=MANAGER, supervisor=MANAGER))

    with pytest.raises(MassBlastConflictError):
        repository.approve_revision(ORG, MANAGER, revision["id"], "blast_manager", "approved", "")
    with pytest.raises(MassBlastConflictError):
        _approve_project(repository, project)


def test_project_is_approved_once_both_assigned_accounts_sign(repository) -> None:
    project, revision = _released(repository)
    repository.approve_revision(ORG, MANAGER, revision["id"], "blast_manager", "approved", "")
    repository.approve_revision(ORG, SUPERVISOR, revision["id"], "explosives_supervisor", "approved", "")

    approved = _approve_project(repository, project)

    assert approved["lifecycle_status"] == "approved"


def test_approvals_of_unassigned_accounts_do_not_count(repository) -> None:
    # Записи до привязки к людям: один пользователь подписал за обе роли.
    project, revision = _released(repository)
    with repository.session_factory() as session, session.begin():
        for role_code in ("blast_manager", "explosives_supervisor"):
            session.add(MassBlastApprovalRow(
                id=str(uuid4()), revision_id=revision["id"], role_code=role_code, actor=AUTHOR,
                decision="approved", comment="", content_sha256=revision["content_sha256"],
                created_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
            ))
    repository.approve_revision(ORG, MANAGER, revision["id"], "blast_manager", "approved", "")

    with pytest.raises(MassBlastConflictError, match="explosives_supervisor|Ответственный за ВМ"):
        _approve_project(repository, project)
