"""Цены материалов: единственное место, где модель читает «Стоимость материалов».

Цена «на дату расчёта» — последняя по `valid_from` запись раздела. Доставка,
включённая в цену поставщика, прибавляется к ней: в смете блока это одна
величина, разделять их незачем.
"""
from __future__ import annotations

from decimal import Decimal

from cost.model.inputs import ModelContext, payload_number, payload_text
from cost.v2.models import ReferenceItem


def latest_price_item(context: ModelContext, material_code: str) -> ReferenceItem | None:
    if not material_code:
        return None
    prices = [
        item
        for item in context.items("material_prices")
        if payload_text(item, "material_code") == material_code
    ]
    if not prices:
        return None
    # Датированная запись всегда свежее недатированной: запись без даты —
    # старая загрузка, а не «цена на сегодня».
    prices.sort(key=lambda item: (item.valid_from is not None, item.valid_from), reverse=True)
    return prices[0]


def material_price(context: ModelContext, material_code: str) -> Decimal:
    """Цена материала: цена поставщика плюс доставка, включённая в цену."""

    row = latest_price_item(context, material_code)
    if row is None:
        return Decimal("0")
    return payload_number(row, "price_rub") + payload_number(row, "delivery_rub")


def price_source(context: ModelContext, material_code: str) -> str:
    """Происхождение цены для колонки «формула» строки затрат."""

    row = latest_price_item(context, material_code)
    return f"material_prices.{row.code}" if row is not None else ""


__all__ = ["latest_price_item", "material_price", "price_source"]
