"""Импорт чертежа: ситуация карьера и система координат объекта (TASK-013, PR 4).

- `cad_sources.title` — название источника. Источники объекта с одинаковым
  названием — версии одной серии ситуации («Положение горных работ» на 01.09
  и на 01.10). Старым источникам достаётся имя файла без расширения.
- Индекс по `(organization_id, site_code, file_sha256)`: тот же файл на том же
  объекте открывает прежний разбор, а не создаёт копию.
- `cad_layer_roles.situation_kind` — вид объекта ситуации, заданный
  человеком (дорога, ЛЭП, склад…); NULL — вид по имени слоя.
- `cad_site_settings.crs_name`, `height_system`, `epsg` — система координат
  объекта («МСК-66 зона 1», «Балтийская 1977»): задаётся один раз, следующие
  файлы её наследуют.

Revision ID: 20261003_0012
Revises: 20261002_0011
Create Date: 2026-10-03
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261003_0012"
down_revision = "20261002_0011"
branch_labels = None
depends_on = None

SCHEMA = "blastex"


def upgrade() -> None:
    op.add_column(
        "cad_sources",
        sa.Column("title", sa.String(length=300), nullable=False, server_default=""),
        schema=SCHEMA,
    )
    op.execute(
        f"UPDATE {SCHEMA}.cad_sources SET title = regexp_replace(file_name, '\\.[^./]*$', '') WHERE title = ''"
    )
    op.create_index(
        "ix_cad_sources_org_site_sha",
        "cad_sources",
        ["organization_id", "site_code", "file_sha256"],
        schema=SCHEMA,
    )
    op.add_column(
        "cad_layer_roles",
        sa.Column("situation_kind", sa.String(length=16), nullable=True),
        schema=SCHEMA,
    )
    op.add_column("cad_site_settings", sa.Column("crs_name", sa.String(length=120), nullable=True), schema=SCHEMA)
    op.add_column(
        "cad_site_settings", sa.Column("height_system", sa.String(length=120), nullable=True), schema=SCHEMA
    )
    op.add_column("cad_site_settings", sa.Column("epsg", sa.Integer(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("cad_site_settings", "epsg", schema=SCHEMA)
    op.drop_column("cad_site_settings", "height_system", schema=SCHEMA)
    op.drop_column("cad_site_settings", "crs_name", schema=SCHEMA)
    op.drop_column("cad_layer_roles", "situation_kind", schema=SCHEMA)
    op.drop_index("ix_cad_sources_org_site_sha", table_name="cad_sources", schema=SCHEMA)
    op.drop_column("cad_sources", "title", schema=SCHEMA)
