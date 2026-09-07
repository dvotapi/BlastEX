"""Цена материала «на дату расчёта»: последняя запись раздела «Стоимость материалов»."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from cost.model.inputs import ModelContext
from cost.model.prices import material_price, price_source
from cost.v2.models import ReferenceItem
from tests.model_fixtures import parameters, physical, references


def context(*prices: ReferenceItem) -> ModelContext:
    return ModelContext(references(material_prices=prices), parameters(), physical())


def price_item(code: str, material_code: str, price: str, **payload: str) -> ReferenceItem:
    valid_from = payload.pop("valid_from", None)
    return ReferenceItem(
        code=code,
        name="Цена",
        payload={"material_code": material_code, "price_rub": price, **payload},
        valid_from=date.fromisoformat(valid_from) if valid_from else None,
    )


def test_price_takes_the_latest_record_and_adds_delivery() -> None:
    ctx = context(
        price_item("PR_OLD", "MAT_VV_EVERSIN", "40", valid_from="2025-01-01"),
        price_item("PR_NEW", "MAT_VV_EVERSIN", "48.9", delivery_rub="1.1", valid_from="2026-01-01"),
    )
    assert material_price(ctx, "MAT_VV_EVERSIN") == Decimal("50.0")
    assert price_source(ctx, "MAT_VV_EVERSIN") == "material_prices.PR_NEW"


def test_record_with_a_date_wins_over_one_without() -> None:
    """Запись без даты — старая загрузка: она не должна перебивать датированную цену."""

    ctx = context(
        price_item("PR_UNDATED", "MAT_VV_EVERSIN", "40"),
        price_item("PR_DATED", "MAT_VV_EVERSIN", "48.9", valid_from="2026-01-01"),
    )
    assert material_price(ctx, "MAT_VV_EVERSIN") == Decimal("48.9")


def test_price_of_an_unknown_material_is_zero() -> None:
    ctx = context()
    assert material_price(ctx, "MAT_NONE") == Decimal("0")
    assert price_source(ctx, "MAT_NONE") == ""
