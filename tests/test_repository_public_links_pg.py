"""Связи с журналом ``public`` в репозитории PostgreSQL.

In-memory репозиторий проверяется в
``tests/test_repository_organization_isolation.py``; здесь тот же контракт
проверяется на реальной базе, где уникальность строки журнала держит
ограничение ``uq_public_links_public_row``, а не словарь в памяти.

Без ``BLASTEX_TEST_DATABASE_URL`` тесты пропускаются, но модуль обязан
импортироваться: фикстура ``public_db`` уже применила миграции Alembic.
"""
from __future__ import annotations

import pytest

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.repository import EconomicsRepositoryError, PublicLink
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg

ORG = "org-public-links"
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
def test_public_link_is_saved_listed_and_upserted(repository) -> None:
    saved = repository.save_public_link(
        ORG, USER, PublicLink(section="sites", code="SITE_LOM", public_table="sites", public_id=1)
    )

    assert saved.synced_at is not None
    listed = repository.list_public_links(ORG)
    assert [(link.code, link.public_id) for link in listed] == [("SITE_LOM", 1)]

    # Тот же ключ (раздел + код) с другой строкой журнала — обновление, а не
    # вторая запись: связь у записи справочника ровно одна.
    repository.save_public_link(
        ORG, USER, PublicLink(section="sites", code="SITE_LOM", public_table="sites", public_id=2)
    )
    assert [(link.code, link.public_id) for link in repository.list_public_links(ORG)] == [
        ("SITE_LOM", 2)
    ]
    assert repository.list_public_links("другая-организация") == ()


@requires_pg
def test_same_public_row_cannot_be_linked_to_another_code(repository) -> None:
    repository.save_public_link(
        ORG, USER, PublicLink(section="sites", code="SITE_LOM", public_table="sites", public_id=7)
    )

    with pytest.raises(EconomicsRepositoryError) as failure:
        repository.save_public_link(
            ORG, USER, PublicLink(section="sites", code="SITE_OTHER", public_table="sites", public_id=7)
        )

    message = str(failure.value)
    assert "sites#7" in message
    # Чужой код в тексте не показывается — см. §4.3 и правку E.
    assert "SITE_LOM" not in message


@requires_pg
def test_mirror_sections_round_trip(repository) -> None:
    assert repository.list_mirror_sections(ORG) == {}

    repository.set_mirror_section(ORG, USER, "rocks", True)
    assert repository.list_mirror_sections(ORG) == {"rocks": True}

    repository.set_mirror_section(ORG, USER, "rocks", False)
    repository.set_mirror_section(ORG, USER, "sites", True)
    assert repository.list_mirror_sections(ORG) == {"rocks": False, "sites": True}
    assert repository.list_mirror_sections("другая-организация") == {}
