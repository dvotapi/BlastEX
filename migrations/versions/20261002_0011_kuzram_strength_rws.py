"""Kuz-Ram: поправка C(A) объектов работ под силу ВВ к ANFO (PR #106).

Kuz-Ram по Каннингему перешёл с силы ВВ к тротилу, RE^−e (RE = Q/4,184), на
(115/RWS)^e (RWS = 100·Q/3,8, к ANFO). Оба множителя пропорциональны теплоте
взрыва, поэтому новый больше старого в одно и то же число раз для любого ВВ:
k = (1,15·3,8/4,184)^e. Поправка C(A) из настроек объекта работ подбиралась
по фактическим взрывам под старый множитель; деление на k возвращает тот же
x50, а значит и тот же негабарит и подобранный q.

Меняется только `inputs.kuzram.rock_factor_correction`, отличный от 1:
C(A) = 1 — модель без подгонки, ей и предназначено исправление. Результат не
опускается ниже нижней границы настройки (0,1). Ручной фактор породы A не
трогается. updated_at и updated_by остаются прежними: это не правка
пользователя.

downgrade умножает обратно все C(A), отличные от 1, — в том числе изменённые
после upgrade; точного отката нет, так как исходные значения не хранятся.

Revision ID: 20261002_0011
Revises: 20261001_0010
Create Date: 2026-10-02
"""
from __future__ import annotations

import math
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20261002_0011"
down_revision = "20261001_0010"
branch_labels = None
depends_on = None

SCHEMA = "blastex"

# Формулы заморожены здесь, а не импортированы из кода: миграция должна
# давать тот же результат, как бы ни менялся cunningham.py потом.
KUZNETSOV_TNT_INDEX = 115.0
ANFO_ENERGY_MJ_KG = 3.8
TNT_ENERGY_MJ_KG = 4.184
STRENGTH_EXPONENTS = {"19/20": 19.0 / 20.0, "19/30": 19.0 / 30.0}
DEFAULT_EXPONENT = "19/20"
CORRECTION_MIN = 0.1
CORRECTION_MAX = 10.0


def strength_ratio(strength_exponent: str) -> float:
    """Во сколько раз (115/RWS)^e больше RE^−e при показателе e."""
    exponent = STRENGTH_EXPONENTS.get(strength_exponent, STRENGTH_EXPONENTS[DEFAULT_EXPONENT])
    base = KUZNETSOV_TNT_INDEX / 100.0 * ANFO_ENERGY_MJ_KG / TNT_ENERGY_MJ_KG
    return base**exponent


def convert_block(kuzram: Any, *, reverse: bool = False) -> dict[str, Any] | None:
    """Новый блок kuzram с пересчитанной C(A) или None, если менять нечего."""
    if not isinstance(kuzram, dict):
        return None
    value = kuzram.get("rock_factor_correction")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value <= 0 or abs(value - 1.0) <= 1e-12:
        return None
    ratio = strength_ratio(str(kuzram.get("strength_exponent") or DEFAULT_EXPONENT))
    converted = value * ratio if reverse else value / ratio
    converted = min(CORRECTION_MAX, max(CORRECTION_MIN, converted))
    return {**kuzram, "rock_factor_correction": converted}


def _rewrite(*, reverse: bool) -> None:
    table = sa.table(
        "calc_object_inputs",
        sa.column("organization_id", sa.String),
        sa.column("work_object_name", sa.String),
        sa.column("inputs", sa.JSON),
        schema=SCHEMA,
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(table.c.organization_id, table.c.work_object_name, table.c.inputs)
    ).all()
    for organization_id, work_object_name, inputs in rows:
        if not isinstance(inputs, dict):
            continue
        block = convert_block(inputs.get("kuzram"), reverse=reverse)
        if block is None:
            continue
        connection.execute(
            table.update()
            .where(
                table.c.organization_id == organization_id,
                table.c.work_object_name == work_object_name,
            )
            .values(inputs={**inputs, "kuzram": block})
        )


def upgrade() -> None:
    _rewrite(reverse=False)


def downgrade() -> None:
    _rewrite(reverse=True)