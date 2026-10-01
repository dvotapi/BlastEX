"""Миграция импорта чертежа обратима: upgrade → downgrade → upgrade."""
from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import inspect

from tests.pg_public import _REPO_ROOT, TEST_DATABASE_URL, public_db, requires_pg  # noqa: F401 — фикстура

CAD_TABLES = {"cad_sources", "cad_entities", "cad_layer_roles", "cad_site_settings"}
PREVIOUS_HEAD = "20260910_0008"


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

    _alembic("upgrade", "20261001_0010")
    assert _cad_tables(public_db) == CAD_TABLES


@requires_pg
def test_site_settings_migration_is_reversible(public_db) -> None:
    _alembic("downgrade", "20260930_0009")
    assert _cad_tables(public_db) == CAD_TABLES - {"cad_site_settings"}

    _alembic("upgrade", "20261001_0010")
    assert _cad_tables(public_db) == CAD_TABLES
