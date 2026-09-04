"""Зеркала разделов справочников на живой базе.

Здесь проверяется то, чего не видно без PostgreSQL: таблица зеркала заводится
при включении настройки, публикация приводит её к ревизии одной транзакцией,
а новая колонка схемы доезжает до уже созданной таблицы. Что именно
приложение считает колонками и как приводит значения — в
``test_public_sync_mirror.py``.

Без ``BLASTEX_TEST_DATABASE_URL`` тесты пропускаются.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.models import ReferenceItem
from cost.v2.public_sync import mirror
from cost.v2.public_sync.mirror import MirrorColumn
from cost.v2.public_sync.settings import PublicSyncSettings
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg

ORG = "org-public-mirror"
USER = "editor@example.ru"

GRANITE = ReferenceItem(
    code="GRANITE",
    name="Гранит",
    payload={"density_t_m3": "2.70", "fracture_class": "III"},
)
SAND = ReferenceItem(
    code="SAND",
    name="Песок",
    payload={"density_t_m3": "1.60"},
    comment="Вскрышные породы",
)


@pytest.fixture()
def repository(public_db):
    """Репозиторий поверх базы со схемой ``public`` и миграциями blastex."""

    created = PostgresEconomicsRepository(TEST_DATABASE_URL)
    try:
        yield created
    finally:
        created.engine.dispose()


def enable_mirrors(
    repository: PostgresEconomicsRepository, *sections: str, exchange: bool = False
) -> PublicSyncSettings:
    return repository.set_public_sync_settings(
        ORG,
        USER,
        PublicSyncSettings(exchange_enabled=exchange, mirror_sections=frozenset(sections)),
    )


def publish(repository: PostgresEconomicsRepository, **sections: Any):
    """Публикует поверх текущей ревизии переданные разделы."""

    base = repository.get_reference_snapshot(ORG)
    return repository.publish_references(
        ORG, USER, base.revision_id, {**base.sections, **sections}
    )


def mirror_rows(engine, section: str = "rocks") -> list[dict[str, Any]]:
    with engine.connect() as connection:
        result = connection.execute(
            text(f'SELECT * FROM public."blastex_{section}" ORDER BY "code"')
        )
        return [dict(mapping) for mapping in result.mappings()]


def scalar(engine, statement: str, **parameters: Any) -> Any:
    with engine.connect() as connection:
        return connection.execute(text(statement), parameters).scalar()


def audit_payload(engine, revision_id: str) -> dict[str, Any]:
    return scalar(
        engine,
        "SELECT after_payload FROM blastex.audit_log WHERE entity_id = :revision_id",
        revision_id=revision_id,
    )


@requires_pg
def test_enabling_a_mirror_creates_a_table_closed_from_other_roles(
    repository, public_db
) -> None:
    enable_mirrors(repository, "rocks")

    assert scalar(public_db, "SELECT to_regclass('public.blastex_rocks')") == "blastex_rocks"
    # Таблица в общей схеме закрыта: RLS включён, доступ даёт только политика
    # приложения.
    assert scalar(
        public_db,
        "SELECT relrowsecurity FROM pg_class WHERE oid = 'public.blastex_rocks'::regclass",
    ) is True
    assert scalar(
        public_db,
        "SELECT policyname FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = 'blastex_rocks'",
    ) == "blastex_full_access"
    # Колонка payload заведена по схеме раздела, с русской подписью.
    assert scalar(
        public_db,
        "SELECT col_description('public.blastex_rocks'::regclass, ordinal_position) "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'blastex_rocks' "
        "AND column_name = 'density_t_m3'",
    ) == "Плотность"


@requires_pg
def test_publication_brings_the_mirror_to_the_revision(repository, public_db) -> None:
    enable_mirrors(repository, "rocks")

    published = publish(repository, rocks=(GRANITE, SAND))

    rows = mirror_rows(public_db)
    assert [row["code"] for row in rows] == ["GRANITE", "SAND"]
    assert {row["revision_id"] for row in rows} == {published.revision_id}
    granite = rows[0]
    assert granite["name"] == "Гранит"
    assert granite["is_active"] is True
    assert granite["density_t_m3"] == Decimal("2.70")
    assert granite["fracture_class"] == "III"
    assert rows[1]["comment"] == "Вскрышные породы"
    assert granite["synced_at"] is not None
    # Сводка выгрузки попадает в журнал аудита рядом с разделами ревизии.
    payload = audit_payload(public_db, published.revision_id)
    assert payload["public_writes"]["mirrors"] == {
        "rocks": {"upserted": 2, "deactivated": 0}
    }


@requires_pg
def test_record_that_left_the_revision_stays_but_stops_acting(
    repository, public_db
) -> None:
    enable_mirrors(repository, "rocks")
    publish(repository, rocks=(GRANITE, SAND))

    published = publish(repository, rocks=(GRANITE,))

    rows = {row["code"]: row for row in mirror_rows(public_db)}
    # Строка не удалена: журнал мог сослаться на неё раньше.
    assert set(rows) == {"GRANITE", "SAND"}
    assert rows["SAND"]["is_active"] is False
    assert rows["SAND"]["revision_id"] == published.revision_id
    assert rows["GRANITE"]["is_active"] is True
    assert audit_payload(public_db, published.revision_id)["public_writes"]["mirrors"] == {
        "rocks": {"upserted": 1, "deactivated": 1}
    }


@requires_pg
def test_new_column_of_the_schema_reaches_an_existing_table(
    repository, public_db, monkeypatch
) -> None:
    enable_mirrors(repository, "rocks")
    publish(repository, rocks=(GRANITE,))
    original = mirror.mirror_columns

    def with_extra_column(section: str) -> list[MirrorColumn]:
        columns = original(section)
        if section == "rocks":
            columns.append(MirrorColumn("extra_note", "text", "Новое поле схемы"))
        return columns

    monkeypatch.setattr(mirror, "mirror_columns", with_extra_column)
    publish(repository, rocks=(GRANITE,))

    assert scalar(
        public_db,
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'blastex_rocks' "
        "AND column_name = 'extra_note'",
    ) == "text"
    assert mirror_rows(public_db)[0]["extra_note"] is None


@requires_pg
def test_settings_survive_a_round_trip_through_the_database(repository) -> None:
    settings = PublicSyncSettings(
        exchange_enabled=True, mirror_sections=frozenset({"rocks", "positions"})
    )

    assert enable_mirrors(repository, "rocks", "positions", exchange=True) == settings
    assert repository.get_public_sync_settings(ORG) == settings

    narrowed = PublicSyncSettings(exchange_enabled=False, mirror_sections=frozenset({"rocks"}))
    assert enable_mirrors(repository, "rocks") == narrowed
    assert repository.get_public_sync_settings(ORG) == narrowed


@requires_pg
def test_publication_without_mirrors_leaves_the_journal_alone(
    repository, public_db
) -> None:
    publish(repository, rocks=(GRANITE,))

    assert scalar(public_db, "SELECT to_regclass('public.blastex_rocks')") is None
    assert "public_writes" not in audit_payload(
        public_db, repository.get_reference_snapshot(ORG).revision_id
    )
