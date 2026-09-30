"""Импорт чертежа маркшейдера: источники, сущности, шаблон слоёв объекта (TASK-013).

Revision ID: 20260930_0009
Revises: 20260910_0008
Create Date: 2026-09-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260930_0009"
down_revision = "20260910_0008"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "cad_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("site_code", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("work_object_name", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("file_name", sa.String(length=300), nullable=False),
        sa.Column("file_format", sa.String(length=8), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_data", sa.LargeBinary(), nullable=False),
        sa.Column("survey_date", sa.Date(), nullable=True),
        sa.Column("coordinate_system", JSONB, nullable=True),
        sa.Column("params", JSONB, nullable=False),
        sa.Column("summary", JSONB, nullable=False),
        sa.Column("uploaded_by", sa.String(length=320), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        # Номер правки источника: запись с устаревшим номером отклоняется.
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id", name="pk_cad_sources"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_cad_sources_org_site_uploaded",
        "cad_sources",
        ["organization_id", "site_code", "uploaded_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "cad_entities",
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.cad_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("handle", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("layer", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("role_origin", sa.String(length=16), nullable=False),
        sa.Column("geometry", JSONB, nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("vertex_count", sa.Integer(), nullable=False),
        sa.Column("length_m", sa.Float(), nullable=False),
        sa.Column("z_kind", sa.String(length=8), nullable=False),
        sa.Column("z_min", sa.Float(), nullable=False),
        sa.Column("z_max", sa.Float(), nullable=False),
        sa.Column("attributes", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("source_id", "handle", name="pk_cad_entities"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_cad_entities_org_source_seq",
        "cad_entities",
        ["organization_id", "source_id", "seq"],
        schema=SCHEMA,
    )

    op.create_table(
        "cad_layer_roles",
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("site_code", sa.String(length=80), nullable=False),
        sa.Column("layer_key", sa.String(length=255), nullable=False),
        sa.Column("layer_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        # Роль подтверждена человеком (ручная правка), а не догадка импорта.
        sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "site_code", "layer_key", name="pk_cad_layer_roles"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("cad_layer_roles", schema=SCHEMA)
    op.drop_index("ix_cad_entities_org_source_seq", table_name="cad_entities", schema=SCHEMA)
    op.drop_table("cad_entities", schema=SCHEMA)
    op.drop_index("ix_cad_sources_org_site_uploaded", table_name="cad_sources", schema=SCHEMA)
    op.drop_table("cad_sources", schema=SCHEMA)
