"""Тесты разницы между журналом ``public`` и черновиком справочников (§4.4).

Базы здесь нет: снимок журнала берётся из тестов сопоставления
(``tests/test_public_sync_mapping``), черновик собирается из ``ReferenceItem``,
связи — из ``PublicLink``. Так проверяется вся логика разницы, даже когда
Docker с PostgreSQL выключен.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cost.v2.models import ReferenceItem
from cost.v2.public_sync import compute_delta
from cost.v2.public_sync.delta import DeltaEntry, FieldChange, PublicDelta
from cost.v2.repository import PublicLink
from tests.test_public_sync_mapping import (
    EQUIPMENT_MODELS,
    SITES,
    TOOL_TYPES,
    make_snapshot,
)

# В снимке §13: 2 контрагента, 2 объекта, 1 модель, 1 единица техники,
# 2 типа СИ, 1 тип инструмента и 4 цены (договор, две позиции спецификации,
# последняя закупка инструмента).
TOTAL_ROWS = 13


def link(section: str, code: str, table: str, public_id: int) -> PublicLink:
    return PublicLink(
        section=section, code=code, public_table=table, public_id=public_id
    )


def by_code(delta: PublicDelta) -> dict[str, DeltaEntry]:
    return {entry.code: entry for entry in delta.entries}


def site_record(**overrides) -> ReferenceItem:
    """Черновик объекта, совпадающий с ``sites#1`` по общим полям."""

    payload = {
        "short_name": "ЛОМ",
        "mineral_type": "неруудные материалы",
        "customer_code": "PUB_COUNTERPARTY_1",
        # Поле blastex, которого в журнале нет: разница его не трогает.
        "mobilization_km": "40",
    }
    payload.update(overrides.pop("payload", {}))
    data: dict = {
        "code": "SITE_LOM",
        "name": "Ломоватский карьер",
        "payload": payload,
        "is_active": True,
    }
    data.update(overrides)
    return ReferenceItem(**data)


def device_record(**overrides) -> ReferenceItem:
    """Черновик СИ, совпадающий с ``initiating_device_types#1``."""

    data: dict = {
        "code": "IDT_ED",
        "name": "ЭД-1-Н",
        "comment": "Электродетонатор непредохранительный",
        "payload": {"material_kind": "СИ", "storage_class": "NSI"},
    }
    data.update(overrides)
    return ReferenceItem(**data)


# --- Пустой черновик --------------------------------------------------------


def test_empty_draft_gives_only_new_entries() -> None:
    delta = compute_delta(make_snapshot(), [], {})

    assert delta.counts == {"new": TOTAL_ROWS, "changed": 0, "deactivated": 0}
    assert len(delta.entries) == TOTAL_ROWS
    assert {entry.kind for entry in delta.entries} == {"new"}
    assert all(entry.changes == () for entry in delta.entries)


def test_new_entries_follow_proposal_order() -> None:
    delta = compute_delta(make_snapshot(), [], {})

    assert [entry.section for entry in delta.entries] == [
        "counterparties",
        "counterparties",
        "sites",
        "sites",
        "equipment_types",
        "equipment_assets",
        "materials",
        "materials",
        "materials",
        "material_prices",
        "material_prices",
        "material_prices",
        "material_prices",
    ]


def test_new_entry_carries_ready_reference_item() -> None:
    entry = by_code(compute_delta(make_snapshot(), [], {}))["PUB_COUNTERPARTY_1"]

    assert entry.kind == "new"
    assert entry.public_table == "counterparties" and entry.public_id == 1
    assert entry.name == 'Акционерное общество "Теплогорский карьер"'
    assert entry.item["code"] == "PUB_COUNTERPARTY_1"
    assert entry.item["payload"]["role"] == "CUSTOMER"
    assert entry.item["is_active"] is True
    assert entry.item["source"]


def test_new_price_keeps_dates_as_iso_strings() -> None:
    entry = by_code(compute_delta(make_snapshot(), [], {}))["PRICE_PUB_EMP_1"]

    assert entry.item["valid_from"] == "2026-02-01"
    assert entry.item["valid_to"] == "2026-12-31"
    assert entry.item["payload"]["price_rub"] == "250.00"


