"""Реестр схем payload по разделам справочников.

`SECTION_SCHEMAS` — единственное место, где раздел связан со своей схемой.
Валидация публикации и эндпоинт `/references/schema` берут поля отсюда, поэтому
добавление раздела сводится к одной строке здесь и записи в
`REFERENCE_SECTION_DEFINITIONS`.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from cost.v2.schemas.base import ReferencePayload
from cost.v2.schemas.costs import (
    AllocationRulePayload,
    CostCenterPayload,
    CostItemPayload,
    CostRulePayload,
    UnitFixedCostPayload,
)
from cost.v2.schemas.equipment import (
    DrillingConditionPayload,
    EquipmentAssetPayload,
    EquipmentTypePayload,
    ResourceNormPayload,
    ResourcePoolPayload,
)
from cost.v2.schemas.labor import CrewTemplatePayload, LaborRatePayload, PositionPayload
from cost.v2.schemas.materials import (
    MaterialLossNormPayload,
    MaterialPayload,
    MaterialPricePayload,
)
from cost.v2.schemas.misc import (
    BasePayload,
    BenchSurfaceConditionPayload,
    BlastDesignParameterPayload,
    MarketPricePayload,
    OperationPayload,
    RockPayload,
    RoutePayload,
    SiteInfrastructurePayload,
    StakeoutModePayload,
    SubcontractRatePayload,
    UnitPayload,
    WarehousePayload,
    WorkPackagePayload,
)
from cost.v2.schemas.organization import (
    CounterpartyPayload,
    OrganizationRatesPayload,
    ProductionUnitPayload,
    SitePayload,
)

__all__ = [
    "SECTION_SCHEMAS",
    "section_schema",
    "section_json_schema",
    "section_fieldsets",
    "referenced_sections",
]


# Группировка полей в форме записи. Заведена только там, где полей много и
# порядок сам по себе ничего не объясняет; остальные разделы рисуются одним
# набором в порядке объявления схемы.
SECTION_FIELDSETS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "positions": (
        ("Роль", ("category", "operation_code")),
        ("Нормативы", ("norm_shifts_per_month", "norm_operations_per_month")),
        ("Сдельная часть", ("piece_driver", "piece_unit")),
        ("Прочее", ("per_diem_applies",)),
    ),
    "labor_rates": (
        ("Должность", ("position_code", "condition_code")),
        ("Постоянная часть", ("fixed_monthly_rub",)),
        ("Сдельная часть", ("piece_rate_rub",)),
    ),
    "organization_rates": (
        ("Налоги и взносы", (
            "income_tax_rate", "social_contribution_rate", "injury_insurance_rate",
            "vacation_reserve_rate", "salary_basis",
        )),
        ("Надбавки", ("overhead_rate", "target_margin_rate", "vat_rate")),
        ("Вахта и смена", ("per_diem_rub", "lodging_rub", "shift_hours")),
    ),
    "equipment_types": (
        ("Вид и загрузка", ("kind", "operation_code", "norm_shifts_per_month")),
        ("ТОиР и запчасти", (
            "maintenance_mode", "maintenance_ratio", "maintenance_rub_per_shift",
            "maintenance_monthly_rub", "spare_parts_rub_per_shift",
        )),
        ("Допуск к работе", ("inspection_rub_per_shift", "medical_rub_per_shift")),
        ("Топливо и ёмкость", ("fuel_l_per_h", "fuel_l_per_km", "capacity", "capacity_unit")),
    ),
    "drilling_conditions": (
        ("Область применения", ("equipment_type_code", "rock_code", "site_code")),
        ("Производительность", ("tech_speed_m_per_h", "unproductive_h_per_shift", "fuel_l_per_m")),
        ("Ресурс инструмента", ("bit_life_m", "hammer_life_m", "rods_life_m", "casing_m_per_m")),
    ),
    "sites": (
        ("Принадлежность", ("customer_code", "production_unit_code", "rock_code")),
        ("Логистика", (
            "distance_from_base_km", "distance_from_warehouse_km", "mobilization_km",
            "mobilization_rate_rub_per_km", "blocks_per_mobilization",
        )),
        ("Условия", ("diesel_price_ton_rub", "customer_provides_fuel", "is_watered")),
    ),
    "unit_fixed_costs": (
        ("Отнесение", ("production_unit_code", "scope", "category", "allocation_driver")),
        ("Персонал", ("position_code", "headcount")),
        ("Сумма", ("monthly_rub",)),
    ),
}


SECTION_SCHEMAS: dict[str, type[ReferencePayload]] = {
    "production_units": ProductionUnitPayload,
    "counterparties": CounterpartyPayload,
    "sites": SitePayload,
    "organization_rates": OrganizationRatesPayload,
    "bases": BasePayload,
    "warehouses": WarehousePayload,
    "routes": RoutePayload,
    "units": UnitPayload,
    "operations": OperationPayload,
    "work_packages": WorkPackagePayload,
    "materials": MaterialPayload,
    "material_prices": MaterialPricePayload,
    "material_loss_norms": MaterialLossNormPayload,
    "positions": PositionPayload,
    "labor_rates": LaborRatePayload,
    "crew_templates": CrewTemplatePayload,
    "equipment_types": EquipmentTypePayload,
    "equipment_assets": EquipmentAssetPayload,
    "resource_pools": ResourcePoolPayload,
    "resource_norms": ResourceNormPayload,
    "drilling_conditions": DrillingConditionPayload,
    "rocks": RockPayload,
    "blast_design_parameters": BlastDesignParameterPayload,
    "bench_surface_conditions": BenchSurfaceConditionPayload,
    "stakeout_modes": StakeoutModePayload,
    "site_infrastructure": SiteInfrastructurePayload,
    "cost_centers": CostCenterPayload,
    "cost_items": CostItemPayload,
    "cost_rules": CostRulePayload,
    "allocation_rules": AllocationRulePayload,
    "unit_fixed_costs": UnitFixedCostPayload,
    "subcontract_rates": SubcontractRatePayload,
    "market_prices": MarketPricePayload,
}


def section_schema(section: str) -> type[ReferencePayload] | None:
    return SECTION_SCHEMAS.get(section)


@lru_cache(maxsize=None)
def section_json_schema(section: str) -> dict[str, Any]:
    """JSON Schema раздела. Схема статична, поэтому считается один раз."""

    model = SECTION_SCHEMAS.get(section)
    if model is None:
        return {}
    return model.model_json_schema()


def section_fieldsets(section: str) -> list[dict[str, Any]]:
    """Группы полей формы. Поля, не попавшие в группы, идут последней «Прочее»."""

    schema = section_json_schema(section)
    properties = [
        name for name, field in (schema.get("properties") or {}).items()
        if not field.get("x-internal")
    ]
    declared = SECTION_FIELDSETS.get(section)
    if not declared:
        return [{"title": "", "fields": properties}]

    grouped: list[dict[str, Any]] = []
    used: set[str] = set()
    for title, fields in declared:
        present = [name for name in fields if name in properties]
        if present:
            grouped.append({"title": title, "fields": present})
            used.update(present)
    rest = [name for name in properties if name not in used]
    if rest:
        grouped.append({"title": "Прочее", "fields": rest})
    return grouped


@lru_cache(maxsize=None)
def reference_paths(section: str) -> tuple[tuple[tuple[str, ...], str], ...]:
    """Все поля-ссылки раздела вместе с путём до них.

    Путь нужен потому, что ссылки живут не только на верхнем уровне: состав
    бригады — список объектов, у каждого своя ссылка на должность. Плоский
    список свойств такие поля не видит, и битая ссылка проходила публикацию.
    """

    schema = section_json_schema(section)
    definitions = schema.get("$defs") or {}
    found: list[tuple[tuple[str, ...], str]] = []
    _collect_refs(schema.get("properties") or {}, definitions, (), found, set())
    return tuple(found)


def referenced_sections(section: str) -> dict[str, str]:
    """Поля-ссылки верхнего уровня: {имя поля: раздел, на который ссылается}."""

    return {path[0]: target for path, target in reference_paths(section) if len(path) == 1}


def _collect_refs(
    properties: dict[str, Any],
    definitions: dict[str, Any],
    prefix: tuple[str, ...],
    found: list[tuple[tuple[str, ...], str]],
    visiting: set[str],
) -> None:
    for name, field in properties.items():
        target = _extract_ref(field)
        if target:
            found.append((prefix + (name,), target))
            continue
        nested_name, nested = _nested_object(field, definitions)
        if nested is None or nested_name in visiting:
            # Схема может ссылаться сама на себя — по кругу не ходим.
            continue
        visiting.add(nested_name)
        _collect_refs(nested.get("properties") or {}, definitions, prefix + (name,), found, visiting)
        visiting.discard(nested_name)


def _nested_object(field: dict[str, Any], definitions: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """Вложенная модель поля: сам объект, элемент списка или вариант anyOf."""

    candidates: list[Any] = [field, field.get("items")]
    candidates.extend(field.get("anyOf", ()))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        ref = candidate.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            continue
        name = ref.removeprefix("#/$defs/")
        definition = definitions.get(name)
        if isinstance(definition, dict):
            return name, definition
    return "", None


def _extract_ref(field: dict[str, Any]) -> str | None:
    if "x-ref" in field:
        return str(field["x-ref"])
    # Необязательное поле приходит как anyOf[тип, null] — метка лежит рядом.
    for variant in field.get("anyOf", ()):
        if isinstance(variant, dict) and "x-ref" in variant:
            return str(variant["x-ref"])
    return None
