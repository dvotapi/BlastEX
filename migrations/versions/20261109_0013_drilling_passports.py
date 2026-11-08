"""Паспорта на бурение и их неизменяемые ревизии (TASK-015, PR 1).

Revision ID: 20261109_0013
Revises: 20261003_0012
Create Date: 2026-11-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261109_0013"
down_revision = "20261003_0012"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "drilling_passports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("design_id", sa.String(length=120), nullable=False),
        sa.Column("passport_no", sa.String(length=120), nullable=False),
        sa.Column("passport_date", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_revision_id", sa.String(length=36), nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_drilling_passport_org_updated", "drilling_passports", ["organization_id", "updated_at"], schema=SCHEMA
    )
    op.create_index("ix_drilling_passport_design", "drilling_passports", ["organization_id", "design_id"], schema=SCHEMA)

    op.create_table(
        "drilling_passport_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "passport_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.drilling_passports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column(
            "previous_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.drilling_passport_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("reference_revision_id", sa.String(length=36), nullable=True),
        sa.Column("formula_version", sa.String(length=80), nullable=False),
        sa.Column("design_id", sa.String(length=120), nullable=False),
        sa.Column("design_revision", sa.Integer(), nullable=False),
        sa.Column("design_sha256", sa.String(length=64), nullable=False),
        sa.Column("context", JSONB, nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.UniqueConstraint("passport_id", "revision_no", name="uq_drilling_passport_revision_no"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_drilling_passport_revision_passport",
        "drilling_passport_revisions",
        ["passport_id", "revision_no"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_drilling_passport_revision_passport", table_name="drilling_passport_revisions", schema=SCHEMA)
    op.drop_table("drilling_passport_revisions", schema=SCHEMA)
    op.drop_index("ix_drilling_passport_design", table_name="drilling_passports", schema=SCHEMA)
    op.drop_index("ix_drilling_passport_org_updated", table_name="drilling_passports", schema=SCHEMA)
    op.drop_table("drilling_passports", schema=SCHEMA)
