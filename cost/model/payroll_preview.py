"""Превью ФОТ должности на объекте (TASK-010): строки, сдельная часть, доля в марже, график.

Собирает функции `cost/model/payroll.py` в один расчёт для эндпоинта
`POST /economics/payroll/preview`. План (смены не заданы) — вахта объекта
минус плановое ТОиР; факт — заданные смены минус простои не по вине машиниста.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

from cost.model.payroll import (
    ZERO,
    CrewCost,
    DowntimeEntry,
    EffectiveShifts,
    MarginCheck,
    MeterItem,
    NormalizedMeters,
    PayrollFlag,
    PayrollInputError,
    PayrollInputs,
    PayrollResult,
    PiecePremium,
    PositionPay,
    ScalePoint,
    SharePoint,
    SiteSchedule,
    effective_shifts,
    fn,
    margin_check,
    normalized_meters,
    pace_flags,
    payroll_month,
    piece_premium,
    plan_effective_shifts,
    premium_cost_factor,
    scale_series,
)
from cost.model.payroll_inputs import (
    PIECE_PAY_SYSTEMS,
    PayrollContext,
    difficulty_tables,
    downtime_reasons,
    payroll_inputs,
    position_pay,
    rock_hardness,
)
from cost.v2.models import ReferenceSnapshot


@dataclass(frozen=True)
class PreviewItem:
    meters: Decimal
    diameter_mm: Decimal
    rock_code: str | None = None
    f: Decimal | None = None


@dataclass(frozen=True)
class PreviewRequest:
    position_code: str
    site_code: str
    year: int
    # Пусто — план: вахта объекта минус плановое ТОиР.
    shifts: Decimal | None = None
    downtime: tuple[DowntimeEntry, ...] = ()
    items: tuple[PreviewItem, ...] = ()
    # Приведённые метры (выработка) одной суммой, без разбивки по породам.
    meters_total: Decimal | None = None
    # Сдельщики экипажа на тех же метрах: (должность, человек в смене).
    crew: tuple[tuple[str, Decimal], ...] = ()
    price_rub_per_m: Decimal | None = None
    variable_rub_per_m: Decimal | None = None


@dataclass(frozen=True)
class PayrollPreview:
    position: PositionPay
    site: SiteSchedule
    year: int
    shifts: EffectiveShifts
    result: PayrollResult
    premium_cost_factor: Decimal
    premium_cost_factor_formula: str
    margin: MarginCheck
    meters: NormalizedMeters | None = None
    premium: PiecePremium | None = None
    series: tuple[ScalePoint, ...] = ()
    flags: tuple[PayrollFlag, ...] = ()
    warnings: tuple[str, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        scale = self.position.scale
        return {
            "position_code": self.position.code,
            "position_name": self.position.name,
            "site_code": self.site.code,
            "year": self.year,
            "rows": [
                {"code": row.code, "name": row.name, "kind": row.kind, "amount_rub": float(row.amount), "formula": row.formula}
                for row in self.result.rows
            ],
            "gross_rub": float(self.result.gross),
            "company_cost_rub": float(self.result.company_cost),
            "meters": _meters_dict(self.meters),
            "shifts": {
                "shifts": float(self.shifts.shifts),
                "effective": float(self.shifts.effective),
                "excusable_hours": float(self.shifts.excusable_hours),
                "maintenance_hours": float(self.shifts.maintenance_hours),
                "written_off_share": _num(self.shifts.written_off_share),
            },
            "premium": _premium_dict(self.premium, scale),
            "premium_cost_factor": float(self.premium_cost_factor),
            "premium_cost_factor_formula": self.premium_cost_factor_formula,
            "margin": _margin_dict(self.margin),
            "series": [
                {"pace": float(point.pace), "rate": float(point.rate), "per_shift": float(point.per_shift)}
                for point in self.series
            ],
            "flags": [{"code": flag.code, "message": flag.message} for flag in self.flags],
            "warnings": list(self.warnings),
            "lineage": dict(self.lineage),
        }


def _num(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _meters_dict(meters: NormalizedMeters | None) -> dict[str, Any] | None:
    if meters is None:
        return None
    return {
        "total": float(meters.total),
        "physical": float(meters.physical),
        "contract_k": float(meters.contract_k),
        "factor": float(meters.factor),
        "rows": [
            {
                "label": row.label,
                "meters": float(row.meters),
                "f": _num(row.f),
                "k_f": float(row.k_f),
                "diameter_mm": float(row.diameter_mm),
                "k_d": float(row.k_d),
                "normalized": float(row.normalized),
            }
            for row in meters.rows
        ],
    }


def _premium_dict(premium: PiecePremium | None, scale: Any) -> dict[str, Any] | None:
    if premium is None or scale is None:
        return None
    return {
        "scale_type": scale.scale_type,
        "gamma": _num(scale.gamma),
        "norm_per_shift": _num(scale.norm_per_shift),
        "rate_norm": _num(scale.rate_norm),
        "ceiling_per_shift": _num(scale.ceiling_per_shift),
        "rate_ceiling": _num(scale.rate_ceiling),
        "output": float(premium.output),
        "effective_shifts": float(premium.effective_shifts),
        "pace": float(premium.pace),
        "per_shift": float(premium.per_shift),
        "last_rate": float(premium.last_rate),
        "mean_rate": _num(premium.mean_rate),
        "total": float(premium.total),
        "tiers": [
            {
                "lower": float(tier.lower),
                "upper": _num(tier.upper),
                "rate": float(tier.rate),
                "units": float(tier.units),
                "amount": float(tier.amount),
            }
            for tier in premium.tiers
        ],
    }


def _point_dict(point: SharePoint | None) -> dict[str, Any] | None:
    if point is None:
        return None
    return {"pace": float(point.pace), "crew_share": float(point.crew_share), "main_share": float(point.main_share)}


def _margin_dict(margin: MarginCheck) -> dict[str, Any]:
    return {
        "status": margin.status,
        "threshold": float(margin.threshold),
        "price_rub_per_m": _num(margin.price),
        "variable_rub_per_m": _num(margin.variable),
        "margin_rub_per_m": _num(margin.margin),
        "plan": _point_dict(margin.plan),
        "ceiling": _point_dict(margin.ceiling),
        "crew": [
            {
                "position_code": member.position_code,
                "name": member.name,
                "headcount": float(member.headcount),
                "cost_factor": float(member.cost_factor),
            }
            for member in margin.crew
        ],
    }


def _shifts(snapshot: ReferenceSnapshot, request: PreviewRequest, context: PayrollContext) -> EffectiveShifts:
    if request.shifts is None:
        if request.downtime:
            raise PayrollInputError("Простои задаются вместе с фактическими сменами вахты.")
        return plan_effective_shifts(context.site.shift_days_on, context.site.maintenance_shifts)
    return effective_shifts(request.shifts, context.rates.shift_hours, request.downtime, downtime_reasons(snapshot))


def _output(
    snapshot: ReferenceSnapshot, request: PreviewRequest, position: PositionPay, site: SiteSchedule
) -> tuple[NormalizedMeters, list[str]]:
    """Выработка для шкалы: приведённые метры по породам, сумма метров или сумма запроса."""

    if request.meters_total is not None:
        return (
            NormalizedMeters(
                total=request.meters_total,
                physical=request.meters_total,
                lineage={"normalized_meters": f"задано суммой: {fn(request.meters_total)}"},
            ),
            [],
        )
    if not request.items:
        return NormalizedMeters(ZERO, ZERO), ["Выработка не задана: сдельная премия 0."]
    if position.difficulty != "NORMALIZED_METERS":
        total = sum((item.meters for item in request.items), ZERO)
        return (
            NormalizedMeters(total, total, lineage={"normalized_meters": f"Σ выработки = {fn(total)} (без приведения)"}),
            [],
        )
    items = []
    for index, item in enumerate(request.items):
        f = rock_hardness(snapshot, item.rock_code) if item.rock_code else item.f
        label = f"{item.rock_code or 'порода'}, Ø {fn(item.diameter_mm)} мм"
        items.append(MeterItem(item.meters, item.diameter_mm, f, label))
    meters = normalized_meters(items, difficulty_tables(snapshot), site.contract_k)
    return meters, list(meters.warnings)


def _crew(
    snapshot: ReferenceSnapshot, request: PreviewRequest, main: PositionPay, inputs: PayrollInputs
) -> tuple[list[CrewCost], list[str]]:
    """Сдельщики экипажа: из запроса, иначе все сдельщики с приведёнными метрами и шкалой.

    У машиниста по умолчанию экипаж — машинист и помощник, по одному в смене:
    оба получают премию по шкале на те же приведённые метры.
    """

    warnings: list[str] = []
    if request.crew:
        members = list(request.crew)
    else:
        members = [
            (item.code, Decimal("1"))
            for item in snapshot.active_items("positions")
            if item.payload.get("difficulty") == "NORMALIZED_METERS"
            and item.payload.get("pay_system") in PIECE_PAY_SYSTEMS
        ]
    crew: list[CrewCost] = []
    for code, headcount in members:
        if code == main.code:
            position = main
        else:
            # Предупреждения чтения соседа по экипажу (оклад по МРОТ) здесь
            # лишние: долю в марже считает шкала, а не оклад.
            position, _ = position_pay(snapshot, code, inputs.calendar)
        if position.pay_system not in PIECE_PAY_SYSTEMS:
            # Повременщику премия по шкале не начисляется, даже если шкала заведена.
            warnings.append(f"Должность «{position.name}» в экипаже на повременной оплате: в долю в марже не входит.")
            continue
        if position.scale is None:
            warnings.append(f"Должность «{position.name}» в экипаже без шкалы сдельной премии: в долю в марже не входит.")
            continue
        if position.difficulty != "NORMALIZED_METERS":
            # Шкалу за километр или тонну на темпе бурения не оценить.
            warnings.append(
                f"Должность «{position.name}» в экипаже получает премию не за приведённые метры: "
                "в долю в марже не входит."
            )
            continue
        factor, _ = premium_cost_factor(PayrollInputs(inputs.calendar, position, inputs.site, inputs.rates))
        crew.append(CrewCost(position.code, position.name, headcount, position.scale, factor))
    return crew, warnings


def payroll_preview(snapshot: ReferenceSnapshot, request: PreviewRequest) -> PayrollPreview:
    inputs, context, read_warnings = payroll_inputs(
        snapshot, position_code=request.position_code, site_code=request.site_code, year=request.year
    )
    position = inputs.position
    warnings: list[str] = list(read_warnings)
    lineage: dict[str, str] = dict(context.lineage)
    shifts = _shifts(snapshot, request, context)
    lineage.update(shifts.lineage)
    flags: list[PayrollFlag] = list(shifts.flags)

    meters: NormalizedMeters | None = None
    premium: PiecePremium | None = None
    scale = position.scale
    if position.pay_system not in PIECE_PAY_SYSTEMS:
        if request.items or request.meters_total is not None:
            warnings.append("Повременная оплата: выработка в премию не входит.")
        scale = None
    elif scale is None:
        warnings.append(f"У ставки должности «{position.name}» нет шкалы сдельной премии: премия 0.")
    else:
        meters, meter_warnings = _output(snapshot, request, position, context.site)
        warnings.extend(meter_warnings)
        lineage.update(meters.lineage)
        if meters.contract_k != 1:
            lineage["contract_k"] = f"sites.{context.site.code}.contract_k = {fn(meters.contract_k)}"
        premium = piece_premium(meters.total, scale, shifts.effective)
        lineage.update(premium.lineage)
        flags.extend(pace_flags(scale, premium.pace))

    result = payroll_month(inputs, premium.total if premium is not None else ZERO)
    warnings.extend(result.warnings)
    factor, factor_formula = premium_cost_factor(inputs)
    lineage["premium_cost_factor"] = factor_formula

    # Доля считается в марже метра бурения: только у сдельщиков на приведённых
    # метрах. Расценку водителя за километр с маржой метра не сравнить.
    if premium is not None and position.difficulty == "NORMALIZED_METERS":
        crew, crew_warnings = _crew(snapshot, request, position, inputs)
        warnings.extend(crew_warnings)
        margin = margin_check(
            main_scale=scale,
            crew=crew,
            pace=premium.pace,
            meters_factor=meters.factor if meters is not None else Decimal("1"),
            price=request.price_rub_per_m,
            variable=request.variable_rub_per_m,
            threshold=inputs.calendar.margin_share_warn,
        )
    else:
        margin = MarginCheck("NOT_APPLICABLE", inputs.calendar.margin_share_warn)
    warnings.extend(margin.warnings)
    if request.meters_total is not None and margin.status == "CHECKED":
        warnings.append(
            "Метры заданы суммой приведённых: доля в марже считается на приведённый метр, а не на погонный; "
            "для доли на погонный метр задайте метры по породам и диаметрам."
        )
    flags.extend(margin.flags)
    lineage.update(margin.lineage)

    unique: list[str] = []
    for warning in warnings:
        if warning not in unique:
            unique.append(warning)
    return PayrollPreview(
        position=position,
        site=context.site,
        year=inputs.calendar.year,
        shifts=shifts,
        result=result,
        premium_cost_factor=factor,
        premium_cost_factor_formula=factor_formula,
        margin=margin,
        meters=meters,
        premium=premium,
        series=scale_series(scale, premium.pace) if scale is not None and premium is not None else (),
        flags=tuple(flags),
        warnings=tuple(unique),
        lineage=lineage,
    )
