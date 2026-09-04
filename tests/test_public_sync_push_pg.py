"""Выгрузка справочников в схему ``public`` при публикации ревизии.

Тесты идут через ``PostgresEconomicsRepository.publish_references`` на живой
базе: только там видно главное — выгрузка и ревизия живут в одной транзакции,
а ограничения журнала (уникальные ключи, внешние ключи, ``NOT NULL``)
проверяет сам PostgreSQL.

Без ``BLASTEX_TEST_DATABASE_URL`` тесты пропускаются.
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.models import ReferenceItem
from cost.v2.public_sync.reader import PublicUnavailable, SqlPublicReader
from cost.v2.public_sync.settings import PublicSyncSettings
from cost.v2.public_sync.writer import PublicWriteError
from tests.pg_public import TEST_DATABASE_URL, public_db, requires_pg, seed_public

ORG = "org-public-push"
USER = "editor@example.ru"

CUSTOMER = ReferenceItem(
    code="KARIER",
    name='Общество с ограниченной ответственностью "Карьер"',
    payload={
        "short_name": 'ООО "Карьер"',
        "inn": "6685101311",
        "role": "CUSTOMER",
    },
)
SITE = ReferenceItem(
    code="NOV",
    name="Новый карьер",
    payload={
        "short_name": "НОВ",
        "mineral_type": "нерудные материалы",
        "customer_code": "KARIER",
    },
)
EQUIPMENT_TYPE = ReferenceItem(
    code="DM45",
    name="DM45",
    payload={
        "kind": "DRILL_RIG",
        "brand": "Epiroc",
        # Тип машины уже есть в журнале (seed_public) — он должен быть
        # переиспользован, а не заведён вторым.
        "machine_type_name": "Буровая установка",
    },
)
EQUIPMENT_ASSET = ReferenceItem(
    code="RIG_02",
    name="Станок №2",
    payload={
        "equipment_type_code": "DM45",
        "inventory_number": "Б-02",
        "serial_number": "SN-DM45-0002",
    },
)
DEVICE = ReferenceItem(
    code="ED_2N",
    name="ЭД-2-Н",
    payload={"material_kind": "СИ", "storage_class": "NSI"},
    comment="Электродетонатор предохранительный",
)


@pytest.fixture()
def repository(public_db):
    """Репозиторий поверх базы со схемой ``public`` и миграциями blastex."""

    created = PostgresEconomicsRepository(TEST_DATABASE_URL)
    try:
        yield created
    finally:
        created.engine.dispose()


def enable_exchange(repository: PostgresEconomicsRepository) -> None:
    repository.set_public_sync_settings(
        ORG, USER, PublicSyncSettings(exchange_enabled=True, mirror_sections=frozenset())
    )


def publish(repository: PostgresEconomicsRepository, **sections: Any):
    """Публикует поверх текущей ревизии переданные разделы."""

    base = repository.get_reference_snapshot(ORG)
    return repository.publish_references(
        ORG, USER, base.revision_id, {**base.sections, **sections}
    )


def publish_all(repository: PostgresEconomicsRepository, site: ReferenceItem = SITE):
    return publish(
        repository,
        counterparties=(CUSTOMER,),
        sites=(site,),
        equipment_types=(EQUIPMENT_TYPE,),
        equipment_assets=(EQUIPMENT_ASSET,),
        materials=(DEVICE,),
    )


def rows(engine, table: str) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        result = connection.execute(text(f'SELECT * FROM public."{table}" ORDER BY id'))
        return [dict(mapping) for mapping in result.mappings()]


def only_row(engine, table: str, column: str, value: Any) -> dict[str, Any]:
    """Единственная строка журнала с таким значением колонки."""

    found = [row for row in rows(engine, table) if row[column] == value]
    assert len(found) == 1, f"ожидалась одна строка {table}, получено {len(found)}"
    return found[0]


def counts(engine) -> dict[str, int]:
    tables = (
        "counterparties",
        "sites",
        "machine_types",
        "equipment_models",
        "equipment_units",
        "initiating_device_types",
    )
    return {table: len(rows(engine, table)) for table in tables}


def audit_payload(engine, revision_id: str) -> dict[str, Any]:
    """Запись журнала аудита о публикации ревизии."""

    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT after_payload FROM blastex.audit_log "
                "WHERE entity_id = :revision_id"
            ),
            {"revision_id": revision_id},
        ).scalar_one()


@requires_pg
def test_publication_writes_new_records_to_the_journal(repository, public_db) -> None:
    seeded = seed_public(public_db)
    enable_exchange(repository)

    publish_all(repository)

    counterparty = only_row(public_db, "counterparties", "inn", "6685101311")
    assert counterparty["full_name"] == CUSTOMER.name
    assert counterparty["is_client"] is True
    assert counterparty["is_supplier"] is False

    site = only_row(public_db, "sites", "short_name", "НОВ")
    # Заказчик в журнале — текст: краткое имя контрагента.
    assert site["client_legal_name"] == 'ООО "Карьер"'

    # Тип машины из журнала переиспользован, а не заведён вторым.
    machine_types = [row["id"] for row in rows(public_db, "machine_types")]
    assert machine_types == [seeded["machine_type"]]
    model = only_row(public_db, "equipment_models", "model_name", "DM45")
    assert model["machine_type_id"] == seeded["machine_type"]
    assert model["brand"] == "Epiroc"

    unit = only_row(public_db, "equipment_units", "internal_id", "Б-02")
    assert unit["model_id"] == model["id"]
    assert unit["status"] == "В работе"

    device = only_row(public_db, "initiating_device_types", "name", "ЭД-2-Н")
    assert device["description"] == "Электродетонатор предохранительный"

    links = {
        (link.section, link.code): (link.public_table, link.public_id)
        for link in repository.list_public_links(ORG)
    }
    assert links == {
        ("counterparties", "KARIER"): ("counterparties", counterparty["id"]),
        ("sites", "NOV"): ("sites", site["id"]),
        ("equipment_types", "DM45"): ("equipment_models", model["id"]),
        ("equipment_assets", "RIG_02"): ("equipment_units", unit["id"]),
        ("materials", "ED_2N"): ("initiating_device_types", device["id"]),
    }


@requires_pg
def test_audit_log_keeps_the_summary_of_the_upload(repository, public_db) -> None:
    seed_public(public_db)
    enable_exchange(repository)

    published = publish_all(repository)

    payload = audit_payload(public_db, published.revision_id)
    # Пять записей blastex; строка `machine_types` не понадобилась.
    assert payload["public_writes"] == {"inserted": 5, "updated": 0, "warnings": []}
    # Сводка добавлена к разделам, а не вместо них.
    assert "counterparties" in payload


@requires_pg
def test_second_publication_without_changes_keeps_the_journal_intact(
    repository, public_db
) -> None:
    seed_public(public_db)
    enable_exchange(repository)
    publish_all(repository)
    before = {table: rows(public_db, table) for table in ("counterparties", "sites")}
    before_counts = counts(public_db)

    published = publish_all(repository)

    assert counts(public_db) == before_counts
    for table, expected in before.items():
        assert rows(public_db, table) == expected
        assert [row["updated_at"] for row in rows(public_db, table)] == [
            row["updated_at"] for row in expected
        ]
    # Ни одного оператора: связанные записи совпали со строками журнала.
    summary = audit_payload(public_db, published.revision_id)["public_writes"]
    assert summary == {"inserted": 0, "updated": 0, "warnings": []}


@requires_pg
def test_changed_short_name_updates_only_that_column(repository, public_db) -> None:
    seed_public(public_db)
    enable_exchange(repository)
    publish_all(repository)
    before = {row["id"]: row for row in rows(public_db, "sites")}
    before_counts = counts(public_db)

    renamed = ReferenceItem(
        code=SITE.code, name=SITE.name, payload={**SITE.payload, "short_name": "НОВ2"}
    )
    published = publish_all(repository, site=renamed)

    assert counts(public_db) == before_counts
    summary = audit_payload(public_db, published.revision_id)["public_writes"]
    assert summary == {"inserted": 0, "updated": 1, "warnings": []}
    after = {row["id"]: row for row in rows(public_db, "sites")}
    assert set(after) == set(before)
    changed = [
        (row_id, column)
        for row_id, row in after.items()
        for column, value in row.items()
        if before[row_id][column] != value
    ]
    assert [column for _row_id, column in changed] == ["short_name"]
    assert after[changed[0][0]]["short_name"] == "НОВ2"


@requires_pg
def test_journal_constraint_rolls_back_the_whole_publication(repository, public_db) -> None:
    seed_public(public_db)
    enable_exchange(repository)
    before_counts = counts(public_db)
    revisions_before = len(repository.list_reference_revisions(ORG))
    # Имя типа техники повторяет `equipment_models.model_name` строки журнала,
    # с которой запись не связана: репозиторий валидацию не вызывает, и на
    # уникальном ключе журнала падает вся транзакция.
    clashing = ReferenceItem(
        code="JK830",
        name="JK830-2",
        payload={**EQUIPMENT_TYPE.payload, "brand": "JK Drilling"},
    )

    with pytest.raises(PublicWriteError) as failure:
        publish(
            repository,
            counterparties=(CUSTOMER,),
            equipment_types=(clashing,),
        )

    assert "project1.public" in str(failure.value)
    assert len(repository.list_reference_revisions(ORG)) == revisions_before
    assert counts(public_db) == before_counts
    assert repository.list_public_links(ORG) == ()


@requires_pg
def test_disabled_exchange_writes_nothing_to_the_journal(repository, public_db) -> None:
    seed_public(public_db)
    before_counts = counts(public_db)

    published = publish_all(repository)

    assert counts(public_db) == before_counts
    assert repository.list_public_links(ORG) == ()
    # Выгрузки не было — и сводки о ней в журнале аудита тоже нет.
    assert "public_writes" not in audit_payload(public_db, published.revision_id)


@requires_pg
def test_exchange_is_not_enabled_without_access_to_the_journal(
    repository, public_db, monkeypatch
) -> None:
    """Включение обмена пробует журнал: без доступа настройка не сохраняется."""

    def unavailable(self) -> None:
        raise PublicUnavailable("Схема public недоступна: нет прав на public.counterparties")

    monkeypatch.setattr(SqlPublicReader, "read", unavailable)

    with pytest.raises(PublicWriteError) as failure:
        enable_exchange(repository)

    assert "project1.public" in str(failure.value)
    # Транзакция откатилась целиком: обмен остался выключенным.
    assert repository.get_public_sync_settings(ORG).exchange_enabled is False


@requires_pg
def test_enabled_exchange_is_probed_only_when_it_is_switched_on(
    repository, public_db, monkeypatch
) -> None:
    """Проба идёт на переходе «выключено → включено», а не при каждом сохранении."""

    seed_public(public_db)
    enable_exchange(repository)
    calls: list[int] = []
    original = SqlPublicReader.read

    def counting(self):
        calls.append(1)
        return original(self)

    monkeypatch.setattr(SqlPublicReader, "read", counting)
    enable_exchange(repository)

    assert calls == []
