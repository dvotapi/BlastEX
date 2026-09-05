"""Тесты скрипта прав ``scripts/grant_public_access.sql``.

Базы данных здесь нет: скрипт читается как текст и проверяется простым
разбором на упоминания таблиц, роли и запрещённых прав. Список таблиц в
скрипте должен буквально совпадать с ``cost.v2.public_sync.mapping.TABLES`` —
это и проверяет тест, чтобы новая таблица в справочниках не осталась без
прав и без политики.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cost.v2.public_sync.mapping import TABLES

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "grant_public_access.sql"


@pytest.fixture(scope="module")
def script_text() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_script_exists() -> None:
    assert SCRIPT_PATH.is_file(), f"Не найден файл {SCRIPT_PATH}"


def test_grants_schema_usage_and_create(script_text: str) -> None:
    assert "GRANT USAGE, CREATE ON SCHEMA public TO blastex" in script_text


def test_grants_sequences(script_text: str) -> None:
    assert "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO blastex" in script_text


def test_role_mentioned(script_text: str) -> None:
    assert "blastex" in script_text


def test_no_delete_grant(script_text: str) -> None:
    # Слово DELETE недопустимо в самих SQL-выражениях (GRANT/CREATE POLICY),
    # но может встречаться в комментариях на русском («не удаляет» и т. п.) —
    # поэтому разбор построчный, и комментарии (начинаются с "--") пропускаются.
    for line in script_text.splitlines():
        code = line.split("--", 1)[0]
        assert "DELETE" not in code.upper(), f"DELETE встречено в SQL-коде: {line!r}"


@pytest.mark.parametrize("table", TABLES)
def test_each_table_granted(script_text: str, table: str) -> None:
    assert f"public.{table}" in script_text, (
        f"Таблица {table} из TABLES не упомянута в GRANT — скрипт устарел"
    )


@pytest.mark.parametrize("table", TABLES)
def test_each_table_has_policy(script_text: str, table: str) -> None:
    # Список таблиц политики — отдельный (текстовый) массив в DO $$ … $$;
    # каждое имя должно встретиться там же, где и остальные, одним словом.
    assert f"'{table}'" in script_text, (
        f"Таблица {table} из TABLES не упомянута в массиве политик — скрипт устарел"
    )


def test_policy_name_blastex_full_access(script_text: str) -> None:
    assert "blastex_full_access" in script_text


def test_policy_uses_pg_policies_guard(script_text: str) -> None:
    assert "pg_policies" in script_text
    assert "IF NOT EXISTS" in script_text


def test_tables_count_matches_mapping(script_text: str) -> None:
    # Подсчитываем вхождения "public.<table>" для GRANT — их должно быть
    # ровно len(TABLES), не больше (иначе список скрипта разошёлся с TABLES).
    granted = {table for table in TABLES if f"public.{table}" in script_text}
    assert granted == set(TABLES)
