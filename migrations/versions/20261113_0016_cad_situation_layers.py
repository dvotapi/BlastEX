"""Импорт чертежа: отбор слоёв плана карьера — ситуация объекта.

`cad_site_settings.situation_layers` — какие слои плана карьера показывать и
их вид (ключ слоя → `{"name", "shown", "kind"}`). Отдельно от шаблона ролей
`cad_layer_roles`: у файла блока «Горизонт +410» — бровки, у плана карьера —
ситуация.

Revision ID: 20261113_0016
Revises: 20261113_0015
Create Date: 2026-11-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261113_0016"
down_revision = "20261113_0015"
branch_labels = None
depends_on = None

SCHEMA = "blastex"


def upgrade() -> None:
    op.add_column(
        "cad_site_settings",
        sa.Column(
            "situation_layers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("cad_site_settings", "situation_layers", schema=SCHEMA)
