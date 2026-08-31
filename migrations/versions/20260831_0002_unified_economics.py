"""Technical passports and PostgreSQL compatibility storage for Cost V1.

Revision ID: 20260831_0002
Revises: 20260830_0001
Create Date: 2026-08-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260831_0002"
down_revision = "20260830_0001"
branch_labels = None
depends_on = None

SCHEMA = "blastex"

def upgrade() -> None:
    op.create_table(
        "technical_passports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("site_code", sa.String(length=80), nullable=False),
        sa.Column("object_name", sa.String(length=300), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column(
            "previous_passport_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.technical_passports.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "reference_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("formula_version", sa.String(length=80), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_variant", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("block_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("physical", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("lineage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_technical_passport_org_site",
        "technical_passports",
        ["organization_id", "site_code", "created_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "legacy_workspace_settings",
        sa.Column("organization_id", sa.String(length=120), primary_key=True),
        sa.Column("team_name", sa.String(length=300), nullable=False),
        sa.Column("active_scenario_id", sa.String(length=120), nullable=False),
        sa.Column("active_work_object_name", sa.String(length=300), nullable=False),
        sa.Column(
            "reference_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "legacy_cost_scenarios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("scenario_key", sa.String(length=120), nullable=False),
        sa.Column(
            "reference_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("labor_assignment_records", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("drilling_calculator_input", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("scenario_phase_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.UniqueConstraint("organization_id", "scenario_key", name="uq_legacy_cost_scenario_key"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_legacy_cost_scenario_org",
        "legacy_cost_scenarios",
        ["organization_id", "updated_at"],
        schema=SCHEMA,
    )

    op.alter_column("calculation_runs", "scenario_id", nullable=True, schema=SCHEMA)
    op.add_column(
        "calculation_runs",
        sa.Column("calculation_scope", sa.String(length=20), nullable=False, server_default="UNIT"),
        schema=SCHEMA,
    )
    op.add_column(
        "calculation_runs",
        sa.Column("technical_passport_id", sa.String(length=36), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "calculation_runs",
        sa.Column("site_code", sa.String(length=80), nullable=False, server_default=""),
        schema=SCHEMA,
    )
    op.add_column(
        "calculation_runs",
        sa.Column("period", sa.String(length=20), nullable=False, server_default=""),
        schema=SCHEMA,
    )
    op.add_column(
        "calculation_runs",
        sa.Column("technical_formula_version", sa.String(length=80), nullable=False, server_default=""),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_calculation_run_technical_passport",
        "calculation_runs",
        "technical_passports",
        ["technical_passport_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_calculation_run_technical_passport",
        "calculation_runs",
        schema=SCHEMA,
        type_="foreignkey",
    )
    for column in (
        "technical_formula_version",
        "period",
        "site_code",
        "technical_passport_id",
        "calculation_scope",
    ):
        op.drop_column("calculation_runs", column, schema=SCHEMA)
    op.alter_column("calculation_runs", "scenario_id", nullable=False, schema=SCHEMA)

    op.drop_index("ix_legacy_cost_scenario_org", table_name="legacy_cost_scenarios", schema=SCHEMA)
    op.drop_table("legacy_cost_scenarios", schema=SCHEMA)
    op.drop_table("legacy_workspace_settings", schema=SCHEMA)
    op.drop_index("ix_technical_passport_org_site", table_name="technical_passports", schema=SCHEMA)
    op.drop_table("technical_passports", schema=SCHEMA)
