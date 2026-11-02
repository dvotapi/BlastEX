"""ТОиР и запчасти техники по возрасту: процент от первоначальной стоимости.

Бюджет ремонта машины растёт с возрастом, поэтому норма — не постоянная
сумма за смену, а ступень шкалы: «до N лет — X % стоимости в год на ТОиР и
Y % на запчасти». Шкала живёт в типе техники (режим ТОиР ``AGE_SCALE``),
дата ввода в эксплуатацию — в основном средстве; возраст считается на дату
расчёта (``ModelContext.as_of``), так что старение машины модель видит сама.

    ₽ за смену = первоначальная стоимость × % ступени / (плановые смены × 12)

База — всегда первоначальная стоимость (решение владельца 02.11.2026), не
остаточная. Чего не хватает (дата, стоимость, плановые смены, ступень) —
ставка нулевая с предупреждением, и вызывающий модуль идёт запасным путём:
прежние поля «₽ за смену».
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cost.model.inputs import ModelContext, formula_number, payload_number, payload_text
from cost.v2.models import ReferenceItem, decimal_value

AGE_SCALE_MODE = "AGE_SCALE"
MONTHS_PER_YEAR = Decimal("12")
DAYS_PER_YEAR = Decimal("365.25")


@dataclass(frozen=True)
class AgeRates:
    """Ставки за смену по ступени шкалы; ``None`` — шкала не применилась."""

    age_years: Decimal
    tier_label: str
    maintenance_pct: Decimal
    spare_parts_pct: Decimal
    maintenance_rub_per_shift: Decimal
    spare_parts_rub_per_shift: Decimal
    initial_cost_rub: Decimal
    plan_shifts: Decimal

    def formula(self, pct: Decimal, rate: Decimal) -> str:
        return (
            f"{formula_number(self.initial_cost_rub)} ₽ × {formula_number(pct)} % / "
            f"({formula_number(self.plan_shifts)} см × 12) = {formula_number(rate)} ₽/см "
            f"(ступень «{self.tier_label}», возраст {formula_number(self.age_years)} лет)"
        )


def uses_age_scale(equipment: ReferenceItem) -> bool:
    return payload_text(equipment, "maintenance_mode", "PER_SHIFT") == AGE_SCALE_MODE


def age_in_years(commissioned_on: date, as_of: date) -> Decimal:
    days = Decimal((as_of - commissioned_on).days)
    return max(days / DAYS_PER_YEAR, Decimal("0"))


def pick_tier(tiers: list[dict], age_years: Decimal) -> dict | None:
    """Первая ступень, чья граница строго больше возраста; последняя — без границы.

    «До 2 лет» — возраст меньше двух: ровно в день второй годовщины машина
    переходит на следующую ступень.
    """

    for tier in tiers:
        upto = tier.get("upto_years")
        if upto in (None, ""):
            return tier
        if age_years < decimal_value(upto):
            return tier
    return None


def age_rates(
    context: ModelContext,
    equipment: ReferenceItem,
    asset: ReferenceItem | None,
    plan_shifts: Decimal,
) -> AgeRates | None:
    """Ставки ТОиР и запчастей за смену по возрасту машины; ``None`` — считать запасным путём."""

    tiers = list(equipment.payload.get("maintenance_age_tiers") or [])
    label = equipment.name
    if not tiers:
        context.warn(f"У техники {label} режим ТОиР «по возрасту», но шкала пуста: ТОиР и запчасти по ставкам за смену.")
        return None
    if asset is None:
        context.warn(f"Для техники {label} не заведено основное средство: ТОиР и запчасти по ставкам за смену.")
        return None
    raw_commissioned = asset.payload.get("commissioned_on")
    commissioned = _commissioned_on(raw_commissioned)
    if commissioned is None:
        reason = "не разобрана" if raw_commissioned else "не задана"
        context.warn(
            f"У основного средства {asset.code} {reason} дата ввода в эксплуатацию"
            + (f" ({raw_commissioned!r})" if raw_commissioned else "")
            + ": ТОиР и запчасти по ставкам за смену."
        )
        return None
    if commissioned > context.as_of:
        # Опечатка в годе дала бы «новую» машину на нижней ступени без следа.
        context.warn(
            f"У основного средства {asset.code} дата ввода {commissioned.isoformat()} позже даты расчёта "
            f"{context.as_of.isoformat()}: возраст принят за ноль, проверьте дату."
        )
    initial = payload_number(asset, "initial_cost_rub")
    if initial <= 0:
        context.warn(f"У основного средства {asset.code} не задана первоначальная стоимость: ТОиР и запчасти по ставкам за смену.")
        return None
    if plan_shifts <= 0:
        context.warn(f"Для техники {label} не заданы плановые смены в месяц: ТОиР и запчасти по ставкам за смену.")
        return None
    age = age_in_years(commissioned, context.as_of)
    tier = pick_tier(tiers, age)
    if tier is None:
        context.warn(f"У техники {label} возраст {formula_number(age)} лет вне шкалы ТОиР: ТОиР и запчасти по ставкам за смену.")
        return None
    maintenance_pct = decimal_value(tier.get("maintenance_pct"))
    spare_parts_pct = decimal_value(tier.get("spare_parts_pct"))
    divisor = plan_shifts * MONTHS_PER_YEAR
    upto = tier.get("upto_years")
    tier_label = f"до {formula_number(decimal_value(upto))} лет" if upto not in (None, "") else "старше"
    return AgeRates(
        age_years=age,
        tier_label=tier_label,
        maintenance_pct=maintenance_pct,
        spare_parts_pct=spare_parts_pct,
        maintenance_rub_per_shift=initial * maintenance_pct / Decimal("100") / divisor,
        spare_parts_rub_per_shift=initial * spare_parts_pct / Decimal("100") / divisor,
        initial_cost_rub=initial,
        plan_shifts=plan_shifts,
    )


def _commissioned_on(raw: object) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


__all__ = ["AGE_SCALE_MODE", "AgeRates", "age_in_years", "age_rates", "pick_tier", "uses_age_scale"]
