"""Действующая цена материала: одно правило для модели блока, вкладки и V1."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from cost.v2.models import ReferenceItem
from cost.v2.prices import effective_price, effective_price_lookup

TODAY = date(2026, 9, 7)


def price(code: str, value: str, *, valid_from: date | None = None, valid_to: date | None = None,
          material: str = "MAT_VV", delivery: str | None = None) -> ReferenceItem:
    payload = {"material_code": material, "price_rub": value}
    if delivery is not None:
        payload["delivery_rub"] = delivery
    return ReferenceItem(code=code, name="Цена", payload=payload, valid_from=valid_from, valid_to=valid_to)


def test_latest_effective_price_wins_and_delivery_is_added() -> None:
    lookup = effective_price_lookup(
        (price("P_OLD", "40", valid_from=date(2025, 1, 1)),
         price("P_NEW", "48.9", valid_from=date(2026, 1, 1), delivery="1.1")),
        "MAT_VV",
        as_of=TODAY,
    )
    assert lookup.chosen is not None and lookup.chosen.code == "P_NEW"
    assert effective_price(lookup) == Decimal("50.0")


def test_future_price_is_not_used_yet() -> None:
    lookup = effective_price_lookup(
        (price("P_NOW", "48.9", valid_from=date(2026, 1, 1)),
         price("P_LATER", "60", valid_from=TODAY + timedelta(days=1))),
        "MAT_VV",
        as_of=TODAY,
    )
    assert lookup.chosen.code == "P_NOW"


def test_expired_price_is_ignored() -> None:
    lookup = effective_price_lookup(
        (price("P_OLD", "40", valid_to=TODAY - timedelta(days=1)),), "MAT_VV", as_of=TODAY
    )
    assert lookup.found
    assert lookup.chosen is None
    assert effective_price(lookup) == Decimal("0")


def test_undated_record_is_the_oldest() -> None:
    lookup = effective_price_lookup(
        (price("P_UNDATED", "40"), price("P_DATED", "48.9", valid_from=date(2026, 1, 1))),
        "MAT_VV",
        as_of=TODAY,
    )
    assert lookup.chosen.code == "P_DATED"


def test_two_undated_records_resolve_by_code_not_by_storage_order() -> None:
    """In-memory и Postgres отдают записи в разном порядке — выбор от него не зависит."""

    first = effective_price_lookup((price("P_B", "20"), price("P_A", "10")), "MAT_VV", as_of=TODAY)
    second = effective_price_lookup((price("P_A", "10"), price("P_B", "20")), "MAT_VV", as_of=TODAY)
    assert first.chosen.code == second.chosen.code == "P_A"
    assert [item.code for item in first.duplicates] == ["P_A", "P_B"]


def test_unknown_material_is_not_found() -> None:
    lookup = effective_price_lookup((price("P_A", "10"),), "MAT_NONE", as_of=TODAY)
    assert not lookup.found
    assert lookup.chosen is None
    assert lookup.source == ""


def test_source_names_the_chosen_record() -> None:
    lookup = effective_price_lookup((price("P_A", "10"),), "MAT_VV", as_of=TODAY)
    assert lookup.source == "material_prices.P_A"
