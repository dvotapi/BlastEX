"""Начальные справочники и серверная валидация публикации Cost V2."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from pydantic import ValidationError as PydanticValidationError

from cost.v2.models import CostBehavior, CostLayer, ReferenceItem, ReferenceSnapshot
from cost.v2.schemas import SECTION_SCHEMAS, referenced_sections
from cost.v2.packages import (
    DEFAULT_OPERATIONS,
    DEFAULT_PACKAGES,
    operation_reference_items,
    package_codes,
    package_reference_items,
)


# Разделы справочника. `columns` — что показывать в списке записей, `view` —
# как раздел рисуется (таблица либо матрица «станок × порода»), `deprecated` —
# раздел ещё читается ради старых ревизий, но в интерфейсе не предлагается.
REFERENCE_SECTION_DEFINITIONS: dict[str, dict[str, Any]] = {
    "production_units": {
        "group": "organization", "label": "Производственные юниты",
        "columns": ["name", "plan_volume_m3", "region"],
    },
    "counterparties": {
        "group": "organization", "label": "Контрагенты",
        "columns": ["name", "role", "inn"],
    },
    "sites": {
        "group": "organization", "label": "Карьеры и объекты",
        "columns": ["name", "customer_code", "rock_code", "distance_from_base_km", "is_watered"],
    },
    "organization_rates": {
        "group": "organization", "label": "Ставки и надбавки организации",
        "columns": ["name", "social_contribution_rate", "overhead_rate", "target_margin_rate", "vat_rate"],
    },
    "bases": {
        "group": "infrastructure", "label": "Производственные базы",
        "columns": ["name", "production_unit_code", "monthly_rub"],
    },
    "warehouses": {
        "group": "infrastructure", "label": "Склады",
        "columns": ["name", "production_unit_code", "area_m2"],
    },
    "routes": {
        "group": "infrastructure", "label": "Маршруты",
        "columns": ["name", "from_code", "to_code", "distance_km"],
    },
    "units": {"group": "operations", "label": "Единицы измерения", "columns": ["name", "symbol", "dimension"]},
    "operations": {"group": "operations", "label": "Элементарные операции", "columns": ["name", "stage", "unit"]},
    "work_packages": {"group": "operations", "label": "Пакеты работ", "columns": ["name", "description"]},
    "materials": {
        "group": "materials", "label": "Материалы и ВМ",
        "columns": ["name", "material_kind", "unit", "storage_class"],
    },
    "material_prices": {
        "group": "materials", "label": "Стоимость материалов",
        "columns": ["name", "material_code", "price_rub", "valid_from"],
    },
    "material_loss_norms": {
        "group": "materials", "label": "Нормативные потери",
        "columns": ["name", "material_code", "operation_code", "loss_rate"],
    },
    "positions": {
        "group": "labor", "label": "Должности и ставки",
        "columns": ["name", "category", "operation_code", "norm_shifts_per_month", "piece_driver"],
    },
    "labor_rates": {
        "group": "labor", "label": "Ставки персонала",
        "columns": ["name", "position_code", "fixed_monthly_rub", "piece_rate_rub", "condition_code"],
    },
    "crew_templates": {"group": "labor", "label": "Составы бригад", "columns": ["name", "package_code"]},
    "equipment_types": {
        "group": "equipment", "label": "Типы оборудования",
        "columns": ["name", "kind", "norm_shifts_per_month", "maintenance_mode", "capacity"],
    },
    "equipment_assets": {
        "group": "equipment", "label": "Основные средства",
        "columns": ["name", "equipment_type_code", "initial_cost_rub", "useful_life_months"],
    },
    "resource_pools": {
        "group": "equipment", "label": "Ресурсные пулы и мощности",
        "columns": ["name", "unit", "monthly_capacity", "fixed_cost_rub"],
    },
    "resource_norms": {
        "group": "equipment", "label": "Нормы ресурсов по операциям",
        "columns": ["name", "operation_code", "resource_code", "norm_per_unit"],
    },
    "rocks": {"group": "blast_design", "label": "Породы", "columns": ["name", "density_t_m3", "hardness_f"]},
    "blast_design_parameters": {
        "group": "blast_design",
        "label": "Нормативы и коэффициенты БВР",
        "columns": ["name", "value", "unit"],
    },
    "drilling_conditions": {
        "group": "drilling", "label": "Условия бурения",
        "view": "matrix",
        "columns": ["name", "equipment_type_code", "rock_code", "site_code", "tech_speed_m_per_h", "bit_life_m"],
    },
    "drilling_productivity": {
        "group": "drilling", "label": "Производительность бурения",
        "deprecated": True,
        "columns": ["name"],
    },
    "bench_surface_conditions": {
        "group": "drilling", "label": "Качество поверхности блока",
        "columns": ["name", "productivity_factor"],
    },
    "stakeout_modes": {
        "group": "drilling", "label": "Вынос скважин в натуру",
        "columns": ["name", "contractor_share"],
    },
    "site_infrastructure": {"group": "drilling", "label": "Инфраструктура объекта", "columns": ["name"]},
    "cost_centers": {"group": "costs", "label": "Центры затрат", "columns": ["name", "production_unit_code", "kind"]},
    "cost_items": {"group": "costs", "label": "Статьи затрат", "columns": ["name", "kind", "cost_center_code"]},
    "cost_rules": {
        "group": "costs", "label": "Правила расчёта затрат",
        "columns": ["name", "operation_code", "behavior_type", "cost_layer", "rate_rub"],
    },
    "allocation_rules": {
        "group": "costs", "label": "Правила распределения",
        "columns": ["name", "cost_item_code", "driver", "target_layer"],
    },
    "unit_fixed_costs": {
        "group": "costs", "label": "Постоянные затраты юнита",
        "columns": ["name", "production_unit_code", "category", "monthly_rub", "headcount"],
    },
    "subcontract_rates": {
        "group": "market", "label": "Ставки субподрядчиков",
        "columns": ["name", "counterparty_code", "operation_code", "rate_rub"],
    },
    "market_prices": {"group": "market", "label": "Рыночные цены", "columns": ["name", "scope", "price_rub"]},
}

REFERENCE_GROUPS: tuple[tuple[str, str], ...] = (
    ("organization", "Организация, юниты и объекты"),
    ("operations", "Виды работ и операции"),
    ("materials", "Материалы, компоненты ВМ и цены"),
    ("labor", "Персонал и бригады"),
    ("equipment", "Оборудование и мощности"),
    ("blast_design", "Технические справочники БВР"),
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
    # Имя поля payload, если ошибка относится к конкретному полю: интерфейс
    # показывает такую ошибку под самим полем, а не общим списком сверху.
    field: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "section": self.section,
            "code": self.code,
            "message": self.message,
            "field": self.field,
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
        _item("PIECE", "Штука", {"symbol": "шт", "dimension": "count", "factor_to_base": 1}),
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
    # Ставки организации по ADR-001: без них модель экономики не стартует, а
    # угадать их нельзя, поэтому запись заводится сразу со значениями по
    # умолчанию и правится сметчиком.
    organization_rates = (
        _item(
            "ORG_RATES_DEFAULT",
            "Ставки и надбавки организации",
            {
                "income_tax_rate": "0.13",
                "social_contribution_rate": "0.30",
                "injury_insurance_rate": "0.0042",
                "vacation_reserve_rate": "0.20",
                "salary_basis": "GROSS",
                "overhead_rate": "0.10",
                "target_margin_rate": "0.10",
                "vat_rate": "0.20",
                "per_diem_rub": "0",
                "lodging_rub": "0",
                "shift_hours": "11",
            },
        ),
    )
    return {
        "units": units,
        "organization_rates": organization_rates,
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
    sections: dict[str, tuple[ReferenceItem, ...]] = {key: () for key in REFERENCE_SECTION_DEFINITIONS}
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

    issues.extend(_schema_issues(sections))
    issues.extend(_reference_issues(sections))

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


def _schema_issues(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    """Прогоняет payload каждой записи через схему её раздела."""

    issues: list[ValidationIssue] = []
    for section, items in sections.items():
        model = SECTION_SCHEMAS.get(section)
        if model is None:
            continue
        for item in items:
            try:
                model.model_validate(item.payload)
            except PydanticValidationError as exc:
                for error in exc.errors():
                    issues.append(
                        ValidationIssue(
                            "error",
                            section,
                            item.code,
                            _humanize(error),
                            field=".".join(str(part) for part in error.get("loc", ())),
                        )
                    )
    return issues


def _humanize(error: Mapping[str, Any]) -> str:
    """Сообщение pydantic → фраза, понятная сметчику."""

    field = ".".join(str(part) for part in error.get("loc", ())) or "запись"
    kind = str(error.get("type", ""))
    if kind == "extra_forbidden":
        return f"Поле «{field}» не входит в схему раздела."
    if kind == "missing":
        return f"Не заполнено обязательное поле «{field}»."
    if kind.startswith("greater_than") or kind.startswith("less_than"):
        return f"Поле «{field}»: значение вне допустимого диапазона."
    if kind == "value_error":
        # Сообщения наших model_validator уже написаны по-русски.
        return str(error.get("msg", "")).removeprefix("Value error, ")
    return f"Поле «{field}»: {error.get('msg', 'неверное значение')}."


def _reference_issues(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    """Проверяет поля `x-ref`: ссылка должна вести на существующую запись."""

    known: dict[str, set[str]] = {
        section: {item.code for item in items} for section, items in sections.items()
    }
    issues: list[ValidationIssue] = []
    for section, items in sections.items():
        refs = referenced_sections(section)
        if not refs:
            continue
        for item in items:
            for field, target in refs.items():
                value = item.payload.get(field)
                if value in (None, ""):
                    continue
                if str(value) not in known.get(target, set()):
                    label = REFERENCE_SECTION_DEFINITIONS.get(target, {}).get("label", target)
                    issues.append(
                        ValidationIssue(
                            "error",
                            section,
                            item.code,
                            f"Ссылка «{value}» не найдена в разделе «{label}».",
                            field=field,
                        )
                    )
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
