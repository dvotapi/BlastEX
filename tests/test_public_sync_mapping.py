"""Тесты сопоставления разделов blastex с таблицами схемы ``public``.

Базы данных здесь нет: снимок ``PublicSnapshot`` собирается из словарей —
тех же полей, что вернёт ``SELECT *``. Числа взяты из §13 спецификации
(реальные данные организации), поэтому формулы цен проверяются на тех же
величинах, что и в журнале.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cost.v2.public_sync.mapping import (
    SECTION_TABLES,
    TABLES,
    Proposal,
    PublicRow,
    PublicSnapshot,
    build_proposals,
    kind_for_machine_type,
    link_table_allowed,
    normalize_legal_name,
    public_code,
)
from cost.v2.schemas import SECTION_SCHEMAS

# --- Данные §13 -------------------------------------------------------------
# Контрагент записан полным юридическим именем, а объект ссылается на него
# кратким и в других кавычках — ради этого случая и нужна нормализация.
COUNTERPARTIES = [
    {
        "id": 1,
        "full_name": 'Акционерное общество "Теплогорский карьер"',
        "short_name": 'АО "Теплогорский карьер"',
        "inn": "6608002092",
        "is_client": True,
        "is_supplier": False,
        "is_active": True,
    },
    {
        "id": 2,
        "full_name": 'Общество с ограниченной ответственностью "ПОМБУР"',
        "short_name": 'ООО "ПОМБУР"',
        "inn": "7203270545",
        "is_client": False,
        "is_supplier": True,
        "is_active": True,
    },
]

SITES = [
    {
        "id": 1,
        "full_name": "Ломоватский карьер",
        "short_name": "ЛОМ",
        "client_legal_name": "АО «Теплогорский карьер»",
        "mineral_type": "неруудные материалы",
        "is_active": True,
    },
    {
        "id": 2,
        "full_name": "Центральный склад ТМЦ",
        "short_name": "ЦСТ",
        "client_legal_name": 'ООО "Директ-Склад"',
        "mineral_type": None,
        "is_active": True,
    },
]

MACHINE_TYPES = [{"id": 1, "name": "Самосвал"}]

EQUIPMENT_MODELS = [
    {"id": 1, "machine_type_id": 1, "brand": "КамАЗ", "model_name": "65115"}
]

EQUIPMENT_UNITS = [
    {
        "id": 1,
        "model_id": 1,
        "internal_id": "С-01",
        "serial_number": "SN-65115-0001",
        "status": "Списано",
        "current_site_id": 1,
    }
]

INITIATING_DEVICE_TYPES = [
    {"id": 1, "name": "ЭД-1-Н", "description": "Электродетонатор непредохранительный"},
    {"id": 2, "name": "СИНВ-Ш", "description": "Система инициирования неэлектрическая"},
]

# У ЭД серия нестандартная, у СИНВ — стандартная: замедление получает только СИНВ.
DELAY_SERIES = [
    {"id": 1, "device_type_id": 1, "delay_ms": 500, "is_standard": False},
    {"id": 2, "device_type_id": 2, "delay_ms": 25, "is_standard": True},
]

TOOL_TYPES = [
    {
        "id": 1,
        "name": "Долото шарошечное 152",
        "expected_lifetime_meters": Decimal("600"),
        "description": "Шарошечное долото для буровой установки JK830-2",
        "diameter": Decimal("152"),
        "thread_type": "З-76",
    }
]

CONTRACTS = [{"id": 1, "counterparty_id": 2}]

PURCHASE_SPECS = [
    {
        "id": 1,
        "contract_id": 1,
        "spec_number": "СПЦ-2026-001",
        "spec_date": date(2026, 1, 20),
        "total_delivery_cost_no_vat": Decimal("131147.54"),
    }
]

SPEC_ITEMS = [
    {
        "id": 1,
        "spec_id": 1,
        "device_type_id": 1,
        "quantity_ordered": Decimal("2.52"),
        "price_per_unit_no_vat": Decimal("335162.90"),
        "conversion_factor": Decimal("1000"),
    },
    {
        "id": 2,
        "spec_id": 1,
        "device_type_id": 2,
        "quantity_ordered": Decimal("2.00"),
        "price_per_unit_no_vat": Decimal("239543.85"),
        "conversion_factor": Decimal("1000"),
    },
]

MATERIAL_PRICES = [
    {
        "id": 1,
        "contract_id": 1,
        "device_type_id": 1,
        "price_per_unit_base": Decimal("250000.00"),
        "unit_conversion_factor": Decimal("1000"),
        "valid_from": date(2026, 2, 1),
        "valid_to": date(2026, 12, 31),
    }
]

# Две покупки одного типа инструмента у одного поставщика: цену даёт поздняя.
TOOLS_INVENTORY = [
    {
        "id": 1,
        "tool_type_id": 1,
        "purchase_price": Decimal("38500"),
        "purchase_date": date(2026, 1, 25),
        "supplier_id": 2,
    },
    {
        "id": 2,
        "tool_type_id": 1,
        "purchase_price": Decimal("41000"),
        "purchase_date": date(2026, 3, 10),
        "supplier_id": 2,
    },
]


def make_snapshot(**overrides: list[dict]) -> PublicSnapshot:
    """Снимок §13; любую таблицу можно заменить через именованный аргумент."""

    tables: dict[str, list[dict]] = {
        "counterparties": COUNTERPARTIES,
        "sites": SITES,
        "machine_types": MACHINE_TYPES,
        "equipment_models": EQUIPMENT_MODELS,
        "equipment_units": EQUIPMENT_UNITS,
        "initiating_device_types": INITIATING_DEVICE_TYPES,
        "delay_series": DELAY_SERIES,
        "tool_types": TOOL_TYPES,
        "contracts": CONTRACTS,
        "explosive_purchase_specs": PURCHASE_SPECS,
        "explosive_spec_items": SPEC_ITEMS,
        "explosive_material_prices": MATERIAL_PRICES,
        "tools_inventory": TOOLS_INVENTORY,
    }
    tables.update(overrides)
    return PublicSnapshot(
        rows={
            table: tuple(PublicRow(table, int(row["id"]), dict(row)) for row in rows)
            for table, rows in tables.items()
        }
    )


def by_code(proposals: list[Proposal]) -> dict[str, Proposal]:
    return {proposal.code: proposal for proposal in proposals}


@pytest.fixture()
def proposals() -> list[Proposal]:
    return build_proposals(make_snapshot(), {}, {})


# --- Нормализация и коды ----------------------------------------------------


def test_normalize_legal_name_ignores_case_spaces_and_quotes() -> None:
    assert normalize_legal_name("АО «Теплогорский  карьер»") == normalize_legal_name(
        'ао "теплогорский карьер"'
    )


def test_normalize_legal_name_survives_empty_value() -> None:
    assert normalize_legal_name("") == ""


def test_public_code_uses_table_prefix() -> None:
    assert public_code("sites", 12) == "PUB_SITE_12"
    assert public_code("counterparties", 5) == "PUB_COUNTERPARTY_5"
    assert public_code("equipment_models", 2) == "PUB_MODEL_2"
    assert public_code("equipment_units", 1) == "PUB_UNIT_1"
    assert public_code("initiating_device_types", 3) == "PUB_IDT_3"
    assert public_code("tool_types", 4) == "PUB_TOOL_4"


def test_link_table_allowed_follows_the_section_catalogue() -> None:
    assert link_table_allowed("sites", "sites")
    assert link_table_allowed("equipment_types", "equipment_models")
    assert link_table_allowed("materials", "initiating_device_types")
    assert link_table_allowed("materials", "tool_types")
    assert link_table_allowed("material_prices", "tools_inventory")
    # Таблица другого раздела и раздел без таблиц журнала.
    assert not link_table_allowed("equipment_types", "sites")
    assert not link_table_allowed("rocks", "sites")


def test_every_section_table_is_read_from_the_journal() -> None:
    for tables in SECTION_TABLES.values():
        for table in tables:
            assert table in TABLES


def test_kind_for_machine_type_falls_back_to_other() -> None:
    assert kind_for_machine_type("Буровая установка") == "DRILL_RIG"
    assert kind_for_machine_type("Машина смесительно-зарядная") == "SZM"
    assert kind_for_machine_type("Экскаватор") == "TRACTOR"
    assert kind_for_machine_type("Самосвал") == "OTHER"
    assert kind_for_machine_type(None) == "OTHER"


# --- Контрагенты и объекты --------------------------------------------------


def test_counterparty_proposal_keeps_role_and_requisites(proposals) -> None:
    client = by_code(proposals)["PUB_COUNTERPARTY_1"]

    assert client.section == "counterparties"
    assert client.public_table == "counterparties"
    assert client.name == 'Акционерное общество "Теплогорский карьер"'
    assert client.payload["short_name"] == 'АО "Теплогорский карьер"'
    assert client.payload["inn"] == "6608002092"
    assert client.payload["role"] == "CUSTOMER"
    assert client.is_active is True
    assert "role" in client.shared_fields and "inn" in client.shared_fields


def test_supplier_gets_supplier_role(proposals) -> None:
    assert by_code(proposals)["PUB_COUNTERPARTY_2"].payload["role"] == "SUPPLIER"


def test_site_matches_customer_by_normalized_legal_name(proposals) -> None:
    lom = by_code(proposals)["PUB_SITE_1"]

    assert lom.section == "sites"
    assert lom.name == "Ломоватский карьер"
    assert lom.payload["customer_code"] == "PUB_COUNTERPARTY_1"
    assert "customer_legal_name" not in lom.payload
    assert lom.payload["short_name"] == "ЛОМ"
    assert lom.payload["mineral_type"] == "неруудные материалы"


def test_site_without_counterparty_keeps_legal_name_as_text(proposals) -> None:
    tsst = by_code(proposals)["PUB_SITE_2"]

    assert tsst.payload["customer_legal_name"] == 'ООО "Директ-Склад"'
    assert "customer_code" not in tsst.payload
    assert "mineral_type" not in tsst.payload


def test_existing_link_code_is_used_for_customer_reference() -> None:
    linked = build_proposals(make_snapshot(), {1: "TEPLOGORSK"}, {})

    assert by_code(linked)["TEPLOGORSK"].section == "counterparties"
    assert by_code(linked)["PUB_SITE_1"].payload["customer_code"] == "TEPLOGORSK"


def test_build_proposals_does_not_mutate_given_dictionaries() -> None:
    counterparty_codes: dict[int, str] = {}
    type_codes: dict[int, str] = {}

    build_proposals(make_snapshot(), counterparty_codes, type_codes)

    assert counterparty_codes == {}
    assert type_codes == {}


# --- Техника ----------------------------------------------------------------


def test_equipment_type_from_model_and_machine_type(proposals) -> None:
    model = by_code(proposals)["PUB_MODEL_1"]

    assert model.section == "equipment_types"
    assert model.name == "65115"
    assert model.payload["brand"] == "КамАЗ"
    assert model.payload["machine_type_name"] == "Самосвал"
    assert model.payload["kind"] == "OTHER"
    # kind ставится только при создании записи, поэтому в разницу не входит.
    assert "kind" not in model.shared_fields
    assert "brand" in model.shared_fields


def test_equipment_asset_is_deactivated_by_written_off_status(proposals) -> None:
    unit = by_code(proposals)["PUB_UNIT_1"]

    assert unit.section == "equipment_assets"
    assert unit.name == "С-01"
    assert unit.payload["inventory_number"] == "С-01"
    assert unit.payload["serial_number"] == "SN-65115-0001"
    assert unit.payload["equipment_type_code"] == "PUB_MODEL_1"
    assert unit.is_active is False
    assert "is_active" in unit.shared_fields


def test_equipment_asset_follows_linked_type_code() -> None:
    linked = build_proposals(make_snapshot(), {}, {1: "KAMAZ_65115"})

    assert by_code(linked)["PUB_UNIT_1"].payload["equipment_type_code"] == "KAMAZ_65115"


def test_equipment_asset_name_is_not_a_shared_field(proposals) -> None:
    # internal_id — инвентарный номер, а не имя: он задаёт name только при
    # создании записи из журнала, но не должен перетирать имя, выбранное
    # пользователем для уже связанной единицы техники (иначе пуш имени в
    # public и обратный маппинг зациклились бы).
    unit = by_code(proposals)["PUB_UNIT_1"]

    assert "name" not in unit.shared_fields


# --- Материалы --------------------------------------------------------------


def test_initiating_device_becomes_material_with_standard_delay(proposals) -> None:
    sinv = by_code(proposals)["PUB_IDT_2"]

    assert sinv.section == "materials"
    assert sinv.name == "СИНВ-Ш"
    assert sinv.comment == "Система инициирования неэлектрическая"
    assert sinv.payload["material_kind"] == "СИ"
    assert sinv.payload["storage_class"] == "NSI"
    assert sinv.payload["delay_ms"] == "25"


def test_initiating_device_without_standard_series_has_no_delay(proposals) -> None:
    ed = by_code(proposals)["PUB_IDT_1"]

    assert "delay_ms" not in ed.payload
    assert "delay_ms" in ed.shared_fields


def test_tool_type_becomes_drilling_tool_material(proposals) -> None:
    tool = by_code(proposals)["PUB_TOOL_1"]

    assert tool.section == "materials"
    assert tool.payload["material_kind"] == "Буровой инструмент"
    assert tool.payload["lifetime_m"] == "600"
    assert tool.payload["diameter_mm"] == "152"
    assert tool.payload["thread_type"] == "З-76"
    assert tool.comment == "Шарошечное долото для буровой установки JK830-2"


# --- Цены -------------------------------------------------------------------


def test_spec_item_price_and_delivery_share(proposals) -> None:
    # 335162.90 / 1000 = 335.16 ₽ за штуку; доля доставки —
    # 335162.90/1000 * 131147.54 / (2.52*335162.90 + 2.00*239543.85).
    first = by_code(proposals)["PRICE_PUB_SPEC_1"]
    second = by_code(proposals)["PRICE_PUB_SPEC_2"]

    assert first.section == "material_prices"
    assert first.payload["material_code"] == "PUB_IDT_1"
    assert first.payload["supplier_code"] == "PUB_COUNTERPARTY_2"
    assert first.payload["price_rub"] == "335.16"
    assert first.payload["delivery_rub"] == "33.21"
    assert first.valid_from == date(2026, 1, 20)
    assert second.payload["price_rub"] == "239.54"
    assert second.payload["delivery_rub"] == "23.73"


def test_spec_without_delivery_cost_gives_zero_delivery() -> None:
    specs = [dict(PURCHASE_SPECS[0], total_delivery_cost_no_vat=None)]
    built = build_proposals(make_snapshot(explosive_purchase_specs=specs), {}, {})

    assert by_code(built)["PRICE_PUB_SPEC_1"].payload["delivery_rub"] == "0.00"


def test_material_price_uses_unit_conversion_factor(proposals) -> None:
    price = by_code(proposals)["PRICE_PUB_EMP_1"]

    assert price.payload["material_code"] == "PUB_IDT_1"
    assert price.payload["price_rub"] == "250.00"
    assert price.payload["delivery_rub"] == "0.00"
    assert price.payload["supplier_code"] == "PUB_COUNTERPARTY_2"
    assert price.valid_from == date(2026, 2, 1)
    assert price.valid_to == date(2026, 12, 31)


def test_tools_inventory_price_takes_latest_purchase(proposals) -> None:
    codes = by_code(proposals)

    assert "PRICE_PUB_TOOL_1" not in codes
    price = codes["PRICE_PUB_TOOL_2"]
    assert price.payload["material_code"] == "PUB_TOOL_1"
    assert price.payload["price_rub"] == "41000.00"
    assert price.payload["supplier_code"] == "PUB_COUNTERPARTY_2"
    assert price.valid_from == date(2026, 3, 10)


def test_tools_inventory_ignores_purchases_without_price_or_date() -> None:
    rows = [dict(TOOLS_INVENTORY[0], purchase_price=None, purchase_date=None)]
    built = build_proposals(make_snapshot(tools_inventory=rows), {}, {})

    assert not [p for p in built if p.code.startswith("PRICE_PUB_TOOL")]


# --- Порядок и устойчивость -------------------------------------------------


def test_proposals_follow_foreign_key_order(proposals) -> None:
    sections = list(dict.fromkeys(proposal.section for proposal in proposals))

    assert sections == [
        "counterparties",
        "sites",
        "equipment_types",
        "equipment_assets",
        "materials",
        "material_prices",
    ]


def test_every_proposal_payload_matches_section_schema(proposals) -> None:
    # Предложение попадает прямо в черновик, поэтому payload обязан проходить
    # схему раздела: extra="forbid" поймает незнакомое поле журнала здесь, а
    # не при публикации ревизии.
    for proposal in proposals:
        SECTION_SCHEMAS[proposal.section].model_validate(proposal.payload)


def test_empty_snapshot_gives_no_proposals() -> None:
    assert build_proposals(PublicSnapshot(rows={}), {}, {}) == []


def test_snapshot_table_returns_empty_tuple_for_unknown_table() -> None:
    assert make_snapshot().table("нет такой таблицы") == ()


def test_static_reader_returns_given_snapshot() -> None:
    from cost.v2.public_sync.reader import StaticPublicReader

    snapshot = make_snapshot()

    assert StaticPublicReader(snapshot).read() is snapshot
