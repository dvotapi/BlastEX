"""`POST /economics/references/public-delta` и `.../public-links`."""
from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import economics
from api.security import SESSION_COOKIE, create_session_token
from api.services.economics_service import get_economics_repository
from api.services.public_sync_service import get_public_reader
from cost.v2.public_sync import PublicSnapshot, PublicUnavailable, StaticPublicReader
from cost.v2.public_sync.mapping import TABLES
from cost.v2.public_sync.settings import PublicSyncSettings
from cost.v2.repository import EconomicsRepositoryError, InMemoryEconomicsRepository
from tests.test_public_sync_mapping import COUNTERPARTIES, make_snapshot


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(economics.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


class _FailingReader:
    """Читалка, всегда падающая — модель недоступности схемы public."""

    def read(self):
        raise PublicUnavailable("Схема public недоступна: нет прав")


def test_public_delta_for_empty_draft_lists_new_counterparty_first(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())

    response = client.post("/api/v1/economics/references/public-delta", json={"sections": {}})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    assert body["error"] == ""
    assert body["counts"]["new"] > 0
    assert body["entries"][0]["kind"] == "new"
    assert body["entries"][0]["section"] == "counterparties"


def test_public_delta_shows_changed_after_link_is_saved(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())

    link_response = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1},
    )
    assert link_response.status_code == 201, link_response.text

    draft_item = {
        "code": "SITE_LOM",
        "name": "Ломоватский карьер",
        "payload": {"mineral_type": "иной тип полезного ископаемого"},
        "is_active": True,
    }
    response = client.post(
        "/api/v1/economics/references/public-delta",
        json={"sections": {"sites": [draft_item]}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    lom_entries = [
        entry
        for entry in body["entries"]
        if entry["section"] == "sites" and entry["code"] == "SITE_LOM"
    ]
    assert len(lom_entries) == 1
    assert lom_entries[0]["kind"] == "changed"


def test_linking_same_public_row_twice_with_different_code_conflicts(monkeypatch) -> None:
    client, _ = _client(monkeypatch)

    first = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM_2", "public_table": "sites", "public_id": 1},
    )
    assert second.status_code == 409, second.text
    message = second.json()["detail"]["message"]
    assert "уже связана с другой записью справочника" in message
    # Код записи, которой строка журнала уже принадлежит, наружу не уходит.
    assert "SITE_LOM" not in message


def test_user_role_cannot_link_but_can_read_delta(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())
    token = create_session_token("user@example.ru", "user", "default", int(time.time()) + 3600)
    user_client = TestClient(client.app)
    user_client.cookies.set(SESSION_COOKIE, token)

    link_response = user_client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1},
    )
    assert link_response.status_code == 403

    delta_response = user_client.post(
        "/api/v1/economics/references/public-delta", json={"sections": {}}
    )
    assert delta_response.status_code == 200, delta_response.text


