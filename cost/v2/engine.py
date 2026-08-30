"""Детерминированный расчёт сценария производственного юнита Cost V2."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
from typing import Any, Iterable, Mapping, Sequence

from cost.v2.models import (
    CapacityChoice,
    CostBehavior,
    CostLayer,
    CostLine,
    EconomicScenario,
    Executor,
    ReferenceItem,
    ReferenceSnapshot,
    ServiceLine,
    StakeoutMode,
    decimal_value,
    money,
    quantity,
)
from cost.v2.packages import OperationDefinition, operation_map, package_map


FORMULA_VERSION = "cost-v2.1"

_VM_IN_HOLE_FORBIDDEN = {
    "PRIMER_ASSEMBLY",
    "STEMMING",
    "INITIATION_NETWORK",
    "BLAST_SAFETY_ZONE",
    "BLAST_EXECUTION",
}
_DIRECT_RESOURCE_CODES = {
    "DRILL_RIG_HOUR",
    "CONTOUR_DRILL_RIG_HOUR",
    "COMPONENT_PLANT_KG",
    "SZM_HOUR",
    "MINER_HOUR",
    "WAREHOUSE_KG",
    "HAZMAT_TRANSPORT_TKM",
    "TRANSPORT_TRIP",
    "OWN_EXCAVATOR_HOUR",
}


@dataclass
class _Portfolio:
    costs: list[CostLine] = field(default_factory=list)
    revenue: dict[tuple[str, str], Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    billed: dict[tuple[str, str], Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    drivers: dict[tuple[str, str], dict[str, Decimal]] = field(default_factory=dict)
    resource_demands: dict[tuple[str, str, str], Decimal] = field(
        default_factory=lambda: defaultdict(Decimal)
    )
    line_meta: dict[str, ServiceLine] = field(default_factory=dict)
    resource_meta: dict[str, ReferenceItem] = field(default_factory=dict)
    resource_utilization: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def calculate_scenario(
    scenario: EconomicScenario,
    references: ReferenceSnapshot,
) -> dict[str, Any]:
    """Рассчитать базовый и кандидатный портфели в одной версии справочников."""

    if scenario.reference_revision_id and scenario.reference_revision_id != references.revision_id:
        raise ValueError(
            "Сценарий зафиксирован на другой ревизии справочников: "
            f"{scenario.reference_revision_id}, получена {references.revision_id}."
        )

    baseline = list(scenario.baseline_service_lines)
    after_by_id = {line.id: line for line in baseline}
    for candidate in scenario.candidate_service_lines:
        if candidate.replaces_service_line_id:
            after_by_id.pop(candidate.replaces_service_line_id, None)
        after_by_id[candidate.id] = candidate
    after = list(after_by_id.values())

    all_months = sorted(
        {
            plan.month
            for line in (*scenario.baseline_service_lines, *scenario.candidate_service_lines)
            for plan in line.monthly_plans
        }
    )
    choices = {choice.resource_code: choice for choice in scenario.capacity_choices}
    before_portfolio = _calculate_portfolio(
        scenario.production_unit_code,
        baseline,
        all_months,
        choices,
        references,
    )
    after_portfolio = _calculate_portfolio(
        scenario.production_unit_code,
        after,
        all_months,
        choices,
        references,
    )

    before = _portfolio_to_dict(before_portfolio, all_months)
    after_result = _portfolio_to_dict(after_portfolio, all_months)
    delta = _delta_view(before, after_result)
    warnings = _dedupe(
        [
            *before_portfolio.warnings,
            *after_portfolio.warnings,
        ]
    )
    return {
        "scenario_id": scenario.id,
        "scenario_name": scenario.name,
        "production_unit_code": scenario.production_unit_code,
        "formula_version": FORMULA_VERSION,
        "reference_revision_id": references.revision_id,
        "before": before,
        "after": after_result,
        "delta": delta,
        "warnings": warnings,
    }


def _calculate_portfolio(
    production_unit_code: str,
    lines: Sequence[ServiceLine],
    months: Sequence[str],
    capacity_choices: Mapping[str, CapacityChoice],
    references: ReferenceSnapshot,
) -> _Portfolio:
    portfolio = _Portfolio()
    operations = operation_map(references)
    packages = package_map(references)
    cost_rules = references.active_items("cost_rules")
    resource_norms = references.active_items("resource_norms")
    subcontract_rates = references.active_items("subcontract_rates")
    market_prices = references.active_items("market_prices")

    for line in lines:
        if not line.id:
            portfolio.warnings.append("В сценарии есть строка услуги без id; строка пропущена.")
            continue
        portfolio.line_meta[line.id] = line
        package = packages.get(line.package_code)
        if package is None:
            portfolio.warnings.append(
                f"{line.name or line.id}: пакет {line.package_code} не найден; строка пропущена."
            )
            continue
        overrides = {item.operation_code: item for item in line.operation_overrides}
        for plan in line.monthly_plans:
            if not _valid_month(plan.month):
                portfolio.warnings.append(
                    f"{line.name or line.id}: месяц {plan.month!r} должен иметь формат YYYY-MM."
                )
                continue
            if plan.billed_quantity < 0 or any(value < 0 for value in plan.physical.values()):
                portfolio.warnings.append(
                    f"{line.name or line.id}, {plan.month}: отрицательные объёмы не допускаются."
                )
                continue
            drivers = _build_drivers(line, plan.physical, plan.billed_quantity, references, portfolio)
            key = (plan.month, line.id)
            portfolio.drivers[key] = drivers
            portfolio.billed[key] += plan.billed_quantity
            price = _market_price(line, plan.month, market_prices, portfolio)
            is_internal_transfer = (
                line.package_code == "VM_WAREHOUSE_TRANSFER"
                and bool(line.options.get("internal_transfer", True))
            )
            portfolio.revenue[key] += Decimal("0") if is_internal_transfer else plan.billed_quantity * price

            for package_operation in package.operations:
                operation = operations.get(package_operation.operation_code)
                if operation is None:
                    portfolio.warnings.append(
                        f"{line.name or line.id}: операция {package_operation.operation_code} не найдена."
                    )
                    continue
                if line.package_code == "VM_IN_HOLE" and operation.code in _VM_IN_HOLE_FORBIDDEN:
                    portfolio.warnings.append(
                        f"{line.name or line.id}: запрещённая для франко-скважины операция "
                        f"{operation.code} пропущена."
                    )
                    continue
                override = overrides.get(operation.code)
                if not _operation_enabled(line, operation.code, package_operation.optional, override):
                    continue
                executor = _operation_executor(line, operation.code, override)
                operation_quantity = (
                    override.quantity
                    if override is not None and override.quantity is not None
                    else drivers.get(operation.driver, Decimal("0"))
                )
                if operation_quantity <= 0:
                    continue
                if executor == Executor.OWN:
                    _apply_operation_cost_rules(
                        portfolio,
                        production_unit_code,
                        line,
                        plan.month,
                        operation,
                        operation_quantity,
                        drivers,
                        cost_rules,
                    )
                    _add_operation_resources(
                        portfolio,
                        line,
                        plan.month,
                        operation,
                        operation_quantity,
                        drivers,
                        resource_norms,
                    )
                elif executor in (Executor.SUBCONTRACTOR, Executor.THIRD_PARTY_SUPPLIER):
                    _add_subcontract_cost(
                        portfolio,
                        line,
                        plan.month,
                        operation,
                        operation_quantity,
                        executor,
                        override,
                        subcontract_rates,
                    )
            _add_infrastructure_costs(portfolio, line, plan.month, drivers)

    _apply_resource_pools(
        portfolio,
        production_unit_code,
        months,
        capacity_choices,
        references.active_items("resource_pools"),
    )
    _apply_unit_cost_rules(
        portfolio,
        production_unit_code,
        months,
        cost_rules,
    )
    return portfolio


def _build_drivers(
    line: ServiceLine,
    raw: Mapping[str, Decimal],
    billed_quantity: Decimal,
    references: ReferenceSnapshot,
    portfolio: _Portfolio,
) -> dict[str, Decimal]:
    drivers = {key: decimal_value(value) for key, value in raw.items()}
    drivers["billed_quantity"] = billed_quantity
    unit = line.billing_unit.upper()
    if unit == "M3" and drivers.get("rock_volume_m3", Decimal("0")) == 0:
        drivers["rock_volume_m3"] = billed_quantity
    if unit == "M" and drivers.get("drilling_m", Decimal("0")) == 0:
        target = "contour_drilling_m" if line.package_code.startswith("CONTOUR_") else "drilling_m"
        drivers[target] = billed_quantity
    if unit == "KG" and drivers.get("explosive_kg", Decimal("0")) == 0:
        drivers["explosive_kg"] = billed_quantity
    if unit == "HOUR" and line.package_code == "OVERSIZE_BREAKING":
        drivers.setdefault("excavator_hours", billed_quantity)

    explosive_kg = drivers.get("explosive_kg", Decimal("0"))
    distance_km = drivers.get("distance_km", Decimal("0"))
    drivers.setdefault("vm_tkm", explosive_kg / Decimal("1000") * distance_km)
    drivers.setdefault("component_tkm", explosive_kg / Decimal("1000") * distance_km)

    drilling_m = drivers.get("drilling_m", Decimal("0"))
    if drilling_m > 0:
        existing_hours = drivers.get("drill_hours", Decimal("0"))
        base_productivity = drivers.get("base_drilling_productivity_m_h", Decimal("0"))
        if base_productivity > 0:
            factor = _drilling_factor(line, references, portfolio)
            drivers["drill_hours"] = drilling_m / (base_productivity * factor)
        elif existing_hours <= 0:
            portfolio.warnings.append(
                f"{line.name or line.id}: не задана базовая производительность бурения; "
                "станко-часы не рассчитаны."
            )

    contour_m = drivers.get("contour_drilling_m", Decimal("0"))
    if contour_m > 0:
        existing_hours = drivers.get("contour_drill_hours", Decimal("0"))
        base_productivity = drivers.get("base_contour_productivity_m_h", Decimal("0"))
        if base_productivity > 0:
            factor = _drilling_factor(line, references, portfolio)
            drivers["contour_drill_hours"] = contour_m / (base_productivity * factor)
        elif existing_hours <= 0:
            portfolio.warnings.append(
                f"{line.name or line.id}: не задана производительность контурного бурения."
            )

    holes = drivers.get("holes", Decimal("0"))
    stakeout_share = _stakeout_share(line, references)
    drivers["stakeout_holes"] = holes * stakeout_share
    return drivers


def _drilling_factor(
    line: ServiceLine,
    references: ReferenceSnapshot,
    portfolio: _Portfolio,
) -> Decimal:
    conditions = line.site_conditions
    manual = conditions.drilling_productivity_factor
    reference_item = references.item(
        "bench_surface_conditions", conditions.bench_surface_condition_code
    )
    reference_factor = (
        decimal_value(reference_item.payload.get("productivity_factor"), Decimal("1"))
        if reference_item
        else Decimal("1")
    )
    factor = manual if manual != Decimal("1") else reference_factor
    share = conditions.uncleared_rock_share_pct
    if share > 0 and reference_item:
        impact = decimal_value(reference_item.payload.get("uncleared_impact_per_share"))
        if impact > 0:
            factor *= max(Decimal("0.05"), Decimal("1") - share / Decimal("100") * impact)
        elif manual == Decimal("1") and reference_factor == Decimal("1"):
            portfolio.warnings.append(
                f"{line.name or line.id}: указана невыбранная горная масса, но для категории "
                f"{conditions.bench_surface_condition_code} не задано снижение производительности."
            )
    if factor <= 0:
        portfolio.warnings.append(
            f"{line.name or line.id}: коэффициент производительности должен быть больше нуля; использовано 1."
        )
        return Decimal("1")
    return factor


def _stakeout_share(line: ServiceLine, references: ReferenceSnapshot) -> Decimal:
    mode = line.site_conditions.stakeout_mode
    reference_item = references.item("stakeout_modes", mode.value)
    if reference_item is not None:
        return decimal_value(reference_item.payload.get("contractor_share"))
    if mode == StakeoutMode.CUSTOMER_ALL_HOLES:
        return Decimal("0")
    if mode == StakeoutMode.CUSTOMER_CONTROL_POINTS:
        return Decimal("0.85")
    return Decimal("1")


def _operation_enabled(
    line: ServiceLine,
    operation_code: str,
    optional: bool,
    override: Any,
) -> bool:
    if override is not None and override.enabled is not None:
        return bool(override.enabled)
    option_keys = {
        "CHARGING_HOSE_ASSISTANCE": "charging_hose_assistance",
        "OVERSIZE_BREAKING": "secondary_breaking",
        "VM_DELIVERY_SITE": "delivery_included",
        "DRILL_DESIGN": "own_drill_design",
    }
    if operation_code == "COMPONENT_MANUFACTURE":
        return str(line.options.get("component_supply_mode", "")) == "OWN_COMPONENT_PRODUCTION"
    if operation_code == "COMPONENT_PURCHASE":
        return str(line.options.get("component_supply_mode", "")) == "PURCHASED_COMPONENTS"
    if operation_code in option_keys and option_keys[operation_code] in line.options:
        return bool(line.options[option_keys[operation_code]])
    return not optional


def _operation_executor(line: ServiceLine, operation_code: str, override: Any) -> Executor:
    if override is not None:
        return override.executor
    if operation_code == "SURVEY_STAKEOUT":
        if line.site_conditions.stakeout_mode == StakeoutMode.CUSTOMER_ALL_HOLES:
            return Executor.CUSTOMER
        return Executor.OWN
    if operation_code == "DRILL_DESIGN" and not bool(line.options.get("own_drill_design", False)):
        return Executor.CUSTOMER
    return Executor.OWN


def _apply_operation_cost_rules(
    portfolio: _Portfolio,
    production_unit_code: str,
    line: ServiceLine,
    month: str,
    operation: OperationDefinition,
    operation_quantity: Decimal,
    drivers: Mapping[str, Decimal],
    rules: Sequence[ReferenceItem],
) -> None:
    matching = [
        rule
        for rule in rules
        if str(rule.payload.get("operation_code", "")) == operation.code
        and _rule_scope_matches(rule, production_unit_code, line)
    ]
    if not matching:
        portfolio.warnings.append(
            f"{line.name or line.id}: для операции {operation.code} не задано правило затрат."
        )
    for rule in matching:
        if bool(rule.payload.get("skip_if_customer_provides_fuel", False)) and line.site_conditions.customer_provides_fuel:
            continue
        driver_code = str(rule.payload.get("driver", operation.driver))
        driver = drivers.get(driver_code, operation_quantity)
        amount, formula = _rule_amount(rule, driver)
        if amount == 0:
            continue
        portfolio.costs.append(
            CostLine(
                month=month,
                service_line_id=line.id,
                service_line_name=line.name,
                operation_code=operation.code,
                cost_item_code=rule.code,
                cost_item_name=rule.name,
                layer=_cost_layer(rule.payload.get("cost_layer")),
                amount_rub=amount,
                formula=formula,
                resource_code=str(rule.payload.get("resource_code", operation.resource_code)),
            )
        )


def _rule_amount(rule: ReferenceItem, driver: Decimal) -> tuple[Decimal, str]:
    payload = rule.payload
    behavior = CostBehavior(str(payload.get("behavior_type", CostBehavior.VARIABLE.value)))
    rate = decimal_value(payload.get("rate_rub"))
    fixed = decimal_value(payload.get("fixed_rub"))
    if behavior == CostBehavior.VARIABLE:
        return driver * rate, f"{driver} × {rate}"
    if behavior == CostBehavior.FIXED:
        return (fixed if driver > 0 else Decimal("0")), f"фиксированно {fixed}"
    if behavior == CostBehavior.MIXED:
        amount = (fixed if driver > 0 else Decimal("0")) + driver * rate
        return amount, f"{fixed} + {driver} × {rate}"
    if behavior == CostBehavior.EVENT:
        return (fixed if driver > 0 else Decimal("0")), f"разовое событие {fixed}"
    if behavior == CostBehavior.STEP_FIXED:
        thresholds = list(payload.get("thresholds") or [])
        if thresholds:
            ordered = sorted(
                thresholds,
                key=lambda row: decimal_value(row.get("limit"), Decimal("Infinity")),
            )
            for threshold in ordered:
                limit = decimal_value(threshold.get("limit"), Decimal("Infinity"))
                if driver <= limit:
                    amount = decimal_value(threshold.get("amount_rub"))
                    return amount, f"ступень до {limit}: {amount}"
            amount = decimal_value(ordered[-1].get("amount_rub"))
            return amount, f"верхняя ступень: {amount}"
        step_capacity = decimal_value(payload.get("step_capacity"))
        step_cost = decimal_value(payload.get("step_cost_rub"))
        if step_capacity <= 0 or driver <= 0:
            return Decimal("0"), "ступень не настроена"
        steps = (driver / step_capacity).to_integral_value(rounding=ROUND_CEILING)
        return steps * step_cost, f"ceil({driver} / {step_capacity}) × {step_cost}"
    if behavior == CostBehavior.ALLOCATED:
        return Decimal("0"), "распределяется на уровне юнита"
    raise ValueError(f"Неподдерживаемое поведение затрат: {behavior}")


def _add_operation_resources(
    portfolio: _Portfolio,
    line: ServiceLine,
    month: str,
    operation: OperationDefinition,
    operation_quantity: Decimal,
    drivers: Mapping[str, Decimal],
    norms: Sequence[ReferenceItem],
) -> None:
    matched = [
        norm for norm in norms if str(norm.payload.get("operation_code", "")) == operation.code
    ]
    for norm in matched:
        resource_code = str(norm.payload.get("resource_code", ""))
        if not resource_code:
            continue
        driver_code = str(norm.payload.get("driver", operation.driver))
        driver = drivers.get(driver_code, operation_quantity)
        rate = decimal_value(norm.payload.get("amount_per_unit"))
        portfolio.resource_demands[(month, resource_code, line.id)] += driver * rate
    if operation.resource_code in _DIRECT_RESOURCE_CODES and not any(
        str(norm.payload.get("resource_code", "")) == operation.resource_code for norm in matched
    ):
        portfolio.resource_demands[(month, operation.resource_code, line.id)] += operation_quantity


def _add_subcontract_cost(
    portfolio: _Portfolio,
    line: ServiceLine,
    month: str,
    operation: OperationDefinition,
    operation_quantity: Decimal,
    executor: Executor,
    override: Any,
    rates: Sequence[ReferenceItem],
) -> None:
    rate = override.subcontract_rate_rub if override is not None else None
    rate_item: ReferenceItem | None = None
    if rate is None:
        rate_item = next(
            (
                item
                for item in rates
                if str(item.payload.get("operation_code", "")) == operation.code
                and str(item.payload.get("site_code", "")) in ("", line.site_code)
            ),
            None,
        )
        rate = decimal_value(rate_item.payload.get("rate_rub")) if rate_item else None
    if rate is None:
        portfolio.warnings.append(
            f"{line.name or line.id}: для внешнего исполнения {operation.code} не задана ставка."
        )
        rate = Decimal("0")
    amount = operation_quantity * rate
    portfolio.costs.append(
        CostLine(
            month=month,
            service_line_id=line.id,
            service_line_name=line.name,
            operation_code=operation.code,
            cost_item_code=(rate_item.code if rate_item else f"EXTERNAL_{operation.code}"),
            cost_item_name=(
                rate_item.name
                if rate_item
                else ("Сторонний поставщик" if executor == Executor.THIRD_PARTY_SUPPLIER else "Субподряд")
            ),
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=amount,
            formula=f"{operation_quantity} × {rate}",
        )
    )
    supervision = override.supervision_cost_rub if override is not None else Decimal("0")
    if supervision > 0:
        portfolio.costs.append(
            CostLine(
                month=month,
                service_line_id=line.id,
                service_line_name=line.name,
                operation_code=operation.code,
                cost_item_code=f"SUPERVISION_{operation.code}",
                cost_item_name="Собственная координация и контроль",
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=supervision,
                formula=f"фиксированно {supervision}",
            )
        )


def _add_infrastructure_costs(
    portfolio: _Portfolio,
    line: ServiceLine,
    month: str,
    drivers: Mapping[str, Decimal],
) -> None:
    conditions = line.site_conditions
    additions: list[tuple[str, str, Decimal, str]] = []
    if not conditions.refueling_available:
        trips = drivers.get("fuel_delivery_trips", drivers.get("trips", Decimal("0")))
        amount = trips * conditions.own_fuel_delivery_cost_rub_trip
        additions.append(("OWN_FUEL_DELIVERY", "Собственная доставка топлива", amount, f"{trips} × {conditions.own_fuel_delivery_cost_rub_trip}"))
    if not conditions.maintenance_box_available:
        shifts = drivers.get("mobile_maintenance_shifts", Decimal("0"))
        amount = shifts * conditions.mobile_maintenance_cost_rub_shift
        additions.append(("MOBILE_MAINTENANCE", "Мобильное ТОиР", amount, f"{shifts} × {conditions.mobile_maintenance_cost_rub_shift}"))
    person_days = drivers.get("person_days", Decimal("0"))
    meal_amount = person_days * conditions.meal_cost_rub_person_day
    additions.append(("MEALS", "Питание персонала", meal_amount, f"{person_days} × {conditions.meal_cost_rub_person_day}"))
    person_nights = drivers.get("person_nights", Decimal("0"))
    accommodation_amount = person_nights * conditions.accommodation_cost_rub_person_night
    additions.append(("ACCOMMODATION", "Проживание персонала", accommodation_amount, f"{person_nights} × {conditions.accommodation_cost_rub_person_night}"))
    for code, name, amount, formula in additions:
        if amount == 0:
            continue
        portfolio.costs.append(
            CostLine(
                month=month,
                service_line_id=line.id,
                service_line_name=line.name,
                operation_code="SITE_INFRASTRUCTURE",
                cost_item_code=code,
                cost_item_name=name,
                layer=CostLayer.PROJECT_DIRECT,
                amount_rub=amount,
                formula=formula,
            )
        )


def _apply_resource_pools(
    portfolio: _Portfolio,
    production_unit_code: str,
    months: Sequence[str],
    choices: Mapping[str, CapacityChoice],
    resources: Sequence[ReferenceItem],
) -> None:
    portfolio.resource_meta = {item.code: item for item in resources}
    line_ids = list(portfolio.line_meta)
    for resource in resources:
        if str(resource.payload.get("production_unit_code", "")) not in ("", production_unit_code):
            continue
        layer = _cost_layer(resource.payload.get("cost_layer"), CostLayer.PRODUCTION)
        for month in months:
            demand_by_line = {
                line_id: portfolio.resource_demands.get((month, resource.code, line_id), Decimal("0"))
                for line_id in line_ids
            }
            total_demand = sum(demand_by_line.values(), Decimal("0"))
            capacity = _period_value(resource.payload.get("monthly_capacity"), month)
            fixed_cost = _period_value(resource.payload.get("fixed_cost_rub"), month) or Decimal("0")
            variable_rate = decimal_value(resource.payload.get("variable_rate_rub"))
            allocation_driver = str(resource.payload.get("allocation_driver", "resource_demand"))

            if variable_rate > 0 and total_demand > 0:
                for line_id, demand in demand_by_line.items():
                    if demand <= 0:
                        continue
                    _append_pool_cost(
                        portfolio,
                        month,
                        line_id,
                        resource,
                        layer,
                        demand * variable_rate,
                        f"{demand} × {variable_rate}",
                        "VARIABLE",
                    )

            if fixed_cost > 0:
                weights = _allocation_weights(
                    portfolio,
                    month,
                    allocation_driver,
                    demand_by_line,
                )
                _allocate_pool_cost(
                    portfolio,
                    month,
                    resource,
                    layer,
                    fixed_cost,
                    weights,
                    f"фиксированно за месяц {fixed_cost}",
                    "FIXED",
                )

            excess = Decimal("0")
            if capacity is not None:
                excess = max(Decimal("0"), total_demand - capacity)
                utilization = (
                    total_demand / capacity * Decimal("100")
                    if capacity > 0
                    else (Decimal("100") if total_demand == 0 else Decimal("Infinity"))
                )
            else:
                utilization = None
            portfolio.resource_utilization.append(
                {
                    "month": month,
                    "resource_code": resource.code,
                    "resource_name": resource.name,
                    "demand": _number(total_demand),
                    "available": _number(capacity) if capacity is not None else None,
                    "utilization_pct": (
                        None
                        if utilization is None or not utilization.is_finite()
                        else _number(utilization)
                    ),
                    "excess": _number(excess),
                }
            )
            if excess <= 0:
                continue
            choice = choices.get(resource.code)
            excess_rate = (
                choice.excess_rate_rub
                if choice
                else decimal_value(resource.payload.get("excess_rate_rub"))
            )
            step_capacity = (
                choice.step_capacity
                if choice
                else decimal_value(resource.payload.get("step_capacity"))
            )
            step_cost = (
                choice.step_cost_rub
                if choice
                else decimal_value(resource.payload.get("step_cost_rub"))
            )
            excess_cost = excess * excess_rate
            if step_capacity > 0 and step_cost > 0:
                steps = (excess / step_capacity).to_integral_value(rounding=ROUND_CEILING)
                excess_cost += steps * step_cost
            portfolio.warnings.append(
                f"{month}: ресурс {resource.name} перегружен на {quantity(excess)} "
                f"({choice.mode.value if choice else 'политика по умолчанию'})."
            )
            if excess_cost > 0:
                weights = _normalize_weights(demand_by_line)
                _allocate_pool_cost(
                    portfolio,
                    month,
                    resource,
                    CostLayer.PRODUCTION,
                    excess_cost,
                    weights,
                    f"дефицит {excess} × {excess_rate} + ступени",
                    "CAPACITY_STEP",
                )


def _apply_unit_cost_rules(
    portfolio: _Portfolio,
    production_unit_code: str,
    months: Sequence[str],
    rules: Sequence[ReferenceItem],
) -> None:
    unit_rules = [rule for rule in rules if not str(rule.payload.get("operation_code", ""))]
    for rule in unit_rules:
        if str(rule.payload.get("production_unit_code", "")) not in ("", production_unit_code):
            continue
        resource_code = str(rule.payload.get("resource_code", ""))
        allocation_driver = str(rule.payload.get("allocation_driver", "revenue"))
        for month in months:
            if resource_code:
                raw_weights = {
                    line_id: portfolio.resource_demands.get((month, resource_code, line_id), Decimal("0"))
                    for line_id in portfolio.line_meta
                }
            else:
                raw_weights = _driver_weights(portfolio, month, allocation_driver)
            total_driver = sum(raw_weights.values(), Decimal("0"))
            behavior = CostBehavior(
                str(rule.payload.get("behavior_type", CostBehavior.VARIABLE.value))
            )
            effective_driver = total_driver
            if total_driver <= 0 and behavior in (
                CostBehavior.FIXED,
                CostBehavior.EVENT,
                CostBehavior.MIXED,
                CostBehavior.STEP_FIXED,
                CostBehavior.ALLOCATED,
            ):
                effective_driver = Decimal("1")
            amount, formula = _rule_amount(rule, effective_driver)
            if amount <= 0:
                continue
            pseudo_resource = ReferenceItem(code=rule.code, name=rule.name)
            _allocate_pool_cost(
                portfolio,
                month,
                pseudo_resource,
                _cost_layer(rule.payload.get("cost_layer"), CostLayer.FULL),
                amount,
                _normalize_weights(raw_weights),
                formula,
                "ALLOCATED_RULE",
            )


def _allocation_weights(
    portfolio: _Portfolio,
    month: str,
    driver: str,
    demand_by_line: Mapping[str, Decimal],
) -> dict[str, Decimal]:
    if driver == "resource_demand" and sum(demand_by_line.values(), Decimal("0")) > 0:
        return _normalize_weights(demand_by_line)
    return _normalize_weights(_driver_weights(portfolio, month, driver))


def _driver_weights(portfolio: _Portfolio, month: str, driver: str) -> dict[str, Decimal]:
    if driver == "revenue":
        return {
            line_id: portfolio.revenue.get((month, line_id), Decimal("0"))
            for line_id in portfolio.line_meta
        }
    if driver == "billed_quantity":
        return {
            line_id: portfolio.billed.get((month, line_id), Decimal("0"))
            for line_id in portfolio.line_meta
        }
    return {
        line_id: portfolio.drivers.get((month, line_id), {}).get(driver, Decimal("0"))
        for line_id in portfolio.line_meta
    }


def _normalize_weights(raw: Mapping[str, Decimal]) -> dict[str, Decimal]:
    positive = {key: value for key, value in raw.items() if value > 0}
    total = sum(positive.values(), Decimal("0"))
    if total <= 0:
        return {}
    return {key: value / total for key, value in positive.items()}


def _allocate_pool_cost(
    portfolio: _Portfolio,
    month: str,
    resource: ReferenceItem,
    layer: CostLayer,
    amount: Decimal,
    weights: Mapping[str, Decimal],
    formula: str,
    suffix: str,
) -> None:
    if not weights:
        portfolio.costs.append(
            CostLine(
                month=month,
                service_line_id="__unit__",
                service_line_name="Нераспределённые затраты юнита",
                operation_code="UNIT_OVERHEAD",
                cost_item_code=f"{resource.code}_{suffix}",
                cost_item_name=resource.name,
                layer=layer,
                amount_rub=amount,
                formula=formula,
                resource_code=resource.code,
            )
        )
        return
    allocated = Decimal("0")
    items = list(weights.items())
    for index, (line_id, weight) in enumerate(items):
        share = amount - allocated if index == len(items) - 1 else amount * weight
        allocated += share
        _append_pool_cost(
            portfolio,
            month,
            line_id,
            resource,
            layer,
            share,
            f"{formula}; доля {weight}",
            suffix,
        )


def _append_pool_cost(
    portfolio: _Portfolio,
    month: str,
    line_id: str,
    resource: ReferenceItem,
    layer: CostLayer,
    amount: Decimal,
    formula: str,
    suffix: str,
) -> None:
    line = portfolio.line_meta.get(line_id)
    portfolio.costs.append(
        CostLine(
            month=month,
            service_line_id=line_id,
            service_line_name=line.name if line else "Нераспределённые затраты юнита",
            operation_code="RESOURCE_POOL",
            cost_item_code=f"{resource.code}_{suffix}",
            cost_item_name=resource.name,
            layer=layer,
            amount_rub=amount,
            formula=formula,
            resource_code=resource.code,
        )
    )


def _portfolio_to_dict(portfolio: _Portfolio, months: Sequence[str]) -> dict[str, Any]:
    period_metrics: dict[str, dict[str, Decimal]] = {}
    for month in months:
        period_metrics[month] = _metrics_for(
            [line for line in portfolio.costs if line.month == month],
            sum((value for (period, _), value in portfolio.revenue.items() if period == month), Decimal("0")),
            sum((value for (period, _), value in portfolio.billed.items() if period == month), Decimal("0")),
        )
    total_metrics = _metrics_for(
        portfolio.costs,
        sum(portfolio.revenue.values(), Decimal("0")),
        sum(portfolio.billed.values(), Decimal("0")),
    )
    service_lines: list[dict[str, Any]] = []
    for line_id, line in portfolio.line_meta.items():
        metrics = _metrics_for(
            [cost for cost in portfolio.costs if cost.service_line_id == line_id],
            sum((value for (month, sid), value in portfolio.revenue.items() if sid == line_id), Decimal("0")),
            sum((value for (month, sid), value in portfolio.billed.items() if sid == line_id), Decimal("0")),
        )
        billed = metrics["billed_quantity"]
        service_lines.append(
            {
                "id": line.id,
                "name": line.name,
                "customer_code": line.customer_code,
                "site_code": line.site_code,
                "package_code": line.package_code,
                "billing_unit": line.billing_unit,
                **_metrics_to_numbers(metrics),
                "break_even_price_rub": (
                    _number(metrics["full_internal_cost"] / billed) if billed > 0 else None
                ),
            }
        )
    return {
        "totals": _metrics_to_numbers(total_metrics),
        "periods": [
            {"month": month, **_metrics_to_numbers(period_metrics[month])}
            for month in months
        ],
        "service_lines": service_lines,
        "resource_utilization": portfolio.resource_utilization,
        "cost_lines": [line.to_dict() for line in portfolio.costs],
        "warnings": _dedupe(portfolio.warnings),
    }


def _metrics_for(
    costs: Iterable[CostLine],
    revenue: Decimal,
    billed: Decimal,
) -> dict[str, Decimal]:
    additions = {layer: Decimal("0") for layer in CostLayer}
    for line in costs:
        additions[line.layer] += line.amount_rub
    variable_cost = additions[CostLayer.VARIABLE]
    project_direct = variable_cost + additions[CostLayer.PROJECT_DIRECT]
    production = project_direct + additions[CostLayer.PRODUCTION]
    full = production + additions[CostLayer.FULL]
    return {
        "billed_quantity": billed,
        "revenue_rub": revenue,
        "variable_cost": variable_cost,
        "project_direct_cost": project_direct,
        "production_cost": production,
        "full_internal_cost": full,
        "contribution_margin": revenue - variable_cost,
        "project_margin": revenue - project_direct,
        "production_margin": revenue - production,
        "full_cost_margin": revenue - full,
        "cost_market_gap": revenue - full,
    }


def _metrics_to_numbers(metrics: Mapping[str, Decimal]) -> dict[str, float]:
    return {key: _number(value) for key, value in metrics.items()}


def _delta_view(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    total_keys = set(before["totals"]) | set(after["totals"])
    totals = {
        key: round(float(after["totals"].get(key, 0)) - float(before["totals"].get(key, 0)), 2)
        for key in total_keys
    }
    before_periods = {item["month"]: item for item in before["periods"]}
    after_periods = {item["month"]: item for item in after["periods"]}
    periods: list[dict[str, Any]] = []
    for month in sorted(set(before_periods) | set(after_periods)):
        left = before_periods.get(month, {})
        right = after_periods.get(month, {})
        keys = (set(left) | set(right)) - {"month"}
        periods.append(
            {
                "month": month,
                **{
                    key: round(float(right.get(key, 0)) - float(left.get(key, 0)), 2)
                    for key in keys
                },
            }
        )
    before_resources = {
        (item["month"], item["resource_code"]): item for item in before["resource_utilization"]
    }
    after_resources = {
        (item["month"], item["resource_code"]): item for item in after["resource_utilization"]
    }
    resources: list[dict[str, Any]] = []
    for key in sorted(set(before_resources) | set(after_resources)):
        left = before_resources.get(key, {})
        right = after_resources.get(key, {})
        before_util = left.get("utilization_pct")
        after_util = right.get("utilization_pct")
        resources.append(
            {
                "month": key[0],
                "resource_code": key[1],
                "resource_name": right.get("resource_name") or left.get("resource_name") or key[1],
                "before_demand": left.get("demand", 0),
                "after_demand": right.get("demand", 0),
                "demand_delta": round(float(right.get("demand", 0)) - float(left.get("demand", 0)), 6),
                "available": right.get("available", left.get("available")),
                "before_utilization_pct": before_util,
                "after_utilization_pct": after_util,
                "utilization_delta_pct": (
                    round(float(after_util) - float(before_util), 2)
                    if before_util is not None and after_util is not None
                    else None
                ),
                "after_excess": right.get("excess", 0),
            }
        )
    return {
        "totals": totals,
        "periods": periods,
        "resource_utilization": resources,
    }


def _market_price(
    line: ServiceLine,
    month: str,
    items: Sequence[ReferenceItem],
    portfolio: _Portfolio,
) -> Decimal:
    if line.market_price_rub > 0:
        return line.market_price_rub
    match = next(
        (
            item
            for item in items
            if str(item.payload.get("package_code", "")) == line.package_code
            and str(item.payload.get("billing_unit", "")) in ("", line.billing_unit)
            and str(item.payload.get("site_code", "")) in ("", line.site_code)
            and str(item.payload.get("valid_from_month", "")) <= month
            and str(item.payload.get("valid_to_month", "9999-12")) >= month
        ),
        None,
    )
    if match:
        return decimal_value(match.payload.get("price_rub"))
    portfolio.warnings.append(
        f"{line.name or line.id}: рыночная цена не задана; выручка рассчитана как 0."
    )
    return Decimal("0")


def _rule_scope_matches(
    rule: ReferenceItem,
    production_unit_code: str,
    line: ServiceLine,
) -> bool:
    payload = rule.payload
    return (
        str(payload.get("production_unit_code", "")) in ("", production_unit_code)
        and str(payload.get("package_code", "")) in ("", line.package_code)
        and str(payload.get("site_code", "")) in ("", line.site_code)
    )


def _cost_layer(value: Any, default: CostLayer = CostLayer.PROJECT_DIRECT) -> CostLayer:
    try:
        return CostLayer(str(value or default.value))
    except ValueError:
        return default


def _period_value(value: Any, month: str) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Mapping):
        selected = value.get(month, value.get("default"))
        return None if selected in (None, "") else decimal_value(selected)
    return decimal_value(value)


def _valid_month(value: str) -> bool:
    if len(value) != 7 or value[4] != "-":
        return False
    try:
        year = int(value[:4])
        month = int(value[5:])
    except ValueError:
        return False
    return year >= 2000 and 1 <= month <= 12


def _number(value: Decimal | None) -> float:
    if value is None:
        return 0.0
    if not value.is_finite():
        return 0.0
    return float(money(value))


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
