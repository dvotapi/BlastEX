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
from cost.model.block_margin import _scale_dict
from cost.model.payroll import Scale, pays_by_meters, scale_series
from cost.model.payroll_inputs import _first_error, _labor_rate, _scale
from cost.model.prices import price_lookup
from cost.v2.models import ReferenceItem, ReferenceSnapshot, decimal_value
from cost.v2.schemas.labor import LaborRatePayload

ZERO = Decimal("0")
STEP = Decimal("0.1")

Inputs = tuple[dict[str, Decimal], ModelParameters, ReferenceSnapshot]
Setter = Callable[[Inputs, Decimal], Inputs]


class WhatIfError(ValueError):
    """Подмена не применима: неизвестная ручка или шкала нарушает правила справочника."""


# Статьи строк самой модели бурения в порядке кольца; ФОТ экипажа идёт последним.
COMPONENT_LABELS: tuple[tuple[str, str], ...] = (
    ("DRILL_TOOLING", "Оснастка"),
    ("DRILL_FUEL", "ДТ"),
    ("DRILL_SPARE_PARTS", "Запчасти"),
    ("DRILL_DEPRECIATION", "Амортизация"),
    ("DRILL_INSURANCE", "Страховка"),
    ("DRILL_MAINTENANCE", "ТОиР"),
    ("DRILL_INSPECTION", "Выпуск и медосмотр"),
)
CREW_COMPONENT = ("CREW_PAYROLL", "ФОТ экипажа")


@dataclass(frozen=True)
class Component:
    """Слагаемое стоимости метра: статья строк бурения или ФОТ экипажа, ₽/м."""

    code: str
    label: str
    rub_per_m: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "label": self.label, "rub_per_m": float(self.rub_per_m)}


@dataclass(frozen=True)
class PremiumCurve:
    """Шкала премии машиниста с подменами и ряд графика r(m), p(m); темп — плановый, если методика применилась."""

    scale: dict[str, Any]
    series: list[dict[str, float]]
    pace: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        return {"scale": self.scale, "series": self.series, "pace": _num(self.pace)}


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
    # Слагаемые метра для кольца; пусто, когда бурение не посчитано.
    components: tuple[Component, ...] = ()
    # Кривая премии машиниста (по шкале с подменами); None — шкалы нет.
    premium_curve: PremiumCurve | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "without_payroll_rub_per_m": _num(self.without_payroll),
            "with_payroll_rub_per_m": _num(self.with_payroll),
            "drilling_m": float(self.drilling_m),
            "payroll_source": self.payroll_source,
            "payroll_applied": self.payroll_applied,
            "warnings": list(self.warnings),
            "components": [component.to_dict() for component in self.components],
            "premium_curve": self.premium_curve.to_dict() if self.premium_curve is not None else None,
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
    # Ноль допустим (непроизводительное время); у прочих ручек значение больше нуля.
    allow_zero: bool = False
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
    # Режим «Методика ФОТ» выбран (своими силами); applies ещё сверяется с базовым прогоном.
    mode_on: bool = False


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


def prices(
    result: BlockEconomics,
    params: ModelParameters,
    references: ReferenceSnapshot | None = None,
    *,
    premium_rate_code: str | None = None,
) -> Prices:
    """Две цены метра из посчитанного блока, слагаемые для кольца и кривая премии.

    `premium_rate_code` — ставка машиниста (из `premium`): по ней из `references`
    (уже с подменами) строится кривая шкалы.
    """

    values = result.natural.values
    drilling_m = values.get("drilling_m", ZERO)
    curve = _premium_curve(references, premium_rate_code, result)
    if params.drilling_executor != "OWN" or drilling_m <= 0 or values.get("rig_shifts", ZERO) <= 0:
        return Prices(None, None, drilling_m, params.payroll_source, False, tuple(result.warnings), premium_curve=curve)
    without = values.get("drilling_rub_per_m", ZERO)
    by_item: dict[str, Decimal] = {}
    crew_rub = ZERO
    # Слагаемые станка — только строки самой модели бурения (тождество объекта,
    # как в `block_margin`): правило затрат с той же статьёй в `drilling_rub_per_m`
    # не входит и в кольцо попасть не должно.
    own = {id(line) for line in result.drilling_lines}
    for line in result.lines:
        if line.operation_code not in labor.DRILLING_OPERATIONS:
            continue
        if line.cost_item_code.startswith("LABOR_"):
            crew_rub += line.amount_rub
        elif id(line) in own:
            by_item[line.cost_item_code] = by_item.get(line.cost_item_code, ZERO) + line.amount_rub
    components = tuple(
        Component(code, label, by_item[code] / drilling_m) for code, label in COMPONENT_LABELS if by_item.get(code)
    )
    if crew_rub:
        components = (*components, Component(*CREW_COMPONENT, crew_rub / drilling_m))
    return Prices(
        without_payroll=without,
        with_payroll=without + crew_rub / drilling_m,
        drilling_m=drilling_m,
        payroll_source=params.payroll_source,
        payroll_applied=result.payroll is not None,
        warnings=tuple(result.warnings),
        components=components,
        premium_curve=curve,
    )


