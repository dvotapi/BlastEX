"""Импорт чертежа: настройки объекта — какая площадь считается площадью блока (TASK-013, PR 2).

Каждый маркшейдер называет «площадью блока» своё: площадь по верхней бровке,
по нижней или их среднее. Выбор инженера хранится на объекте работ
(`site_code`) и применяется к следующим файлам этого объекта.

Revision ID: 20261001_0010
Revises: 20260930_0009
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261001_0010"
down_revision = "20260930_0009"
branch_labels = None
depends_on = None

SCHEMA = "blastex"


def upgrade() -> None:
    op.create_table(
        "cad_site_settings",
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("site_code", sa.String(length=80), nullable=False),
        # top — S верх, bottom — S низ, mean — (S верх + S низ) / 2.
        sa.Column("area_basis", sa.String(length=16), nullable=False, server_default="mean"),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "site_code", name="pk_cad_site_settings"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("cad_site_settings", schema=SCHEMA)
