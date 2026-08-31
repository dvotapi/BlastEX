"""Mass-blast projects, immutable revisions and generated documents.

Revision ID: 20260831_0003
Revises: 20260831_0002
Create Date: 2026-08-31
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260831_0003"
down_revision = "20260831_0002"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "mass_blast_projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("site_code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("blast_date", sa.String(length=10), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_revision_id", sa.String(length=36), nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_mass_blast_project_org_updated", "mass_blast_projects", ["organization_id", "updated_at"], schema=SCHEMA)

    op.create_table(
        "mass_blast_project_revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.mass_blast_projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("reference_revision_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.reference_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("technical_formula_version", sa.String(length=80), nullable=False),
        sa.Column("document_template_version", sa.String(length=80), nullable=False),
        sa.Column("input_snapshot", JSONB, nullable=False),
        sa.Column("technical_snapshots", JSONB, nullable=False),
        sa.Column("document_context", JSONB, nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.UniqueConstraint("project_id", "revision_no", name="uq_mass_blast_revision_no"),
        schema=SCHEMA,
    )
    op.create_index("ix_mass_blast_revision_project", "mass_blast_project_revisions", ["project_id", "revision_no"], schema=SCHEMA)

    op.create_table(
        "mass_blast_project_blocks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("design_id", sa.String(length=120), nullable=False),
        sa.Column("design_revision", sa.Integer(), nullable=False),
        sa.Column("design_sha256", sa.String(length=64), nullable=False),
        sa.Column("technical_passport_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.technical_passports.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("block_code", sa.String(length=120), nullable=False),
        sa.Column("horizon", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("object_name", sa.String(length=300), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.UniqueConstraint("revision_id", "sequence_no", name="uq_mass_blast_block_sequence"),
        schema=SCHEMA,
    )
    op.create_index("ix_mass_blast_block_design", "mass_blast_project_blocks", ["design_id"], schema=SCHEMA)

    op.create_table(
        "mass_blast_attachments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.mass_blast_projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_mass_blast_attachment_project", "mass_blast_attachments", ["project_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "mass_blast_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("template_version", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.UniqueConstraint("revision_id", "kind", "format", name="uq_mass_blast_document_revision_kind"),
        schema=SCHEMA,
    )
    op.create_index("ix_mass_blast_document_revision", "mass_blast_documents", ["revision_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "mass_blast_approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey(f"{SCHEMA}.mass_blast_project_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role_code", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=320), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("revision_id", "role_code", "actor", name="uq_mass_blast_approval_actor"),
        schema=SCHEMA,
    )
    op.create_index("ix_mass_blast_approval_revision", "mass_blast_approvals", ["revision_id", "created_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_mass_blast_approval_revision", table_name="mass_blast_approvals", schema=SCHEMA)
    op.drop_table("mass_blast_approvals", schema=SCHEMA)
    op.drop_index("ix_mass_blast_document_revision", table_name="mass_blast_documents", schema=SCHEMA)
    op.drop_table("mass_blast_documents", schema=SCHEMA)
    op.drop_index("ix_mass_blast_attachment_project", table_name="mass_blast_attachments", schema=SCHEMA)
    op.drop_table("mass_blast_attachments", schema=SCHEMA)
    op.drop_index("ix_mass_blast_block_design", table_name="mass_blast_project_blocks", schema=SCHEMA)
    op.drop_table("mass_blast_project_blocks", schema=SCHEMA)
    op.drop_index("ix_mass_blast_revision_project", table_name="mass_blast_project_revisions", schema=SCHEMA)
    op.drop_table("mass_blast_project_revisions", schema=SCHEMA)
    op.drop_index("ix_mass_blast_project_org_updated", table_name="mass_blast_projects", schema=SCHEMA)
    op.drop_table("mass_blast_projects", schema=SCHEMA)
