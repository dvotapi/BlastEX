"""Тесты чтения схемы ``public`` на реальном PostgreSQL.

Тесты с фикстурой ``public_db`` (дымовой и чтение журнала через
``SqlPublicReader``) пропускаются без ``BLASTEX_TEST_DATABASE_URL``.

Остальные тесты проверяют разбор DDL (``_statements``) без обращения к базе
данных — обычная зависимость от ``Docs/public_schema.sql`` как эталона.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from sqlalchemy import create_engine

from cost.v2.public_sync.reader import PublicUnavailable, SqlPublicReader
from tests import pg_public
from tests.pg_public import (
    _PUBLIC_SCHEMA_SQL,
    RESET_STATEMENTS,
    _statements,
    public_db,
    requires_pg,
    seed_public,
    tracked_migration_head,
)

# BLASTEX_TEST_DATABASE_URL требуют только тесты с фикстурой public_db;
# разбор DDL (_statements) и обработка ошибки драйвера работают без
# PostgreSQL, поэтому маркер skipif навешан на конкретные тесты, а не на
# весь модуль через pytestmark.


@requires_pg
def test_public_schema_loads_and_seeds(public_db) -> None:
    ids = seed_public(public_db)

    with public_db.connect() as conn:
        assert conn.execute(text("select count(*) from public.sites")).scalar() == 2
        assert (
            conn.execute(text("select count(*) from blastex.public_links")).scalar()
            == 0
        )
    assert ids["site_lom"] > 0


def test_reset_statements_drop_both_schemas() -> None:
    """Сброс базы сносит и ``blastex``: Alembic хранит версию в ``public``.

    Без удаления ``blastex`` второй тест с фикстурой начинал бы с пустой
    ``alembic_version`` и уже существующих таблиц — ``upgrade head`` падал бы
    на миграции 0001.
    """
    joined = " | ".join(RESET_STATEMENTS)

    assert "DROP SCHEMA IF EXISTS blastex CASCADE" in RESET_STATEMENTS
    assert "DROP SCHEMA IF EXISTS public CASCADE" in RESET_STATEMENTS
    assert joined.index("DROP SCHEMA IF EXISTS public") < joined.index("CREATE SCHEMA public")


def test_statements_drops_authorization_line() -> None:
    ddl = 'CREATE SCHEMA public AUTHORIZATION user1;\nCREATE TABLE public.t (id int4);\n'
    statements = _statements(ddl)

    assert all("AUTHORIZATION" not in statement for statement in statements)


def test_statements_skips_rls_auto_enable_function() -> None:
    ddl = (
        "CREATE TABLE public.t (id int4);\n"
        "CREATE OR REPLACE FUNCTION public.rls_auto_enable()\n"
        " RETURNS event_trigger\n"
        " LANGUAGE plpgsql\n"
        "AS $function$\n"
        "DECLARE\n"
        "  cmd record;\n"
        "BEGIN\n"
        "  EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);\n"
        "  RAISE LOG 'done: %', cmd.object_identity;\n"
        "END;\n"
        "$function$\n"
        ";\n"
        "CREATE TABLE public.u (id int4);\n"
    )
    statements = _statements(ddl)

    assert not any("rls_auto_enable" in statement for statement in statements)
    assert not any("DECLARE" in statement for statement in statements)
    assert not any("EXECUTE format" in statement for statement in statements)
    assert not any("$function$" in statement for statement in statements)
    # У последнего оператора в строке DDL может остаться завершающая ";" —
    # split по "\n" не добавляет разделитель после последней строки файла,
    # это не считается ошибкой разбора (";" — валидное окончание запроса).
    assert [s.rstrip(";") for s in statements] == [
        "CREATE TABLE public.t (id int4)",
        "CREATE TABLE public.u (id int4)",
    ]


def test_statements_keeps_every_create_table_from_real_ddl() -> None:
    ddl = _PUBLIC_SCHEMA_SQL.read_text(encoding="utf-8")
    create_table_lines = [
        line
        for line in ddl.splitlines()
        if line.strip().startswith("CREATE TABLE public.")
    ]
    statements = _statements(ddl)

    table_statements = [s for s in statements if s.startswith("CREATE TABLE public.")]
    assert len(table_statements) == len(create_table_lines)
    for line in create_table_lines:
        table_name = line.split("(")[0].strip()
        assert any(statement.startswith(table_name) for statement in statements)


def test_statements_from_real_ddl_are_never_empty() -> None:
    ddl = _PUBLIC_SCHEMA_SQL.read_text(encoding="utf-8")
    statements = _statements(ddl)

    assert statements
    assert all(statement.strip() for statement in statements)


def test_statements_from_real_ddl_do_not_reference_user1() -> None:
    ddl = _PUBLIC_SCHEMA_SQL.read_text(encoding="utf-8")
    statements = _statements(ddl)

    assert not any("AUTHORIZATION user1" in statement for statement in statements)


def test_statements_drops_standalone_sequences_owned_by_identity_columns() -> None:
    # В дампе DBeaver `CREATE SEQUENCE public.<table>_id_seq` дублирует
    # последовательность, которую и так создаёт `CREATE TABLE` для колонки
    # `id` (serial4 / GENERATED ... AS IDENTITY). Если оставить оба
    # оператора, `CREATE TABLE` упадёт с "relation ... already exists".
    ddl = (
        "CREATE SEQUENCE public.widgets_id_seq\n"
        "\tINCREMENT BY 1\n"
        "\tMINVALUE 1\n"
        "\tMAXVALUE 2147483647\n"
        "\tSTART 1\n"
        "\tCACHE 1\n"
        "\tNO CYCLE;\n"
        "CREATE TABLE public.widgets ( id serial4 NOT NULL, name text NOT NULL, CONSTRAINT widgets_pkey PRIMARY KEY (id));\n"
    )
    statements = _statements(ddl)

    assert not any(statement.startswith("CREATE SEQUENCE") for statement in statements)
    assert any(statement.startswith("CREATE TABLE public.widgets") for statement in statements)


def test_statements_from_real_ddl_have_no_standalone_sequences() -> None:
    ddl = _PUBLIC_SCHEMA_SQL.read_text(encoding="utf-8")
    statements = _statements(ddl)

    assert not any(statement.startswith("CREATE SEQUENCE") for statement in statements)


def test_tracked_migration_head_matches_git_tracked_chain() -> None:
    """DB-free: голова определяется по файлам git, а не по каталогу целиком.

    Независимо от ``tracked_migration_head`` разбирает список отслеживаемых
    git файлов и убеждается, что найденная голова — ``20260904_0006`` и что
    ни один отслеживаемый файл не ссылается на неё как на ``down_revision``.
    """
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["git", "ls-files", "migrations/versions"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_paths = [
        repo_root / line
        for line in result.stdout.splitlines()
        if line.strip().endswith(".py")
    ]
    assert tracked_paths, "git ls-files не нашёл ни одной миграции"

    down_revisions = set()
    for path in tracked_paths:
        content = path.read_text(encoding="utf-8")
        match = re.search(r'^down_revision\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if match:
            down_revisions.add(match.group(1))

    head = tracked_migration_head()

    assert head == "20260904_0006"
    assert head not in down_revisions


def test_tracked_migration_head_fallback_ignores_duplicate_suffix(tmp_path, monkeypatch) -> None:
    """Без git сканируется каталог, а файлы вида «... N.py» игнорируются.

    Воспроизводит ситуацию с untracked конфликт-копиями редактора/облачной
    синхронизации: та же ревизия зарегистрирована повторно в файле с
    суффиксом « 2.py» — фолбэк должен вернуть голову линейной цепочки,
    построенной только по «настоящим» файлам.
    """
    (tmp_path / "20260101_0001_first.py").write_text(
        'revision = "20260101_0001"\ndown_revision = None\n', encoding="utf-8"
    )
    (tmp_path / "20260102_0002_second.py").write_text(
        'revision = "20260102_0002"\ndown_revision = "20260101_0001"\n',
        encoding="utf-8",
    )
    (tmp_path / "20260103_0003_third.py").write_text(
        'revision = "20260103_0003"\ndown_revision = "20260102_0002"\n',
        encoding="utf-8",
    )
    # Untracked-дубликат: та же ревизия "20260102_0002", что и второй файл —
    # если фолбэк его не отфильтрует, цепочка перестанет быть однозначной.
    (tmp_path / "20260102_0002_second 2.py").write_text(
        'revision = "20260102_0002"\ndown_revision = "20260101_0001"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(pg_public, "_MIGRATIONS_DIR", tmp_path)

    def _raise_git_missing(*args, **kwargs):
        raise FileNotFoundError("git отсутствует")

    monkeypatch.setattr(pg_public.subprocess, "run", _raise_git_missing)

    assert pg_public.tracked_migration_head() == "20260103_0003"


@requires_pg
def test_sql_reader_reads_seeded_tables(public_db) -> None:
    seed_public(public_db)
    snapshot = SqlPublicReader(public_db).read()

    assert len(snapshot.table("sites")) == 2
    assert snapshot.table("sites")[0].values["full_name"]


@requires_pg
def test_sql_reader_reports_missing_schema(public_db) -> None:
    with public_db.begin() as conn:
        conn.execute(text("DROP TABLE public.sites CASCADE"))

    with pytest.raises(PublicUnavailable, match="public"):
        SqlPublicReader(public_db).read()


def test_sql_reader_wraps_driver_error_into_public_unavailable() -> None:
    # SQLite здесь — просто источник ошибки драйвера: схемы public в ней нет.
    # Проверяется не база, а то, что ошибка превращается в PublicUnavailable
    # с русским текстом и причиной от драйвера.
    engine = create_engine("sqlite://", future=True)

    with pytest.raises(PublicUnavailable, match="Схема public недоступна") as error:
        SqlPublicReader(engine).read()

    assert "\n" not in str(error.value)
