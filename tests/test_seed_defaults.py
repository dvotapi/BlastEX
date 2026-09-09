"""Эталонная ревизия: модель считает с первого дня, ничего не дублируя."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from cost.model.engine import compute_block_economics
from cost.v2.models import ReferenceItem
from cost.v2.references import default_reference_snapshot, has_validation_errors, validate_reference_sections
from cost.v2.seed_defaults import guess_length_m, guess_mass_kg, guess_role, seed_reference
from tests import model_fixtures as fx


def material(code: str, name: str, **payload) -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload={"unit": "KG", **payload})


IMPORTED_MATERIALS = (
    material("MAT_VV_EVERSIN", "ЭВВ Эверсин-100"),
    material("EXP_PVV_GRANULIT_RP", "Гранулит-РП"),
    material("MAT_NSI_90", 'НСИ "Rionel" MS-20-9 м', unit="PIECE"),
    material("MAT_NSI_120", "Устройство Искра-С-*-12", unit="PIECE"),
    material("PUB_IDT_2", "СИНВ-Ш", unit="PIECE"),
    material("MAT_SURFACE_NSI_4", "Устройство Искра-П-*-4", unit="PIECE"),
    material("MAT_START_NSI_200", "Устройство ИСКРА-СТАРТ-В-200", unit="PIECE"),
    material("MAT_SV_SFERIT_08", 'Детонатор промежуточный "Сферит ДП" - 60 / 0,8'),
    material("MAT_SV_DPU_PT600", "Детонатор промежуточный ДПУ-ПТ600"),
    material("PUB_IDT_1", "ЭД-1-Н", unit="PIECE"),
    material("PUB_TOOL_1", "Долото шарошечное 152", unit="PIECE"),
    material("MAT_MISC", "Ветошь", unit="KG"),
)


def imported_snapshot():
    """Как после импорта V1: станки без норм, машин нет, правил затрат нет."""

    base = default_reference_snapshot()
    rigs = (
        ReferenceItem(code="TYPE_JK_830_3", name="JK 830-3", payload={"kind": "DRILL_RIG", "fuel_l_per_h": "50"}),
        ReferenceItem(code="TYPE_ZEGA_D480A", name="ZEGA D480A", payload={"kind": "DRILL_RIG", "fuel_l_per_h": "55"}),
    )
    sections = dict(base.sections)
    sections.update(
        {
            "materials": IMPORTED_MATERIALS,
            "equipment_types": rigs,
            "equipment_assets": (
                ReferenceItem(code="RIG_JK_830_3", name="JK 830-3 инв.", payload={
                    "equipment_type_code": "TYPE_JK_830_3", "depreciation_per_shift_rub": "11854",
                }),
            ),
            "sites": fx.SITES,
            "rocks": fx.ROCKS,
            "production_units": fx.PRODUCTION_UNITS,
            "material_prices": (
                ReferenceItem(code="PR_EVERSIN", name="Цена", payload={"material_code": "MAT_VV_EVERSIN", "price_rub": "48.9"}),
                ReferenceItem(code="PR_SFERIT", name="Цена", payload={"material_code": "MAT_SV_SFERIT_08", "price_rub": "150"}),
                ReferenceItem(code="PR_NSI_120", name="Цена", payload={"material_code": "MAT_NSI_120", "price_rub": "1100"}),
                ReferenceItem(code="PR_SURFACE_4", name="Цена", payload={"material_code": "MAT_SURFACE_NSI_4", "price_rub": "214"}),
                ReferenceItem(code="PR_START_200", name="Цена", payload={"material_code": "MAT_START_NSI_200", "price_rub": "3210"}),
                ReferenceItem(code="PR_TOOL", name="Цена", payload={"material_code": "PUB_TOOL_1", "price_rub": "38500"}),
            ),
            "organization_rates": (
                ReferenceItem(code="RATES", name="Ставки", payload={"salary_basis": "GROSS", "per_diem_rub": "0", "lodging_rub": "0"}),
            ),
        }
    )
    return replace(base, revision_id="REV-IMPORTED", sections=sections)


def test_roles_lengths_and_masses_are_guessed_from_names() -> None:
    sections, report = seed_reference(imported_snapshot())
    roles = {item.code: item.payload.get("nomenclature_role") for item in sections["materials"]}

    assert roles["MAT_VV_EVERSIN"] == "EXPLOSIVE"
    assert roles["EXP_PVV_GRANULIT_RP"] == "EXPLOSIVE"
    assert roles["MAT_NSI_90"] == "NSI_DOWNHOLE"
    assert roles["MAT_NSI_120"] == "NSI_DOWNHOLE"
    assert roles["PUB_IDT_2"] == "NSI_DOWNHOLE"
    assert roles["MAT_SURFACE_NSI_4"] == "NSI_SURFACE"
    assert roles["MAT_START_NSI_200"] == "NSI_START"
    assert roles["MAT_SV_SFERIT_08"] == "BOOSTER"
    assert roles["PUB_IDT_1"] == "DETONATOR_ELECTRIC"
    assert roles["PUB_TOOL_1"] == "DRILL_TOOL"
    assert roles.get("MAT_MISC") in (None, "OTHER")

    payloads = {item.code: item.payload for item in sections["materials"]}
    assert payloads["MAT_NSI_90"]["length_m"] == "9"
    assert payloads["MAT_NSI_120"]["length_m"] == "12"
    assert payloads["MAT_SV_SFERIT_08"]["mass_kg"] == "0.8"
    assert payloads["MAT_SV_DPU_PT600"]["mass_kg"] == "0.6"
    assert len(report.roles) == 11


def test_guessers_do_not_invent_values() -> None:
    assert guess_role(material("X", "Ветошь")) is None
    assert guess_length_m(material("X", "НСИ без длины")) is None
    assert guess_mass_kg(material("X", "Детонатор промежуточный")) is None


def test_every_rig_gets_norms_and_an_asset_but_no_invented_condition() -> None:
    sections, report = seed_reference(imported_snapshot())

    rigs = {item.code: item.payload for item in sections["equipment_types"] if item.payload.get("kind") == "DRILL_RIG"}
    assert rigs["TYPE_ZEGA_D480A"]["norm_shifts_per_month"] == "40"
    assert rigs["TYPE_ZEGA_D480A"]["fuel_l_per_h"] == "55"  # своё значение не перезаписано
    # Ни JK 830-3, ни ZEGA D480A не JK830-2 — реальной нормы для них нет,
    # а придумывать её больше нельзя: условие бурения не заводится.
    conditions = {item.payload["equipment_type_code"]: item.payload for item in sections["drilling_conditions"]}
    assert conditions == {}
    assets = {item.payload["equipment_type_code"] for item in sections["equipment_assets"]}
    # У JK 830-3 основное средство уже было — второе не создаётся.
    assert assets == {"TYPE_JK_830_3", "TYPE_ZEGA_D480A", "SZM_12T", "TRUCK_3T", "TRUCK_EMULSION_20T"}
    assert set(report.machines) == {"SZM_12T", "TRUCK_3T", "TRUCK_EMULSION_20T"}


def test_only_jk830_2_gets_a_real_default_drilling_condition() -> None:
    """Единственная норма без риска соврать — паспортный эталон JK830-2."""

    snapshot = imported_snapshot()
    rig = ReferenceItem(code="PUB_MODEL_1", name="JK830-2", payload={"kind": "DRILL_RIG"})
    sections = {**snapshot.sections, "equipment_types": (*snapshot.sections["equipment_types"], rig)}

    sections, report = seed_reference(replace(snapshot, sections=sections))

    conditions = {item.payload["equipment_type_code"]: item.payload for item in sections["drilling_conditions"]}
    assert set(conditions) == {"PUB_MODEL_1"}
    assert conditions["PUB_MODEL_1"]["tech_speed_m_per_h"] == "12"
    assert conditions["PUB_MODEL_1"]["bit_life_m"] == "700"
    assert conditions["PUB_MODEL_1"]["bit_material_code"] == "PUB_TOOL_1"
    assert "COND_PUB_MODEL_1_DEFAULT" in report.conditions


def test_jk830_2_match_ignores_spacing_but_not_other_models() -> None:
    """«JK 830-2» и «JK830-2» — один станок; «JK830-20» — другой, не эталон."""

    snapshot = imported_snapshot()
    same_model = ReferenceItem(code="TYPE_JK_SPACED", name="JK 830-2", payload={"kind": "DRILL_RIG"})
    other_model = ReferenceItem(code="TYPE_JK_20", name="JK830-20", payload={"kind": "DRILL_RIG"})
    sections = {
        **snapshot.sections,
        "equipment_types": (*snapshot.sections["equipment_types"], same_model, other_model),
    }

    sections, _ = seed_reference(replace(snapshot, sections=sections))

    covered = {item.payload["equipment_type_code"] for item in sections["drilling_conditions"]}
    assert "TYPE_JK_SPACED" in covered
    assert "TYPE_JK_20" not in covered


def test_logistics_rules_ppe_and_per_diem_are_added_once() -> None:
    first, _ = seed_reference(imported_snapshot())
    again = replace(imported_snapshot(), sections={k: tuple(v) for k, v in first.items()})
    second, report = seed_reference(again)

    assert {item.code for item in first["cost_rules"]} >= {"RULE_VM_DELIVERY", "RULE_STEMMING"}
    assert all(item.payload["cost_item_code"] in {i.code for i in first["cost_items"]} for item in first["cost_rules"])
    assert [item.code for item in first["unit_fixed_costs"]].count("UNIT_PPE") == 1
    assert first["organization_rates"][0].payload["per_diem_rub"] == "700"
    assert first["organization_rates"][0].payload["salary_basis"] == "GROSS"
    assert report.to_dict() == {key: [] for key in report.to_dict()}
    assert [i.code for i in second["cost_rules"]] == [i.code for i in first["cost_rules"]]


def test_a_rule_published_before_the_section_field_gets_one() -> None:
    """Ревизия старше поля: доставка ВМ не должна остаться в общепроизводственных."""

    base = imported_snapshot()
    old_rules = (
        ReferenceItem(
            code="RULE_VM_DELIVERY",
            name="Доставка ВМ со склада на объект",
            payload={
                "operation_code": "VM_DELIVERY_SITE",
                "cost_item_code": "VM_DELIVERY",
                "behavior_type": "VARIABLE",
                "cost_layer": "variable",
                "driver": "vm_tkm",
                "rate_rub": "25",
            },
        ),
        ReferenceItem(
            code="RULE_HAND_MADE",
            name="Правило сметчика",
            payload={
                "operation_code": "STEMMING",
                "cost_item_code": "VM_DELIVERY",
                "behavior_type": "FIXED",
                "cost_layer": "variable",
                "fixed_rub": "1000",
            },
        ),
    )
    sections = {**base.sections, "cost_rules": old_rules}
    sections["cost_items"] = (
        *sections.get("cost_items", ()),
        ReferenceItem(code="VM_DELIVERY", name="Доставка ВМ", payload={"kind": "logistics"}),
    )

    seeded, report = seed_reference(replace(base, sections=sections))

    rules = {item.code: item.payload for item in seeded["cost_rules"]}
    # Правило из списка сида знает свой раздел, чужое — общепроизводственное.
    assert rules["RULE_VM_DELIVERY"]["estimate_section"] == "VM_LOGISTICS"
    assert rules["RULE_HAND_MADE"]["estimate_section"] == "OVERHEAD"
    # Ставку, которую правил сметчик, дозаполнение не трогает.
    assert rules["RULE_VM_DELIVERY"]["rate_rub"] == "25"
    # Отчёт называет и дозаполненные правила, и созданные.
    assert {"RULE_VM_DELIVERY", "RULE_HAND_MADE"} <= set(report.rules)

    again, second = seed_reference(
        replace(base, sections={**sections, "cost_rules": tuple(seeded["cost_rules"])})
    )
    assert second.rules == []


def test_seeded_revision_is_valid_and_the_model_computes_without_reference_gaps() -> None:
    # Без реальной нормы (не JK830-2) станок так и остаётся с пробелом в
    # условиях бурения — «без пробелов» это гарантия только для JK830-2.
    base = imported_snapshot()
    rig = ReferenceItem(code="PUB_MODEL_1", name="JK830-2", payload={"kind": "DRILL_RIG"})
    base = replace(base, sections={**base.sections, "equipment_types": (*base.sections["equipment_types"], rig)})
    sections, _ = seed_reference(base)
    assert not has_validation_errors(validate_reference_sections(sections))

    references = replace(base, sections={k: tuple(v) for k, v in sections.items()})
    result = compute_block_economics(
        fx.snapshot(),
        fx.parameters(
            rig_code="PUB_MODEL_1",
            rig_plan_shifts=None,
            szm_code="SZM_12T",
            delivery_truck_code="TRUCK_3T",
            emulsion_truck_code="TRUCK_EMULSION_20T",
            crew=(),
            nomenclature={
                "EXPLOSIVE": "MAT_VV_EVERSIN",
                "BOOSTER": "MAT_SV_SFERIT_08",
                "NSI_DOWNHOLE": "MAT_NSI_120",
                "NSI_SURFACE": "MAT_SURFACE_NSI_4",
                "NSI_START": "MAT_START_NSI_200",
            },
        ),
        references,
    )

    codes = {line.cost_item_code for line in result.lines}
    # Расход топлива на метр — не паспортная величина JK830-2, которую нашли
    # в документации: без неё DRILL_FUEL не считается (fuel_l_per_m == 0).
    assert {"DRILL_TOOLING", "DRILL_DEPRECIATION", "SZM_DEPRECIATION", "EMULSION_TRUCK_DEPRECIATION"} <= codes
    assert {"VM_DELIVERY", "STEMMING", "UNIT_UNIT_PPE"} & codes
    gaps = [w for w in result.warnings if "нет условий бурения" in w or "не заведено основное средство" in w or "не задан" in w.lower()]
    assert gaps == [], gaps
    assert result.price_per_m3["full"] > Decimal("0")


def test_asset_without_cost_is_filled_in_not_skipped() -> None:
    """Единица из журнала приходит с инвентарным номером, но без стоимости.

    Пропустить её значит оставить амортизацию нулевой навсегда: запись есть,
    и модель считает технику обеспеченной.
    """

    snapshot = replace(
        imported_snapshot(),
        sections={
            **imported_snapshot().sections,
            "equipment_assets": (
                ReferenceItem(
                    code="PUB_UNIT_1",
                    name="JK830-2 Б-01",
                    payload={"equipment_type_code": "TYPE_JK_830_3", "inventory_number": "Б-01"},
                ),
            ),
        },
    )
    sections, report = seed_reference(snapshot)

    asset = next(item for item in sections["equipment_assets"] if item.code == "PUB_UNIT_1")
    assert asset.payload["initial_cost_rub"] == "20000000"
    assert asset.payload["useful_life_months"] == "84"
    assert asset.payload["inventory_number"] == "Б-01"
    assert "уточните" in asset.comment.lower()
    assert "PUB_UNIT_1" in report.assets
    # Второй прогон ничего не меняет.
    again, second = seed_reference(replace(snapshot, sections={k: tuple(v) for k, v in sections.items()}))
    assert second.assets == []


def test_asset_with_its_own_cost_is_left_alone() -> None:
    snapshot = replace(
        imported_snapshot(),
        sections={
            **imported_snapshot().sections,
            "equipment_assets": (
                ReferenceItem(
                    code="RIG_OWN",
                    name="Свой станок",
                    payload={
                        "equipment_type_code": "TYPE_JK_830_3",
                        "initial_cost_rub": "21906500",
                        "useful_life_months": "84",
                    },
                ),
            ),
        },
    )
    sections, report = seed_reference(snapshot)

    asset = next(item for item in sections["equipment_assets"] if item.code == "RIG_OWN")
    assert asset.payload["initial_cost_rub"] == "21906500"
    assert report.assets == ["ASSET_TYPE_ZEGA_D480A", "ASSET_SZM_12T", "ASSET_TRUCK_3T", "ASSET_TRUCK_EMULSION_20T"]


def test_asset_with_per_shift_depreciation_only_is_left_alone() -> None:
    """Записи Cost V1 хранят амортизацию за смену — этого модели достаточно."""

    snapshot = replace(
        imported_snapshot(),
        sections={
            **imported_snapshot().sections,
            "equipment_assets": (
                ReferenceItem(
                    code="RIG_V1",
                    name="Станок из V1",
                    payload={
                        "equipment_type_code": "TYPE_JK_830_3",
                        "depreciation_per_shift_rub": "11854",
                    },
                ),
            ),
        },
    )
    sections, _ = seed_reference(snapshot)

    asset = next(item for item in sections["equipment_assets"] if item.code == "RIG_V1")
    assert "initial_cost_rub" not in asset.payload


def test_inactive_condition_does_not_count_as_coverage() -> None:
    """Модель ищет условия среди активных: деактивированное — то же, что никакого."""

    base = imported_snapshot()
    rig = ReferenceItem(code="PUB_MODEL_1", name="JK830-2", payload={"kind": "DRILL_RIG"})
    retired = ReferenceItem(
        code="COND_OLD",
        name="Старая норма",
        payload={"equipment_type_code": "PUB_MODEL_1", "tech_speed_m_per_h": "9"},
        is_active=False,
    )
    snapshot = replace(
        base,
        sections={
            **base.sections,
            "equipment_types": (*base.sections["equipment_types"], rig),
            "drilling_conditions": (retired,),
        },
    )

    sections, report = seed_reference(snapshot)

    rigs = {
        item.payload["equipment_type_code"]
        for item in sections["drilling_conditions"]
        if item.is_active
    }
    assert rigs == {"PUB_MODEL_1"}
    assert "COND_PUB_MODEL_1_DEFAULT" in report.conditions


def test_inactive_asset_does_not_count_as_coverage() -> None:
    """Списанная единица не даёт амортизации: нужна активная замена."""

    retired = ReferenceItem(
        code="ASSET_OLD",
        name="Списанный станок",
        payload={
            "equipment_type_code": "TYPE_JK_830_3",
            "initial_cost_rub": "21906500",
            "useful_life_months": "84",
        },
        is_active=False,
    )
    snapshot = replace(
        imported_snapshot(),
        sections={**imported_snapshot().sections, "equipment_assets": (retired,)},
    )

    sections, report = seed_reference(snapshot)

    active = {
        item.payload["equipment_type_code"] for item in sections["equipment_assets"] if item.is_active
    }
    assert "TYPE_JK_830_3" in active
    assert "ASSET_TYPE_JK_830_3" in report.assets
    # Списанную запись не трогаем: её стоимость — история, а не пустое место.
    old = next(item for item in sections["equipment_assets"] if item.code == "ASSET_OLD")
    assert not old.is_active and old.payload["initial_cost_rub"] == "21906500"


def test_partially_configured_rig_gets_the_missing_rates() -> None:
    """У станка есть норма смен, но нет ставок ТОиР: их и надо дозаполнить."""

    partial = ReferenceItem(
        code="TYPE_PARTIAL",
        name="Станок с частью норм",
        payload={"kind": "DRILL_RIG", "norm_shifts_per_month": "30", "maintenance_rub_per_shift": "900"},
    )
    snapshot = replace(
        imported_snapshot(),
        sections={**imported_snapshot().sections, "equipment_types": (partial,)},
    )

    sections, report = seed_reference(snapshot)

    payload = next(item for item in sections["equipment_types"] if item.code == "TYPE_PARTIAL").payload
    assert payload["norm_shifts_per_month"] == "30"  # своё не трогаем
    assert payload["maintenance_rub_per_shift"] == "900"  # и заполненную ставку тоже
    assert payload["spare_parts_rub_per_shift"] == "2750"
    assert payload["inspection_rub_per_shift"] == "200"
    assert payload["maintenance_ratio"] == "0.14"
    assert "TYPE_PARTIAL" in report.rigs_normed


def test_role_is_guessed_by_name_before_code() -> None:
    """Название точнее кода: «НСИ Искра-П» — поверхностное, хотя код как у скважинных.

    Данные прода: позиция заведена под кодом MAT_NSI_ISKRA_P_50, а по смыслу
    это то же устройство, что MAT_SURFACE_NSI_5.
    """

    surface = ReferenceItem(code="MAT_NSI_ISKRA_P_50", name="НСИ Искра-П-*-5", payload={})
    downhole = ReferenceItem(code="MAT_NSI_ISKRA_S_120", name="НСИ Искра-С-*-12", payload={})

    assert guess_role(surface) == "NSI_SURFACE"
    assert guess_role(downhole) == "NSI_DOWNHOLE"


def test_length_is_read_from_the_code_tail_in_decimetres() -> None:
    """У «Искра-С» длины в названии нет, а хвост кода её несёт."""

    assert guess_length_m(ReferenceItem(code="MAT_NSI_ISKRA_S_85", name="НСИ Искра-С-*-8,5", payload={})) == Decimal("8.5")
    assert guess_length_m(ReferenceItem(code="MAT_NSI_ISKRA_S_120", name="НСИ Искра-С-*-12", payload={})) == Decimal("12")
    # Название важнее кода: у этой позиции они расходятся (код 80, имя 18 м).
    assert guess_length_m(ReferenceItem(code="MAT_NSI_RIONEL_S_80", name='НСИ "Rionel" MS-20-18 м', payload={})) == Decimal("18")


def test_explicit_placement_words_beat_the_generic_nsi_rule() -> None:
    """«Поверхностное» и «скважинное» в названии сильнее общего слова «НСИ»."""

    surface = ReferenceItem(code="MAT_X1", name="НСИ поверхностное 5", payload={})
    downhole = ReferenceItem(code="MAT_X2", name="Скважинное НСИ 9 м", payload={})

    assert guess_role(surface) == "NSI_SURFACE"
    assert guess_role(downhole) == "NSI_DOWNHOLE"


def test_delay_marking_in_the_code_is_not_taken_for_a_length() -> None:
    """Хвост кода бывает интервалом замедления, а не дециметрами длины.

    «СИНВ-Ш 500» — 500 мс; принять это за 50 м значит подсунуть автоподбору
    самое «длинное» изделие в справочнике.
    """

    delay = ReferenceItem(code="MAT_NSI_SINV_SH_500", name="СИНВ-Ш 500", payload={})
    short_delay = ReferenceItem(code="MAT_NSI_RIONEL_MS_20", name="НСИ Rionel MS-20", payload={})

    assert guess_length_m(delay) is None
    assert guess_length_m(short_delay) is None
    # Правдоподобные длины по-прежнему читаются.
    assert guess_length_m(ReferenceItem(code="MAT_NSI_ISKRA_S_85", name="НСИ Искра-С", payload={})) == Decimal("8.5")
    assert guess_length_m(ReferenceItem(code="MAT_NSI_180", name="НСИ 18", payload={})) == Decimal("18")
