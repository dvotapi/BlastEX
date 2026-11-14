"""Съёмка старого блока на объекте (TASK-014, PR 5а).

`site_surveys` — точки съёмки блока, которого нет в проектах BlastEX; их
читает «Подбор по соседним блокам» (PR 5б). Повторная загрузка того же файла
для того же блока запрещена уникальным индексом.

Revision ID: 20261114_0017
Revises: 20261113_0016
Create Date: 2026-11-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261114_0017"
down_revision = "20261113_0016"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
TABLE = "site_surveys"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("site_code", sa.Text(), nullable=False),
        sa.Column("block_label", sa.Text(), nullable=False),
        sa.Column("horizon_m", sa.Numeric(), nullable=True),
        sa.Column("survey_date", sa.Date(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("file_sha256", sa.Text(), nullable=False),
        sa.Column("points", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_site_surveys_org_site_date",
        TABLE,
        ["organization_id", "site_code", sa.text("survey_date DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        "uq_site_surveys_file",
        TABLE,
        ["organization_id", "site_code", "block_label", "file_sha256"],
        unique=True,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("uq_site_surveys_file", table_name=TABLE, schema=SCHEMA)
    op.drop_index("ix_site_surveys_org_site_date", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
