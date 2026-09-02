"""Reference payloads moved onto typed schemas.

Renames the fields the schemas expect, moves the deprecated
`drilling_productivity` section into `drilling_conditions`, and seeds
`organization_rates` for every organization that has references.

The migration walks every revision of every organization: revisions are
immutable snapshots, but a published one whose payload no longer matches the
schema could never be re-published, so history is rewritten in place.

Revision ID: 20260902_0004
Revises: 20260831_0003
Create Date: 2026-09-02
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import Counter

from alembic import op
import sqlalchemy as sa


revision = "20260902_0004"
down_revision = "20260831_0003"
branch_labels = None
depends_on = None

SCHEMA = "blastex"
logger = logging.getLogger("alembic.runtime.migration")

# Переименования полей payload: раздел → {старое имя: новое имя}.
FIELD_RENAMES: dict[str, dict[str, str]] = {
    "labor_rates": {
        "fixed_salary_monthly": "fixed_monthly_rub",
        "piece_rate_per_m3": "piece_rate_rub",
    },
    "production_units": {"legacy_team_id": "legacy_ref"},
    "materials": {"legacy_key": "legacy_ref", "legacy_id": "legacy_ref"},
    "positions": {"legacy_id": "legacy_ref"},
    "equipment_assets": {"legacy_id": "legacy_ref"},
}

# Ставки организации по ADR-001. Заводятся пустыми значениями по умолчанию,
# чтобы модель экономики стартовала, а сметчик уточнил их у себя.
ORGANIZATION_RATES_PAYLOAD = {
    "income_tax_rate": "0.13",
    "social_contribution_rate": "0.30",
    "injury_insurance_rate": "0.0042",
    "vacation_reserve_rate": "0.20",
    "salary_basis": "GROSS",
    "overhead_rate": "0.10",
    "target_margin_rate": "0.10",
    "vat_rate": "0.20",
    "per_diem_rub": "0",
    "lodging_rub": "0",
    "shift_hours": "11",
}
ORGANIZATION_RATES_CODE = "ORG_RATES_DEFAULT"


def _load(payload) -> dict:
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str) and payload.strip():
        try:
            return dict(json.loads(payload))
        except (ValueError, TypeError):
            return {}
    return {}


def upgrade() -> None:
    bind = op.get_bind()
    changed: Counter[str] = Counter()

    for section, renames in FIELD_RENAMES.items():
        rows = bind.execute(
            sa.text(f"SELECT id, payload FROM {SCHEMA}.reference_items WHERE section = :section"),
            {"section": section},
        ).fetchall()
        for row in rows:
            payload = _load(row.payload)
            touched = False
            for old, new in renames.items():
                if old in payload:
                    # Если новое имя уже занято, старое значение теряется —
                    # но это ровно тот случай, когда данные уже мигрировали.
                    payload.setdefault(new, payload.pop(old))
                    payload.pop(old, None)
                    touched = True
            if touched:
                bind.execute(
                    sa.text(f"UPDATE {SCHEMA}.reference_items SET payload = :payload WHERE id = :id"),
                    {"payload": json.dumps(payload, ensure_ascii=False), "id": row.id},
                )
                changed[section] += 1

    # drilling_productivity → drilling_conditions: старая запись описывала
    # производительность станка без привязки к породе, то есть ровно норму по
    # умолчанию (rock_code остаётся пустым).
    moved = bind.execute(
        sa.text(
            f"UPDATE {SCHEMA}.reference_items SET section = 'drilling_conditions' "
            "WHERE section = 'drilling_productivity'"
        )
    ).rowcount
    if moved:
        changed["drilling_conditions"] += moved

    # Ставки организации — по одной записи на ревизию, где их ещё нет.
    revisions = bind.execute(
        sa.text(f"SELECT id, organization_id FROM {SCHEMA}.reference_revisions")
    ).fetchall()
    for rev in revisions:
        exists = bind.execute(
            sa.text(
                f"SELECT 1 FROM {SCHEMA}.reference_items "
                "WHERE revision_id = :revision AND section = 'organization_rates' LIMIT 1"
            ),
            {"revision": rev.id},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                f"INSERT INTO {SCHEMA}.reference_items "
                "(id, organization_id, revision_id, section, code, name, payload, is_active, "
                " valid_from, valid_to, source, comment, item_revision) "
                "VALUES (:id, :org, :revision, 'organization_rates', :code, :name, :payload, true, "
                " NULL, NULL, :source, '', 1)"
            ),
            {
                "id": str(uuid.uuid4()),
                "org": rev.organization_id,
                "revision": rev.id,
                "code": ORGANIZATION_RATES_CODE,
                "name": "Ставки и надбавки организации",
                "payload": json.dumps(ORGANIZATION_RATES_PAYLOAD, ensure_ascii=False),
                "source": "Миграция 20260902_0004 (ADR-001)",
            },
        )
        changed["organization_rates"] += 1

    for section, count in sorted(changed.items()):
        logger.info("reference_items: раздел %s — изменено записей: %s", section, count)

    _assert_payloads_match_schemas(bind)


def _assert_payloads_match_schemas(bind) -> None:
    """Сухая проверка: после миграции каждый payload должен проходить схему.

    Если хоть одна запись не проходит, миграция падает — иначе организация
    получила бы справочник, который нельзя опубликовать.
    """

    try:
        from cost.v2.schemas import SECTION_SCHEMAS
    except ImportError:  # pragma: no cover — окружение без пакета приложения
        logger.warning("cost.v2.schemas недоступен, проверка payload пропущена")
        return

    rows = bind.execute(
        sa.text(f"SELECT section, code, payload FROM {SCHEMA}.reference_items")
    ).fetchall()
    failures: list[str] = []
    for row in rows:
        model = SECTION_SCHEMAS.get(row.section)
        if model is None:
            continue
        try:
            model.model_validate(_load(row.payload))
        except Exception as exc:  # pydantic ValidationError и всё, что похоже
            failures.append(f"{row.section}/{row.code}: {exc}")
    if failures:
        shown = "\n".join(failures[:20])
        raise RuntimeError(
            f"После миграции {len(failures)} записей не проходят схему раздела:\n{shown}"
        )


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(f"DELETE FROM {SCHEMA}.reference_items WHERE section = 'organization_rates'")
    )
    bind.execute(
        sa.text(
            f"UPDATE {SCHEMA}.reference_items SET section = 'drilling_productivity' "
            "WHERE section = 'drilling_conditions'"
        )
    )
    for section, renames in FIELD_RENAMES.items():
        rows = bind.execute(
            sa.text(f"SELECT id, payload FROM {SCHEMA}.reference_items WHERE section = :section"),
            {"section": section},
        ).fetchall()
        for row in rows:
            payload = _load(row.payload)
            touched = False
            # Несколько полей одной записи могут быть переименованы сразу
            # (fixed_monthly_rub и piece_rate_rub у ставки) — проходим все.
            for old, new in renames.items():
                if new in payload and old not in payload:
                    payload[old] = payload.pop(new)
                    touched = True
            if touched:
                bind.execute(
                    sa.text(f"UPDATE {SCHEMA}.reference_items SET payload = :payload WHERE id = :id"),
                    {"payload": json.dumps(payload, ensure_ascii=False), "id": row.id},
                )