# --- Связанная запись -------------------------------------------------------


def test_linked_site_reports_changed_shared_field() -> None:
    sites = [dict(SITES[0], short_name="ЛМ"), SITES[1]]

    delta = compute_delta(
        make_snapshot(sites=sites),
        [link("sites", "SITE_LOM", "sites", 1)],
        {"sites": [site_record()]},
    )

    entry = by_code(delta)["SITE_LOM"]
    assert entry.kind == "changed"
    assert entry.section == "sites"
    assert entry.public_table == "sites" and entry.public_id == 1
    assert entry.changes == (FieldChange("payload.short_name", "ЛОМ", "ЛМ"),)
    assert entry.item["payload"]["short_name"] == "ЛМ"
    # Поля черновика, которых нет в журнале, остаются на месте.
    assert entry.item["payload"]["mobilization_km"] == "40"
    assert delta.counts["changed"] == 1
    assert delta.counts["new"] == TOTAL_ROWS - 1


def test_linked_site_without_changes_gives_no_entry() -> None:
    delta = compute_delta(
        make_snapshot(),
        [link("sites", "SITE_LOM", "sites", 1)],
        {"sites": [site_record()]},
    )

    assert "SITE_LOM" not in by_code(delta)
    assert delta.counts["changed"] == 0
    assert delta.counts["deactivated"] == 0


def test_inactive_public_row_deactivates_active_record() -> None:
    sites = [dict(SITES[0], is_active=False), SITES[1]]

    delta = compute_delta(
        make_snapshot(sites=sites),
        [link("sites", "SITE_LOM", "sites", 1)],
        {"sites": [site_record()]},
    )

    entry = by_code(delta)["SITE_LOM"]
    assert entry.kind == "deactivated"
    assert entry.changes == (FieldChange("is_active", True, False),)
    assert entry.item["is_active"] is False
    assert delta.counts["deactivated"] == 1
    assert delta.counts["changed"] == 0


def test_inactive_row_with_other_changes_is_changed() -> None:
    sites = [dict(SITES[0], is_active=False, short_name="ЛМ"), SITES[1]]

    delta = compute_delta(
        make_snapshot(sites=sites),
        [link("sites", "SITE_LOM", "sites", 1)],
        {"sites": [site_record()]},
    )

    entry = by_code(delta)["SITE_LOM"]
    assert entry.kind == "changed"
    assert {change.key for change in entry.changes} == {
        "is_active",
        "payload.short_name",
    }


def test_already_inactive_record_is_not_reported_again() -> None:
    sites = [dict(SITES[0], is_active=False), SITES[1]]

    delta = compute_delta(
        make_snapshot(sites=sites),
        [link("sites", "SITE_LOM", "sites", 1)],
        {"sites": [site_record(is_active=False)]},
    )

    assert "SITE_LOM" not in by_code(delta)


def test_link_without_draft_record_is_skipped() -> None:
    delta = compute_delta(make_snapshot(), [link("sites", "SITE_LOM", "sites", 1)], {})

    assert not [entry for entry in delta.entries if entry.public_id == 1
                and entry.public_table == "sites"]
    assert delta.counts["new"] == TOTAL_ROWS - 1


def test_draft_code_matching_public_code_counts_as_link() -> None:
    # Пользователь применил предложение раньше, а связь ещё не сохранена:
    # запись с кодом PUB_* считается связанной, дубля не будет.
    draft = {"sites": [site_record(code="PUB_SITE_1")]}

    delta = compute_delta(make_snapshot(), [], draft)

    assert "PUB_SITE_1" not in by_code(delta)
    assert delta.counts["new"] == TOTAL_ROWS - 1


def test_missing_payload_key_in_public_clears_draft_value() -> None:
    sites = [dict(SITES[0], mineral_type=None), SITES[1]]

    delta = compute_delta(
        make_snapshot(sites=sites),
        [link("sites", "SITE_LOM", "sites", 1)],
        {"sites": [site_record()]},
    )

    entry = by_code(delta)["SITE_LOM"]
    assert entry.changes == (
        FieldChange("payload.mineral_type", "неруудные материалы", None),
    )
    assert "mineral_type" not in entry.item["payload"]


