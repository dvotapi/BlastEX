"""Cost V2: ревизии справочников, сценарии и расчётные снимки.

Revision ID: 20260830_0001
Revises: None
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260830_0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "blastex"


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema(SCHEMA, if_not_exists=True))
    op.create_table(
        "reference_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.String(length=320), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "organization_id", "sequence_no", name="uq_reference_revision_sequence"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_reference_revision_latest",
        "reference_revisions",
        ["organization_id", "sequence_no"],
        schema=SCHEMA,
    )
    op.create_table(
        "reference_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column(
            "revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("section", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default=""),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("item_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("revision_id", "section", "code", name="uq_reference_item_code"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_reference_item_lookup",
        "reference_items",
        ["organization_id", "revision_id", "section"],
        schema=SCHEMA,
    )
    op.create_table(
        "economic_scenarios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("production_unit_code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_economic_scenario_org_updated",
        "economic_scenarios",
        ["organization_id", "updated_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "calculation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column(
            "scenario_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.economic_scenarios.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reference_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("formula_version", sa.String(length=80), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_calculation_run_scenario",
        "calculation_runs",
        ["organization_id", "scenario_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("actor", sa.String(length=320), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=False),
        sa.Column("before_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_org_created",
        "audit_log",
        ["organization_id", "created_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Явный rollback только новой схемы; текущие JSON Cost V1 не затрагиваются.
    op.drop_index("ix_audit_org_created", table_name="audit_log", schema=SCHEMA)
    op.drop_table("audit_log", schema=SCHEMA)
    op.drop_index("ix_calculation_run_scenario", table_name="calculation_runs", schema=SCHEMA)
    op.drop_table("calculation_runs", schema=SCHEMA)
    op.drop_index("ix_economic_scenario_org_updated", table_name="economic_scenarios", schema=SCHEMA)
    op.drop_table("economic_scenarios", schema=SCHEMA)
    op.drop_index("ix_reference_item_lookup", table_name="reference_items", schema=SCHEMA)
    op.drop_table("reference_items", schema=SCHEMA)
    op.drop_index("ix_reference_revision_latest", table_name="reference_revisions", schema=SCHEMA)
    op.drop_table("reference_revisions", schema=SCHEMA)
    op.execute(sa.schema.DropSchema(SCHEMA))
