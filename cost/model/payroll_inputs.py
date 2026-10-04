"""Входы методики ФОТ из снимка справочников (TASK-010).

Записи читаются через схемы разделов: умолчания полей те же, что у формы
справочника, поэтому объект, заведённый до TASK-010, считается по графику
компании 15/15. Нет должности, объекта или параметров года — ошибка входа
(методика без них не считается); нет ставки, ставок организации или таблиц
сложности — предупреждение и значение по умолчанию.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

from pydantic import BaseModel, ValidationError

from cost.model.payroll import (
    ZERO,
    DifficultyTables,
    DowntimeReason,
    HardnessBand,
    PayrollCalendar,
    PayrollInputError,
    PayrollInputs,
    PayrollRates,
    PositionPay,
    Scale,
    ScaleTier,
    SiteSchedule,
    fn,
    week_hours_for,
)
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.payroll_params import payroll_params_for_year
from cost.v2.schemas.labor import LaborRatePayload, PositionPayload
from cost.v2.schemas.misc import RockPayload
from cost.v2.schemas.organization import OrganizationRatesPayload, SitePayload
from cost.v2.schemas.payroll import DowntimeReasonPayload, DrillingDifficultyPayload

PIECE_PAY_SYSTEMS = frozenset({"PIECE_PROGRESSIVE", "PIECE_BONUS"})


@dataclass(frozen=True)
class PayrollContext:
    """Общее для всех должностей одного расчёта: год, объект, ставки организации."""

    calendar: PayrollCalendar
    site: SiteSchedule
    rates: PayrollRates
    warnings: tuple[str, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    where = ".".join(str(part) for part in error.get("loc", ()))
    return f"{where}: {error.get('msg', '')}" if where else str(error.get("msg", ""))


def _parse(model: type[BaseModel], item: ReferenceItem, what: str) -> BaseModel:
    try:
        return model.model_validate(item.payload)
    except ValidationError as exc:
        raise PayrollInputError(f"{what} {item.code} не проходит проверку справочника ({_first_error(exc)}).") from exc


def payroll_context(snapshot: ReferenceSnapshot, *, site_code: str, year: int) -> PayrollContext:
    warnings: list[str] = []
    lineage: dict[str, str] = {}

    choice = payroll_params_for_year(snapshot.sections.get("payroll_params", ()), year)
    if choice is None:
        raise PayrollInputError("Нет параметров ФОТ года (раздел «Параметры ФОТ»): методика не считается.")
    if choice.note:
        warnings.append(choice.note)
    params = choice.params
    calendar = PayrollCalendar(
        year=params.year,
        mrot=params.mrot,
        annual_hours_40=params.annual_hours_40,
        annual_hours_36=params.annual_hours_36,
        work_days_year=params.work_days_year,
        holidays_year=params.holidays_year,
        night_pct=params.night_pct,
        vacation_days_base=params.vacation_days_base,
        margin_share_warn=params.margin_share_warn,
        source=f"payroll_params.{choice.item.code}",
    )
    lineage["calendar"] = f"{calendar.source} ({calendar.year} год)"

    site_item = snapshot.item("sites", site_code)
    if site_item is None:
        raise PayrollInputError(f"Объект работ {site_code} не найден в справочнике.")
    site_payload = _parse(SitePayload, site_item, "Объект работ")
    site = SiteSchedule(
        code=site_item.code,
        name=site_item.name,
        shift_days_on=site_payload.shift_days_on,
        shift_days_off=site_payload.shift_days_off,
        travel_days=site_payload.travel_days,
        night_shift_share=site_payload.night_shift_share,
        maintenance_shifts=site_payload.maintenance_shifts,
        regional_coefficient=site_payload.regional_coefficient,
        northern_pct=site_payload.northern_pct,
        contract_k=site_payload.contract_k,
        is_remote=site_payload.is_remote,
    )
    lineage["site"] = f"sites.{site.code}"

    rates_item = next(iter(snapshot.active_items("organization_rates")), None)
    if rates_item is None:
        warnings.append(
            "Не заполнен раздел «Ставки и надбавки организации»: взносы, НДФЛ, вахтовая надбавка "
            "и длительность смены взяты по умолчанию."
        )
        rates_payload = OrganizationRatesPayload()
        rates_source = "organization_rates (умолчания)"
    else:
        rates_payload = _parse(OrganizationRatesPayload, rates_item, "Ставки организации")
        rates_source = f"organization_rates.{rates_item.code}"
    if rates_payload.salary_basis == "NET":
        warnings.append("Оклады заданы на руки, а методика ФОТ считает оклад до НДФЛ: проверьте оклады должностей.")
    rates = PayrollRates(
        ndfl_rate=rates_payload.income_tax_rate,
        sfr_rate=rates_payload.social_contribution_rate,
        injury_rate=rates_payload.injury_insurance_rate,
        shift_allowance_per_day=rates_payload.per_diem_rub,
        shift_hours=rates_payload.shift_hours,
        extra_tariffs={row.work_conditions_class: row.rate for row in rates_payload.extra_tariffs},
        source=rates_source,
    )
    lineage["rates"] = rates_source
    return PayrollContext(calendar, site, rates, tuple(warnings), lineage)


def _labor_rate(snapshot: ReferenceSnapshot, position_code: str) -> tuple[ReferenceItem | None, str]:
    """Ставка без условия бурения; иначе первая ставка должности с предупреждением.

    Шкала задаётся только ставкой без условия (Т1): порода уже в приведённых метрах.
    """

    rows = [
        item
        for item in snapshot.active_items("labor_rates")
        if str(item.payload.get("position_code") or "") == position_code
    ]
    plain = next((item for item in rows if not item.payload.get("condition_code")), None)
    if plain is not None:
        return plain, ""
    if rows:
        return rows[0], (
            f"Ставка должности {position_code} взята по условию бурения "
            f"{rows[0].payload.get('condition_code')}: ставки без условия нет."
        )
    return None, ""


def _scale(rate: LaborRatePayload, source: str) -> Scale | None:
    if rate.scale_type is None:
        return None
    return Scale(
        scale_type=rate.scale_type,
        norm_per_shift=rate.norm_per_shift,
        rate_norm=rate.rate_norm,
        ceiling_per_shift=rate.ceiling_per_shift,
        rate_ceiling=rate.rate_ceiling,
        tiers=tuple(ScaleTier(tier.upto_per_shift, tier.rate) for tier in rate.tiers),
        source=source,
    )


def position_pay(
    snapshot: ReferenceSnapshot, position_code: str, calendar: PayrollCalendar
) -> tuple[PositionPay, tuple[str, ...]]:
    """Должность с окладом, неделей и шкалой; оклад не задан — МРОТ года (TASK-010 §2.2)."""

    item = snapshot.item("positions", position_code)
    if item is None:
        raise PayrollInputError(f"Должность {position_code} не найдена в справочнике.")
    position = _parse(PositionPayload, item, "Должность")
    warnings: list[str] = []
    rate_item, note = _labor_rate(snapshot, position_code)
    if note:
        warnings.append(note)
    rate = _parse(LaborRatePayload, rate_item, "Ставка") if rate_item is not None else None
    if rate is not None and rate.fixed_monthly_rub > 0:
        salary, salary_source = rate.fixed_monthly_rub, f"labor_rates.{rate_item.code}"
    else:
        # Пустой оклад ставки — тот же пробел, что отсутствие ставки: уровень I
        # методики — оклад не ниже МРОТ.
        salary, salary_source = calendar.mrot, f"МРОТ {calendar.year} ({calendar.source})"
        warnings.append(
            f"Оклад должности «{item.name}» не задан в «Ставках персонала»: взят МРОТ {fn(calendar.mrot)} ₽."
        )
    scale = _scale(rate, f"labor_rates.{rate_item.code}") if rate is not None else None
    return (
        PositionPay(
            code=item.code,
            name=item.name,
            salary=salary,
            salary_source=salary_source,
            week_hours=week_hours_for(position.work_conditions_class, position.week_hours_override),
            work_conditions_class=position.work_conditions_class,
            hazard_pct=position.hazard_pct,
            night_hours_per_shift=position.night_hours_per_shift,
            extra_vacation_days=position.extra_vacation_days,
            pay_system=position.pay_system,
            difficulty=position.difficulty,
            kpi_bonus_pct=rate.kpi_bonus_pct if rate is not None else ZERO,
            scale=scale,
            per_diem_applies=position.per_diem_applies,
        ),
        tuple(warnings),
    )


def payroll_inputs(
    snapshot: ReferenceSnapshot, *, position_code: str, site_code: str, year: int
) -> tuple[PayrollInputs, PayrollContext, tuple[str, ...]]:
    """Входы `payroll_month` для должности на объекте и предупреждения чтения."""

    context = payroll_context(snapshot, site_code=site_code, year=year)
    position, warnings = position_pay(snapshot, position_code, context.calendar)
    inputs = PayrollInputs(context.calendar, position, context.site, context.rates)
    return inputs, context, (*context.warnings, *warnings)


def difficulty_tables(snapshot: ReferenceSnapshot) -> DifficultyTables:
    """Таблицы «Сложности бурения»; записи нет — пустые таблицы (коэффициенты 1 с предупреждением)."""

    item = next(iter(snapshot.active_items("drilling_difficulty")), None)
    if item is None:
        return DifficultyTables(source="drilling_difficulty (нет записи)")
    payload = _parse(DrillingDifficultyPayload, item, "Сложность бурения")
    return DifficultyTables(
        hardness=tuple(HardnessBand(band.f_from, band.f_to, band.k) for band in payload.hardness),
        diameter={row.diameter_mm: row.k for row in payload.diameter},
        source=f"drilling_difficulty.{item.code}",
    )


def downtime_reasons(snapshot: ReferenceSnapshot) -> dict[str, DowntimeReason]:
    reasons: dict[str, DowntimeReason] = {}
    for item in snapshot.active_items("downtime_reasons"):
        payload = _parse(DowntimeReasonPayload, item, "Причина простоя")
        reasons[item.code] = DowntimeReason(item.code, item.name, payload.excusable, payload.planned_maintenance)
    return reasons


def rock_hardness(snapshot: ReferenceSnapshot, rock_code: str) -> Decimal | None:
    item = snapshot.item("rocks", rock_code)
    if item is None:
        raise PayrollInputError(f"Порода {rock_code} не найдена в справочнике.")
    return _parse(RockPayload, item, "Порода").hardness_f