def test_public_delta_reports_unavailable_schema(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: _FailingReader()

    response = client.post("/api/v1/economics/references/public-delta", json={"sections": {}})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is False
    assert "Схема public недоступна" in body["error"]
    assert body["counts"] == {"new": 0, "changed": 0, "deactivated": 0}
    assert body["entries"] == []


def test_public_delta_treats_empty_journal_as_unavailable(monkeypatch) -> None:
    """Пустой ответ журнала — не «всё совпадает», а отсутствие прав.

    При включённом RLS без политик `SELECT` возвращает ноль строк без ошибки:
    разница вышла бы нулевой, плашка спряталась бы, и пользователь решил бы,
    что синхронизация в порядке.
    """
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(
        PublicSnapshot(rows={})
    )

    response = client.post("/api/v1/economics/references/public-delta", json={"sections": {}})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is False
    assert "не отдал ни одной записи" in body["error"]
    assert "RLS" in body["error"]
    assert body["entries"] == []


def test_public_delta_treats_all_tables_empty_as_unavailable(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    empty = make_snapshot(**{table: [] for table in TABLES})
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(empty)

    body = client.post(
        "/api/v1/economics/references/public-delta", json={"sections": {}}
    ).json()

    assert body["available"] is False
    assert "не отдал ни одной записи" in body["error"]


def test_public_delta_with_rows_stays_available(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())

    body = client.post(
        "/api/v1/economics/references/public-delta", json={"sections": {}}
    ).json()

    assert body["available"] is True
    assert body["error"] == ""


def test_public_delta_skips_records_with_invalid_values(monkeypatch) -> None:
    """Запись журнала с недопустимым значением пропускается, а не рушит ответ."""

    client, _ = _client(monkeypatch)
    broken = dict(COUNTERPARTIES[0])
    broken["full_name"] = "К" * 400  # `name` справочника — не длиннее 300 символов
    snapshot = make_snapshot(counterparties=[broken, COUNTERPARTIES[1]])
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(snapshot)

    response = client.post("/api/v1/economics/references/public-delta", json={"sections": {}})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    assert "Пропущено записей с недопустимыми значениями: 1" in body["error"]
    codes = [entry["code"] for entry in body["entries"] if entry["section"] == "counterparties"]
    assert "PUB_COUNTERPARTY_1" not in codes
    assert "PUB_COUNTERPARTY_2" in codes
    assert body["counts"]["new"] == len([e for e in body["entries"] if e["kind"] == "new"])


def test_public_delta_reports_repository_failure_as_unavailable_service(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())

    def broken(*_args, **_kwargs):
        raise EconomicsRepositoryError("база недоступна")

    monkeypatch.setattr(repository, "list_public_links", broken)

    response = client.post("/api/v1/economics/references/public-delta", json={"sections": {}})

    assert response.status_code == 503, response.text


def test_public_links_list_reports_repository_failure(monkeypatch) -> None:
    client, repository = _client(monkeypatch)

    def broken(*_args, **_kwargs):
        raise RuntimeError("нет соединения")

    monkeypatch.setattr(repository, "list_public_links", broken)

    assert client.get("/api/v1/economics/references/public-links").status_code == 503


def test_public_link_save_failure_without_conflict_is_service_error(monkeypatch) -> None:
    client, repository = _client(monkeypatch)

    def broken(*_args, **_kwargs):
        raise RuntimeError("нет соединения")

    monkeypatch.setattr(repository, "save_public_link", broken)

    response = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1},
    )

    assert response.status_code == 503, response.text


def test_public_link_rejects_unknown_section_and_table(monkeypatch) -> None:
    client, _ = _client(monkeypatch)

    unknown_section = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "выдуманный", "code": "X", "public_table": "sites", "public_id": 1},
    )
    unknown_table = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "X", "public_table": "выдуманная", "public_id": 1},
    )

    assert unknown_section.status_code == 422, unknown_section.text
    assert "Неизвестный раздел справочников" in unknown_section.text
    assert unknown_table.status_code == 422, unknown_table.text
    assert "Неизвестная таблица журнала" in unknown_table.text


