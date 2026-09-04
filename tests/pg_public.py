"""Фикстуры тестовой базы PostgreSQL со схемой ``public`` (проект ``project1``).

Модуль содержит только фикстуры и помощники для тестов: разбор DDL из
``Docs/public_schema.sql``, фикстуру ``public_db`` (пересоздаёт схему
``public`` и применяет миграции Alembic для схемы ``blastex``) и
``seed_public`` — минимальный набор данных по §13 спецификации.

Тесты, использующие ``public_db``, пропускаются (``SKIPPED``), если не задана
переменная окружения ``BLASTEX_TEST_DATABASE_URL``.

ВАЖНО: никогда не указывайте в ``BLASTEX_TEST_DATABASE_URL`` боевую базу
``project1`` — фикстура выполняет ``DROP SCHEMA public CASCADE`` и уничтожит
все данные организации. Используйте отдельную тестовую базу (например,
``project1_test``).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text

TEST_DATABASE_URL = os.getenv("BLASTEX_TEST_DATABASE_URL", "").strip()

requires_pg = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="BLASTEX_TEST_DATABASE_URL не задан"
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PUBLIC_SCHEMA_SQL = _REPO_ROOT / "Docs" / "public_schema.sql"
_RLS_FUNCTION_MARKER = "CREATE OR REPLACE FUNCTION public.rls_auto_enable"
_DOLLAR_QUOTE = "$function$"
_STANDALONE_SEQUENCE_MARKER = "CREATE SEQUENCE public."


def _strip_line_comment(line: str) -> str:
    """Убирает однострочный SQL-комментарий ``-- ...`` из конца строки.

    В дампе DBeaver комментарий обычно занимает всю строку, но встречается и
    хвостом после кода на той же строке (например, ``NO CYCLE;-- ...
    определение`` у ``CREATE SEQUENCE``) — без этой обрезки точка с запятой
    «слипается» со следующим оператором, и разбиение по ``;\\n`` их не
    разделяет.
    """
    index = line.find("--")
    return line if index == -1 else line[:index]


def _statements(ddl: str) -> list[str]:
    """Разбивает дамп DDL на отдельные операторы.

    Комментарии (``-- ...``, целой строкой или хвостом после кода) и
    оператор ``CREATE SCHEMA public AUTHORIZATION user1;`` (роль ``user1`` в
    тестовой базе не существует) отбрасываются. Разделитель операторов —
    ``;\\n``, как в дампе DBeaver.

    Функция ``public.rls_auto_enable`` пропускается целиком: это функция
    событийного триггера, её выполнение требует прав суперпользователя, а RLS
    на тестовые таблицы уже включает сам DDL (``ENABLE ROW LEVEL SECURITY``
    в каждом ``CREATE TABLE``). Тело функции написано на PL/pgSQL и само
    содержит символы ``;\\n`` (например, после ``EXECUTE format(...)``), из-за
    чего наивное разбиение по ``;\\n`` дробит функцию на несколько
    операторов — все они отбрасываются до закрывающей кавычки
    ``$function$`` включительно.

    Отдельные операторы ``CREATE SEQUENCE public.<table>_id_seq`` тоже
    отбрасываются: в дампе они для каждой таблицы дублируют
    последовательность, которую и так создаёт сама таблица через
    ``serial4``/``GENERATED ... AS IDENTITY`` у колонки ``id`` (это артефакт
    полного DDL-экспорта DBeaver — «Sequences» выгружаются как отдельные
    объекты каталога, даже если они принадлежат identity/serial-колонке). Без
    этого фильтра ``CREATE TABLE`` падает с ``relation "..._id_seq" already
    exists``, поскольку последовательность с таким именем уже создана явно
    выше по файлу. В дампе нет ни одной последовательности вне этого
    шаблона и ни одного ``nextval``/``setval`` с ручной ссылкой на них.
    """
    body_lines = [_strip_line_comment(line) for line in ddl.splitlines()]
    body = "\n".join(line for line in body_lines if line.strip())
    body = body.replace("CREATE SCHEMA public AUTHORIZATION user1;", "")
    raw_statements = [part.strip() for part in body.split(";\n") if part.strip()]

    statements: list[str] = []
    skipping_function = False
    dollar_quotes_seen = 0
    for statement in raw_statements:
        if statement.startswith(_STANDALONE_SEQUENCE_MARKER):
            continue
        if not skipping_function and _RLS_FUNCTION_MARKER in statement:
            skipping_function = True
        if skipping_function:
            dollar_quotes_seen += statement.count(_DOLLAR_QUOTE)
            if dollar_quotes_seen >= 2:
                skipping_function = False
            continue
        statements.append(statement)
    return statements


@pytest.fixture()
def public_db() -> Engine:
    """Пересоздаёт схему ``public`` из DDL и применяет миграции ``blastex``.

    После теста ничего не чистит: следующий тест, использующий эту фикстуру,
    сам пересоздаёт схему ``public`` с нуля.
    """
    engine = create_engine(TEST_DATABASE_URL, future=True)

    ddl_text = _PUBLIC_SCHEMA_SQL.read_text(encoding="utf-8")
    statements = _statements(ddl_text)

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
        for statement in statements:
            # exec_driver_sql, а не text(): вьюхи содержат `::`-приведения
            # типов, которые SQLAlchemy иначе пытается разобрать как
            # именованные параметры.
            connection.exec_driver_sql(statement)

    subprocess_env = dict(os.environ)
    subprocess_env["BLASTEX_DATABASE_URL"] = TEST_DATABASE_URL
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_REPO_ROOT,
        env=subprocess_env,
        check=True,
    )

    return engine


def seed_public(engine: Engine) -> dict[str, Any]:
    """Наполняет схему ``public`` минимальным набором данных по §13.

    Возвращает словарь идентификаторов вставленных записей.
    """
    ids: dict[str, Any] = {}

    with engine.begin() as connection:
        ids["counterparty_client"] = connection.execute(
            text(
                """
                insert into public.counterparties
                    (full_name, short_name, inn, is_client, is_supplier, is_active)
                values
                    (:full_name, :short_name, :inn, true, false, true)
                returning id
                """
            ),
            {
                "full_name": 'АО "Теплогорский карьер"',
                "short_name": "ТГК",
                "inn": "6608002092",
            },
        ).scalar_one()

        ids["counterparty_supplier"] = connection.execute(
            text(
                """
                insert into public.counterparties
                    (full_name, short_name, inn, is_client, is_supplier, is_active)
                values
                    (:full_name, :short_name, :inn, false, true, true)
                returning id
                """
            ),
            {
                "full_name": 'ООО "ПОМБУР"',
                "short_name": "ПОМБУР",
                "inn": "7203270545",
            },
        ).scalar_one()

        ids["site_lom"] = connection.execute(
            text(
                """
                insert into public.sites
                    (full_name, short_name, client_legal_name, mineral_type, is_active)
                values
                    (:full_name, :short_name, :client_legal_name, :mineral_type, true)
                returning id
                """
            ),
            {
                "full_name": "Ломоватский карьер",
                "short_name": "ЛОМ",
                "client_legal_name": 'АО "Теплогорский карьер"',
                "mineral_type": "неруудные материалы",
            },
        ).scalar_one()

        ids["site_tsst"] = connection.execute(
            text(
                """
                insert into public.sites
                    (full_name, short_name, client_legal_name, mineral_type, is_active)
                values
                    (:full_name, :short_name, :client_legal_name, :mineral_type, true)
                returning id
                """
            ),
            {
                "full_name": "Центральный склад ТМЦ",
                "short_name": "ЦСТ",
                "client_legal_name": "Центральный склад ТМЦ",
                "mineral_type": None,
            },
        ).scalar_one()

        ids["machine_type"] = connection.execute(
            text(
                """
                insert into public.machine_types (name)
                values (:name)
                returning id
                """
            ),
            {"name": "Буровая установка"},
        ).scalar_one()

        ids["equipment_model"] = connection.execute(
            text(
                """
                insert into public.equipment_models
                    (machine_type_id, brand, model_name)
                values
                    (:machine_type_id, :brand, :model_name)
                returning id
                """
            ),
            {
                "machine_type_id": ids["machine_type"],
                "brand": "JK Drilling",
                "model_name": "JK830-2",
            },
        ).scalar_one()

        ids["equipment_unit"] = connection.execute(
            text(
                """
                insert into public.equipment_units
                    (model_id, internal_id, serial_number, status, current_site_id)
                values
                    (:model_id, :internal_id, :serial_number, :status, :current_site_id)
                returning id
                """
            ),
            {
                "model_id": ids["equipment_model"],
                "internal_id": "Б-01",
                "serial_number": "SN-JK830-0001",
                "status": "В работе",
                "current_site_id": ids["site_lom"],
            },
        ).scalar_one()

        ids["device_type_1"] = connection.execute(
            text(
                """
                insert into public.initiating_device_types (name, description)
                values (:name, :description)
                returning id
                """
            ),
            {"name": "ЭД-1-Н", "description": "Электродетонатор непредохранительный"},
        ).scalar_one()

        ids["device_type_2"] = connection.execute(
            text(
                """
                insert into public.initiating_device_types (name, description)
                values (:name, :description)
                returning id
                """
            ),
            {"name": "СИНВ-Ш", "description": "Система инициирования неэлектрическая"},
        ).scalar_one()

        connection.execute(
            text(
                """
                insert into public.delay_series (device_type_id, delay_ms, is_standard)
                values (:device_type_id, :delay_ms, true)
                """
            ),
            {"device_type_id": ids["device_type_2"], "delay_ms": 25},
        )

        ids["tool_type"] = connection.execute(
            text(
                """
                insert into public.tool_types
                    (name, expected_lifetime_meters, description, diameter, thread_type)
                values
                    (:name, :expected_lifetime_meters, :description, :diameter, :thread_type)
                returning id
                """
            ),
            {
                "name": "Долото шарошечное 152",
                "expected_lifetime_meters": 600,
                "description": "Шарошечное долото для буровой установки JK830-2",
                "diameter": 152,
                "thread_type": "З-76",
            },
        ).scalar_one()

        ids["contract"] = connection.execute(
            text(
                """
                insert into public.contracts
                    (counterparty_id, direction, contract_number, contract_date)
                values
                    (:counterparty_id, :direction, :contract_number, :contract_date)
                returning id
                """
            ),
            {
                "counterparty_id": ids["counterparty_supplier"],
                "direction": "Поставщик",
                "contract_number": "Д-2026-001",
                "contract_date": "2026-01-15",
            },
        ).scalar_one()

        ids["purchase_spec"] = connection.execute(
            text(
                """
                insert into public.explosive_purchase_specs
                    (contract_id, spec_number, spec_date, total_delivery_cost_no_vat)
                values
                    (:contract_id, :spec_number, :spec_date, :total_delivery_cost_no_vat)
                returning id
                """
            ),
            {
                "contract_id": ids["contract"],
                "spec_number": "СПЦ-2026-001",
                "spec_date": "2026-01-20",
                "total_delivery_cost_no_vat": 15000,
            },
        ).scalar_one()

        ids["spec_item"] = connection.execute(
            text(
                """
                insert into public.explosive_spec_items
                    (spec_id, device_type_id, quantity_ordered, price_per_unit_no_vat, conversion_factor)
                values
                    (:spec_id, :device_type_id, :quantity_ordered, :price_per_unit_no_vat, :conversion_factor)
                returning id
                """
            ),
            {
                "spec_id": ids["purchase_spec"],
                "device_type_id": ids["device_type_1"],
                "quantity_ordered": 2000,
                "price_per_unit_no_vat": 45000,
                "conversion_factor": 1000,
            },
        ).scalar_one()

        ids["tools_inventory"] = connection.execute(
            text(
                """
                insert into public.tools_inventory
                    (tool_type_id, serial_number, purchase_price, purchase_date, supplier_id, status)
                values
                    (:tool_type_id, :serial_number, :purchase_price, :purchase_date, :supplier_id, :status)
                returning id
                """
            ),
            {
                "tool_type_id": ids["tool_type"],
                "serial_number": "SN-BIT-152-0001",
                "purchase_price": 38500,
                "purchase_date": "2026-01-25",
                "supplier_id": ids["counterparty_supplier"],
                "status": "Склад",
            },
        ).scalar_one()

    return ids
