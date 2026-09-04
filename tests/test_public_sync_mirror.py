"""Зеркала разделов справочников в схеме ``public`` — без базы.

Здесь проверяется всё, что зеркало решает само: имя таблицы, набор и типы
колонок по схеме раздела, идемпотентный DDL и приведение значений payload к
типам колонок. Поход в PostgreSQL — в ``test_public_sync_mirror_pg.py``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from cost.v2.models import ReferenceItem
from cost.v2.public_sync.mirror import (
    MirrorColumn,
    create_table_sql,
    ensure_mirror,
    mirror_columns,
    mirror_table_name,
    mirror_value,
    sync_mirror,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def column(section: str, name: str) -> MirrorColumn:
    found = [item for item in mirror_columns(section) if item.name == name]
    assert found, f"колонки {name} нет среди колонок зеркала {section}"
    return found[0]


class RecordingSession:
    """Сессия-заглушка: запоминает операторы вместо похода в базу."""

    def __init__(self, rowcount: int = 0) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._rowcount = rowcount

    def execute(self, statement: Any, parameters: Any = None) -> Any:
        self.calls.append((str(statement), parameters))
        return SimpleNamespace(rowcount=self._rowcount)


def test_table_name_carries_the_blastex_prefix() -> None:
    assert mirror_table_name("rocks") == "blastex_rocks"


def test_section_without_a_mirror_has_no_table_name() -> None:
    # `sites` выгружается прямым сопоставлением таблиц, зеркала у него нет:
    # имя таблицы подставляется в SQL напрямую, поэтому чужое имя — ошибка.
    with pytest.raises(ValueError):
        mirror_table_name("sites")


def test_column_types_follow_the_schema_annotations() -> None:
    assert column("rocks", "density_t_m3").sql_type == "numeric"
    assert column("rocks", "fracture_class").sql_type == "text"
    assert column("crew_templates", "members").sql_type == "jsonb"
    assert column("positions", "per_diem_applies").sql_type == "boolean"
    # Перечисление остаётся текстом, число — numeric.
    assert column("market_prices", "scope").sql_type == "text"
    assert column("production_units", "plan_volume_m3").sql_type == "numeric"


def test_reference_field_is_plain_text() -> None:
    assert column("production_units", "base_code").sql_type == "text"


def test_internal_fields_stay_out_of_the_mirror() -> None:
    assert "legacy_ref" not in [item.name for item in mirror_columns("rocks")]


def test_columns_start_with_the_record_fields() -> None:
    names = [item.name for item in mirror_columns("rocks")]
    assert names[:9] == [
        "code",
        "name",
        "is_active",
        "valid_from",
        "valid_to",
        "source",
        "comment",
        "revision_id",
        "synced_at",
    ]
    assert names[9:] == [
        "density_t_m3",
        "hardness_f",
        "fracture_class",
        "ucs_mpa",
        "fissuring_ff",
    ]


def test_column_comment_is_the_russian_label() -> None:
    assert column("rocks", "density_t_m3").comment == "Плотность"
    assert column("rocks", "ucs_mpa").comment == "Прочность на сжатие"


def test_ddl_is_idempotent() -> None:
    statements = create_table_sql("rocks")
    joined = "\n".join(statements)

    assert 'CREATE TABLE IF NOT EXISTS public."blastex_rocks"' in joined
    # Колонка, добавленная в схему позже, доезжает до существующей таблицы —
    # и служебная тоже: зеркало могло быть создано прежней версией BlastEX.
    for name in ("density_t_m3", "fracture_class", "source", "revision_id", "synced_at"):
        assert (
            f'ALTER TABLE public."blastex_rocks" ADD COLUMN IF NOT EXISTS "{name}"'
            in joined
        )
    assert 'COMMENT ON COLUMN public."blastex_rocks"."density_t_m3" IS' in joined


def test_service_columns_follow_the_specification() -> None:
    assert column("rocks", "revision_id").sql_type == "varchar(36)"
    assert column("rocks", "synced_at").sql_type == "timestamptz"
    joined = "\n".join(create_table_sql("rocks"))

    # Ревизия и момент выгрузки есть у каждой строки зеркала (§5). Умолчание
    # нужно, чтобы колонка доехала до уже заполненной таблицы: `ADD COLUMN`
    # с `NOT NULL` без него отвергается.
    assert '"revision_id" varchar(36) NOT NULL' in joined
    assert '"synced_at" timestamptz NOT NULL' in joined


def test_ddl_closes_the_table_from_other_roles() -> None:
    joined = "\n".join(create_table_sql("rocks"))

    assert 'ALTER TABLE public."blastex_rocks" ENABLE ROW LEVEL SECURITY' in joined
    assert "blastex_full_access" in joined
    # Политика создаётся только если её ещё нет: `CREATE POLICY` не знает
    # `IF NOT EXISTS`.
    assert "pg_policies" in joined


def test_ensure_mirror_runs_the_whole_ddl_in_the_given_session() -> None:
    session = RecordingSession()

    ensure_mirror(session, "rocks")

    assert [statement for statement, _ in session.calls] == create_table_sql("rocks")


@pytest.mark.parametrize(
    ("sql_type", "value", "expected"),
    [
        ("numeric", "2.70", Decimal("2.70")),
        ("numeric", Decimal("2.7"), Decimal("2.7")),
        ("numeric", 3, Decimal("3")),
        ("numeric", "", None),
        ("numeric", "не число", None),
        ("text", "", None),
        ("text", None, None),
        ("text", "III", "III"),
        ("boolean", True, True),
        ("boolean", False, False),
        # Написания pydantic: значение из импорта могло не пройти схему и
        # приехать сюда строкой.
        ("boolean", "off", False),
        ("boolean", "n", False),
        ("boolean", "f", False),
        ("boolean", "on", True),
        ("boolean", "y", True),
        ("boolean", "t", True),
        # Чужое написание — не «истина по факту непустой строки», а NULL: так
        # же, как с числом и датой.
        ("boolean", "да", None),
        ("date", "2026-09-04", date(2026, 9, 4)),
        ("date", date(2026, 9, 4), date(2026, 9, 4)),
        ("date", "", None),
        ("jsonb", [{"position_code": "DRILLER"}], '[{"position_code": "DRILLER"}]'),
        ("jsonb", None, None),
    ],
)
def test_values_take_the_shape_of_their_column(sql_type: str, value: Any, expected: Any) -> None:
    assert mirror_value(MirrorColumn("x", sql_type, ""), value) == expected


def test_json_keeps_russian_letters_readable() -> None:
    encoded = mirror_value(MirrorColumn("x", "jsonb", ""), ["порода"])

    assert encoded == '["порода"]'


def test_sync_upserts_every_record_of_the_revision() -> None:
    session = RecordingSession()
    items = (
        ReferenceItem("GRANITE", "Гранит", {"density_t_m3": "2.70"}),
        ReferenceItem("SAND", "Песок", {"density_t_m3": "1.60"}, is_active=False),
    )

    upserted, _deactivated, _warnings = sync_mirror(session, "rocks", "rev-2", items, NOW)

    insert_sql, insert_params = session.calls[0]
    assert upserted == 2
    assert 'INSERT INTO public."blastex_rocks"' in insert_sql
    assert 'ON CONFLICT ("code") DO UPDATE SET' in insert_sql
    assert [row["code"] for row in insert_params] == ["GRANITE", "SAND"]
    assert insert_params[0]["density_t_m3"] == Decimal("2.70")
    assert insert_params[0]["revision_id"] == "rev-2"
    assert insert_params[0]["synced_at"] == NOW
    # Неактивная запись ревизии тоже попадает в зеркало — со своим признаком.
    assert [row["is_active"] for row in insert_params] == [True, False]


def test_sync_deactivates_the_records_that_left_the_revision() -> None:
    session = RecordingSession(rowcount=3)
    items = (ReferenceItem("GRANITE", "Гранит"),)

    _upserted, deactivated, _warnings = sync_mirror(session, "rocks", "rev-2", items, NOW)

    update_sql, update_params = session.calls[-1]
    assert deactivated == 3
    assert 'UPDATE public."blastex_rocks"' in update_sql
    assert '"is_active" = false' in update_sql
    # Гасятся только действующие строки: давно погашенную незачем метить
    # новой ревизией, да и счётчик тогда честный.
    assert 'AND "is_active"' in update_sql
    assert update_params["codes"] == ["GRANITE"]
    assert update_params["revision_id"] == "rev-2"


def test_empty_revision_deactivates_the_whole_mirror() -> None:
    session = RecordingSession(rowcount=5)

    upserted, deactivated, _warnings = sync_mirror(session, "rocks", "rev-2", (), NOW)

    assert (upserted, deactivated) == (0, 5)
    # Вставлять нечего — остаётся один оператор.
    assert len(session.calls) == 1
    assert session.calls[0][1]["codes"] == []


def test_payload_is_typed_by_the_schema_of_the_section() -> None:
    # Схема раздела разбирает payload до выгрузки: «off» — это ложь, а не
    # просто непустая строка, и гадать по строкам зеркалу не приходится.
    session = RecordingSession()
    items = (
        ReferenceItem(
            "MASTER",
            "Мастер участка",
            {"category": "INDIRECT", "per_diem_applies": "off", "piece_unit": "1"},
        ),
    )

    _upserted, _deactivated, warnings = sync_mirror(
        session, "positions", "rev-2", items, NOW
    )

    row = session.calls[0][1][0]
    assert row["per_diem_applies"] is False
    assert row["piece_unit"] == Decimal("1")
    assert warnings == ()


def test_payload_that_the_schema_rejects_is_written_as_it_is() -> None:
    session = RecordingSession()
    items = (
        ReferenceItem(
            "MASTER", "Мастер участка", {"category": "INDIRECT", "per_diem_applies": "да"}
        ),
    )

    _upserted, _deactivated, warnings = sync_mirror(
        session, "positions", "rev-2", items, NOW
    )

    row = session.calls[0][1][0]
    assert row["per_diem_applies"] is None
    assert len(warnings) == 1
    assert "MASTER" in warnings[0]
    assert "per_diem_applies" in warnings[0]
