"""Действующая цена материала из раздела «Стоимость материалов».

Раздел хранит историю: у записи есть срок действия. Действующей считается
запись, чьё окно `valid_from … valid_to` накрывает дату расчёта, а среди
таких — с самой поздней датой начала; запись без даты — самая старая.
Правило одно на всех: модель блока, подсказка цены на вкладке и калькуляторы
Cost V1 читают его отсюда, иначе два экрана показывали бы разную стоимость
одного ВВ.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from cost.v2.models import ReferenceItem, decimal_value


@dataclass(frozen=True)
class PriceLookup:
    """Результат подбора: что нашли и почему цена может быть нулевой."""

    material_code: str
    # Есть ли для материала хоть одна запись цены.
    found: bool
    # Действующая запись; None — цен нет либо все просрочены или будущие.
    chosen: ReferenceItem | None
    # Записи с той же датой начала, что и выбранная: сметчик должен знать,
    # что справочник неоднозначен.
    duplicates: tuple[ReferenceItem, ...] = ()

    @property
    def source(self) -> str:
        return f"material_prices.{self.chosen.code}" if self.chosen is not None else ""


def effective_price_lookup(
    prices: Iterable[ReferenceItem], material_code: str, *, as_of: date | None = None
) -> PriceLookup:
    today = as_of or date.today()
    own = [
        item
        for item in prices
        if str(item.payload.get("material_code") or "") == material_code
    ]
    if not own:
        return PriceLookup(material_code, found=False, chosen=None)
    valid = [
        item
        for item in own
        if (item.valid_from is None or item.valid_from <= today)
        and (item.valid_to is None or item.valid_to >= today)
    ]
    if not valid:
        return PriceLookup(material_code, found=True, chosen=None)
    latest = max(item.valid_from or date.min for item in valid)
    # Порядок хранения у in-memory и Postgres разный; код записи — единственный
    # ключ, который одинаков везде.
    candidates = tuple(
        sorted(
            (item for item in valid if (item.valid_from or date.min) == latest),
            key=lambda item: item.code,
        )
    )
    return PriceLookup(material_code, found=True, chosen=candidates[0], duplicates=candidates)


def effective_price(lookup: PriceLookup) -> Decimal:
    """Цена с доставкой, включённой в цену поставщика; ноль, если записи нет."""

    if lookup.chosen is None:
        return Decimal("0")
    payload = lookup.chosen.payload
    return decimal_value(payload.get("price_rub")) + decimal_value(payload.get("delivery_rub"))


__all__ = ["PriceLookup", "effective_price", "effective_price_lookup"]
