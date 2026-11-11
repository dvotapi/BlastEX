"""Слои проекта массового взрыва — документы дня взрыва (TASK-018, PR 2).

Слой (наряд-путёвка, уведомление, акт готовности, талон-допуск, акт приёмки)
ссылается на ревизию проекта, но её не меняет; у слоя свои данные и
неизменяемые ревизии.

Revision ID: 20261111_0014
Revises: 20261109_0013
Create Date: 2026-11-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261111_0014"
down_revision = "20261109_0013"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "mass_blast_layers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column(
            "project_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.mass_blast_projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column(
            "project_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_revision_id", sa.String(length=36), nullable=True),
        sa.Column("seed", JSONB, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_mass_blast_layer_project", "mass_blast_layers", ["project_id", "kind"], schema=SCHEMA)

    op.create_table(
        "mass_blast_layer_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "layer_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.mass_blast_layers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column(
            "project_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("context", JSONB, nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.UniqueConstraint("layer_id", "revision_no", name="uq_mass_blast_layer_revision_no"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_mass_blast_layer_revision_layer", "mass_blast_layer_revisions", ["layer_id", "revision_no"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_mass_blast_layer_revision_layer", table_name="mass_blast_layer_revisions", schema=SCHEMA)
    op.drop_table("mass_blast_layer_revisions", schema=SCHEMA)
    op.drop_index("ix_mass_blast_layer_project", table_name="mass_blast_layers", schema=SCHEMA)
    op.drop_table("mass_blast_layers", schema=SCHEMA)
