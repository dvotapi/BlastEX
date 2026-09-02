"""Снимки прогонов модели себестоимости блока.

Каждый прогон вкладки «Экономика» сохраняется целиком: паспорт, пакет,
ревизия справочников, параметры модели и результат. Сравнение сценариев
идёт между снимками, поэтому пересчитывать старый прогон не требуется.

Revision ID: 20260903_0005
Revises: 20260902_0004
Create Date: 2026-09-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260903_0005"
down_revision = "20260902_0004"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "economics_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column(
            "technical_passport_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.technical_passports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("package_code", sa.String(length=80), nullable=False),
        sa.Column(
            "reference_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("parameters", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_economics_run_passport",
        "economics_runs",
        ["organization_id", "technical_passport_id", "created_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_economics_run_passport", table_name="economics_runs", schema=SCHEMA)
    op.drop_table("economics_runs", schema=SCHEMA)
