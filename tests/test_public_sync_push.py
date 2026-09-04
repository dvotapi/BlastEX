"""Тесты плана выгрузки справочников blastex в схему ``public``.

Базы данных здесь нет: снимок журнала собирается из словарей — тех же полей,
что вернёт ``SELECT *`` (как в ``test_public_sync_mapping``), а разделы — из
``ReferenceItem``. Проверяется только план: SQL выполняет ``writer``.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

import pytest

from cost.v2.models import ReferenceItem
from cost.v2.public_sync.mapping import PublicRow, PublicSnapshot
from cost.v2.public_sync.push import (
    PublicInsert,
    PublicUpdate,
    PublicWritePlan,
    plan_public_writes,
    public_constraint_issues,
)
from cost.v2.repository import PublicLink

# --- Помощники --------------------------------------------------------------


def item(
    code: str,
    name: str,
    payload: dict[str, Any] | None = None,
    *,
    is_active: bool = True,
    comment: str = "",
) -> ReferenceItem:
    return ReferenceItem(
        code=code, name=name, payload=dict(payload or {}), is_active=is_active, comment=comment
    )


def snapshot(**tables: Sequence[dict[str, Any]]) -> PublicSnapshot:
    return PublicSnapshot(
        rows={
            table: tuple(PublicRow(table, int(row["id"]), dict(row)) for row in rows)
            for table, rows in tables.items()
        }
    )


EMPTY = snapshot()


def link(section: str, code: str, table: str, public_id: int) -> PublicLink:
    return PublicLink(section=section, code=code, public_table=table, public_id=public_id)


def inserts_for(plan: PublicWritePlan, table: str) -> list[PublicInsert]:
    return [insert for insert in plan.inserts if insert.table == table]


def only_insert(plan: PublicWritePlan, table: str) -> PublicInsert:
    found = inserts_for(plan, table)
    assert len(found) == 1, f"ожидалась одна вставка в {table}, получено {len(found)}"
    return found[0]


def only_update(plan: PublicWritePlan) -> PublicUpdate:
    assert len(plan.updates) == 1, f"ожидалось одно обновление, получено {len(plan.updates)}"
    return plan.updates[0]


# --- Записи разделов --------------------------------------------------------

CUSTOMER = item(
    "TEPLOGORSK",
    'Акционерное общество "Теплогорский карьер"',
    {
        "short_name": 'АО "Теплогорский карьер"',
        "inn": "6608002092",
        "role": "CUSTOMER",
    },
)
SUPPLIER = item(
    "POMBUR",
    'Общество с ограниченной ответственностью "ПОМБУР"',
    {"short_name": 'ООО "ПОМБУР"', "inn": "7203270545", "role": "SUPPLIER"},
)
SITE = item(
    "LOM",
    "Ломоватский карьер",
    {
        "short_name": "ЛОМ",
        "mineral_type": "нерудные материалы",
        "customer_code": "TEPLOGORSK",
    },
)
EQUIPMENT_TYPE = item(
    "JK830",
    "JK830-2",
    {"kind": "DRILL_RIG", "brand": "Jinke", "machine_type_name": "Буровая установка"},
)
EQUIPMENT_ASSET = item(
    "RIG_01",
    "Станок №1",
    {
        "equipment_type_code": "JK830",
        "inventory_number": "БУ-01",
        "serial_number": "SN-JK830-0001",
    },
)
DEVICE = item(
    "ED_1N",
    "ЭД-1-Н",
    {"material_kind": "СИ", "storage_class": "NSI", "delay_ms": "500"},
    comment="Электродетонатор непредохранительный",
)
TOOL = item(
    "BIT_152",
    "Долото шарошечное 152",
    {
        "material_kind": "Буровой инструмент",
        "lifetime_m": "600",
        "diameter_mm": "152",
        "thread_type": "З-76",
    },
    comment="Шарошечное долото для буровой установки JK830-2",
)


# --- Вставки ----------------------------------------------------------------


def test_new_counterparty_becomes_insert_with_role_flags() -> None:
    plan = plan_public_writes({"counterparties": [CUSTOMER]}, [], EMPTY)

    insert = only_insert(plan, "counterparties")
    assert plan.updates == ()
    assert (insert.section, insert.code) == ("counterparties", "TEPLOGORSK")
    assert insert.values == {
        "full_name": 'Акционерное общество "Теплогорский карьер"',
        "short_name": 'АО "Теплогорский карьер"',
        "inn": "6608002092",
        "is_client": True,
        "is_supplier": False,
        "is_active": True,
    }
    assert insert.depends_on == ()
    assert insert.foreign_keys == ()


def test_supplier_role_raises_supplier_flag() -> None:
    plan = plan_public_writes({"counterparties": [SUPPLIER]}, [], EMPTY)

    insert = only_insert(plan, "counterparties")
    assert insert.values["is_client"] is False
    assert insert.values["is_supplier"] is True


def test_subcontractor_role_is_supplier_for_journal() -> None:
    subcontractor = item("SUB", "Подрядчик", {"role": "SUBCONTRACTOR", "inn": "7203270545"})

    plan = plan_public_writes({"counterparties": [subcontractor]}, [], EMPTY)

    insert = only_insert(plan, "counterparties")
    assert insert.values["is_supplier"] is True


def test_site_takes_client_legal_name_from_counterparty_short_name() -> None:
    plan = plan_public_writes(
        {"counterparties": [CUSTOMER], "sites": [SITE]}, [], EMPTY
    )

    insert = only_insert(plan, "sites")
    assert insert.values == {
        "full_name": "Ломоватский карьер",
        "short_name": "ЛОМ",
        "mineral_type": "нерудные материалы",
        "client_legal_name": 'АО "Теплогорский карьер"',
        "is_active": True,
    }
    assert insert.depends_on == ()


def test_site_falls_back_to_counterparty_name_without_short_name() -> None:
    customer = item("CUST", "Полное имя заказчика", {"role": "CUSTOMER", "inn": "6608002092"})
    site = item("S", "Объект", {"customer_code": "CUST"})

    plan = plan_public_writes({"counterparties": [customer], "sites": [site]}, [], EMPTY)

    assert only_insert(plan, "sites").values["client_legal_name"] == "Полное имя заказчика"


def test_site_without_customer_code_uses_legal_name_text() -> None:
    site = item("S", "Объект", {"customer_legal_name": 'ООО "Директ-Склад"'})

    plan = plan_public_writes({"sites": [site]}, [], EMPTY)

    assert only_insert(plan, "sites").values["client_legal_name"] == 'ООО "Директ-Склад"'


def test_equipment_type_insert_creates_machine_type_and_depends_on_it() -> None:
    plan = plan_public_writes({"equipment_types": [EQUIPMENT_TYPE]}, [], EMPTY)

    machine_type = only_insert(plan, "machine_types")
    assert machine_type.values == {"name": "Буровая установка"}
    # У типа машины нет записи blastex: связь для него не создаётся.
    assert (machine_type.section, machine_type.code) == ("", "Буровая установка")

    model = only_insert(plan, "equipment_models")
    assert model.values == {"model_name": "JK830-2", "brand": "Jinke"}
    assert "machine_type_id" not in model.values
    assert model.depends_on == (("machine_types", "Буровая установка"),)
    assert model.foreign_keys == (("machine_type_id", "machine_types", "Буровая установка"),)
    assert plan.inserts.index(machine_type) < plan.inserts.index(model)


def test_machine_type_is_not_created_when_journal_already_has_it() -> None:
    journal = snapshot(machine_types=[{"id": 7, "name": "Буровая установка"}])

    plan = plan_public_writes({"equipment_types": [EQUIPMENT_TYPE]}, [], journal)

    assert inserts_for(plan, "machine_types") == []
    assert only_insert(plan, "equipment_models").depends_on == (
        ("machine_types", "Буровая установка"),
    )


def test_machine_type_is_created_once_for_several_models() -> None:
    other = item("JK830B", "JK830-3", {"brand": "Jinke", "machine_type_name": "Буровая установка"})

    plan = plan_public_writes({"equipment_types": [EQUIPMENT_TYPE, other]}, [], EMPTY)

    assert len(inserts_for(plan, "machine_types")) == 1


def test_machine_type_of_journal_is_reused_ignoring_case() -> None:
    # Журнал пишет тип машины как хочет: сравнение без регистра и крайних
    # пробелов, а в план идёт написание журнала — по нему писатель ищет строку.
    journal = snapshot(machine_types=[{"id": 7, "name": "буровая  установка"}])
    equipment_type = item(
        "JK830", "JK830-2", {"kind": "DRILL_RIG", "machine_type_name": " Буровая установка "}
    )

    plan = plan_public_writes({"equipment_types": [equipment_type]}, [], journal)

    assert inserts_for(plan, "machine_types") == []
    assert only_insert(plan, "equipment_models").depends_on == (
        ("machine_types", "буровая  установка"),
    )


def test_each_machine_type_is_inserted_before_its_model() -> None:
    # Порядок вставок топологический, а не «все типы, потом все модели».
    excavator = item("EX200", "EX-200", {"kind": "TRACTOR", "machine_type_name": "Экскаватор"})

    plan = plan_public_writes({"equipment_types": [EQUIPMENT_TYPE, excavator]}, [], EMPTY)

    order = {(insert.table, insert.code): number for number, insert in enumerate(plan.inserts)}
    assert order[("machine_types", "Буровая установка")] < order[("equipment_models", "JK830")]
    assert order[("machine_types", "Экскаватор")] < order[("equipment_models", "EX200")]


def test_machine_type_name_falls_back_to_kind_label() -> None:
    szm = item("SZM_1", "СЗМ-10", {"kind": "SZM"})
    other = item("MISC", "Прочее", {"kind": "OTHER"})

    plan = plan_public_writes({"equipment_types": [szm, other]}, [], EMPTY)

    names = [insert.values["name"] for insert in inserts_for(plan, "machine_types")]
    assert names == ["Машина смесительно-зарядная", "Прочая техника"]


def test_kind_with_several_labels_gives_other_machine_type() -> None:
    # `TRACTOR` — это и бульдозер, и экскаватор, и погрузчик: угадывать
    # подпись нельзя, в журнал идёт «Прочая техника».
    tractor = item("D9", "Бульдозер D9", {"kind": "TRACTOR"})

    plan = plan_public_writes({"equipment_types": [tractor]}, [], EMPTY)

    assert only_insert(plan, "machine_types").values == {"name": "Прочая техника"}


def test_equipment_type_without_brand_gets_empty_string() -> None:
    equipment_type = item("T", "Модель", {"kind": "OTHER"})

    plan = plan_public_writes({"equipment_types": [equipment_type]}, [], EMPTY)

    assert only_insert(plan, "equipment_models").values["brand"] == ""


def test_equipment_unit_depends_on_model_and_starts_in_work() -> None:
    plan = plan_public_writes(
        {"equipment_types": [EQUIPMENT_TYPE], "equipment_assets": [EQUIPMENT_ASSET]}, [], EMPTY
    )

    unit = only_insert(plan, "equipment_units")
    assert unit.values == {
        "internal_id": "БУ-01",
        "serial_number": "SN-JK830-0001",
        "status": "В работе",
    }
    assert "model_id" not in unit.values
    assert unit.depends_on == (("equipment_models", "JK830"),)
    assert unit.foreign_keys == (("model_id", "equipment_models", "JK830"),)


def test_equipment_unit_uses_code_without_inventory_number() -> None:
    asset = item("RIG_02", "Станок №2", {"equipment_type_code": "JK830"})

    plan = plan_public_writes(
        {"equipment_types": [EQUIPMENT_TYPE], "equipment_assets": [asset]}, [], EMPTY
    )

    assert only_insert(plan, "equipment_units").values["internal_id"] == "RIG_02"


def test_equipment_unit_of_linked_type_still_depends_on_model() -> None:
    journal = snapshot(
        machine_types=[{"id": 1, "name": "Буровая установка"}],
        equipment_models=[
            {"id": 5, "machine_type_id": 1, "brand": "Jinke", "model_name": "JK830-2"}
        ],
    )
    links = [link("equipment_types", "JK830", "equipment_models", 5)]

    plan = plan_public_writes(
        {"equipment_types": [EQUIPMENT_TYPE], "equipment_assets": [EQUIPMENT_ASSET]},
        links,
        journal,
    )

    assert inserts_for(plan, "equipment_models") == []
    assert only_insert(plan, "equipment_units").depends_on == (("equipment_models", "JK830"),)


def test_equipment_unit_without_reachable_type_is_skipped_with_warning() -> None:
    # Тип отключён, поэтому в журнал не выгружается: подставить model_id было
    # бы неоткуда, и единица пропускается.
    inactive_type = item("JK830", "JK830-2", {"kind": "DRILL_RIG"}, is_active=False)

    plan = plan_public_writes(
        {"equipment_types": [inactive_type], "equipment_assets": [EQUIPMENT_ASSET]}, [], EMPTY
    )

    assert inserts_for(plan, "equipment_units") == []
    assert any("RIG_01" in warning for warning in plan.warnings)


def test_devices_and_tools_go_to_their_tables() -> None:
    plan = plan_public_writes({"materials": [DEVICE, TOOL]}, [], EMPTY)

    device = only_insert(plan, "initiating_device_types")
    # Замедление живёт в дочерней таблице delay_series и только читается.
    assert device.values == {
        "name": "ЭД-1-Н",
        "description": "Электродетонатор непредохранительный",
    }
    tool = only_insert(plan, "tool_types")
    assert tool.values == {
        "name": "Долото шарошечное 152",
        "description": "Шарошечное долото для буровой установки JK830-2",
        "expected_lifetime_meters": Decimal("600"),
        "diameter": Decimal("152"),
        "thread_type": "З-76",
    }


def test_other_material_kinds_are_not_exported() -> None:
    explosive = item("VV", "Гранулит", {"material_kind": "ВВ"})

    assert plan_public_writes({"materials": [explosive]}, [], EMPTY).is_empty()


def test_inserts_follow_dependency_order() -> None:
    sections = {
        "counterparties": [CUSTOMER],
        "sites": [SITE],
        "equipment_types": [EQUIPMENT_TYPE],
        "equipment_assets": [EQUIPMENT_ASSET],
        "materials": [DEVICE, TOOL],
    }

    plan = plan_public_writes(sections, [], EMPTY)

    assert [insert.table for insert in plan.inserts] == [
        "counterparties",
        "sites",
        "machine_types",
        "equipment_models",
        "equipment_units",
        "initiating_device_types",
        "tool_types",
    ]


def test_inactive_unit_without_link_is_not_inserted() -> None:
    # Поэтому новая строка журнала всегда «В работе»: списанную единицу без
    # связи план не заводит вовсе.
    asset = item("RIG_09", "Станок №9", {"equipment_type_code": "JK830"}, is_active=False)

    plan = plan_public_writes(
        {"equipment_types": [EQUIPMENT_TYPE], "equipment_assets": [asset]}, [], EMPTY
    )

    assert inserts_for(plan, "equipment_units") == []
    assert plan.warnings == ()


def test_inactive_record_without_link_is_not_exported() -> None:
    closed = item("OLD", "Закрытый объект", {"customer_legal_name": "Заказчик"}, is_active=False)

    plan = plan_public_writes({"sites": [closed]}, [], EMPTY)

    assert plan.is_empty()
    assert plan.warnings == ()


def test_empty_sections_give_empty_plan() -> None:
    assert plan_public_writes({}, [], EMPTY).is_empty()


# --- Обновления -------------------------------------------------------------


CUSTOMER_ROW = {
    "id": 1,
    "full_name": 'Акционерное общество "Теплогорский карьер"',
    "short_name": 'АО "Теплогорский карьер"',
    "inn": "6608002092",
    "is_client": True,
    "is_supplier": False,
    "is_active": True,
}


def linked_site_journal(**overrides: Any) -> PublicSnapshot:
    row = {
        "id": 3,
        "full_name": "Ломоватский карьер",
        "short_name": "ЛОМ",
        "client_legal_name": 'АО "Теплогорский карьер"',
        "mineral_type": "нерудные материалы",
        "is_active": True,
    }
    row.update(overrides)
    return snapshot(counterparties=[CUSTOMER_ROW], sites=[row])


SITE_LINK = [
    link("counterparties", "TEPLOGORSK", "counterparties", 1),
    link("sites", "LOM", "sites", 3),
]


def test_update_carries_only_changed_column() -> None:
    plan = plan_public_writes(
        {"counterparties": [CUSTOMER], "sites": [SITE]},
        SITE_LINK,
        linked_site_journal(short_name="ЛМ"),
    )

    update = only_update(plan)
    assert plan.inserts == ()
    assert (update.table, update.public_id) == ("sites", 3)
    assert update.values == {"short_name": "ЛОМ"}


def test_unchanged_record_gives_empty_plan() -> None:
    plan = plan_public_writes(
        {"counterparties": [CUSTOMER], "sites": [SITE]}, SITE_LINK, linked_site_journal()
    )

    assert plan.is_empty()
    assert plan.warnings == ()


def test_empty_string_and_null_are_the_same_value() -> None:
    site = item("LOM", "Ломоватский карьер", {"customer_legal_name": "Заказчик"})
    journal = snapshot(
        sites=[
            {
                "id": 3,
                "full_name": "Ломоватский карьер",
                "short_name": "",
                "client_legal_name": "Заказчик",
                "mineral_type": None,
                "is_active": True,
            }
        ]
    )

    assert plan_public_writes({"sites": [site]}, SITE_LINK, journal).is_empty()


def test_journal_client_flag_is_not_reset_by_supplier_role() -> None:
    journal = snapshot(
        counterparties=[
            {
                "id": 2,
                "full_name": 'Общество с ограниченной ответственностью "ПОМБУР"',
                "short_name": 'ООО "ПОМБУР"',
                "inn": "7203270545",
                "is_client": True,
                "is_supplier": False,
                "is_active": True,
            }
        ]
    )
    links = [link("counterparties", "POMBUR", "counterparties", 2)]

    update = only_update(plan_public_writes({"counterparties": [SUPPLIER]}, links, journal))

    assert update.values == {"is_supplier": True}


def test_deactivation_reaches_the_journal() -> None:
    site = item("LOM", "Ломоватский карьер", {"short_name": "ЛОМ"}, is_active=False)
    journal = linked_site_journal(client_legal_name="", mineral_type=None)

    update = only_update(plan_public_writes({"sites": [site]}, SITE_LINK, journal))

    assert update.values == {"is_active": False}


def test_inactive_unit_keeps_journal_status_and_warns() -> None:
    asset = item(
        "RIG_01",
        "Станок №1",
        {"equipment_type_code": "JK830", "inventory_number": "БУ-02"},
        is_active=False,
    )
    journal = snapshot(
        equipment_units=[
            {
                "id": 9,
                "model_id": 5,
                "internal_id": "БУ-01",
                "serial_number": None,
                "status": "В работе",
            }
        ]
    )
    links = [link("equipment_assets", "RIG_01", "equipment_units", 9)]

    plan = plan_public_writes({"equipment_assets": [asset]}, links, journal)

    update = only_update(plan)
    assert update.values == {"internal_id": "БУ-02"}
    assert "status" not in update.values
    assert plan.warnings == (
        "Единица RIG_01 неактивна в BlastEX, статус в журнале не изменён.",
    )


def test_unit_written_off_in_journal_does_not_warn() -> None:
    asset = item(
        "RIG_01",
        "Станок №1",
        {"equipment_type_code": "JK830", "inventory_number": "БУ-01"},
        is_active=False,
    )
    journal = snapshot(
        equipment_units=[
            {
                "id": 9,
                "model_id": 5,
                "internal_id": "БУ-01",
                "serial_number": None,
                "status": "Списано",
            }
        ]
    )
    links = [link("equipment_assets", "RIG_01", "equipment_units", 9)]

    plan = plan_public_writes({"equipment_assets": [asset]}, links, journal)

    assert plan.is_empty()
    assert plan.warnings == ()


def test_link_without_journal_row_warns_and_skips_record() -> None:
    plan = plan_public_writes({"sites": [SITE]}, [link("sites", "LOM", "sites", 3)], EMPTY)

    assert plan.is_empty()
    assert plan.warnings == (
        "Запись sites/LOM: строка журнала sites#3 не найдена, выгрузка пропущена.",
    )


def test_link_to_another_table_is_skipped_with_warning() -> None:
    # Материалу сменили вид: связь ведёт в tool_types, а выгружать его теперь
    # нужно в initiating_device_types.
    device = item("BIT_152", "Долото шарошечное 152", {"material_kind": "СИ"})
    journal = snapshot(tool_types=[{"id": 4, "name": "Долото шарошечное 152"}])
    links = [link("materials", "BIT_152", "tool_types", 4)]

    plan = plan_public_writes({"materials": [device]}, links, journal)

    assert plan.is_empty()
    assert plan.warnings == (
        "Запись materials/BIT_152: связь ведёт на tool_types, "
        "а выгрузка идёт в initiating_device_types; запись пропущена.",
    )


def test_material_kind_without_journal_table_warns_when_linked() -> None:
    # Материал перевели в ВВ: своей таблицы в журнале у него нет, но связь со
    # строкой осталась — молча бросать её нельзя.
    explosive = item("BIT_152", "Гранулит", {"material_kind": "ВВ"})
    journal = snapshot(tool_types=[{"id": 4, "name": "Долото шарошечное 152"}])
    links = [link("materials", "BIT_152", "tool_types", 4)]

    plan = plan_public_writes({"materials": [explosive]}, links, journal)

    assert plan.is_empty()
    assert plan.warnings == (
        "Запись materials/BIT_152: вид «ВВ» в журнал не выгружается, "
        "строка tool_types#4 не обновляется.",
    )


def test_unlinked_material_of_other_kind_does_not_warn() -> None:
    explosive = item("VV", "Гранулит", {"material_kind": "ВВ"})

    plan = plan_public_writes({"materials": [explosive]}, [], EMPTY)

    assert plan.warnings == ()


def test_empty_value_is_not_written_to_not_null_column() -> None:
    # ИНН очистили: колонка журнала NOT NULL, поэтому она не обновляется —
    # иначе транзакция упала бы целиком.
    customer = item(
        "TEPLOGORSK",
        'Акционерное общество "Теплогорский карьер"',
        {"short_name": 'АО "Теплогорский карьер"', "role": "CUSTOMER"},
        is_active=False,
    )
    links = [link("counterparties", "TEPLOGORSK", "counterparties", 1)]

    plan = plan_public_writes(
        {"counterparties": [customer]}, links, snapshot(counterparties=[CUSTOMER_ROW])
    )

    assert only_update(plan).values == {"is_active": False}
    assert plan.warnings == (
        "Запись counterparties/TEPLOGORSK: колонка inn в журнале обязательна, "
        "пустое значение не записано.",
    )


def test_nullable_column_is_cleared_as_usual() -> None:
    site = item("LOM", "Ломоватский карьер", {"customer_code": "TEPLOGORSK"})

    plan = plan_public_writes(
        {"counterparties": [CUSTOMER], "sites": [site]}, SITE_LINK, linked_site_journal()
    )

    assert only_update(plan).values == {"short_name": None, "mineral_type": None}
    assert plan.warnings == ()


def test_tool_numbers_are_compared_as_numbers() -> None:
    journal = snapshot(
        tool_types=[
            {
                "id": 4,
                "name": "Долото шарошечное 152",
                "description": "Шарошечное долото для буровой установки JK830-2",
                "expected_lifetime_meters": Decimal("600.00"),
                "diameter": Decimal("152.0"),
                "thread_type": "З-76",
            }
        ]
    )
    links = [link("materials", "BIT_152", "tool_types", 4)]

    assert plan_public_writes({"materials": [TOOL]}, links, journal).is_empty()


# --- Ограничения журнала ----------------------------------------------------


def fields_of(issues: Sequence[Any]) -> list[tuple[str, str, str]]:
    return [(issue.section, issue.code, issue.field) for issue in issues]


def test_missing_and_malformed_inn_are_errors() -> None:
    sections = {
        "counterparties": [
            item("NO_INN", "Без ИНН", {"role": "CUSTOMER"}),
            item("BAD_INN", "Кривой ИНН", {"role": "CUSTOMER", "inn": "660800"}),
        ]
    }

    issues = public_constraint_issues(sections, [])

    assert fields_of(issues) == [
        ("counterparties", "NO_INN", "inn"),
        ("counterparties", "BAD_INN", "inn"),
    ]
    assert all(issue.level == "error" for issue in issues)


def test_twelve_digit_inn_is_accepted() -> None:
    sections = {"counterparties": [item("IP", "ИП", {"role": "SUPPLIER", "inn": "660800209212"})]}

    assert public_constraint_issues(sections, []) == []


def test_site_without_customer_is_an_error() -> None:
    sections = {"sites": [item("S", "Объект")]}

    issues = public_constraint_issues(sections, [])

    assert fields_of(issues) == [("sites", "S", "customer_code")]


def test_site_with_customer_text_only_is_valid() -> None:
    sections = {"sites": [item("S", "Объект", {"customer_legal_name": "Заказчик"})]}

    assert public_constraint_issues(sections, []) == []


def test_long_site_short_name_is_an_error() -> None:
    sections = {
        "sites": [item("S", "Объект", {"customer_legal_name": "Заказчик", "short_name": "ЛОМБУР"})]
    }

    issues = public_constraint_issues(sections, [])

    assert fields_of(issues) == [("sites", "S", "short_name")]


def test_asset_without_type_and_with_unknown_type_are_errors() -> None:
    sections = {
        "equipment_types": [EQUIPMENT_TYPE],
        "equipment_assets": [
            item("NO_TYPE", "Без типа"),
            item("BAD_TYPE", "Чужой тип", {"equipment_type_code": "НЕТ_ТАКОГО"}),
            EQUIPMENT_ASSET,
        ],
    }

    issues = public_constraint_issues(sections, [])

    assert fields_of(issues) == [
        ("equipment_assets", "NO_TYPE", "equipment_type_code"),
        ("equipment_assets", "BAD_TYPE", "equipment_type_code"),
    ]


def test_duplicate_equipment_type_name_is_an_error() -> None:
    sections = {
        "equipment_types": [
            EQUIPMENT_TYPE,
            item("JK830B", "JK830-2", {"kind": "DRILL_RIG"}),
            item("OLD", "JK830-2", {"kind": "DRILL_RIG"}, is_active=False),
        ]
    }

    issues = public_constraint_issues(sections, [])

    assert fields_of(issues) == [("equipment_types", "JK830B", "name")]


def test_linked_counterparty_is_checked_even_when_inactive() -> None:
    # Связанную запись план обновляет независимо от активности, значит и
    # ограничения журнала по её колонкам нужно проверить.
    customer = item("TEPLOGORSK", "Заказчик", {"role": "CUSTOMER"}, is_active=False)
    links = [link("counterparties", "TEPLOGORSK", "counterparties", 1)]

    issues = public_constraint_issues({"counterparties": [customer]}, links)

    assert fields_of(issues) == [("counterparties", "TEPLOGORSK", "inn")]


def test_linked_site_is_checked_by_written_columns() -> None:
    site = item("LOM", "Ломоватский карьер", {"short_name": "ЛОМБУР"}, is_active=False)
    links = [link("sites", "LOM", "sites", 3)]

    issues = public_constraint_issues({"sites": [site]}, links)

    assert fields_of(issues) == [
        ("sites", "LOM", "customer_code"),
        ("sites", "LOM", "short_name"),
    ]


def test_inactive_records_are_not_checked() -> None:
    sections = {
        "counterparties": [item("NO_INN", "Без ИНН", {"role": "CUSTOMER"}, is_active=False)],
        "sites": [item("S", "Объект", is_active=False)],
        "equipment_assets": [item("NO_TYPE", "Без типа", is_active=False)],
    }

    assert public_constraint_issues(sections, []) == []


CONFLICT_SECTIONS = {
    "counterparties": [CUSTOMER],
    "equipment_types": [EQUIPMENT_TYPE],
    "equipment_assets": [EQUIPMENT_ASSET],
}

CONFLICT_JOURNAL = snapshot(
    counterparties=[
        {
            "id": 1,
            "full_name": 'АО "Теплогорский карьер"',
            "inn": "6608002092",
            "is_client": True,
            "is_active": True,
        }
    ],
    equipment_models=[{"id": 5, "brand": "Jinke", "model_name": "JK830-2"}],
    equipment_units=[{"id": 9, "model_id": 5, "internal_id": "БУ-01", "status": "В работе"}],
)


def test_journal_conflicts_are_reported_with_snapshot() -> None:
    issues = public_constraint_issues(CONFLICT_SECTIONS, [], CONFLICT_JOURNAL)

    assert fields_of(issues) == [
        ("counterparties", "TEPLOGORSK", "inn"),
        ("equipment_types", "JK830", "name"),
        ("equipment_assets", "RIG_01", "inventory_number"),
    ]
    assert all("Из project1" in issue.message for issue in issues)


def test_journal_conflicts_are_skipped_without_snapshot() -> None:
    assert public_constraint_issues(CONFLICT_SECTIONS, []) == []


def test_linked_records_do_not_conflict_with_their_own_rows() -> None:
    links = [
        link("counterparties", "TEPLOGORSK", "counterparties", 1),
        link("equipment_types", "JK830", "equipment_models", 5),
        link("equipment_assets", "RIG_01", "equipment_units", 9),
    ]

    assert public_constraint_issues(CONFLICT_SECTIONS, links, CONFLICT_JOURNAL) == []


def test_duplicate_name_does_not_hide_journal_conflict() -> None:
    # Повтор внутри раздела — не повод пропустить конфликт с журналом: сметчику
    # нужны обе ошибки, иначе он починит одну и снова упрётся во вторую.
    sections = {
        "equipment_types": [EQUIPMENT_TYPE, item("JK830B", "JK830-2", {"kind": "DRILL_RIG"})]
    }

    issues = public_constraint_issues(sections, [], CONFLICT_JOURNAL)

    assert fields_of(issues) == [
        ("equipment_types", "JK830", "name"),
        ("equipment_types", "JK830B", "name"),
        ("equipment_types", "JK830B", "name"),
    ]
    assert "повторяется" in issues[1].message
    assert "Из project1" in issues[2].message


def test_unit_conflict_uses_code_without_inventory_number() -> None:
    sections = {
        "equipment_types": [EQUIPMENT_TYPE],
        "equipment_assets": [item("БУ-01", "Станок", {"equipment_type_code": "JK830"})],
    }

    issues = public_constraint_issues(sections, [], CONFLICT_JOURNAL)

    assert ("equipment_assets", "БУ-01", "inventory_number") in fields_of(issues)


@pytest.mark.parametrize("section", ["counterparties", "sites", "equipment_assets"])
def test_missing_sections_are_not_required(section: str) -> None:
    assert public_constraint_issues({section: []}, []) == []


# --- Длины колонок журнала --------------------------------------------------


def test_long_model_name_and_brand_are_errors() -> None:
    sections = {
        "equipment_types": [
            item("LONG", "Д" * 129, {"kind": "DRILL_RIG"}),
            item("BRAND", "DM45", {"kind": "DRILL_RIG", "brand": "E" * 129}),
        ]
    }

    issues = public_constraint_issues(sections, [])

    assert fields_of(issues) == [
        ("equipment_types", "LONG", "name"),
        ("equipment_types", "BRAND", "brand"),
    ]
    assert "128" in issues[0].message


def test_names_at_the_limit_are_accepted() -> None:
    sections = {
        "equipment_types": [item("LONG", "Д" * 128, {"kind": "DRILL_RIG", "brand": "E" * 128})]
    }

    assert public_constraint_issues(sections, []) == []


def test_long_inventory_and_serial_numbers_are_errors() -> None:
    sections = {
        "equipment_types": [EQUIPMENT_TYPE],
        "equipment_assets": [
            item(
                "RIG_LONG",
                "Станок",
                {
                    "equipment_type_code": "JK830",
                    "inventory_number": "Б" * 65,
                    "serial_number": "S" * 129,
                },
            )
        ],
    }

    issues = public_constraint_issues(sections, [])

    assert fields_of(issues) == [
        ("equipment_assets", "RIG_LONG", "inventory_number"),
        ("equipment_assets", "RIG_LONG", "serial_number"),
    ]
    assert "64" in issues[0].message
    assert "128" in issues[1].message


def test_long_code_without_inventory_number_is_an_error() -> None:
    # Без инвентарного номера в журнал уходит код записи: он бывает длиннее
    # колонки, и сметчику надо объяснить, почему виноват код.
    sections = {
        "equipment_types": [EQUIPMENT_TYPE],
        "equipment_assets": [item("Б" * 65, "Станок", {"equipment_type_code": "JK830"})],
    }

    issues = public_constraint_issues(sections, [])

    assert fields_of(issues) == [("equipment_assets", "Б" * 65, "inventory_number")]
    assert "код" in issues[0].message


def test_length_is_checked_for_linked_inactive_records() -> None:
    # Связанную запись план обновляет независимо от активности: слишком
    # длинное значение уронит транзакцию так же, как у активной.
    asset = item(
        "RIG_01",
        "Станок",
        {"equipment_type_code": "JK830", "serial_number": "S" * 129},
        is_active=False,
    )
    links = [link("equipment_assets", "RIG_01", "equipment_units", 9)]

    issues = public_constraint_issues({"equipment_assets": [asset]}, links)

    assert fields_of(issues) == [("equipment_assets", "RIG_01", "serial_number")]
