"""Цены материалов в модели блока: обёртка над правилом действующей цены.

Само правило («какая запись действует на дату расчёта») живёт в
`cost/v2/prices.py` и общее для модели, вкладки и Cost V1; здесь оно лишь
привязано к контексту прогона и его дате.
"""
from __future__ import annotations

from decimal import Decimal

from cost.model.inputs import ModelContext
from cost.v2.prices import PriceLookup, effective_price, effective_price_lookup


def price_lookup(context: ModelContext, material_code: str) -> PriceLookup:
    if not material_code:
        return PriceLookup(material_code, found=False, chosen=None)
    return effective_price_lookup(
        context.items("material_prices"), material_code, as_of=context.as_of
    )


def material_price(context: ModelContext, material_code: str) -> Decimal:
    """Цена материала на дату расчёта с доставкой; ноль, если цены нет."""

    return effective_price(price_lookup(context, material_code))


def price_source(context: ModelContext, material_code: str) -> str:
    """Происхождение цены для колонки «формула» строки затрат."""

    return price_lookup(context, material_code).source


__all__ = ["material_price", "price_lookup", "price_source"]