def test_public_link_rejects_table_of_another_section(monkeypatch) -> None:
    """Раздел и таблица порознь известны, а вместе не сопоставлены (§4.1)."""

    client, repository = _client(monkeypatch)

    response = client.post(
        "/api/v1/economics/references/public-links",
        json={
            "section": "equipment_types",
            "code": "JK830",
            "public_table": "sites",
            "public_id": 1,
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["message"] == (
        "Раздел equipment_types не сопоставлен с таблицей sites."
    )
    assert repository.list_public_links("default") == ()


# --- Ожидающие связи черновика ----------------------------------------------


def _site_item(code: str, name: str = "Ломоватский карьер") -> dict:
    return {
        "code": code,
        "name": name,
        "payload": {"mineral_type": "иной тип полезного ископаемого"},
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
        "source": "",
        "comment": "",
        "revision": 1,
    }


def _publish(client, sections: dict, links: list[dict]):
    """Публикация текущей ревизии с заменёнными разделами и связями."""

    snapshot = client.get("/api/v1/economics/references/snapshot").json()
    return client.post(
        "/api/v1/economics/references/publish",
        json={
            "base_revision": snapshot["revision_id"],
            "sections": {**snapshot["sections"], **sections},
            "comment": "",
            "public_links": links,
        },
    )


def test_pending_link_makes_row_linked_without_saving_it(monkeypatch) -> None:
    """Связь из черновика учитывается в разнице, но в базу не пишется."""

    client, repository = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())

    response = client.post(
        "/api/v1/economics/references/public-delta",
        json={
            "sections": {"sites": [_site_item("SITE_LOM")]},
            "pending_links": [
                {"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1}
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    linked = [
        entry
        for entry in body["entries"]
        if entry["public_table"] == "sites" and entry["public_id"] == 1
    ]
    assert [(entry["kind"], entry["code"]) for entry in linked] == [("changed", "SITE_LOM")]
    # Ожидающая связь остаётся в черновике: публикации не было.
    assert repository.list_public_links("default") == ()


def test_pending_link_overrides_saved_link_of_the_same_public_row(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())
    saved = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_OLD", "public_table": "sites", "public_id": 1},
    )
    assert saved.status_code == 201, saved.text

    body = client.post(
        "/api/v1/economics/references/public-delta",
        json={
            "sections": {"sites": [_site_item("SITE_NEW")]},
            "pending_links": [
                {"section": "sites", "code": "SITE_NEW", "public_table": "sites", "public_id": 1}
            ],
        },
    ).json()

    linked = [
        entry
        for entry in body["entries"]
        if entry["public_table"] == "sites" and entry["public_id"] == 1
    ]
    assert [(entry["kind"], entry["code"]) for entry in linked] == [("changed", "SITE_NEW")]


def test_public_delta_skips_entry_with_invalid_payload_value(monkeypatch) -> None:
    """Отрицательное замедление не проходит схему раздела — предложение пропущено."""

    client, _ = _client(monkeypatch)
    broken_delays = [
        {"id": 1, "device_type_id": 1, "delay_ms": 500, "is_standard": False},
        {"id": 2, "device_type_id": 2, "delay_ms": -5, "is_standard": True},
    ]
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(
        make_snapshot(delay_series=broken_delays)
    )

    body = client.post("/api/v1/economics/references/public-delta", json={"sections": {}}).json()

    assert body["available"] is True
    assert "Пропущено записей с недопустимыми значениями: 1" in body["error"]
    codes = [entry["code"] for entry in body["entries"]]
    assert "PUB_IDT_2" not in codes
    assert "PUB_IDT_1" in codes


def test_publish_saves_pending_links(monkeypatch) -> None:
    client, repository = _client(monkeypatch)

    response = _publish(
        client,
        {"sites": [_site_item("SITE_LOM")]},
        [{"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1}],
    )

    assert response.status_code == 200, response.text
    links = repository.list_public_links("default")
    assert [(link.section, link.code, link.public_table, link.public_id) for link in links] == [
        ("sites", "SITE_LOM", "sites", 1)
    ]
    assert links[0].synced_at is not None


def test_publish_rejects_link_to_table_of_another_section(monkeypatch) -> None:
    client, repository = _client(monkeypatch)

    response = _publish(
        client,
        {"sites": [_site_item("SITE_LOM")]},
        [
            {
                "section": "equipment_types",
                "code": "SITE_LOM",
                "public_table": "sites",
                "public_id": 1,
            }
        ],
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["message"] == (
        "Раздел equipment_types не сопоставлен с таблицей sites."
    )
    assert repository.list_public_links("default") == ()


def test_publish_ignores_link_to_code_missing_from_revision(monkeypatch) -> None:
    """Запись, удалённую из черновика перед публикацией, связывать не с чем."""

    client, repository = _client(monkeypatch)

    response = _publish(
        client,
        {"sites": [_site_item("SITE_LOM")]},
        [{"section": "sites", "code": "SITE_GONE", "public_table": "sites", "public_id": 1}],
    )

    assert response.status_code == 200, response.text
    assert repository.list_public_links("default") == ()


def test_publish_with_conflicting_link_changes_nothing(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    saved = client.post(
        "/api/v1/economics/references/public-links",
        json={"section": "sites", "code": "SITE_OLD", "public_table": "sites", "public_id": 1},
    )
    assert saved.status_code == 201, saved.text
    before = client.get("/api/v1/economics/references/snapshot").json()["revision_id"]

    # Запись со старым кодом остаётся в ревизии: значит, записи две и строку
    # журнала делить между ними нельзя. Пропади старый код — это было бы
    # переименование, и связь просто переехала бы (см. тест ниже).
    response = _publish(
        client,
        {"sites": [_site_item("SITE_OLD", "Прежний карьер"), _site_item("SITE_LOM")]},
        [{"section": "sites", "code": "SITE_LOM", "public_table": "sites", "public_id": 1}],
    )

    assert response.status_code == 409, response.text
    message = response.json()["detail"]["message"]
    assert "уже связана с другой записью справочника" in message
    assert "SITE_OLD" not in message
    # Ревизия не создана: связь и справочники пишутся одной транзакцией.
    assert client.get("/api/v1/economics/references/snapshot").json()["revision_id"] == before
    assert [link.code for link in repository.list_public_links("default")] == ["SITE_OLD"]


# --- Переименование связанной записи ----------------------------------------


def _counterparty_item(code: str) -> dict:
    """Контрагент, совпадающий со строкой журнала `counterparties#1` по ИНН."""

    return {
        "code": code,
        "name": 'Акционерное общество "Теплогорский карьер"',
        "payload": {
            "role": "CUSTOMER",
            "inn": "6608002092",
            "short_name": 'АО "Теплогорский карьер"',
        },
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
        "source": "",
        "comment": "",
        "revision": 1,
    }


def _enable_exchange(client, repository) -> None:
    """Обмен включён, а журнал — снимок `make_snapshot` и для чтения, и для плана."""

    repository.public_snapshot = make_snapshot()
    repository.set_public_sync_settings(
        "default",
        "editor@example.ru",
        PublicSyncSettings(exchange_enabled=True, mirror_sections=frozenset()),
    )
    client.app.dependency_overrides[get_public_reader] = lambda: StaticPublicReader(make_snapshot())


def _counterparty_issues(client, code: str, links: list[dict]) -> list[dict]:
    """Замечания проверки по разделу контрагентов (остальные разделы не переданы)."""

    response = client.post(
        "/api/v1/economics/references/validate",
        json={"sections": {"counterparties": [_counterparty_item(code)]}, "public_links": links},
    )
    assert response.status_code == 200, response.text
    return [issue for issue in response.json()["issues"] if issue["section"] == "counterparties"]


def test_renamed_record_keeps_its_link_on_validate_and_publish(monkeypatch) -> None:
    """Код связанной записи поправили: связь переезжает, дубля в журнале нет."""

    client, repository = _client(monkeypatch)
    _enable_exchange(client, repository)
    link = {
        "section": "counterparties",
        "code": "KARIER",
        "public_table": "counterparties",
        "public_id": 1,
    }
    first = _publish(client, {"counterparties": [_counterparty_item("KARIER")]}, [link])
    assert first.status_code == 200, first.text

    # Фронт присылает связь, перенесённую на новый код записи.
    renamed = {**link, "code": "KARIER_2"}
    assert _counterparty_issues(client, "KARIER_2", [renamed]) == []
    # Без переноса та же запись выглядит несвязанной: её ИНН «уже есть в журнале».
    assert _counterparty_issues(client, "KARIER_2", []) != []

    response = _publish(client, {"counterparties": [_counterparty_item("KARIER_2")]}, [renamed])

    assert response.status_code == 200, response.text
    links = repository.list_public_links("default")
    assert [(link.section, link.code, link.public_id) for link in links] == [
        ("counterparties", "KARIER_2", 1)
    ]
    # Строка журнала осталась связанной: второй записи под новым кодом нет.
    plan = repository._public_writes["default"][-1]
    assert [insert.code for insert in plan.inserts] == []