def test_empty_string_equals_missing_value() -> None:
    draft = {"sites": [site_record(payload={"customer_legal_name": ""})]}

    delta = compute_delta(
        make_snapshot(), [link("sites", "SITE_LOM", "sites", 1)], draft
    )

    assert "SITE_LOM" not in by_code(delta)


def test_name_and_comment_are_compared_as_top_level_fields() -> None:
    draft = {"materials": [device_record(name="ЭД", comment="старое пояснение")]}

    delta = compute_delta(
        make_snapshot(),
        [link("materials", "IDT_ED", "initiating_device_types", 1)],
        draft,
    )

    entry = by_code(delta)["IDT_ED"]
    assert entry.kind == "changed"
    assert entry.changes == (
        FieldChange("name", "ЭД", "ЭД-1-Н"),
        FieldChange(
            "comment", "старое пояснение", "Электродетонатор непредохранительный"
        ),
    )
    assert entry.item["name"] == "ЭД-1-Н"
    assert entry.name == "ЭД-1-Н"


# --- Вид техники ------------------------------------------------------------


def test_equipment_kind_is_never_compared() -> None:
    # В журнале «Самосвал» (kind OTHER), в черновике пользователь выбрал
    # буровую установку — словарь не должен перетирать этот выбор.
    draft = {
        "equipment_types": [
            ReferenceItem(
                code="TYPE_JK",
                name="65115",
                payload={
                    "kind": "DRILL_RIG",
                    "brand": "КамАЗ",
                    "machine_type_name": "Самосвал",
                },
            )
        ]
    }

    delta = compute_delta(
        make_snapshot(),
        [link("equipment_types", "TYPE_JK", "equipment_models", 1)],
        draft,
    )

    assert "TYPE_JK" not in by_code(delta)


def test_changed_equipment_type_keeps_draft_kind() -> None:
    models = [dict(EQUIPMENT_MODELS[0], brand="KAMAZ")]
    draft = {
        "equipment_types": [
            ReferenceItem(
                code="TYPE_JK",
                name="65115",
                payload={
                    "kind": "DRILL_RIG",
                    "brand": "КамАЗ",
                    "machine_type_name": "Самосвал",
                },
            )
        ]
    }

    delta = compute_delta(
        make_snapshot(equipment_models=models),
        [link("equipment_types", "TYPE_JK", "equipment_models", 1)],
        draft,
    )

    entry = by_code(delta)["TYPE_JK"]
    assert entry.changes == (FieldChange("payload.brand", "КамАЗ", "KAMAZ"),)
    assert entry.item["payload"]["kind"] == "DRILL_RIG"


def test_linked_type_code_reaches_equipment_asset() -> None:
    draft = {
        "equipment_types": [
            ReferenceItem(
                code="TYPE_JK",
                name="65115",
                payload={
                    "kind": "OTHER",
                    "brand": "КамАЗ",
                    "machine_type_name": "Самосвал",
                },
            )
        ]
    }

    delta = compute_delta(
        make_snapshot(),
        [link("equipment_types", "TYPE_JK", "equipment_models", 1)],
        draft,
    )

    unit = by_code(delta)["PUB_UNIT_1"]
    assert unit.item["payload"]["equipment_type_code"] == "TYPE_JK"


def test_linked_equipment_asset_with_different_name_gives_no_entry() -> None:
    # internal_id — инвентарный номер, а не имя единицы техники: связанная
    # запись с тем же inventory_number, но другим именем не должна попадать в
    # разницу — иначе применение предложения переименовало бы технику в её
    # инвентарный номер (см. §4.1 «equipment_assets»).
    asset = ReferenceItem(
        code="ASSET_JK_65115",
        name="КамАЗ бортовой №3",  # Отличается от internal_id "С-01"
        payload={
            "inventory_number": "С-01",
            "serial_number": "SN-65115-0001",
            "equipment_type_code": "PUB_MODEL_1",
        },
        # Единица #1 в снимке уже списана (status = "Списано") — без этого
        # совпадёт только имя, а is_active даст лишнюю запись "deactivated".
        is_active=False,
    )

    delta = compute_delta(
        make_snapshot(),
        [link("equipment_assets", "ASSET_JK_65115", "equipment_units", 1)],
        {"equipment_assets": [asset]},
    )

    assert "ASSET_JK_65115" not in by_code(delta)
    assert delta.counts["changed"] == 0


