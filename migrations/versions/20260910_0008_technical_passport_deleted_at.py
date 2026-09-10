"""Удаление технического паспорта пометкой `deleted_at`.

Паспорт нельзя стереть строкой: на него ссылаются прогоны экономики,
событийные расчёты и блоки проектов (везде FK RESTRICT), а сами расчёты
должны переживать удаление паспорта. Поэтому удаление — время в
`deleted_at`: такой паспорт исчезает из списков и не принимает новых
расчётов, но остаётся читаемым по идентификатору.

Частичный индекс повторяет `ix_technical_passport_org_site` только для
живых паспортов — списку в интерфейсе нужны именно они.

Revision ID: 20260910_0008
Revises: 20260906_0007
Create Date: 2026-09-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260910_0008"
down_revision = "20260906_0007"
branch_labels = None
depends_on = None

SCHEMA = "blastex"


def upgrade() -> None:
    op.add_column(
        "technical_passports",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_technical_passport_active",
        "technical_passports",
        ["organization_id", "site_code", "created_at"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_technical_passport_active", table_name="technical_passports", schema=SCHEMA
    )
    op.drop_column("technical_passports", "deleted_at", schema=SCHEMA)