def _premium_curve(
    references: ReferenceSnapshot | None, rate_code: str | None, result: BlockEconomics
) -> PremiumCurve | None:
    if references is None or not rate_code:
        return None
    item = references.item("labor_rates", rate_code)
    if item is None:
        return None
    try:
        scale = _scale(LaborRatePayload.model_validate(item.payload), f"labor_rates.{rate_code}")
    except ValidationError:
        return None
    if scale is None:
        return None
    # Плановый темп есть только у применившейся методики; без него ряд — по узлам шкалы.
    pace = decimal_value(result.payroll["pace"]["m_plan"]) if result.payroll is not None else None
    return PremiumCurve(_scale_dict(scale) or {}, _curve_points(scale, pace), pace)


def _curve_points(scale: Scale, pace: Decimal | None) -> list[dict[str, float]]:
    """Те же точки, что `payroll.series` блока экономики (Т6): кривая одна — по которой считают премию."""

    return [
        {"pace": float(point.pace), "rate": float(point.rate), "per_shift": float(point.per_shift)}
        for point in scale_series(scale, pace)
    ]


def _run(
    inputs: Inputs,
    lineage: Mapping[str, str],
    *,
    passport_name: str,
    as_of: date | None,
    premium_rate_code: str | None = None,
) -> Prices:
    physical, params, references = inputs
    result = compute_block_economics(
        {"physical": physical, "lineage": dict(lineage)}, params, references, passport_name=passport_name, as_of=as_of
    )
    return prices(result, params, references, premium_rate_code=premium_rate_code)


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


def knobs(
    params: ModelParameters,
    references: ReferenceSnapshot,
    physical: Mapping[str, Any],
    *,
    as_of: date | None = None,
) -> tuple[Knob, ...]:
    """Ручки стоимости метра по параметрам черновика; чего нет в справочниках — нет и ручки.

    `as_of` — дата расчёта: по ней берётся действующая цена оснастки, как в самом расчёте.
    """

    context = ModelContext(references, params, physical, as_of=as_of)
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
                allow_zero=True,
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


def premium(
    params: ModelParameters,
    references: ReferenceSnapshot,
    physical: Mapping[str, Any],
    *,
    payroll_applied: bool | None = None,
) -> Premium | None:
    """Шкала премии машиниста: первая сдельная должность экипажа бурения со шкалой; нет — None.

    `payroll_applied` — применилась ли методика в базовом прогоне: режим
    «Методика ФОТ» может откатиться на ставки (нет «Параметров ФОТ» года,
    ставки помощника), и тогда шкала цену не двигает, хотя режим выбран.
    """

    context = ModelContext(references, params, physical)
    for position_code, _headcount, _shifts in labor.crew_members(context):
        position = context.item("positions", position_code)
        if position is None or payload_text(position, "operation_code") not in labor.DRILLING_OPERATIONS:
            continue
        # Та же проверка, что у `block_payroll`: премию по шкале получает только
        # сдельщик за приведённые метры; у повременщика шкала в ставке не действует.
        if not pays_by_meters(payload_text(position, "pay_system") or None, payload_text(position, "difficulty") or None):
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
        mode_on = params.payroll_source == "PAYROLL" and params.drilling_executor == "OWN"
        premium_block = Premium(
            position_code,
            position.name,
            rate_item.code,
            scale_type,
            tuple(knob_list),
            applies=mode_on,
            note="" if mode_on else _NOTE_RATES,
            mode_on=mode_on,
        )
        return premium_block if payroll_applied is None else _with_applied(premium_block, payroll_applied)
    return None


def _with_applied(block: Premium, payroll_applied: bool) -> Premium:
    """Сверка с базовым прогоном: режим выбран, но методика откатилась на ставки — шкала не действует."""

    applies = block.mode_on and payroll_applied
    if applies:
        note = ""
    elif block.mode_on:
        note = _NOTE_FALLBACK
    else:
        note = _NOTE_RATES
    return replace(block, applies=applies, note=note)


_NOTE_FALLBACK = "Методика ФОТ к экипажу не применилась (см. «Модель сообщает»): шкала премии цену не двигает."
_NOTE_RATES = "Шкала премии действует только при источнике ФОТ «Методика ФОТ»."


# Соседние поля кривой: (ручка, поле-ограничитель, зазор, «это верхняя граница»).
# Потолок строго выше нормы, расценка на потолке не ниже расценки на норме.
_CURVE_LIMITS: tuple[tuple[str, str, Decimal, bool], ...] = (
    ("PREMIUM_NORM", "PREMIUM_CEILING", Decimal("1"), True),
    ("PREMIUM_CEILING", "PREMIUM_NORM", Decimal("1"), False),
    ("PREMIUM_RATE_NORM", "PREMIUM_RATE_CEILING", ZERO, True),
    ("PREMIUM_RATE_CEILING", "PREMIUM_RATE_NORM", ZERO, False),
)