# --- Ссылки на переименованные записи ---------------------------------------


def test_linked_material_code_reaches_its_prices() -> None:
    delta = compute_delta(
        make_snapshot(),
        [link("materials", "IDT_ED", "initiating_device_types", 1)],
        {"materials": [device_record()]},
    )

    codes = by_code(delta)
    assert "PUB_IDT_1" not in codes
    assert "IDT_ED" not in codes  # общие поля совпадают
    assert codes["PRICE_PUB_EMP_1"].item["payload"]["material_code"] == "IDT_ED"
    assert codes["PRICE_PUB_SPEC_1"].item["payload"]["material_code"] == "IDT_ED"
    # Второй тип СИ не связан — у него остаётся код PUB_*.
    assert codes["PRICE_PUB_SPEC_2"].item["payload"]["material_code"] == "PUB_IDT_2"


def test_linked_tool_code_reaches_its_price() -> None:
    tool = ReferenceItem(
        code="TOOL_BIT_152",
        name="Долото шарошечное 152",
        comment="Шарошечное долото для буровой установки JK830-2",
        payload={
            "material_kind": "Буровой инструмент",
            "lifetime_m": "600",
            "diameter_mm": "152",
            "thread_type": "З-76",
        },
    )

    delta = compute_delta(
        make_snapshot(),
        [link("materials", "TOOL_BIT_152", "tool_types", 1)],
        {"materials": [tool]},
    )

    codes = by_code(delta)
    assert "PUB_TOOL_1" not in codes
    assert codes["PRICE_PUB_TOOL_2"].item["payload"]["material_code"] == "TOOL_BIT_152"


def test_linked_counterparty_code_reaches_site_and_price() -> None:
    draft = {
        "counterparties": [
            ReferenceItem(
                code="TEPLOGORSK",
                name='Акционерное общество "Теплогорский карьер"',
                payload={
                    "short_name": 'АО "Теплогорский карьер"',
                    "inn": "6608002092",
                    "role": "CUSTOMER",
                },
            )
        ]
    }
    links = [
        link("counterparties", "TEPLOGORSK", "counterparties", 1),
        # Поставщик связан, но его запись из черновика удалили: предложение
        # пропускается, а ссылки на код связи остаются рабочими.
        link("counterparties", "POMBUR", "counterparties", 2),
    ]

    delta = compute_delta(make_snapshot(), links, draft)

    codes = by_code(delta)
    assert "PUB_COUNTERPARTY_1" not in codes and "PUB_COUNTERPARTY_2" not in codes
    assert codes["PUB_SITE_1"].item["payload"]["customer_code"] == "TEPLOGORSK"
    assert codes["PRICE_PUB_EMP_1"].item["payload"]["supplier_code"] == "POMBUR"
    assert codes["PRICE_PUB_TOOL_2"].item["payload"]["supplier_code"] == "POMBUR"


# --- Цены -------------------------------------------------------------------


def test_spec_price_with_other_amount_is_changed() -> None:
    price = ReferenceItem(
        code="PRICE_PUB_SPEC_1",
        name="ЭД-1-Н — спецификация СПЦ-2026-001",
        payload={
            "material_code": "PUB_IDT_1",
            "supplier_code": "PUB_COUNTERPARTY_2",
            "price_rub": "300.00",
            "delivery_rub": "33.21",
        },
        valid_from=date(2026, 1, 20),
    )

    delta = compute_delta(make_snapshot(), [], {"material_prices": [price]})

    entry = by_code(delta)["PRICE_PUB_SPEC_1"]
    assert entry.kind == "changed"
    assert entry.changes == (FieldChange("payload.price_rub", "300.00", "335.16"),)
    assert entry.item["payload"]["price_rub"] == "335.16"
    assert entry.item["payload"]["delivery_rub"] == "33.21"


