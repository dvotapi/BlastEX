"""Чувствительность полной цены м³ к ключевым параметрам.

Детерминированный перебор ±10 % по фиксированному списку: два прогона движка
на параметр, никакой оптимизации. Задача таблицы — показать, какие три ручки
двигают цену сильнее всего.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Callable, Mapping

from cost.model.engine import compute_block_economics
from cost.model.inputs import CrewMember, ModelParameters
from cost.model.labor import crew_members
from cost.v2.models import ReferenceItem, ReferenceSnapshot, decimal_value
from cost.v2.technical_adapter import TechnicalDriverSnapshot


STEP = Decimal("0.1")

Inputs = tuple[dict[str, Decimal], ModelParameters, ReferenceSnapshot]
Transform = Callable[[Inputs, Decimal], Inputs]


@dataclass(frozen=True)
class SensitivityRow:
    code: str
    label: str
    base_price: Decimal
    price_minus: Decimal
    price_plus: Decimal

    @property
    def delta(self) -> Decimal:
        return self.price_plus - self.price_minus

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "base_price_rub_m3": float(self.base_price),
            "price_minus_rub_m3": float(self.price_minus),
            "price_plus_rub_m3": float(self.price_plus),
            "delta_rub_m3": float(self.delta),
        }


def _scale_physical(*keys: str) -> Transform:
    def transform(inputs: Inputs, factor: Decimal) -> Inputs:
        physical, params, references = inputs
        updated = dict(physical)
        for key in keys:
            if key in updated:
                updated[key] = updated[key] * factor
        return updated, params, references

    return transform


def _scale_param(field: str) -> Transform:
    def transform(inputs: Inputs, factor: Decimal) -> Inputs:
        physical, params, references = inputs
        current = getattr(params, field)
        if current is None:
            return inputs
        return physical, replace(params, **{field: current * factor}), references

    return transform


def _scale_crew(inputs: Inputs, factor: Decimal) -> Inputs:
    physical, params, references = inputs
    crew = params.crew
    if not crew:
        return inputs
    scaled = tuple(
        CrewMember(
            position_code=member.position_code,
            headcount=member.headcount * factor,
            shifts_per_block=member.shifts_per_block,
        )
        for member in crew
    )
    return physical, replace(params, crew=scaled), references


def _scale_reference(
    section: str, field: str, predicate: Callable[[ReferenceItem], bool] | None = None
) -> Transform:
    def transform(inputs: Inputs, factor: Decimal) -> Inputs:
        physical, params, references = inputs
        items = references.sections.get(section, ())
        updated: list[ReferenceItem] = []
        for item in items:
            value = item.payload.get(field)
            if value in (None, "") or (predicate is not None and not predicate(item)):
                updated.append(item)
                continue
            payload = dict(item.payload)
            payload[field] = str(decimal_value(value) * factor)
            updated.append(replace(item, payload=payload))
        sections = dict(references.sections)
        sections[section] = tuple(updated)
        return physical, params, replace(references, sections=sections)

    return transform


def _is_explosive_driver(item: ReferenceItem) -> bool:
    return str(item.payload.get("driver", "")) in {"explosive_kg", "bulk_kg", "cartridge_kg"}


PARAMETERS: tuple[tuple[str, str, Transform], ...] = (
    ("EXPLOSIVE_PRICE", "Цена ВВ (ставки правил по массе ВВ)", _scale_reference("cost_rules", "rate_rub", _is_explosive_driver)),
    ("EXPLOSIVE_KG", "Масса ВВ на блок", _scale_physical("explosive_kg", "bulk_kg", "cartridge_kg")),
    ("DRILLING_M", "Погонаж бурения", _scale_physical("drilling_m")),
    ("UNIT_PLAN_VOLUME", "Плановый объём юнита", _scale_param("unit_plan_volume_m3")),
    ("RIG_PLAN_SHIFTS", "Плановые смены станка", _scale_param("rig_plan_shifts")),
    ("CREW_HEADCOUNT", "Численность бригады", _scale_crew),
    ("DIESEL_PRICE", "Цена дизельного топлива", _scale_reference("sites", "diesel_price_ton_rub")),
    ("PIECE_RATE", "Сдельные расценки", _scale_reference("labor_rates", "piece_rate_rub")),
)


def compute(
    snapshot: TechnicalDriverSnapshot | Mapping[str, Any],
    params: ModelParameters,
    references: ReferenceSnapshot,
    *,
    passport_name: str = "Блок",
) -> list[SensitivityRow]:
    base_params = _materialize_crew(snapshot, params, references)
    physical = _physical(snapshot)
    base = compute_block_economics(
        {"physical": physical, "lineage": _lineage(snapshot)},
        base_params,
        references,
        passport_name=passport_name,
    )
    base_price = base.price_per_m3.get("full", Decimal("0"))
    lineage = _lineage(snapshot)

    rows: list[SensitivityRow] = []
    for code, label, transform in PARAMETERS:
        prices: list[Decimal] = []
        for factor in (Decimal("1") - STEP, Decimal("1") + STEP):
            changed_physical, changed_params, changed_references = transform(
                (dict(physical), base_params, references), factor
            )
            result = compute_block_economics(
                {"physical": changed_physical, "lineage": lineage},
                changed_params,
                changed_references,
                passport_name=passport_name,
            )
            prices.append(result.price_per_m3.get("full", Decimal("0")))
        rows.append(
            SensitivityRow(
                code=code,
                label=label,
                base_price=base_price,
                price_minus=prices[0],
                price_plus=prices[1],
            )
        )
    rows.sort(key=lambda row: abs(row.delta), reverse=True)
    return rows


def _materialize_crew(
    snapshot: TechnicalDriverSnapshot | Mapping[str, Any],
    params: ModelParameters,
    references: ReferenceSnapshot,
) -> ModelParameters:
    """Разложить шаблон бригады в явный состав.

    Иначе перебор по численности ничего не изменит: шаблон пересчитывается
    заново на каждом прогоне.
    """

    if params.crew:
        return params
    from cost.model.inputs import ModelContext  # локально: только ради состава

    context = ModelContext(references, params, _physical(snapshot))
    crew = tuple(
        CrewMember(position_code=code, headcount=headcount, shifts_per_block=shifts)
        for code, headcount, shifts in crew_members(context)
    )
    return replace(params, crew=crew) if crew else params


def _physical(snapshot: TechnicalDriverSnapshot | Mapping[str, Any]) -> dict[str, Decimal]:
    if isinstance(snapshot, TechnicalDriverSnapshot):
        return dict(snapshot.physical)
    data = dict(snapshot)
    raw = data.get("physical", data)
    return {str(key): decimal_value(value) for key, value in dict(raw).items()}


def _lineage(snapshot: TechnicalDriverSnapshot | Mapping[str, Any]) -> dict[str, str]:
    if isinstance(snapshot, TechnicalDriverSnapshot):
        return dict(snapshot.lineage)
    return {str(key): str(value) for key, value in dict(dict(snapshot).get("lineage", {})).items()}
