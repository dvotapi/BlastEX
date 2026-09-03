"""Надбавки поверх себестоимости: ОХР → рентабельность → НДС.

Надбавки — отдельный шаг, а не строки затрат: при моделировании цены их
меняют чаще всего, и они не должны попадать в структуру себестоимости.
"""
from __future__ import annotations

from decimal import Decimal

from cost.model.inputs import ModelContext
from cost.v2.models import CostLayer, CostLine


def layer_totals(lines: tuple[CostLine, ...] | list[CostLine]) -> dict[CostLayer, Decimal]:
    """Накопительные итоги по слоям: variable → project_direct → production → full."""

    additions = {layer: Decimal("0") for layer in CostLayer}
    for line in lines:
        additions[line.layer] += line.amount_rub
    variable = additions[CostLayer.VARIABLE]
    project_direct = variable + additions[CostLayer.PROJECT_DIRECT]
    production = project_direct + additions[CostLayer.PRODUCTION]
    full = production + additions[CostLayer.FULL]
    return {
        CostLayer.VARIABLE: variable,
        CostLayer.PROJECT_DIRECT: project_direct,
        CostLayer.PRODUCTION: production,
        CostLayer.FULL: full,
    }


def apply(
    context: ModelContext, totals: dict[CostLayer, Decimal]
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """Вернуть цены за м³ и суммы надбавок по блоку."""

    params = context.params
    rates = context.rates
    overhead_rate = params.overhead_rate if params.overhead_rate is not None else rates.overhead_rate
    margin_rate = (
        params.target_margin_rate
        if params.target_margin_rate is not None
        else rates.target_margin_rate
    )
    vat_rate = params.vat_rate if params.vat_rate is not None else rates.vat_rate

    marginal_cost = totals[CostLayer.PROJECT_DIRECT]
    full_cost = totals[CostLayer.FULL]
    overhead = full_cost * overhead_rate
    cost_with_overhead = full_cost + overhead
    margin = cost_with_overhead * margin_rate
    price = cost_with_overhead + margin
    vat = price * vat_rate

    volume = context.block_volume_m3
    if volume <= 0:
        context.warn("Объём блока равен нулю: цены за м³ не рассчитаны.")
        prices = {key: Decimal("0") for key in ("marginal", "full", "with_margin", "with_vat")}
    else:
        prices = {
            "marginal": marginal_cost / volume,
            "full": full_cost / volume,
            "with_margin": price / volume,
            "with_vat": (price + vat) / volume,
        }
    markup = {
        "overhead_rate": overhead_rate,
        "target_margin_rate": margin_rate,
        "vat_rate": vat_rate,
        "marginal_cost_rub": marginal_cost,
        "full_cost_rub": full_cost,
        "overhead_rub": overhead,
        "margin_rub": margin,
        "price_rub": price,
        "vat_rub": vat,
        "price_with_vat_rub": price + vat,
    }
    return prices, markup