def test_price_validity_dates_are_compared() -> None:
    price = ReferenceItem(
        code="PRICE_PUB_EMP_1",
        name="ЭД-1-Н — цена с 2026-02-01",
        payload={
            "material_code": "PUB_IDT_1",
            "supplier_code": "PUB_COUNTERPARTY_2",
            "price_rub": "250.00",
            "delivery_rub": "0.00",
        },
        valid_from=date(2026, 2, 1),
        valid_to=date(2026, 6, 30),
    )

    delta = compute_delta(make_snapshot(), [], {"material_prices": [price]})

    entry = by_code(delta)["PRICE_PUB_EMP_1"]
    assert entry.changes == (
        FieldChange("valid_to", "2026-06-30", "2026-12-31"),
    )
    assert entry.item["valid_to"] == "2026-12-31"
    assert entry.item["valid_from"] == "2026-02-01"


def test_matching_price_gives_no_entry() -> None:
    price = ReferenceItem(
        code="PRICE_PUB_EMP_1",
        name="ЭД-1-Н — цена с 2026-02-01",
        payload={
            "material_code": "PUB_IDT_1",
            "supplier_code": "PUB_COUNTERPARTY_2",
            "price_rub": "250.00",
            "delivery_rub": "0.00",
        },
        valid_from=date(2026, 2, 1),
        valid_to=date(2026, 12, 31),
    )

    delta = compute_delta(make_snapshot(), [], {"material_prices": [price]})

    assert "PRICE_PUB_EMP_1" not in by_code(delta)


def test_price_with_different_name_gives_no_entry() -> None:
    # Цена с переименованным именем, но идентичными price_rub/delivery_rub/
    # valid_from/valid_to/supplier_code не должна создавать запись в разнице:
    # имя не входит в shared_fields и не перетирает выбор пользователя (§4.4).
    price = ReferenceItem(
        code="PRICE_PUB_SPEC_1",
        name="Пользовательское имя цены",  # Отличается от "ЭД-1-Н — спецификация..."
        payload={
            "material_code": "PUB_IDT_1",
            "supplier_code": "PUB_COUNTERPARTY_2",
            "price_rub": "335.16",
            "delivery_rub": "33.21",
        },
        valid_from=date(2026, 1, 20),
    )

    delta = compute_delta(make_snapshot(), [], {"material_prices": [price]})

    assert "PRICE_PUB_SPEC_1" not in by_code(delta)
    assert delta.counts["changed"] == 0


# --- Сравнение значений -----------------------------------------------------


@pytest.mark.parametrize(
    "lifetime, diameter",
    [
        ("600.0", "152.00"),
        (600, 152),
        (Decimal("600.000"), Decimal("152")),
        ("6E+2", "152"),
    ],
)
def test_decimal_like_values_do_not_differ(lifetime, diameter) -> None:
    tool = ReferenceItem(
        code="PUB_TOOL_1",
        name="Долото шарошечное 152",
        comment="Шарошечное долото для буровой установки JK830-2",
        payload={
            "material_kind": "Буровой инструмент",
            "lifetime_m": lifetime,
            "diameter_mm": diameter,
            "thread_type": "З-76",
        },
    )

    delta = compute_delta(make_snapshot(), [], {"materials": [tool]})

    assert "PUB_TOOL_1" not in by_code(delta)


def test_real_number_difference_is_reported() -> None:
    types = [dict(TOOL_TYPES[0], expected_lifetime_meters=Decimal("700"))]
    tool = ReferenceItem(
        code="PUB_TOOL_1",
        name="Долото шарошечное 152",
        comment="Шарошечное долото для буровой установки JK830-2",
        payload={
            "material_kind": "Буровой инструмент",
            "lifetime_m": "600",
            "diameter_mm": "152",
            "thread_type": "З-76",
        },
    )

    delta = compute_delta(
        make_snapshot(tool_types=types), [], {"materials": [tool]}
    )

    entry = by_code(delta)["PUB_TOOL_1"]
    assert entry.changes == (FieldChange("payload.lifetime_m", "600", "700"),)


