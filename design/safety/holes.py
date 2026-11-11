"""Скважины проекта блока в величинах главы XII ФНП 494.

Только чтение `BlastDesign`: длины по декам заряжания, расстояния до
соседей — `design.editing`, масса ПД — у самого ПД или в справочнике
материалов. Проект не меняется.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from design.editing import local_spacing, previous_row_distance, row_index
from design.models import (
    BlastDesign,
    Deck,
    HoleLoad,
    Primer,
    charge_column_bounds_m,
    explosive_charge_mass_kg,
    is_explosive_deck_kind,
    stemming_length_m,
)

__all__ = ["MaterialIndex", "SafetyHole", "material_index", "primer_items", "safety_holes"]


@dataclass(frozen=True)
class SafetyHole:
    """Одна заряженная скважина: всё, что нужно формулам (1), (16), (17)."""

    hole_id: str
    length_m: float          # L — глубина пробуренной скважины
    diameter_m: float        # d — с учётом разбуривания (поле скважины)
    stemming_m: float        # l_заб
    charge_length_m: float   # l_зар — сумма длин взрывчатых дек
    free_length_m: float     # l_св — свободная от заряда верхняя часть
    charge_kg: float         # масса ВВ по декам
    spacing_m: float | None  # между скважинами в ряду
    row_step_m: float | None  # между рядами; у первого ряда нет (ЛСПП — не «между рядами»)
    primer_count: int
    primer_kg: float

    @property
    def capacity_kg_m(self) -> float:
        """P — вместимость 1 м: масса заряда к длине колонки."""
        return self.charge_kg / self.charge_length_m if self.charge_length_m > 0 else 0.0

    @property
    def eta_charge(self) -> float:
        """η_з = l_зар / L."""
        return self.charge_length_m / self.length_m if self.length_m > 0 else 0.0

    @property
    def eta_stemming(self) -> float:
        """η_заб = l_заб / l_св; забойка на всю свободную часть — 1, без забойки — 0."""
        if self.stemming_m <= 0 or self.free_length_m <= 0:
            return 0.0
        return min(1.0, self.stemming_m / self.free_length_m)

    @property
    def distance_m(self) -> float | None:
        """a формулы (1): наименьшее из расстояний в ряду и между рядами."""
        known = [value for value in (self.spacing_m, self.row_step_m) if value is not None and value > 0]
        return min(known) if known else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_id": self.hole_id,
            "length_m": round(self.length_m, 3),
            "diameter_m": round(self.diameter_m, 4),
            "stemming_m": round(self.stemming_m, 3),
            "charge_length_m": round(self.charge_length_m, 3),
            "free_length_m": round(self.free_length_m, 3),
            "charge_kg": round(self.charge_kg, 3),
            "spacing_m": None if self.spacing_m is None else round(self.spacing_m, 3),
            "row_step_m": None if self.row_step_m is None else round(self.row_step_m, 3),
            "primer_count": self.primer_count,
            "primer_kg": round(self.primer_kg, 3),
            "eta_charge": round(self.eta_charge, 4),
            "eta_stemming": round(self.eta_stemming, 4),
        }


@dataclass(frozen=True)
class MaterialIndex:
    """Записи справочника материалов: по коду и по наименованию (без регистра)."""

    by_key: Mapping[str, Mapping[str, Any]]
    items: tuple[Mapping[str, Any], ...]

    def find(self, product: str) -> Mapping[str, Any] | None:
        key = _key(product)
        return self.by_key.get(key) if key else None

    def by_role(self, role: str) -> list[Mapping[str, Any]]:
        return [item for item in self.items if item["payload"].get("nomenclature_role") == role]


def material_index(materials: Iterable[Any] | None) -> MaterialIndex:
    """Материалы в одном виде: {code, name, payload}. Неактивные не берутся.

    Принимает `ReferenceItem` и словари вида `ReferenceItem.to_dict()`.
    """

    items: list[Mapping[str, Any]] = []
    by_key: dict[str, Mapping[str, Any]] = {}
    for raw in materials or ():
        get = raw.get if isinstance(raw, Mapping) else lambda name, default=None, _r=raw: getattr(_r, name, default)
        if get("is_active", True) is False:
            continue
        item = {"code": str(get("code", "") or ""), "name": str(get("name", "") or ""), "payload": dict(get("payload") or {})}
        items.append(item)
        for key in (_key(item["code"]), _key(item["name"])):
            if key:
                by_key.setdefault(key, item)
    items.sort(key=lambda item: item["code"])
    return MaterialIndex(by_key=by_key, items=tuple(items))


def primer_items(load: HoleLoad | None) -> list[Primer]:
    """ПД скважины: объекты, а у старых проектов — глубины без марки."""

    if load is None:
        return []
    if load.primer_items:
        return list(load.primer_items)
    return [Primer(position_m=depth) for depth in load.primers]


def primer_mass_kg(primer: Primer, materials: MaterialIndex) -> float | None:
    """Масса ПД: у самого ПД, иначе масса единицы материала той же марки."""

    if primer.mass_kg > 0:
        return float(primer.mass_kg)
    material = materials.find(primer.product)
    if material is not None:
        try:
            mass = float(material["payload"].get("mass_kg") or 0)
        except (TypeError, ValueError):
            mass = 0.0
        if mass > 0:
            return mass
    return None


def safety_holes(
    design: BlastDesign,
    materials: MaterialIndex,
) -> tuple[list[SafetyHole], list[str], list[str]]:
    """Заряженные включённые скважины; второе — включённые без заряда, третье — ПД без массы."""

    enabled = [hole for hole in design.holes if hole.enabled]
    loads = {load.hole_id: load for load in design.loads}
    rows = row_index(enabled)
    holes: list[SafetyHole] = []
    uncharged: list[str] = []
    no_mass: list[str] = []
    for hole in enabled:
        load = loads.get(hole.id)
        decks = list(load.decks) if load else []
        charge_kg = explosive_charge_mass_kg(decks)
        if charge_kg <= 0:
            uncharged.append(hole.id)
            continue
        primers = primer_items(load)
        primer_kg = 0.0
        for primer in primers:
            mass = primer_mass_kg(primer, materials)
            if mass is None:
                no_mass.append(hole.id)
            else:
                primer_kg += mass
        holes.append(
            SafetyHole(
                hole_id=hole.id,
                length_m=hole.length_m,
                diameter_m=hole.diameter_mm / 1000.0,
                stemming_m=stemming_length_m(decks),
                charge_length_m=_charge_length(decks),
                free_length_m=_free_length(decks),
                charge_kg=charge_kg,
                spacing_m=local_spacing(enabled, hole),
                row_step_m=previous_row_distance(rows, hole),
                primer_count=len(primers),
                primer_kg=primer_kg,
            )
        )
    return holes, uncharged, sorted(set(no_mass))


def _charge_length(decks: list[Deck]) -> float:
    return sum(abs(deck.to_m - deck.from_m) for deck in decks if is_explosive_deck_kind(deck.kind))


def _free_length(decks: list[Deck]) -> float:
    top, _ = charge_column_bounds_m(decks)
    return max(0.0, float(top)) if top is not None else 0.0


def _key(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()