def premium_bounds(knob_list: Sequence[Knob]) -> dict[str, tuple[Decimal | None, Decimal | None]]:
    """Границы (min, max) ручек кривой по значениям соседних ручек — правила `LaborRatePayload`.

    Плечо ±10 %, вышедшее за границу, сделало бы шкалу недопустимой: методика
    откатилась бы на ставки, и «эффект премии» мерил бы смену способа расчёта.
    """

    values = {knob.code: knob.base for knob in knob_list}
    bounds: dict[str, tuple[Decimal | None, Decimal | None]] = {}
    for code, neighbour, gap, upper in _CURVE_LIMITS:
        if code not in values or neighbour not in values:
            continue
        bounds[code] = (None, values[neighbour] - gap) if upper else (values[neighbour] + gap, None)
    return bounds


def _clamp(value: Decimal, bounds: tuple[Decimal | None, Decimal | None] | None) -> Decimal:
    if bounds is None:
        return value
    low, high = bounds
    if low is not None and value < low:
        return low
    if high is not None and value > high:
        return high
    return value


# --- Расчёт -------------------------------------------------------------------


def _physical(snapshot: Mapping[str, Any]) -> dict[str, Decimal]:
    raw = dict(snapshot).get("physical", snapshot)
    return {str(key): decimal_value(value) for key, value in dict(raw).items()}


def _lineage(snapshot: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in dict(dict(snapshot).get("lineage", {})).items()}


def _price_of(result: Prices) -> Decimal | None:
    return result.with_payroll


def _rows(
    knob_list: Sequence[Knob],
    inputs: Inputs,
    lineage: Mapping[str, str],
    *,
    passport_name: str,
    as_of: date | None,
    base_price: Decimal | None = None,
    bounds: Mapping[str, tuple[Decimal | None, Decimal | None]] | None = None,
) -> list[KnobRow]:
    rows: list[KnobRow] = []
    for knob in knob_list:
        side: list[Decimal | None] = []
        for factor in (Decimal("1") - STEP, Decimal("1") + STEP):
            probe = _clamp(knob.base * factor, bounds.get(knob.code) if bounds else None)
            if probe == knob.base:
                # Плечо упёрлось в границу шкалы: двигать нечего, цена — базовая.
                side.append(base_price)
                continue
            physical, params, references = inputs
            changed = knob.setter((dict(physical), params, references), probe)
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
    # Шкала читается один раз: `applies` зависит от базового прогона и ставится ниже.
    scale = premium(params, references, physical)
    base = _run(
        inputs, lineage, passport_name=passport_name, as_of=as_of, premium_rate_code=scale.rate_code if scale else None
    )
    rows = _rows(
        knobs(params, references, physical, as_of=as_of), inputs, lineage, passport_name=passport_name, as_of=as_of
    )
    rows.sort(key=lambda row: abs(row.delta), reverse=True)
    if scale is not None:
        scale = _with_applied(scale, base.payroll_applied)
    # Недействующая шкала цену не двигает: прогоны ±10 % были бы холостыми.
    premium_rows = (
        _rows(
            scale.knobs,
            inputs,
            lineage,
            passport_name=passport_name,
            as_of=as_of,
            base_price=base.with_payroll,
            bounds=premium_bounds(scale.knobs),
        )
        if scale is not None and scale.applies
        else [KnobRow(knob, base.with_payroll, base.with_payroll) for knob in scale.knobs]
        if scale is not None
        else []
    )
    return Sensitivity(base, tuple(rows), scale, tuple(premium_rows))


def apply_overrides(
    params: ModelParameters,
    references: ReferenceSnapshot,
    physical: Mapping[str, Any],
    overrides: Mapping[str, Decimal],
    *,
    as_of: date | None = None,
    scale: Premium | None = None,
) -> Inputs:
    """Абсолютные значения ручек поверх снимка; неизвестная ручка или кривая шкала — `WhatIfError`.

    `scale` — уже прочитанная шкала премии (из `what_if`), чтобы не читать её второй раз.
    """

    known = {knob.code: knob for knob in knobs(params, references, physical, as_of=as_of)}
    scale = scale if scale is not None else premium(params, references, physical)
    if scale is not None:
        known.update({knob.code: knob for knob in scale.knobs})
    inputs: Inputs = (_physical({"physical": physical}), params, references)
    for code, value in overrides.items():
        knob = known.get(code)
        if knob is None:
            raise WhatIfError(f"Ручка {code} недоступна для этого блока.")
        if value < 0 or (value == 0 and not knob.allow_zero):
            raise WhatIfError(
                f"«{knob.label}»: значение должно быть " + ("не меньше нуля." if knob.allow_zero else "больше нуля.")
            )
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
    scale = premium(params, references, physical)
    rate_code = scale.rate_code if scale is not None else None
    base = _run((physical, params, references), lineage, passport_name=passport_name, as_of=as_of, premium_rate_code=rate_code)
    changed = apply_overrides(params, references, physical, overrides, as_of=as_of, scale=scale)
    return base, _run(changed, lineage, passport_name=passport_name, as_of=as_of, premium_rate_code=rate_code)


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
