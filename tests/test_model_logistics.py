from decimal import Decimal

from cost.model import logistics
from cost.model.inputs import ModelContext
from tests import model_fixtures as fx


def _context(**physical) -> ModelContext:
    return ModelContext(fx.references(), fx.parameters(), fx.physical(**physical))


def test_szm_shifts_derived_from_bulk_mass_and_capacity() -> None:
    """42 т насыпного ВВ при 12 т на рейс — четыре рейса, четыре смены."""

    context = _context()
    logistics.compute(context)

    assert context.value("szm_trips") == Decimal("4")
    assert context.value("szm_shifts") == Decimal("4")


def test_cartridges_travel_from_warehouse_in_tonne_kilometres() -> None:
    context = _context(cartridge_kg=2200, bulk_kg=39800)
    logistics.compute(context)

    assert context.value("vm_tkm") == Decimal("2.2") * 270
    assert context.value("delivery_trips") == Decimal("1")
    assert context.value("delivery_shifts") == Decimal("1")


def test_bulk_components_are_delivered_directly_to_site() -> None:
    context = _context()
    logistics.compute(context)

    assert context.value("component_tkm") == Decimal("42") * 220


def test_mobilization_is_shared_between_blocks() -> None:
    context = _context()
    logistics.compute(context)

    trip_km = Decimal("220") * 2 / 6
    assert context.value("mobilization_trip_km") == trip_km
    line = next(item for item in context.lines if item.cost_item_code == "MOBILIZATION")
    assert line.amount_rub == trip_km * 450


def test_delivery_fuel_uses_round_trip_distance() -> None:
    context = _context(cartridge_kg=2200, bulk_kg=39800)
    logistics.compute(context)

    line = next(item for item in context.lines if item.cost_item_code == "VM_TRANSPORT_FUEL")
    price_l = Decimal("52200") / Decimal("1176.47")
    assert line.amount_rub == Decimal("1") * 270 * 2 * Decimal("0.45") * price_l


def test_package_without_delivery_produces_no_logistics_lines() -> None:
    context = ModelContext(
        fx.references(), fx.parameters(package_code="DRILLING"), fx.physical()
    )
    logistics.compute(context)

    assert "szm_shifts" not in context.values
    assert "vm_tkm" not in context.values
