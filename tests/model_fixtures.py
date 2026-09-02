"""Справочники и паспорт блока для тестов модели себестоимости.

Числа взяты из ADR-001 (разбор сметы): скорость 12 м/ч, смена 11 ч,
непроизводительный час, станок 40 смен в месяц, взрывник 55 000 ₽ при 10
взрывах в месяц. Это делает тесты читаемыми против исходной методики.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, Mapping

from cost.model.inputs import CrewMember, ModelParameters
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import default_reference_snapshot


def item(code: str, name: str, payload: Mapping[str, Any]) -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload=dict(payload), source="test")


PRODUCTION_UNITS = (item("UNIT_1", "Юнит Пермь", {"plan_volume_m3": "600000", "region": "Пермский край"}),)

ROCKS = (item("ROCK_GRANITE", "Гранит f12", {"density_t_m3": "2.7", "hardness_f": "12"}),)

SITES = (
    item(
        "SITE_MAIN",
        "Карьер Ломовской",
        {
            "production_unit_code": "UNIT_1",
            "rock_code": "ROCK_GRANITE",
            "distance_from_base_km": "220",
            "distance_from_warehouse_km": "270",
            "diesel_price_ton_rub": "52200",
            "blocks_per_mobilization": "6",
            "mobilization_rate_rub_per_km": "450",
            "mobilization_km": "220",
            "is_remote": True,
        },
    ),
)

MATERIALS = (
    item("MAT_BIT", "Коронка", {"unit": "PIECE", "material_kind": "ТМЦ", "storage_class": "NONE"}),
    item("MAT_HAMMER", "ППУ", {"unit": "PIECE", "material_kind": "ТМЦ", "storage_class": "NONE"}),
    item("MAT_RODS", "Штанги", {"unit": "PIECE", "material_kind": "ТМЦ", "storage_class": "NONE"}),
    item("MAT_CASING", "Обсадная труба", {"unit": "M", "material_kind": "ТМЦ", "storage_class": "NONE"}),
    item("MAT_ANFO", "Гранулит", {"unit": "KG", "material_kind": "ВВ", "storage_class": "BULK"}),
    item("MAT_NSI", "НСИ скважинное", {"unit": "PIECE", "material_kind": "СИ", "storage_class": "NSI"}),
)

MATERIAL_PRICES = (
    item("PR_BIT", "Коронка", {"material_code": "MAT_BIT", "price_rub": "35000"}),
    item("PR_HAMMER", "ППУ", {"material_code": "MAT_HAMMER", "price_rub": "210000"}),
    item("PR_RODS", "Штанги", {"material_code": "MAT_RODS", "price_rub": "150000"}),
    item("PR_CASING", "Обсадная труба", {"material_code": "MAT_CASING", "price_rub": "1200"}),
    item("PR_ANFO", "Гранулит", {"material_code": "MAT_ANFO", "price_rub": "45"}),
    item("PR_NSI", "НСИ скважинное", {"material_code": "MAT_NSI", "price_rub": "900"}),
)

EQUIPMENT_TYPES = (
    item(
        "RIG_JK830",
        "Буровой станок JK830",
        {
            "kind": "DRILL_RIG",
            "operation_code": "PRODUCTION_DRILLING",
            "norm_shifts_per_month": "40",
            "maintenance_ratio": "0.14",
            "maintenance_mode": "PER_SHIFT",
            "maintenance_rub_per_shift": "750",
            "spare_parts_rub_per_shift": "2750",
            "inspection_rub_per_shift": "200",
            "medical_rub_per_shift": "200",
            "fuel_l_per_h": "50",
        },
    ),
    item(
        "SZM_12T",
        "СЗМ 12 т",
        {
            "kind": "SZM",
            "operation_code": "BULK_CHARGING_SZM",
            "norm_shifts_per_month": "20",
            "maintenance_mode": "PER_SHIFT",
            "maintenance_rub_per_shift": "500",
            "inspection_rub_per_shift": "200",
            "medical_rub_per_shift": "200",
            "fuel_l_per_h": "10",
            "capacity": "12000",
            "capacity_unit": "KG",
        },
    ),
    item(
        "TRUCK_3T",
        "Доставщик ВМ 3 т",
        {
            "kind": "HAZMAT_TRUCK",
            "operation_code": "VM_DELIVERY_SITE",
            "norm_shifts_per_month": "20",
            "maintenance_mode": "PER_SHIFT",
            "maintenance_rub_per_shift": "300",
            "fuel_l_per_km": "0.45",
            "capacity": "3000",
            "capacity_unit": "KG",
        },
    ),
)

EQUIPMENT_ASSETS = (
    item(
        "ASSET_RIG",
        "JK830 инв. 001",
        {
            "equipment_type_code": "RIG_JK830",
            "production_unit_code": "UNIT_1",
            "initial_cost_rub": "28450000",
            "useful_life_months": "60",
            "insurance_monthly_rub": "500",
        },
    ),
    item(
        "ASSET_SZM",
        "СЗМ инв. 002",
        {
            "equipment_type_code": "SZM_12T",
            "initial_cost_rub": "12000000",
            "useful_life_months": "60",
            "insurance_monthly_rub": "500",
        },
    ),
    item(
        "ASSET_TRUCK",
        "Доставщик инв. 003",
        {
            "equipment_type_code": "TRUCK_3T",
            "initial_cost_rub": "6000000",
            "useful_life_months": "60",
            "insurance_monthly_rub": "500",
        },
    ),
)

DRILLING_CONDITIONS = (
    item(
        "COND_GRANITE",
        "JK830 по граниту",
        {
            "equipment_type_code": "RIG_JK830",
            "rock_code": "ROCK_GRANITE",
            "tech_speed_m_per_h": "12",
            "unproductive_h_per_shift": "1",
            "fuel_l_per_m": "4.2",
            "bit_life_m": "700",
            "hammer_life_m": "7000",
            "rods_life_m": "15000",
            "casing_m_per_m": "0.03",
            "bit_material_code": "MAT_BIT",
            "hammer_material_code": "MAT_HAMMER",
            "rods_material_code": "MAT_RODS",
            "casing_material_code": "MAT_CASING",
        },
    ),
    item(
        "COND_DEFAULT",
        "JK830 по умолчанию",
        {
            "equipment_type_code": "RIG_JK830",
            "tech_speed_m_per_h": "10",
            "unproductive_h_per_shift": "1",
            "fuel_l_per_m": "4.5",
            "bit_life_m": "600",
            "bit_material_code": "MAT_BIT",
        },
    ),
)

POSITIONS = (
    item(
        "POS_DRILLER",
        "Бурильщик",
        {
            "category": "DIRECT",
            "operation_code": "PRODUCTION_DRILLING",
            "norm_shifts_per_month": "15",
            "piece_driver": "drilling_m",
            "piece_unit": "1",
            "per_diem_applies": True,
        },
    ),
    item(
        "POS_BLASTER",
        "Взрывник",
        {
            "category": "DIRECT",
            "operation_code": "BLAST_EXECUTION",
            "norm_shifts_per_month": "21",
            "norm_operations_per_month": "10",
            "piece_driver": "rock_volume_m3",
            "piece_unit": "1000",
            "per_diem_applies": True,
        },
    ),
    item(
        "POS_SZM_DRIVER",
        "Водитель-оператор СЗМ",
        {
            "category": "DIRECT",
            "operation_code": "BULK_CHARGING_SZM",
            "norm_shifts_per_month": "20",
            "piece_driver": "explosive_kg",
            "piece_unit": "1000",
        },
    ),
    item(
        "POS_WAREHOUSE_HEAD",
        "Заведующий складом",
        {"category": "INDIRECT", "norm_shifts_per_month": "21"},
    ),
)

LABOR_RATES = (
    item("LR_DRILLER", "Бурильщик", {"position_code": "POS_DRILLER", "fixed_monthly_rub": "60000", "piece_rate_rub": "150"}),
    item("LR_BLASTER", "Взрывник", {"position_code": "POS_BLASTER", "fixed_monthly_rub": "55000", "piece_rate_rub": "700"}),
    item("LR_SZM", "Водитель СЗМ", {"position_code": "POS_SZM_DRIVER", "fixed_monthly_rub": "50000", "piece_rate_rub": "200"}),
    item("LR_WH_HEAD", "Заведующий складом", {"position_code": "POS_WAREHOUSE_HEAD", "fixed_monthly_rub": "40000"}),
)

CREW_TEMPLATES = (
    item(
        "CREW_DRILL_AND_BLAST",
        "Бригада полного комплекса",
        {
            "package_code": "DRILL_AND_BLAST",
            "members": [
                {"position_code": "POS_DRILLER", "headcount": "0"},
                {"position_code": "POS_BLASTER", "headcount": "2"},
                {"position_code": "POS_SZM_DRIVER", "headcount": "1"},
            ],
        },
    ),
)

UNIT_FIXED_COSTS = (
    item(
        "UFC_BASE",
        "Содержание базы",
        {"production_unit_code": "UNIT_1", "scope": "UNIT", "category": "FACILITY", "monthly_rub": "400000"},
    ),
    item(
        "UFC_WH_HEAD",
        "Заведующий складом",
        {
            "production_unit_code": "UNIT_1",
            "scope": "UNIT",
            "category": "INDIRECT_LABOR",
            "position_code": "POS_WAREHOUSE_HEAD",
            "headcount": "1",
        },
    ),
)

WAREHOUSE_POOL = item(
    "WAREHOUSE_AREA",
    "Аренда склада ВМ",
    {
        "unit": "M2",
        "resource_kind": "STORAGE_AREA",
        "capacity_unit": "m2",
        "monthly_capacity": "10",
        "fixed_cost_rub": "83333",
        "step_capacity": "1",
        "step_cost_rub": "8333",
        "capacity_mode": "RENT",
        "consumption_norms": [
            {"driver": "downhole_nsi", "units_per_capacity": "300"},
            {"driver": "cartridge_kg", "units_per_capacity": "220"},
        ],
    },
)

COST_RULES = (
    item(
        "RULE_ANFO",
        "Гранулит на блок",
        {
            "operation_code": "EVV_MANUFACTURE_ON_SITE",
            "cost_item_code": "MATERIAL_EXPLOSIVE",
            "behavior_type": "VARIABLE",
            "cost_layer": "variable",
            "driver": "explosive_kg",
            "rate_rub": "45",
        },
    ),
    item(
        "RULE_NSI",
        "НСИ скважинное",
        {
            "operation_code": "PRIMER_ASSEMBLY",
            "cost_item_code": "MATERIAL_NSI",
            "behavior_type": "VARIABLE",
            "cost_layer": "variable",
            "driver": "downhole_nsi",
            "rate_rub": "900",
        },
    ),
    item(
        "RULE_DELIVERY",
        "Доставка ВМ на объект",
        {
            "operation_code": "VM_DELIVERY_SITE",
            "cost_item_code": "VM_DELIVERY",
            "behavior_type": "VARIABLE",
            "cost_layer": "variable",
            "driver": "vm_tkm",
            "rate_rub": "25",
        },
    ),
)

SUBCONTRACT_RATES = (
    item(
        "SUB_DRILLING",
        "Субподряд бурения",
        {"operation_code": "PRODUCTION_DRILLING", "unit": "M", "rate_rub": "900"},
    ),
)


def references(**overrides: Any) -> ReferenceSnapshot:
    """Снимок справочников для тестов; любой раздел можно подменить."""

    base = default_reference_snapshot()
    sections = dict(base.sections)
    sections.update(
        {
            "production_units": PRODUCTION_UNITS,
            "rocks": ROCKS,
            "sites": SITES,
            "materials": MATERIALS,
            "material_prices": MATERIAL_PRICES,
            "equipment_types": EQUIPMENT_TYPES,
            "equipment_assets": EQUIPMENT_ASSETS,
            "drilling_conditions": DRILLING_CONDITIONS,
            "positions": POSITIONS,
            "labor_rates": LABOR_RATES,
            "crew_templates": CREW_TEMPLATES,
            "unit_fixed_costs": UNIT_FIXED_COSTS,
            "cost_rules": COST_RULES,
            "subcontract_rates": SUBCONTRACT_RATES,
            "resource_pools": (*base.sections["resource_pools"], WAREHOUSE_POOL),
        }
    )
    sections.update(overrides)
    return replace(base, revision_id="REV-TEST", sections=sections)


def physical(**overrides: Any) -> dict[str, Decimal]:
    """Драйверы паспорта: блок 60 000 м³ при выходе 4,3 м³ с погонного метра."""

    values: dict[str, Decimal] = {
        "rock_volume_m3": Decimal("60000"),
        "drilling_m": Decimal("13953.488372"),
        "explosive_kg": Decimal("42000"),
        "bulk_kg": Decimal("42000"),
        "cartridge_kg": Decimal("0"),
        "holes": Decimal("1224"),
        "downhole_nsi": Decimal("1224"),
        "surface_nsi": Decimal("1224"),
        "intermediate_detonators": Decimal("1224"),
        "boosters": Decimal("1224"),
        "nsi_length_m": Decimal("14688"),
        "start_nsi": Decimal("2"),
        "blasts": Decimal("1"),
    }
    values.update({key: Decimal(str(value)) for key, value in overrides.items()})
    return values


def parameters(**overrides: Any) -> ModelParameters:
    defaults: dict[str, Any] = {
        "package_code": "DRILL_AND_BLAST",
        "site_code": "SITE_MAIN",
        "reference_revision_id": "REV-TEST",
        "unit_plan_volume_m3": Decimal("600000"),
        "rig_code": "RIG_JK830",
        "rig_plan_shifts": Decimal("40"),
        "szm_code": "SZM_12T",
        "delivery_truck_code": "TRUCK_3T",
        "crew": (
            CrewMember("POS_DRILLER", Decimal("0")),
            CrewMember("POS_BLASTER", Decimal("2")),
            CrewMember("POS_SZM_DRIVER", Decimal("1")),
        ),
    }
    defaults.update(overrides)
    return ModelParameters(**defaults)


def snapshot(**overrides: Any) -> dict[str, Any]:
    return {"physical": physical(**overrides), "lineage": {}}
