"""Что двигает цену метра бурения: ручки, их чувствительность и «что если».

Страница «Бурение» показывает стоимость метра собственного бурения и даёт
покрутить самые сильные ручки, не трогая черновик и справочники. Для этого
модуль:

- собирает список ручек по параметрам черновика (`knobs`): скорость и
  простой выбранного условия бурения, плановые смены станка, цена ДТ объекта,
  стойкость и цена оснастки, численность экипажа — плюс шкала сдельной премии
  машиниста (`premium`);
- считает чувствительность (`compute`): ±10 % по каждой ручке, два прогона
  движка на ручку, сортировка по |Δ| цены метра с ФОТ экипажа — тот же
  приём, что у `cost/model/sensitivity.py` для цены м³;
- подменяет абсолютные значения ручек в памяти (`apply_overrides`) и
  считает две цены метра (`what_if`): без ФОТ и с ФОТ экипажа бурения.

Цены — себестоимость, без ОХР и рентабельности, как «Стоимость 1 п.м.» на
странице: без ФОТ — `drilling_rub_per_m` (строки самой модели бурения:
оснастка, ДТ, запчасти, амортизация, страховка, ТО); с ФОТ — плюс строки
ФОТ экипажа операций бурения на метр (ставки или методика — по
`payroll_source`; взносы и суточные лежат без операции и в цену не входят,
как и в `block_margin`). Шкала премии двигает цену только при методике ФОТ;
при ставках ручки премии отдаются с пометкой, что не действуют.

Подмены — только в памяти запроса: справочники и черновик не меняются, в
ответе нет ничего, что можно было бы сохранить.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from pydantic import ValidationError

from cost.model import drilling, labor
from cost.model.engine import compute_block_economics
from cost.model.inputs import BlockEconomics, ModelContext, ModelParameters, payload_number, payload_text
from cost.model.payroll_inputs import _first_error, _labor_rate
from cost.model.prices import price_lookup
from cost.v2.models import ReferenceItem, ReferenceSnapshot, decimal_value
from cost.v2.schemas.labor import LaborRatePayload

ZERO = Decimal("0")
STEP = Decimal("0.1")

Inputs = tuple[dict[str, Decimal], ModelParameters, ReferenceSnapshot]
Setter = Callable[[Inputs, Decimal], Inputs]


class WhatIfError(ValueError):
    """Подмена не применима: неизвестная ручка или шкала нарушает правила справочника."""


@dataclass(frozen=True)
class Prices:
    """Две цены метра собственного бурения; None — бурение не посчитано (нет нормы, субподряд)."""

    without_payroll: Decimal | None
    with_payroll: Decimal | None
    drilling_m: Decimal
    payroll_source: str
    # Методика ФОТ реально применилась (блок `payroll` в ответе есть).
    payroll_applied: bool
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "without_payroll_rub_per_m": _num(self.without_payroll),
            "with_payroll_rub_per_m": _num(self.with_payroll),
            "drilling_m": float(self.drilling_m),
            "payroll_source": self.payroll_source,
            "payroll_applied": self.payroll_applied,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class Knob:
    code: str
    label: str
    unit: str
    # Текущее значение справочника или параметра — база бегунка.
    base: Decimal
    # Откуда взято: `drilling_conditions.COND_1.tech_speed_m_per_h`, `параметр вкладки`.
    source: str
    setter: Setter = field(repr=False, compare=False)
    # Ручка — настоящий параметр черновика (плановые смены): в ранжировании
    # показывается, но «что если» по ней не нужно — есть свой бегунок.
    draft_param: bool = False
    group: str = "cost"


@dataclass(frozen=True)
class KnobRow:
    knob: Knob
    price_minus: Decimal | None
    price_plus: Decimal | None

    @property
    def delta(self) -> Decimal:
        if self.price_minus is None or self.price_plus is None:
            return ZERO
        return self.price_plus - self.price_minus

    def to_dict(self) -> dict[str, Any]:
        knob = self.knob
        return {
            "code": knob.code,
            "label": knob.label,
            "unit": knob.unit,
            "base_value": float(knob.base),
            "source": knob.source,
            "draft_param": knob.draft_param,
            "price_minus_rub_per_m": _num(self.price_minus),
            "price_plus_rub_per_m": _num(self.price_plus),
            "delta_rub_per_m": float(self.delta),
        }


@dataclass(frozen=True)
class Premium:
    """Шкала сдельной премии машиниста: ставка должности выбранного экипажа."""

    position_code: str
    position_name: str
    rate_code: str
    scale_type: str
    knobs: tuple[Knob, ...]
    # Шкала двигает цену метра только при методике ФОТ.
    applies: bool
    note: str = ""


@dataclass(frozen=True)
class Sensitivity:
    base: Prices
    rows: tuple[KnobRow, ...]
    premium: Premium | None
    premium_rows: tuple[KnobRow, ...]

    def to_dict(self) -> dict[str, Any]:
        premium = None
        if self.premium is not None:
            premium = {
                "position_code": self.premium.position_code,
                "position_name": self.premium.position_name,
                "scale_type": self.premium.scale_type,
                "applies": self.premium.applies,
                "note": self.premium.note,
                "knobs": [row.to_dict() for row in self.premium_rows],
            }
        return {"base": self.base.to_dict(), "knobs": [row.to_dict() for row in self.rows], "premium": premium}


# --- Цены ------------------------------------------------------------------


def prices(result: BlockEconomics, params: ModelParameters) -> Prices:
    """Две цены метра из посчитанного блока."""

    values = result.natural.values
    drilling_m = values.get("drilling_m", ZERO)
    if params.drilling_executor != "OWN" or drilling_m <= 0 or values.get("rig_shifts", ZERO) <= 0:
        return Prices(None, None, drilling_m, params.payroll_source, False, tuple(result.warnings))
    without = values.get("drilling_rub_per_m", ZERO)
    crew_rub = sum(
        (
            line.amount_rub
            for line in result.lines
            if line.operation_code in labor.DRILLING_OPERATIONS and line.cost_item_code.startswith("LABOR_")
        ),
        ZERO,
    )
    return Prices(
        without_payroll=without,
        with_payroll=without + crew_rub / drilling_m,
        drilling_m=drilling_m,
        payroll_source=params.payroll_source,
        payroll_applied=result.payroll is not None,
        warnings=tuple(result.warnings),
    )


def _run(inputs: Inputs, lineage: Mapping[str, str], *, passport_name: str, as_of: date | None) -> Prices:
    physical, params, references = inputs
    result = compute_block_economics(
        {"physical": physical, "lineage": dict(lineage)}, params, references, passport_name=passport_name, as_of=as_of
    )
    return prices(result, params)


# --- Подмены ----------------------------------------------------------------


def _set_reference(section: str, code: str, field_name: str) -> Setter:
    def setter(inputs: Inputs, value: Decimal) -> Inputs:
        physical, params, references = inputs
        updated = tuple(
            replace(item, payload={**item.payload, field_name: str(value)}) if item.code == code else item
            for item in references.sections.get(section, ())
        )
        return physical, params, replace(references, sections={**references.sections, section: updated})

    return setter


def _set_material_price(material_code: str) -> Setter:
    """Цена материала: все записи прайс-листа по коду, чтобы действующая на дату тоже сменилась."""

    def setter(inputs: Inputs, value: Decimal) -> Inputs:
        physical, params, references = inputs
        updated = tuple(
            replace(item, payload={**item.payload, "price_rub": str(value), "delivery_rub": "0"})
            if payload_text(item, "material_code") == material_code
            else item
            for item in references.sections.get("material_prices", ())
        )
        return physical, params, replace(references, sections={**references.sections, "material_prices": updated})

    return setter


def _set_param(name: str) -> Setter:
    def setter(inputs: Inputs, value: Decimal) -> Inputs:
        physical, params, references = inputs
        return physical, replace(params, **{name: value}), references

    return setter


def _set_tier_rate(rate_code: str, index: int) -> Setter:
    def setter(inputs: Inputs, value: Decimal) -> Inputs:
        physical, params, references = inputs
        updated: list[ReferenceItem] = []
        for item in references.sections.get("labor_rates", ()):
            if item.code != rate_code:
                updated.append(item)
                continue
            tiers = [dict(tier) for tier in item.payload.get("tiers", ())]
            tiers[index] = {**tiers[index], "rate": str(value)}
            updated.append(replace(item, payload={**item.payload, "tiers": tiers}))
        return physical, params, replace(references, sections={**references.sections, "labor_rates": tuple(updated)})

    return setter


def _chain(*setters: Setter) -> Setter:
    def setter(inputs: Inputs, value: Decimal) -> Inputs:
        for step in setters:
            inputs = step(inputs, value)
        return inputs

    return setter


# --- Ручки -------------------------------------------------------------------


TOOLING_LABELS = {
    "bit_material_code": ("Стойкость коронки", "Цена коронки"),
    "hammer_material_code": ("Стойкость ППУ", "Цена ППУ"),
    "rods_material_code": ("Стойкость штанг", "Цена штанг"),
}


def knobs(params: ModelParameters, references: ReferenceSnapshot, physical: Mapping[str, Any]) -> tuple[Knob, ...]:
    """Ручки стоимости метра по параметрам черновика; чего нет в справочниках — нет и ручки."""

    context = ModelContext(references, params, physical)
    result: list[Knob] = []
    rock_code = payload_text(context.site, "rock_code") or None
    condition, _ = drilling.pick_condition(context, params.rig_code, rock_code, params.site_code)
    rig_type = context.item("equipment_types", params.rig_code) if params.rig_code else None
    if condition is not None:
        where = f"drilling_conditions.{condition.code}"
        result.append(
            Knob(
                "TECH_SPEED",
                "Техническая скорость станка",
                "м/ч",
                payload_number(condition, "tech_speed_m_per_h"),
                f"{where}.tech_speed_m_per_h",
                _set_reference("drilling_conditions", condition.code, "tech_speed_m_per_h"),
            )
        )
        result.append(
            Knob(
                "UNPRODUCTIVE_H",
                "Непроизводительное время в смене",
                "ч/см",
                payload_number(condition, "unproductive_h_per_shift"),
                f"{where}.unproductive_h_per_shift",
                _set_reference("drilling_conditions", condition.code, "unproductive_h_per_shift"),
            )
        )
        for code_field, life_field, _label in drilling.TOOLING_PARTS:
            material_code = payload_text(condition, code_field)
            life = payload_number(condition, life_field)
            if not material_code or life <= 0:
                continue
            prefix = code_field.removesuffix("_material_code").upper()
            life_label, price_label = TOOLING_LABELS[code_field]
            result.append(
                Knob(
                    f"{prefix}_LIFE",
                    life_label,
                    "м",
                    life,
                    f"{where}.{life_field}",
                    _set_reference("drilling_conditions", condition.code, life_field),
                )
            )
            lookup = price_lookup(context, material_code)
            if lookup.chosen is not None:
                price = decimal_value(lookup.chosen.payload.get("price_rub")) + decimal_value(
                    lookup.chosen.payload.get("delivery_rub")
                )
                result.append(
                    Knob(
                        f"{prefix}_PRICE",
                        price_label,
                        "₽",
                        price,
                        f"material_prices.{lookup.chosen.code}.price_rub",
                        _set_material_price(material_code),
                    )
                )
    plan_shifts = params.rig_plan_shifts or payload_number(rig_type, "norm_shifts_per_month")
    if plan_shifts > 0:
        result.append(
            Knob(
                "RIG_PLAN_SHIFTS",
                "Плановые смены станка",
                "см/мес",
                plan_shifts,
                "параметр вкладки" if params.rig_plan_shifts else f"equipment_types.{params.rig_code}.norm_shifts_per_month",
                _set_param("rig_plan_shifts"),
                draft_param=True,
            )
        )
    if context.site is not None and payload_number(context.site, "diesel_price_ton_rub") > 0:
        result.append(
            Knob(
                "DIESEL_PRICE",
                "Цена дизельного топлива",
                "₽/т",
                payload_number(context.site, "diesel_price_ton_rub"),
                f"sites.{context.site.code}.diesel_price_ton_rub",
                _set_reference("sites", context.site.code, "diesel_price_ton_rub"),
            )
        )
    result.append(
        Knob(
            "CREW_SCALE",
            "Численность экипажа",
            "×",
            params.crew_scale,
            "множитель людей в смене",
            _set_param("crew_scale"),
        )
    )
    return tuple(result)


PREMIUM_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("PREMIUM_NORM", "norm_per_shift", "Норма за смену", "прив. м/см"),
    ("PREMIUM_RATE_NORM", "rate_norm", "Расценка на норме", "₽/прив. м"),
    ("PREMIUM_CEILING", "ceiling_per_shift", "Потолок за смену", "прив. м/см"),
    ("PREMIUM_RATE_CEILING", "rate_ceiling", "Расценка на потолке", "₽/прив. м"),
)


def premium(params: ModelParameters, references: ReferenceSnapshot, physical: Mapping[str, Any]) -> Premium | None:
    """Шкала премии машиниста: первая сдельная должность экипажа бурения со шкалой; нет — None."""

    context = ModelContext(references, params, physical)
    for position_code, _headcount, _shifts in labor.crew_members(context):
        position = context.item("positions", position_code)
        if position is None or payload_text(position, "operation_code") not in labor.DRILLING_OPERATIONS:
            continue
        rate_item, _note = _labor_rate(references, position_code)
        if rate_item is None or not rate_item.payload.get("scale_type"):
            continue
        scale_type = str(rate_item.payload["scale_type"])
        where = f"labor_rates.{rate_item.code}"
        knob_list: list[Knob] = []
        if scale_type == "STEP":
            tiers = rate_item.payload.get("tiers") or ()
            for index, tier in enumerate(tiers):
                if not isinstance(tier, Mapping):
                    continue
                upto = tier.get("upto_per_shift")
                label = f"Расценка ступени {index + 1}" + (f" (до {upto})" if upto not in (None, "") else " (выше)")
                knob_list.append(
                    Knob(
                        f"PREMIUM_TIER_RATE_{index}",
                        label,
                        "₽/прив. м",
                        decimal_value(tier.get("rate")),
                        f"{where}.tiers[{index}].rate",
                        _set_tier_rate(rate_item.code, index),
                        group="premium",
                    )
                )
        else:
            for code, field_name, label, unit in PREMIUM_FIELDS:
                value = rate_item.payload.get(field_name)
                if value in (None, ""):
                    continue
                knob_list.append(
                    Knob(
                        code,
                        label,
                        unit,
                        decimal_value(value),
                        f"{where}.{field_name}",
                        _set_reference("labor_rates", rate_item.code, field_name),
                        group="premium",
                    )
                )
        applies = params.payroll_source == "PAYROLL" and params.drilling_executor == "OWN"
        note = "" if applies else "Шкала премии действует только при источнике ФОТ «Методика ФОТ»."
        return Premium(position_code, position.name, rate_item.code, scale_type, tuple(knob_list), applies, note)
    return None


# --- Расчёт -------------------------------------------------------------------


def _physical(snapshot: Mapping[str, Any]) -> dict[str, Decimal]:
    raw = dict(snapshot).get("physical", snapshot)
    return {str(key): decimal_value(value) for key, value in dict(raw).items()}


def _lineage(snapshot: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(dict(snapshot).get("lineage", {})).items()}


def _price_of(result: Prices) -> Decimal | None:
    return result.with_payroll


def _rows(
    knob_list: Sequence[Knob], inputs: Inputs, lineage: Mapping[str, str], *, passport_name: str, as_of: date | None
) -> list[KnobRow]:
    rows: list[KnobRow] = []
    for knob in knob_list:
        side: list[Decimal | None] = []
        for factor in (Decimal("1") - STEP, Decimal("1") + STEP):
            physical, params, references = inputs
            changed = knob.setter((dict(physical), params, references), knob.base * factor)
            side.append(_price_of(_run(changed, lineage, passport_name=passport_name, as_of=as_of)))
        rows.append(KnobRow(knob, side[0], side[1]))
    return rows


def compute(
    snapshot: Mapping[str, Any],
    params: ModelParameters,
    references: ReferenceSnapshot,
    *,
    passport_name: str = "Блок",
    as_of: date | None = None,
) -> Sensitivity:
    """Ручки цены метра, отсортированные по |Δ| цены с ФОТ экипажа при ±10 %."""

    physical = _physical(snapshot)
    lineage = _lineage(snapshot)
    inputs: Inputs = (physical, params, references)
    base = _run(inputs, lineage, passport_name=passport_name, as_of=as_of)
    rows = _rows(knobs(params, references, physical), inputs, lineage, passport_name=passport_name, as_of=as_of)
    rows.sort(key=lambda row: abs(row.delta), reverse=True)
    scale = premium(params, references, physical)
    premium_rows = (
        _rows(scale.knobs, inputs, lineage, passport_name=passport_name, as_of=as_of) if scale is not None else []
    )
    return Sensitivity(base, tuple(rows), scale, tuple(premium_rows))


def apply_overrides(
    params: ModelParameters,
    references: ReferenceSnapshot,
    physical: Mapping[str, Any],
    overrides: Mapping[str, Decimal],
) -> Inputs:
    """Абсолютные значения ручек поверх снимка; неизвестная ручка или кривая шкала — `WhatIfError`."""

    known = {knob.code: knob for knob in knobs(params, references, physical)}
    scale = premium(params, references, physical)
    if scale is not None:
        known.update({knob.code: knob for knob in scale.knobs})
    inputs: Inputs = (_physical({"physical": physical}), params, references)
    for code, value in overrides.items():
        knob = known.get(code)
        if knob is None:
            raise WhatIfError(f"Ручка {code} недоступна для этого блока.")
        if value <= 0:
            raise WhatIfError(f"«{knob.label}»: значение должно быть больше нуля.")
        inputs = knob.setter(inputs, value)
    if scale is not None and any(code in {knob.code for knob in scale.knobs} for code in overrides):
        rate_item = inputs[2].item("labor_rates", scale.rate_code)
        try:
            LaborRatePayload.model_validate(rate_item.payload if rate_item is not None else {})
        except ValidationError as exc:
            raise WhatIfError(f"Шкала премии не проходит проверку справочника: {_first_error(exc)}") from exc
    return inputs


def what_if(
    snapshot: Mapping[str, Any],
    params: ModelParameters,
    references: ReferenceSnapshot,
    overrides: Mapping[str, Decimal],
    *,
    passport_name: str = "Блок",
    as_of: date | None = None,
) -> tuple[Prices, Prices]:
    """Цены метра на базе и с подменёнными ручками: (база, результат)."""

    physical = _physical(snapshot)
    lineage = _lineage(snapshot)
    base = _run((physical, params, references), lineage, passport_name=passport_name, as_of=as_of)
    changed = apply_overrides(params, references, physical, overrides)
    return base, _run(changed, lineage, passport_name=passport_name, as_of=as_of)


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
