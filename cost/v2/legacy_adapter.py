"""Опубликованная ревизия справочников Cost V2 → структуры движка Cost V1.

Движок V1 (`cost/strategies`, `cost/drilling.py`, `cost/geometry.py`) читает
свои dataclass'ы; их единственный источник теперь — разделы схемы `blastex`.
Пустой раздел даёт значения по умолчанию и предупреждение, а не исключение.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, TypeVar

from Blast import RockProperties
from cost.catalog import DEFAULT_CATALOG, CatalogItem
from cost.depreciation_data import (
    DEFAULT_DEPRECIATION_ASSETS,
    FixedAssetDepreciation,
    calculate_depreciation_per_shift_rub,
)
from cost.drilling_data import DEFAULT_DRILL_RIGS, DEFAULT_WORK_OBJECTS, DrillRig, WorkObject
from cost.explosive_data import DEFAULT_EXPLOSIVES, ExplosiveCatalogItem
from cost.fixed_costs import DEFAULT_FIXED_COSTS, SECTION_TITLES, FixedCostItem
from cost.labor import DEFAULT_LABOR_CATALOG, JobPosition
from cost.rock_data import DEFAULT_ROCKS
from cost.v2.models import ReferenceItem, ReferenceSnapshot

# Категории номенклатуры Cost V1; «nsi» — старое имя «downhole_nsi».
_CATALOG_CATEGORIES: dict[str, str] = {
    "explosive": "explosive",
    "detonator": "detonator",
    "downhole_nsi": "downhole_nsi",
    "nsi": "downhole_nsi",
    "surface_nsi": "surface_nsi",
    "start_nsi": "start_nsi",
}
# Так импорт V1 помечал взрывчатые вещества; «ВВ» — вид материала по схеме.
_EXPLOSIVE_CATEGORY = "EXPLOSIVE"
_EXPLOSIVE_KIND = "ВВ"

T = TypeVar("T")


@dataclass(frozen=True)
class LegacyReferences:
    work_objects: tuple[WorkObject, ...]
    drill_rigs: tuple[DrillRig, ...]
    rocks: tuple[RockProperties, ...]
    explosives: tuple[ExplosiveCatalogItem, ...]
    depreciation_assets: tuple[FixedAssetDepreciation, ...]
    catalog: tuple[CatalogItem, ...]
    fixed_costs: tuple[FixedCostItem, ...]
    labor_catalog: tuple[JobPosition, ...]
    warnings: tuple[str, ...] = ()


def default_legacy_references() -> LegacyReferences:
    """Значения по умолчанию Cost V1 — для тестов и пустой организации."""

    return LegacyReferences(
        work_objects=tuple(DEFAULT_WORK_OBJECTS),
        drill_rigs=tuple(DEFAULT_DRILL_RIGS),
        rocks=tuple(DEFAULT_ROCKS),
        explosives=tuple(DEFAULT_EXPLOSIVES),
        depreciation_assets=tuple(DEFAULT_DEPRECIATION_ASSETS),
        catalog=tuple(DEFAULT_CATALOG),
        fixed_costs=tuple(DEFAULT_FIXED_COSTS),
        labor_catalog=tuple(DEFAULT_LABOR_CATALOG),
    )


def legacy_references_from_snapshot(snapshot: ReferenceSnapshot) -> LegacyReferences:
    warnings: list[str] = []
    sites = snapshot.active_items("sites")
    types = {item.code: item for item in snapshot.active_items("equipment_types")}
    assets = snapshot.active_items("equipment_assets")
    materials = snapshot.active_items("materials")
    prices = snapshot.active_items("material_prices")
    units = {item.code: str(item.payload.get("symbol") or item.name) for item in snapshot.active_items("units")}
    rates = {
        str(item.payload.get("position_code")): item
        for item in snapshot.active_items("labor_rates")
    }

    work_objects = _fallback(
        "Раздел «Карьеры и объекты» пуст",
        [_work_object(item, warnings) for item in sites],
        DEFAULT_WORK_OBJECTS,
        warnings,
    )
    drill_rigs = _fallback(
        "В разделе «Основные средства» нет техники вида «Буровой станок»",
        [_drill_rig(item, types) for item in assets if _kind(item, types) == "DRILL_RIG"],
        DEFAULT_DRILL_RIGS,
        warnings,
    )
    depreciation = _fallback(
        "В разделе «Основные средства» нет записей со сроком службы и сменами",
        [_depreciation(item) for item in assets if _has_depreciation_inputs(item)],
        DEFAULT_DEPRECIATION_ASSETS,
        warnings,
    )
    rocks = _fallback(
        "Раздел «Породы» пуст",
        [_rock(item, warnings) for item in snapshot.active_items("rocks")],
        DEFAULT_ROCKS,
        warnings,
    )
    explosives = _fallback(
        "В разделе «Материалы и ВМ» нет ВВ",
        [_explosive(item, warnings) for item in materials if _is_explosive(item)],
        DEFAULT_EXPLOSIVES,
        warnings,
    )
    catalog = _fallback(
        "В разделе «Материалы и ВМ» нет номенклатуры "
        "(категории explosive/detonator/downhole_nsi/surface_nsi/start_nsi)",
        [_catalog_item(item, prices, units, warnings) for item in materials if _catalog_category(item)],
        DEFAULT_CATALOG,
        warnings,
    )
    fixed_costs = _fallback(
        "В разделе «Статьи затрат» нет статей с разделом сметы V1",
        [_fixed_cost(item) for item in snapshot.sections.get("cost_items", ()) if _is_legacy_fixed_cost(item)],
        DEFAULT_FIXED_COSTS,
        warnings,
    )
    labor = _fallback(
        "Раздел «Должности и ставки» пуст",
        [_position(item, rates, warnings) for item in snapshot.active_items("positions")],
        DEFAULT_LABOR_CATALOG,
        warnings,
    )
    return LegacyReferences(
        work_objects=work_objects,
        drill_rigs=drill_rigs,
        rocks=rocks,
        explosives=explosives,
        depreciation_assets=depreciation,
        catalog=catalog,
        fixed_costs=fixed_costs,
        labor_catalog=labor,
        warnings=tuple(warnings),
    )


# --- Преобразования по разделам --------------------------------------------


def _work_object(item: ReferenceItem, warnings: list[str]) -> WorkObject:
    km = _optional_number(item.payload.get("mobilization_km"))
    if km is None:
        warnings.append(f"Объект «{item.name}»: плечо мобилизации не задано, принято 0 км.")
        km = 0.0
    return WorkObject(
        name=item.name,
        mobilization_km=km,
        diesel_price_ton_rub=_optional_number(item.payload.get("diesel_price_ton_rub")),
    )


def _kind(asset: ReferenceItem, types: dict[str, ReferenceItem]) -> str:
    type_item = types.get(str(asset.payload.get("equipment_type_code") or ""))
    return str(type_item.payload.get("kind") or "") if type_item else ""


def _drill_rig(asset: ReferenceItem, types: dict[str, ReferenceItem]) -> DrillRig:
    type_item = types.get(str(asset.payload.get("equipment_type_code") or ""))
    fuel = _optional_number(asset.payload.get("fuel_l_per_h"))
    if fuel is None and type_item is not None:
        fuel = _optional_number(type_item.payload.get("fuel_l_per_h"))
    return DrillRig(
        name=asset.name,
        depreciation_per_shift_rub=_depreciation_per_shift(asset),
        fuel_l_per_h=fuel or 0.0,
    )


def _depreciation_per_shift(asset: ReferenceItem) -> float:
    explicit = _optional_number(asset.payload.get("depreciation_per_shift_rub"))
    if explicit is not None:
        return explicit
    return calculate_depreciation_per_shift_rub(
        _number(asset.payload.get("initial_cost_rub")),
        _number(asset.payload.get("useful_life_months")),
        _number(asset.payload.get("productive_shifts_per_month")),
    )


def _has_depreciation_inputs(asset: ReferenceItem) -> bool:
    return (
        _number(asset.payload.get("useful_life_months")) > 0
        and _number(asset.payload.get("productive_shifts_per_month")) > 0
    )


def _depreciation(asset: ReferenceItem) -> FixedAssetDepreciation:
    initial = _number(asset.payload.get("initial_cost_rub"))
    life = _number(asset.payload.get("useful_life_months"))
    shifts = _number(asset.payload.get("productive_shifts_per_month"))
    return FixedAssetDepreciation(
        name=asset.name,
        initial_cost_rub=initial,
        useful_life_months=life,
        productive_shifts_per_month=shifts,
        depreciation_per_shift_rub=calculate_depreciation_per_shift_rub(initial, life, shifts),
    )


def _rock(item: ReferenceItem, warnings: list[str]) -> RockProperties:
    ucs = _optional_number(item.payload.get("ucs_mpa"))
    fissuring = _optional_number(item.payload.get("fissuring_ff"))
    if ucs is None or fissuring is None:
        warnings.append(f"Порода «{item.name}»: не заданы прочность или трещиноватость, приняты нули.")
    return RockProperties(
        name=item.name,
        density_t_m3=_number(item.payload.get("density_t_m3")),
        ucs_mpa=ucs or 0.0,
        fissuring_ff=fissuring or 0.0,
    )


def _is_explosive(item: ReferenceItem) -> bool:
    return (
        str(item.payload.get("category") or "") == _EXPLOSIVE_CATEGORY
        or str(item.payload.get("material_kind") or "") == _EXPLOSIVE_KIND
    )


def _explosive(item: ReferenceItem, warnings: list[str]) -> ExplosiveCatalogItem:
    density = _optional_number(item.payload.get("density_t_m3"))
    power = _optional_number(item.payload.get("power_mj_kg"))
    if density is None or power is None:
        warnings.append(f"ВВ «{item.name}»: не заданы плотность или энергия, приняты нули.")
    return ExplosiveCatalogItem(
        key=_legacy_id(item),
        name=item.name,
        density_t_m3=density or 0.0,
        power_mj_kg=power or 0.0,
        chart_label=str(item.payload.get("chart_label") or item.name.upper()),
    )


def _catalog_category(item: ReferenceItem) -> str | None:
    return _CATALOG_CATEGORIES.get(str(item.payload.get("category") or ""))


def _catalog_item(
    item: ReferenceItem,
    prices: Iterable[ReferenceItem],
    units: dict[str, str],
    warnings: list[str],
) -> CatalogItem:
    unit_code = str(item.payload.get("unit") or "")
    return CatalogItem(
        id=_legacy_id(item),
        name=item.name,
        category=_catalog_category(item),  # type: ignore[arg-type]
        unit=units.get(unit_code, unit_code),
        price=_material_price(item, prices, warnings),
        mass_kg=_optional_number(item.payload.get("mass_kg")),
        length_m=_optional_number(item.payload.get("length_m")),
        note=item.comment,
    )


def _material_price(item: ReferenceItem, prices: Iterable[ReferenceItem], warnings: list[str]) -> float:
    """Цена материала в смете V1 — действующая сегодня, вместе с доставкой.

    Раздел «Стоимость материалов» хранит историю: у записи есть срок действия.
    Берём ту, что действует на сегодня, а среди них — с самой поздней датой
    начала (пустая дата считается самой старой). Просроченные и будущие цены
    в смету не попадают.
    """

    today = date.today()
    own = [p for p in prices if str(p.payload.get("material_code") or "") == item.code]
    if not own:
        warnings.append(f"Материал «{item.name}»: в разделе «Стоимость материалов» не задана цена, принят 0.")
        return 0.0
    valid = [
        p
        for p in own
        if (p.valid_from is None or p.valid_from <= today) and (p.valid_to is None or p.valid_to >= today)
    ]
    if not valid:
        warnings.append(
            f"Материал «{item.name}»: срок действия всех цен истек или ещё не наступил, принят 0."
        )
        return 0.0
    latest = max((p.valid_from or date.min) for p in valid)
    candidates = [p for p in valid if (p.valid_from or date.min) == latest]
    if len(candidates) > 1:
        warnings.append(
            f"Материал «{item.name}»: на одну дату задано несколько цен "
            f"({', '.join(p.code for p in candidates)}), взята первая."
        )
    chosen = candidates[0]
    return _number(chosen.payload.get("price_rub")) + _number(chosen.payload.get("delivery_rub"))


def _is_legacy_fixed_cost(item: ReferenceItem) -> bool:
    return str(item.payload.get("legacy_section") or "") in SECTION_TITLES


def _fixed_cost(item: ReferenceItem) -> FixedCostItem:
    return FixedCostItem(
        id=_legacy_id(item),
        section=str(item.payload.get("legacy_section")),
        name=item.name,
        amount_rub=_number(item.payload.get("amount_rub")),
        note=item.comment,
        enabled=item.is_active,
    )


def _position(item: ReferenceItem, rates: dict[str, ReferenceItem], warnings: list[str]) -> JobPosition:
    rate = rates.get(item.code)
    if rate is None:
        warnings.append(f"Должность «{item.name}»: в разделе «Ставки персонала» нет ставки, принят 0.")
    return JobPosition(
        id=_legacy_id(item),
        name=item.name,
        fixed_salary_monthly=_number(rate.payload.get("fixed_monthly_rub")) if rate else 0.0,
        piece_rate_per_m3=_number(rate.payload.get("piece_rate_rub")) if rate else 0.0,
    )


# --- Вспомогательные --------------------------------------------------------


def _legacy_id(item: ReferenceItem) -> str:
    return str(item.payload.get("legacy_ref") or item.code)


def _fallback(reason: str, items: list[T], defaults: Iterable[T], warnings: list[str]) -> tuple[T, ...]:
    """Пустой результат — не ошибка: предупреждение говорит, чего не хватило.

    `reason` описывает нехватку словами интерфейса («нет техники вида …»), а не
    ключом раздела: пустой раздел и раздел без нужных записей — разные случаи.
    """

    if items:
        return tuple(items)
    warnings.append(f"{reason}: используются значения Cost V1 по умолчанию.")
    return tuple(defaults)


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _number(value: Any) -> float:
    parsed = _optional_number(value)
    return parsed if parsed is not None else 0.0
