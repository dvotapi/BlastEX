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

__all__ = ["SECTION_SCHEMAS", "section_schema", "section_json_schema", "referenced_sections"]


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


def referenced_sections(section: str) -> dict[str, str]:
    """Поля-ссылки раздела: {имя поля: раздел, на который ссылается}."""

    schema = section_json_schema(section)
    refs: dict[str, str] = {}
    for name, field in (schema.get("properties") or {}).items():
        target = _extract_ref(field)
        if target:
            refs[name] = target
    return refs


def _extract_ref(field: dict[str, Any]) -> str | None:
    if "x-ref" in field:
        return str(field["x-ref"])
    # Необязательное поле приходит как anyOf[тип, null] — метка лежит рядом.
    for variant in field.get("anyOf", ()):
        if isinstance(variant, dict) and "x-ref" in variant:
            return str(variant["x-ref"])
    return None
