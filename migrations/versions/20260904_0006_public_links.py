"""Связи записей blastex с таблицами схемы public и переключатели зеркал.

`public_links` хранит, какой записи журнала буровых работ соответствует
запись справочника; `public_mirror_sections` — какие разделы выгружаются
зеркалом `public.blastex_<section>` (спецификация §4.3, §5).

Revision ID: 20260904_0006
Revises: 20260903_0005
Create Date: 2026-09-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260904_0006"
down_revision = "20260903_0005"
branch_labels = None
depends_on = None

SCHEMA = "blastex"


def upgrade() -> None:
    op.create_table(
        "public_links",
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("public_table", sa.String(length=64), nullable=False),
        sa.Column("public_id", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "section", "code", name="pk_public_links"),
        sa.UniqueConstraint("public_table", "public_id", name="uq_public_links_public_row"),
        schema=SCHEMA,
    )
    op.create_table(
        "public_mirror_sections",
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "section", name="pk_public_mirror_sections"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("public_mirror_sections", schema=SCHEMA)
    op.drop_table("public_links", schema=SCHEMA)
