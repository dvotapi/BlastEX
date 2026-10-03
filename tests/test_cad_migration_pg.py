"""Миграция импорта чертежа обратима: upgrade → downgrade → upgrade."""
from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import inspect, text

from tests.pg_public import _REPO_ROOT, TEST_DATABASE_URL, public_db, requires_pg  # noqa: F401 — фикстура

CAD_TABLES = {"cad_sources", "cad_entities", "cad_layer_roles", "cad_site_settings"}
PREVIOUS_HEAD = "20260910_0008"
HEAD = "20261003_0012"


def _alembic(*args: str) -> None:
    env = dict(os.environ)
    env["BLASTEX_DATABASE_URL"] = TEST_DATABASE_URL
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=_REPO_ROOT, env=env, check=True)


def _cad_tables(engine) -> set[str]:
    return CAD_TABLES & set(inspect(engine).get_table_names(schema="blastex"))


@requires_pg
def test_cad_migration_is_reversible(public_db) -> None:
    assert _cad_tables(public_db) == CAD_TABLES

    _alembic("downgrade", PREVIOUS_HEAD)
    assert _cad_tables(public_db) == set()

    _alembic("upgrade", "20260930_0009")
    assert _cad_tables(public_db) == CAD_TABLES - {"cad_site_settings"}

    _alembic("upgrade", HEAD)
    assert _cad_tables(public_db) == CAD_TABLES


@requires_pg
def test_site_settings_migration_is_reversible(public_db) -> None:
    _alembic("downgrade", "20260930_0009")
    assert _cad_tables(public_db) == CAD_TABLES - {"cad_site_settings"}

    _alembic("upgrade", HEAD)
    assert _cad_tables(public_db) == CAD_TABLES


def _columns(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table, schema="blastex")}


def _sha_index(engine) -> bool:
    return any(
        index["name"] == "ix_cad_sources_org_site_sha"
        for index in inspect(engine).get_indexes("cad_sources", schema="blastex")
    )


@requires_pg
def test_situation_migration_is_reversible_and_titles_old_sources(public_db) -> None:
    """PR 4: название источника, вид слоя ситуации, СК объекта."""

    # Откат только PR 4: предыдущая ревизия — Kuz-Ram (#106), её не трогаем.
    _alembic("downgrade", "20261002_0011")
    public_db.dispose()
    assert "title" not in _columns(public_db, "cad_sources")
    assert "situation_kind" not in _columns(public_db, "cad_layer_roles")
    assert not {"crs_name", "height_system", "epsg"} & _columns(public_db, "cad_site_settings")
    assert not _sha_index(public_db)
    with public_db.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO blastex.cad_sources (id, organization_id, site_code, work_object_name, file_name,"
                " file_format, file_size, file_sha256, file_data, params, summary, uploaded_by, uploaded_at, revision)"
                " VALUES ('old', 'org', 'SITE', '', '28.09 граница блока 66.v2.dwg', 'dwg', 1, :sha, :data,"
                " '{}', '{}', 'u', now(), 1)"
            ),
            {"sha": "0" * 64, "data": b"x"},
        )

    _alembic("upgrade", HEAD)
    public_db.dispose()
    assert "title" in _columns(public_db, "cad_sources")
    assert "situation_kind" in _columns(public_db, "cad_layer_roles")
    assert {"crs_name", "height_system", "epsg"} <= _columns(public_db, "cad_site_settings")
    assert _sha_index(public_db)
    with public_db.connect() as connection:
        title = connection.execute(text("SELECT title FROM blastex.cad_sources WHERE id = 'old'")).scalar_one()
    assert title == "28.09 граница блока 66.v2"
