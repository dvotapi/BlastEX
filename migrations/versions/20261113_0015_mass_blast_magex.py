"""Наряд-путёвка ↔ MagEX: версии выписки и последнее исполнение (TASK-018, PR 7).

- `mass_blast_magex_versions` — каждая отправленная версия наряда: номер `ver`
  (растёт в слое), подписанная строка JWS (её же печатает QR), хэш содержимого
  без `iat`, состояние (`SENDING`, `PENDING` — очередь повтора, `ACCEPTED`,
  `REJECTED`, `SUPERSEDED`), ответ MagEX, попытки и срок следующей.
- `mass_blast_magex_naryads` — последнее прочитанное исполнение наряда
  (`GET /naryads/{id}`): показ без связи и блокировка полей после выдачи.

Revision ID: 20261113_0015
Revises: 20261111_0014
Create Date: 2026-11-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261113_0015"
down_revision = "20261111_0014"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "mass_blast_magex_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column(
            "layer_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.mass_blast_layers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ver", sa.Integer(), nullable=False),
        sa.Column(
            "layer_revision_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.mass_blast_layer_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("jws", sa.Text(), nullable=False),
        sa.Column("kid", sa.String(length=200), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response", JSONB, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("layer_id", "ver", name="uq_mass_blast_magex_version"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_mass_blast_magex_version_due", "mass_blast_magex_versions", ["status", "next_attempt_at"], schema=SCHEMA
    )
    op.create_table(
        "mass_blast_magex_naryads",
        sa.Column(
            "layer_id",
            sa.String(length=36),
            sa.ForeignKey(f"{SCHEMA}.mass_blast_layers.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("execution", JSONB, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("mass_blast_magex_naryads", schema=SCHEMA)
    op.drop_index("ix_mass_blast_magex_version_due", table_name="mass_blast_magex_versions", schema=SCHEMA)
    op.drop_table("mass_blast_magex_versions", schema=SCHEMA)