def test_leading_zero_text_is_not_compared_as_number() -> None:
    # ИНН «0608002092» — текст: как число он совпал бы с «608002092».
    counterparties = [
        dict(
            {
                "id": 1,
                "full_name": 'Акционерное общество "Теплогорский карьер"',
                "short_name": 'АО "Теплогорский карьер"',
                "is_client": True,
                "is_active": True,
            },
            inn="0608002092",
        )
    ]
    record = ReferenceItem(
        code="PUB_COUNTERPARTY_1",
        name='Акционерное общество "Теплогорский карьер"',
        payload={
            "short_name": 'АО "Теплогорский карьер"',
            "inn": "608002092",
            "role": "CUSTOMER",
        },
    )

    delta = compute_delta(
        make_snapshot(counterparties=counterparties),
        [],
        {"counterparties": [record]},
    )

    entry = by_code(delta)["PUB_COUNTERPARTY_1"]
    assert entry.changes == (
        FieldChange("payload.inn", "608002092", "0608002092"),
    )


def test_emptied_comment_becomes_empty_string_not_none() -> None:
    # `ReferenceItem.comment` — строка: None превратился бы в текст «None».
    devices = [{"id": 1, "name": "ЭД-1-Н", "description": None}]

    delta = compute_delta(
        make_snapshot(initiating_device_types=devices),
        [link("materials", "IDT_ED", "initiating_device_types", 1)],
        {"materials": [device_record()]},
    )

    entry = by_code(delta)["IDT_ED"]
    assert entry.changes == (
        FieldChange("comment", "Электродетонатор непредохранительный", None),
    )
    assert entry.item["comment"] == ""
    assert ReferenceItem.from_dict(entry.item).comment == ""


def test_text_that_looks_numeric_is_not_lost() -> None:
    # Резьба «З-76» и подобные строки не должны попадать в числовое сравнение.
    types = [dict(TOOL_TYPES[0], thread_type="T-51")]
    tool = ReferenceItem(
        code="PUB_TOOL_1",
        name="Долото шарошечное 152",
        comment="Шарошечное долото для буровой установки JK830-2",
        payload={
            "material_kind": "Буровой инструмент",
            "lifetime_m": "600",
            "diameter_mm": "152",
            "thread_type": "З-76",
        },
    )

    delta = compute_delta(
        make_snapshot(tool_types=types), [], {"materials": [tool]}
    )

    entry = by_code(delta)["PUB_TOOL_1"]
    assert entry.changes == (FieldChange("payload.thread_type", "З-76", "T-51"),)


# --- Устойчивость -----------------------------------------------------------


def test_compute_delta_does_not_touch_draft_records() -> None:
    sites = [dict(SITES[0], short_name="ЛМ"), SITES[1]]
    record = site_record()
    payload_before = dict(record.payload)

    compute_delta(
        make_snapshot(sites=sites),
        [link("sites", "SITE_LOM", "sites", 1)],
        {"sites": [record]},
    )

    assert record.payload == payload_before
    assert record.name == "Ломоватский карьер"


def test_every_entry_item_is_a_valid_reference_record() -> None:
    # Запись предложения уходит прямо в черновик: она обязана собираться
    # обратно в ReferenceItem и проходить схему своего раздела.
    from cost.v2.schemas import SECTION_SCHEMAS

    sites = [dict(SITES[0], short_name="ЛМ"), SITES[1]]
    delta = compute_delta(
        make_snapshot(sites=sites),
        [link("sites", "SITE_LOM", "sites", 1)],
        {"sites": [site_record()]},
    )

    for entry in delta.entries:
        record = ReferenceItem.from_dict(entry.item)
        assert record.code == entry.code
        SECTION_SCHEMAS[entry.section].model_validate(record.payload)


def test_empty_snapshot_gives_empty_delta() -> None:
    from cost.v2.public_sync.mapping import PublicSnapshot

    delta = compute_delta(PublicSnapshot(rows={}), [], {})

    assert delta.entries == ()
    assert delta.counts == {"new": 0, "changed": 0, "deactivated": 0}


def test_unknown_draft_sections_are_ignored() -> None:
    delta = compute_delta(
        make_snapshot(), [], {"rocks": [ReferenceItem(code="ROCK", name="Гранит")]}
    )

    assert delta.counts["new"] == TOTAL_ROWS
