"""Начальные справочники и серверная валидация публикации Cost V2."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from cost.v2.models import CostBehavior, CostLayer, ReferenceItem, ReferenceSnapshot
from cost.v2.packages import (
    DEFAULT_OPERATIONS,
    DEFAULT_PACKAGES,
    operation_reference_items,
    package_codes,
    package_reference_items,
)


REFERENCE_SECTION_DEFINITIONS: dict[str, dict[str, str]] = {
    "production_units": {"group": "organization", "label": "Производственные юниты"},
    "counterparties": {"group": "organization", "label": "Контрагенты"},
    "sites": {"group": "organization", "label": "Карьеры и объекты"},
    "bases": {"group": "infrastructure", "label": "Производственные базы"},
    "warehouses": {"group": "infrastructure", "label": "Склады"},
    "routes": {"group": "infrastructure", "label": "Маршруты"},
    "units": {"group": "operations", "label": "Единицы измерения"},
    "operations": {"group": "operations", "label": "Элементарные операции"},
    "work_packages": {"group": "operations", "label": "Пакеты работ"},
    "materials": {"group": "materials", "label": "Материалы и ВМ"},
    "material_prices": {"group": "materials", "label": "Стоимость материалов"},
    "material_loss_norms": {"group": "materials", "label": "Нормативные потери"},
    "positions": {"group": "labor", "label": "Должности"},
    "labor_rates": {"group": "labor", "label": "Ставки персонала"},
    "crew_templates": {"group": "labor", "label": "Составы бригад"},
    "equipment_types": {"group": "equipment", "label": "Типы оборудования"},
    "equipment_assets": {"group": "equipment", "label": "Основные средства"},
    "resource_pools": {"group": "equipment", "label": "Ресурсные пулы и мощности"},
    "resource_norms": {"group": "equipment", "label": "Нормы ресурсов по операциям"},
    "drilling_productivity": {"group": "drilling", "label": "Производительность бурения"},
    "bench_surface_conditions": {"group": "drilling", "label": "Качество поверхности блока"},
    "stakeout_modes": {"group": "drilling", "label": "Вынос скважин в натуру"},
    "site_infrastructure": {"group": "drilling", "label": "Инфраструктура объекта"},
    "cost_centers": {"group": "costs", "label": "Центры затрат"},
    "cost_items": {"group": "costs", "label": "Статьи затрат"},
    "cost_rules": {"group": "costs", "label": "Правила расчёта затрат"},
    "allocation_rules": {"group": "costs", "label": "Правила распределения"},
    "subcontract_rates": {"group": "market", "label": "Ставки субподрядчиков"},
    "market_prices": {"group": "market", "label": "Рыночные цены"},
}

REFERENCE_GROUPS: tuple[tuple[str, str], ...] = (
    ("organization", "Организация, юниты и объекты"),
    ("operations", "Виды работ и операции"),
    ("materials", "Материалы, компоненты ВМ и цены"),
    ("labor", "Персонал и бригады"),
    ("equipment", "Оборудование и мощности"),
    ("drilling", "Бурение и условия блока"),
    ("infrastructure", "Базы, склады и маршруты"),
    ("costs", "Статьи затрат и распределение"),
    ("market", "Субподряд и рынок"),
)

_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{0,79}$")
_FORBIDDEN_VM_IN_HOLE = {
    "PRIMER_ASSEMBLY",
    "STEMMING",
    "INITIATION_NETWORK",
    "BLAST_SAFETY_ZONE",
    "BLAST_EXECUTION",
}


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    section: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "section": self.section,
            "code": self.code,
            "message": self.message,
        }


def _item(code: str, name: str, payload: Mapping[str, Any] | None = None) -> ReferenceItem:
    return ReferenceItem(
        code=code,
        name=name,
        payload=dict(payload or {}),
        source="BlastEX Cost V2",
    )


def _system_items() -> dict[str, tuple[ReferenceItem, ...]]:
    units = (
        _item("KG", "Килограмм", {"symbol": "кг", "dimension": "mass", "factor_to_base": 1}),
        _item("T", "Тонна", {"symbol": "т", "dimension": "mass", "factor_to_base": 1000}),
        _item("M", "Погонный метр", {"symbol": "м", "dimension": "length", "factor_to_base": 1}),
        _item("M2", "Квадратный метр", {"symbol": "м²", "dimension": "area", "factor_to_base": 1}),
        _item("M3", "Кубический метр", {"symbol": "м³", "dimension": "volume", "factor_to_base": 1}),
        _item("HOUR", "Час", {"symbol": "ч", "dimension": "time", "factor_to_base": 1}),
        _item("SHIFT", "Смена", {"symbol": "смена", "dimension": "time"}),
        _item("TRIP", "Рейс", {"symbol": "рейс", "dimension": "count"}),
        _item("BLAST", "Взрыв", {"symbol": "взрыв", "dimension": "count"}),
        _item("CONTRACT_LINE", "Договорная позиция", {"symbol": "поз.", "dimension": "count"}),
    )
    resource_pools = tuple(
        _item(code, name, {"unit": unit, "monthly_capacity": None, "fixed_cost_rub": 0, "variable_rate_rub": 0, "cost_layer": layer, "allocation_driver": allocation_driver})
        for code, name, unit, layer, allocation_driver in (
            ("ENGINEERING_HOUR", "Проектно-инженерный персонал", "HOUR", "project_direct", "resource_demand"),
            ("SURVEY_CAPACITY", "Маркшейдерская разбивка", "HOUR", "project_direct", "resource_demand"),
            ("DRILL_RIG_HOUR", "Основные буровые станки", "HOUR", "production", "resource_demand"),
            ("CONTOUR_DRILL_RIG_HOUR", "Контурные буровые станки", "HOUR", "production", "resource_demand"),
            ("COMPONENT_PLANT_KG", "Пункт изготовления компонентов ЭВВ", "KG", "production", "resource_demand"),
            ("SZM_HOUR", "Смесительно-зарядные машины", "HOUR", "production", "resource_demand"),
            ("MINER_HOUR", "Горнорабочие", "HOUR", "project_direct", "resource_demand"),
            ("BLAST_CREW_HOUR", "Взрывной персонал", "HOUR", "project_direct", "resource_demand"),
            ("WAREHOUSE_KG", "Мощность склада ВМ", "KG", "production", "resource_demand"),
            ("HAZMAT_TRANSPORT_TKM", "Спецтранспорт ВМ", "T", "production", "resource_demand"),
            ("TRANSPORT_TRIP", "Мобилизационный транспорт", "TRIP", "project_direct", "resource_demand"),
            ("OWN_EXCAVATOR_HOUR", "Собственный экскаватор с гидроклином", "HOUR", "production", "resource_demand"),
            ("UNIT_AHP", "АХП производственного юнита", "CONTRACT_LINE", "full", "revenue"),
        )
    )
    return {
        "units": units,
        "operations": operation_reference_items(),
        "work_packages": package_reference_items(),
        "resource_pools": resource_pools,
        "bench_surface_conditions": (
            _item("PREPARED", "Подготовленная поверхность", {"productivity_factor": 1}),
        ),
        "stakeout_modes": (
            _item("CUSTOMER_CONTROL_POINTS", "Заказчик выносит опорные скважины", {"contractor_share": 0.85}),
            _item("CUSTOMER_ALL_HOLES", "Заказчик выносит все скважины", {"contractor_share": 0}),
            _item("CONTRACTOR_ALL_HOLES", "Подрядчик выносит все скважины", {"contractor_share": 1}),
        ),
        "site_infrastructure": (
            _item("REFUELING", "Заправка бурового станка", {"required_fields": ["available", "provider", "price_rub"]}),
            _item("MAINTENANCE_BOX", "Бокс для ТОиР", {"required_fields": ["available", "capacity", "price_rub"]}),
            _item("CANTEEN", "Столовая", {"required_fields": ["available", "meal_price_rub"]}),
            _item("ACCOMMODATION", "Проживание", {"required_fields": ["available", "capacity", "night_price_rub", "distance_km"]}),
        ),
        "cost_items": tuple(
            _item(behavior.value, behavior.value, {"kind": "behavior_type"})
            for behavior in CostBehavior
        ) + tuple(
            _item(f"LAYER_{layer.value.upper()}", layer.value, {"kind": "cost_layer"})
            for layer in CostLayer
        ),
    }


def default_reference_sections() -> dict[str, tuple[ReferenceItem, ...]]:
    sections = {key: tuple() for key in REFERENCE_SECTION_DEFINITIONS}
    sections.update(_system_items())
    return sections


def default_reference_snapshot() -> ReferenceSnapshot:
    return ReferenceSnapshot(
        revision_id="SYSTEM-1",
        published_at=datetime.now(timezone.utc).replace(microsecond=0),
        published_by="system",
        sections=default_reference_sections(),
    )


def normalize_sections(
    raw_sections: Mapping[str, Sequence[ReferenceItem | Mapping[str, Any]]],
) -> dict[str, tuple[ReferenceItem, ...]]:
    sections: dict[str, tuple[ReferenceItem, ...]] = {}
    for section in REFERENCE_SECTION_DEFINITIONS:
        rows = raw_sections.get(section, ())
        sections[section] = tuple(
            item if isinstance(item, ReferenceItem) else ReferenceItem.from_dict(item)
            for item in rows
        )
    return sections


def validate_reference_sections(
    raw_sections: Mapping[str, Sequence[ReferenceItem | Mapping[str, Any]]],
) -> list[ValidationIssue]:
    sections = normalize_sections(raw_sections)
    issues: list[ValidationIssue] = []

    unknown = sorted(set(raw_sections) - set(REFERENCE_SECTION_DEFINITIONS))
    for section in unknown:
        issues.append(ValidationIssue("error", section, "", "Неизвестный раздел справочника."))

    for section, items in sections.items():
        seen: set[str] = set()
        for item in items:
            if not item.code:
                issues.append(ValidationIssue("error", section, "", "Не заполнен код записи."))
                continue
            if item.code in seen:
                issues.append(ValidationIssue("error", section, item.code, "Код повторяется в разделе."))
            seen.add(item.code)
            if not _CODE_RE.fullmatch(item.code):
                issues.append(
                    ValidationIssue(
                        "error",
                        section,
                        item.code,
                        "Код должен состоять из латинских заглавных букв, цифр, точки, дефиса или подчёркивания.",
                    )
                )
            if not item.name:
                issues.append(ValidationIssue("error", section, item.code, "Не заполнено наименование."))
            if item.valid_from and item.valid_to and item.valid_to < item.valid_from:
                issues.append(ValidationIssue("error", section, item.code, "valid_to раньше valid_from."))

    operations = {item.code for item in sections["operations"] if item.is_active}
    packages = {item.code: item for item in sections["work_packages"] if item.is_active}
    for required in package_codes():
        if required not in packages:
            issues.append(
                ValidationIssue("error", "work_packages", required, "Обязательный пакет отключён или отсутствует.")
            )

    for package in packages.values():
        package_operations: list[str] = []
        for raw in package.payload.get("operations", []):
            code = str(raw if isinstance(raw, str) else raw.get("operation_code", ""))
            if not code:
                issues.append(ValidationIssue("error", "work_packages", package.code, "В составе пакета есть операция без кода."))
            elif code not in operations:
                issues.append(ValidationIssue("error", "work_packages", package.code, f"Операция {code} отсутствует или отключена."))
            if code in package_operations:
                issues.append(ValidationIssue("error", "work_packages", package.code, f"Операция {code} включена дважды."))
            package_operations.append(code)

        if package.code == "VM_IN_HOLE":
            forbidden = sorted(set(package_operations) & _FORBIDDEN_VM_IN_HOLE)
            if forbidden:
                issues.append(
                    ValidationIssue(
                        "error",
                        "work_packages",
                        package.code,
                        "Франко-скважина не может включать: " + ", ".join(forbidden),
                    )
                )

    operation_codes = {item.code for item in DEFAULT_OPERATIONS} | operations
    resource_codes = {item.code for item in sections["resource_pools"] if item.is_active}
    for item in sections["cost_rules"]:
        payload = item.payload
        operation_code = str(payload.get("operation_code", ""))
        resource_code = str(payload.get("resource_code", ""))
        if operation_code and operation_code not in operation_codes:
            issues.append(ValidationIssue("error", "cost_rules", item.code, f"Неизвестная операция {operation_code}."))
        if resource_code and resource_code not in resource_codes:
            issues.append(ValidationIssue("error", "cost_rules", item.code, f"Неизвестный ресурс {resource_code}."))
        try:
            CostBehavior(str(payload.get("behavior_type", CostBehavior.VARIABLE.value)))
            CostLayer(str(payload.get("cost_layer", CostLayer.PROJECT_DIRECT.value)))
        except ValueError as exc:
            issues.append(ValidationIssue("error", "cost_rules", item.code, str(exc)))
        for numeric_key in ("rate_rub", "fixed_rub", "step_capacity", "step_cost_rub"):
            value = payload.get(numeric_key)
            if value in (None, ""):
                continue
            try:
                if Decimal(str(value)) < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                issues.append(ValidationIssue("error", "cost_rules", item.code, f"{numeric_key} должно быть неотрицательным числом."))

    for item in sections["resource_pools"]:
        for numeric_key in ("monthly_capacity", "fixed_cost_rub", "variable_rate_rub"):
            value = item.payload.get(numeric_key)
            if value in (None, ""):
                continue
            try:
                if Decimal(str(value)) < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                issues.append(ValidationIssue("error", "resource_pools", item.code, f"{numeric_key} должно быть неотрицательным числом."))
        if item.payload.get("monthly_capacity") in (None, ""):
            issues.append(ValidationIssue("warning", "resource_pools", item.code, "Месячная мощность не заполнена; перегрузка ресурса не контролируется."))

    if not sections["production_units"]:
        issues.append(ValidationIssue("warning", "production_units", "", "Не добавлен производственный юнит."))
    if not sections["cost_rules"]:
        issues.append(ValidationIssue("warning", "cost_rules", "", "Не добавлены правила затрат; расчёт себестоимости будет нулевым."))

    return issues


def has_validation_errors(issues: Sequence[ValidationIssue]) -> bool:
    return any(issue.level == "error" for issue in issues)


def section_catalog() -> list[dict[str, str]]:
    return [
        {"code": code, "label": meta["label"], "group": meta["group"]}
        for code, meta in REFERENCE_SECTION_DEFINITIONS.items()
    ]


def group_catalog() -> list[dict[str, str]]:
    return [{"code": code, "label": label} for code, label in REFERENCE_GROUPS]
