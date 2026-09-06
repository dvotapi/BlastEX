"""Настройки листа расчёта по объекту работ.

`calc_object_inputs` хранит последний введённый набор параметров листа
расчёта для пары (организация, объект работ) — черновик формы, который
подставляется при повторном открытии того же объекта.

Revision ID: 20260906_0007
Revises: 20260904_0006
Create Date: 2026-09-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260906_0007"
down_revision = "20260904_0006"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "calc_object_inputs",
        sa.Column("organization_id", sa.String(length=120), nullable=False),
        sa.Column("work_object_name", sa.String(length=300), nullable=False),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=320), nullable=False),
        sa.PrimaryKeyConstraint(
            "organization_id", "work_object_name", name="pk_calc_object_inputs"
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("calc_object_inputs", schema=SCHEMA)
