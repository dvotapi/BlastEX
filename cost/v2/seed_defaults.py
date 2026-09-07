"""Эталонная ревизия справочников для модели блока.

Импорт Cost V1 приносит объекты, материалы с ценами и буровые станки, но не
то, чем считает модель: роли номенклатуры, условия бурения, нормы смен и
ТОиР станков, основные средства машин, правила затрат логистики, СИЗ. Без
этого вкладка «Экономика блока» пуста на любом стенде. Здесь всё это
достраивается по тому, что уже есть: роль — по названию позиции, условие
бурения — на каждый станок, основное средство — на каждую машину без него.

Числа демонстрационные и помечены источником `seed`: сметчик правит их в
справочнике, а модель считает с первого дня. Идемпотентно — повторный
запуск ничего не дублирует и не перезаписывает заполненное.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Callable

from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import normalize_sections

SOURCE = "seed"

# Роль по названию позиции: порядок важен — «ИСКРА-СТАРТ» содержит «Искра»,
# а «Детонатор промежуточный» не должен уйти в электродетонаторы.
_ROLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("NSI_START", ("старт",)),
    ("NSI_SURFACE", ("искра-п",)),
    ("BOOSTER", ("детонатор промежуточный", "сферит", "дпу", "промежуточн")),
    ("DETONATOR_ELECTRIC", ("электродетонатор", "эд-")),
    ("NSI_DOWNHOLE", ("нси", "искра-с", "rionel", "синв")),
    ("EXPLOSIVE", ("эвв", "гвв", "гранулит", "эверсин", "березит", "нитронит", "протолит", "порэмит", "эмульс")),
    ("DRILL_TOOL", ("долото", "коронк", "ппу", "пневмоудар", "штанг", "обсадн", "переводник")),
)
_ROLE_BY_CODE_PREFIX: tuple[tuple[str, str], ...] = (
    ("MAT_VV_", "EXPLOSIVE"),
    ("EXP_", "EXPLOSIVE"),
    ("MAT_ANFO", "EXPLOSIVE"),
    ("MAT_SV_", "BOOSTER"),
    ("MAT_START_NSI", "NSI_START"),
    ("MAT_SURFACE_NSI", "NSI_SURFACE"),
    ("MAT_NSI", "NSI_DOWNHOLE"),
)

_LENGTH_IN_NAME = re.compile(r"(\d+(?:[,.]\d+)?)\s*м\b")
_LENGTH_IN_CODE = re.compile(r"MAT_NSI_(\d+)$")
_MASS_IN_NAME = re.compile(r"(\d+[,.]\d+)")
_MASS_GRAMS_IN_NAME = re.compile(r"ПТ\s*(\d{3})", re.IGNORECASE)


@dataclass
class SeedReport:
    roles: list[str] = field(default_factory=list)
    rigs_normed: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    machines: list[str] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    fixed_costs: list[str] = field(default_factory=list)
    rates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {name: list(values) for name, values in self.__dict__.items()}


def seed_reference(snapshot: ReferenceSnapshot) -> tuple[dict[str, list[ReferenceItem]], SeedReport]:
    sections = {name: list(items) for name, items in normalize_sections(snapshot.sections).items()}
    report = SeedReport()
    _material_roles(sections, report)
    _rig_norms(sections, report)
    _machines(sections, report)
    _assets(sections, report)
    _drilling_conditions(sections, report)
    _logistics_rules(sections, report)
    _fixed_costs(sections, report)
    _organization_rates(sections, report)
    return sections, report


# --- материалы ------------------------------------------------------------


def guess_role(item: ReferenceItem) -> str | None:
    for prefix, role in _ROLE_BY_CODE_PREFIX:
        if item.code.startswith(prefix):
            return role
    name = item.name.lower()
    for role, needles in _ROLE_RULES:
        if any(needle in name for needle in needles):
            return role
    return None


def guess_length_m(item: ReferenceItem) -> Decimal | None:
    match = _LENGTH_IN_NAME.search(item.name)
    if match:
        return Decimal(match.group(1).replace(",", "."))
    match = _LENGTH_IN_CODE.search(item.code)
    if match:
        # Код хранит дециметры: MAT_NSI_90 — 9 м, MAT_NSI_120 — 12 м.
        return Decimal(match.group(1)) / 10
    return None


def guess_mass_kg(item: ReferenceItem) -> Decimal | None:
    grams = _MASS_GRAMS_IN_NAME.search(item.name)
    if grams:
        return Decimal(grams.group(1)) / 1000
    numbers = [Decimal(value.replace(",", ".")) for value in _MASS_IN_NAME.findall(item.name)]
    small = [value for value in numbers if 0 < value <= 5]
    return small[-1] if small else None


def _material_roles(sections: dict[str, list[ReferenceItem]], report: SeedReport) -> None:
    updated: list[ReferenceItem] = []
    for item in sections["materials"]:
        payload = dict(item.payload)
        role = payload.get("nomenclature_role") or "OTHER"
        if role == "OTHER":
            guessed = guess_role(item)
            if guessed:
                payload["nomenclature_role"] = role = guessed
                report.roles.append(f"{item.code} → {guessed}")
        if role == "NSI_DOWNHOLE" and not payload.get("length_m"):
            length = guess_length_m(item)
            if length is not None:
                payload["length_m"] = str(length)
        if role == "BOOSTER" and not payload.get("mass_kg"):
            mass = guess_mass_kg(item)
            if mass is not None:
                payload["mass_kg"] = str(mass)
        updated.append(replace(item, payload=payload) if payload != item.payload else item)
    sections["materials"] = updated


# --- техника --------------------------------------------------------------

RIG_DEFAULTS: dict[str, str] = {
    "norm_shifts_per_month": "40",
    "maintenance_ratio": "0.14",
    "maintenance_mode": "PER_SHIFT",
    "maintenance_rub_per_shift": "750",
    "spare_parts_rub_per_shift": "2750",
    "inspection_rub_per_shift": "200",
    "medical_rub_per_shift": "200",
}

MACHINE_DEFAULTS: dict[str, tuple[str, str, dict[str, str]]] = {
    "SZM": ("SZM_12T", "СЗМ 12 т", {
        "operation_code": "BULK_CHARGING_SZM", "norm_shifts_per_month": "20",
        "maintenance_mode": "PER_SHIFT", "maintenance_rub_per_shift": "500",
        "inspection_rub_per_shift": "200", "medical_rub_per_shift": "200",
        "fuel_l_per_h": "10", "capacity": "12000", "capacity_unit": "KG",
    }),
    "HAZMAT_TRUCK": ("TRUCK_3T", "Доставщик ВМ 3 т (Sollers Atlant)", {
        "operation_code": "VM_DELIVERY_SITE", "norm_shifts_per_month": "20",
        "maintenance_mode": "PER_SHIFT", "maintenance_rub_per_shift": "300",
        "inspection_rub_per_shift": "200", "medical_rub_per_shift": "200",
        "fuel_l_per_km": "0.45", "capacity": "3000", "capacity_unit": "KG",
    }),
    "EMULSION_TRUCK": ("TRUCK_EMULSION_20T", "Тягач с полуприцепом 20 т", {
        "operation_code": "COMPONENT_DELIVERY", "norm_shifts_per_month": "18",
        "maintenance_mode": "PER_SHIFT", "maintenance_rub_per_shift": "400",
        "inspection_rub_per_shift": "200", "medical_rub_per_shift": "200",
        "fuel_l_per_km": "0.5", "capacity": "20000", "capacity_unit": "KG",
    }),
}

# Первоначальная стоимость и срок службы по виду техники, если основное
# средство не заведено: без него амортизация не начисляется вовсе.
_ASSET_COMMENT = "Демонстрационная стоимость: уточните по бухгалтерии."

ASSET_DEFAULTS: dict[str, tuple[str, str]] = {
    "DRILL_RIG": ("20000000", "84"),
    "SZM": ("12000000", "60"),
    "HAZMAT_TRUCK": ("6000000", "60"),
    "EMULSION_TRUCK": ("9000000", "60"),
}


def _kind(item: ReferenceItem) -> str:
    return str(item.payload.get("kind") or "DRILL_RIG")


def _blank(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    return value in (None, "") or _number(value) == 0


def _number(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _rig_norms(sections: dict[str, list[ReferenceItem]], report: SeedReport) -> None:
    updated: list[ReferenceItem] = []
    for item in sections["equipment_types"]:
        if _kind(item) != "DRILL_RIG":
            updated.append(item)
            continue
        payload = dict(item.payload)
        if _blank(payload, "norm_shifts_per_month"):
            for key, value in RIG_DEFAULTS.items():
                if _blank(payload, key) if key != "maintenance_mode" else not payload.get(key):
                    payload[key] = value
            payload.setdefault("operation_code", "PRODUCTION_DRILLING")
            report.rigs_normed.append(item.code)
        updated.append(replace(item, payload=payload) if payload != item.payload else item)
    sections["equipment_types"] = updated


def _machines(sections: dict[str, list[ReferenceItem]], report: SeedReport) -> None:
    kinds = {_kind(item) for item in sections["equipment_types"] if item.is_active}
    for kind, (code, name, payload) in MACHINE_DEFAULTS.items():
        if kind in kinds:
            continue
        sections["equipment_types"].append(
            ReferenceItem(code=code, name=name, payload={"kind": kind, **payload}, source=SOURCE)
        )
        report.machines.append(code)


def _depreciable(payload: dict[str, Any]) -> bool:
    """Есть ли у записи, из чего считать амортизацию.

    Модель берёт либо первоначальную стоимость со сроком службы, либо
    амортизацию за смену (так хранит Cost V1). Пустая запись — та, где нет
    ни того, ни другого: она выглядит заведённой, но даёт нулевую
    амортизацию без предупреждения.
    """

    has_initial = not _blank(payload, "initial_cost_rub") and not _blank(payload, "useful_life_months")
    return has_initial or not _blank(payload, "depreciation_per_shift_rub")


def _assets(sections: dict[str, list[ReferenceItem]], report: SeedReport) -> None:
    updated: list[ReferenceItem] = []
    covered: set[str] = set()
    # Единица из журнала приходит с инвентарным и заводским номером, но без
    # стоимости: дозаполняем её, а не пропускаем как «уже заведённую».
    for item in sections["equipment_assets"]:
        machine_code = str(item.payload.get("equipment_type_code") or "")
        machine = next((m for m in sections["equipment_types"] if m.code == machine_code), None)
        kind = _kind(machine) if machine is not None else ""
        if _depreciable(item.payload) or kind not in ASSET_DEFAULTS:
            covered.add(machine_code)
            updated.append(item)
            continue
        cost, life = ASSET_DEFAULTS[kind]
        payload = {**item.payload, "initial_cost_rub": cost, "useful_life_months": life}
        payload.setdefault("insurance_monthly_rub", "500")
        covered.add(machine_code)
        updated.append(
            replace(item, payload=payload, comment=_ASSET_COMMENT)
        )
        report.assets.append(item.code)
    sections["equipment_assets"] = updated

    for machine in sections["equipment_types"]:
        kind = _kind(machine)
        if kind not in ASSET_DEFAULTS or machine.code in covered or not machine.is_active:
            continue
        cost, life = ASSET_DEFAULTS[kind]
        code = f"ASSET_{machine.code}"
        sections["equipment_assets"].append(
            ReferenceItem(
                code=code,
                name=f"{machine.name}: основное средство",
                payload={
                    "equipment_type_code": machine.code,
                    "initial_cost_rub": cost,
                    "useful_life_months": life,
                    "insurance_monthly_rub": "500",
                },
                source=SOURCE,
                comment=_ASSET_COMMENT,
            )
        )
        report.assets.append(code)


# --- бурение --------------------------------------------------------------


def _tool(sections: dict[str, list[ReferenceItem]], *needles: str) -> str | None:
    for item in sections["materials"]:
        if item.payload.get("nomenclature_role") != "DRILL_TOOL":
            continue
        if any(needle in item.name.lower() for needle in needles):
            return item.code
    return None


def _drilling_conditions(sections: dict[str, list[ReferenceItem]], report: SeedReport) -> None:
    with_condition = {
        str(item.payload.get("equipment_type_code")) for item in sections["drilling_conditions"]
    }
    bit = _tool(sections, "коронк", "долот")
    hammer = _tool(sections, "ппу", "пневмоудар")
    rods = _tool(sections, "штанг")
    for rig in sections["equipment_types"]:
        if _kind(rig) != "DRILL_RIG" or rig.code in with_condition or not rig.is_active:
            continue
        payload: dict[str, Any] = {
            "equipment_type_code": rig.code,
            "tech_speed_m_per_h": "10",
            "unproductive_h_per_shift": "1",
            "fuel_l_per_m": "4.5",
        }
        if bit:
            payload.update({"bit_life_m": "600", "bit_material_code": bit})
        if hammer:
            payload.update({"hammer_life_m": "7000", "hammer_material_code": hammer})
        if rods:
            payload.update({"rods_life_m": "15000", "rods_material_code": rods})
        code = f"COND_{rig.code}_DEFAULT"
        sections["drilling_conditions"].append(
            ReferenceItem(
                code=code,
                name=f"{rig.name}: норма по умолчанию",
                payload=payload,
                source=SOURCE,
                comment="Демонстрационная норма: уточните скорость и ресурс оснастки.",
            )
        )
        report.conditions.append(code)


# --- затраты --------------------------------------------------------------

LOGISTICS_RULES: tuple[tuple[str, str, str, str, str], ...] = (
    # код, название, операция, драйвер, ставка ₽ за единицу
    ("RULE_VM_DELIVERY", "Доставка ВМ со склада на объект", "VM_DELIVERY_SITE", "vm_tkm", "25"),
    ("RULE_COMPONENT_DELIVERY", "Доставка компонентов эмульсии", "COMPONENT_DELIVERY", "component_tkm", "18"),
    ("RULE_STEMMING", "Забойка скважин", "STEMMING", "holes", "60"),
    ("RULE_WAREHOUSE_PICKING", "Комплектация ВМ на складе", "WAREHOUSE_PICKING", "explosive_kg", "0.5"),
)


def _logistics_rules(sections: dict[str, list[ReferenceItem]], report: SeedReport) -> None:
    rules = {item.code for item in sections["cost_rules"]}
    items = {item.code for item in sections["cost_items"]}
    for code, name, operation, driver, rate in LOGISTICS_RULES:
        if code in rules:
            continue
        item_code = code.replace("RULE_", "", 1)
        if item_code not in items:
            sections["cost_items"].append(
                ReferenceItem(code=item_code, name=name, payload={"kind": "logistics"}, source=SOURCE)
            )
            items.add(item_code)
        sections["cost_rules"].append(
            ReferenceItem(
                code=code,
                name=name,
                payload={
                    "operation_code": operation,
                    "cost_item_code": item_code,
                    "behavior_type": "VARIABLE",
                    "cost_layer": "variable",
                    "driver": driver,
                    "rate_rub": rate,
                },
                source=SOURCE,
                comment="Демонстрационная ставка: уточните по договорам.",
            )
        )
        report.rules.append(code)


def _fixed_costs(sections: dict[str, list[ReferenceItem]], report: SeedReport) -> None:
    if any(item.payload.get("category") == "PPE" for item in sections["unit_fixed_costs"]):
        return
    sections["unit_fixed_costs"].append(
        ReferenceItem(
            code="UNIT_PPE",
            name="СИЗ и охрана труда",
            payload={"scope": "UNIT", "category": "PPE", "monthly_rub": "60000", "allocation_driver": "rock_volume_m3"},
            source=SOURCE,
            comment="Демонстрационная сумма в месяц: уточните по фактическим закупкам.",
        )
    )
    report.fixed_costs.append("UNIT_PPE")


def _organization_rates(sections: dict[str, list[ReferenceItem]], report: SeedReport) -> None:
    """Суточные и проживание: без них вахта не считается. Основу оклада не трогаем —
    «на руки» или «до НДФЛ» решает бухгалтерия."""

    if not sections["organization_rates"]:
        return
    item = sections["organization_rates"][0]
    payload = dict(item.payload)
    if _blank(payload, "per_diem_rub"):
        payload["per_diem_rub"] = "700"
        report.rates.append("per_diem_rub=700")
    if _blank(payload, "lodging_rub"):
        payload["lodging_rub"] = "1500"
        report.rates.append("lodging_rub=1500")
    if payload != item.payload:
        sections["organization_rates"][0] = replace(item, payload=payload)


__all__ = ["SeedReport", "guess_length_m", "guess_mass_kg", "guess_role", "seed_reference"]
