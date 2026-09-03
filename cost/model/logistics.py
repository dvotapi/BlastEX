"""Логистика ВМ: рейсы, смены СЗМ и доставщика, тонно-километры, мобилизация.

Ставки за тонно-километр остаются правилами затрат: здесь считаются только
натуральные величины плюс те деньги, которые считаются по норме расхода
(ДТ транспорта и мобилизация по расстоянию объекта).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

from cost.model.inputs import ModelContext, payload_number
from cost.v2.models import CostLayer, ReferenceItem


SZM_OPERATION = "BULK_CHARGING_SZM"
DELIVERY_OPERATION = "VM_DELIVERY_SITE"
COMPONENT_DELIVERY_OPERATION = "COMPONENT_DELIVERY"
MOBILIZATION_OPERATION = "MOBILIZATION"


def compute(context: ModelContext) -> None:
    _split_explosive_mass(context)
    _szm(context)
    _delivery(context)
    _mobilization(context)


def _split_explosive_mass(context: ModelContext) -> None:
    """Разделить массу ВВ на насыпную и патронированную.

    Патроны приходят со склада и занимают его ёмкость, насыпные компоненты
    едут на объект напрямую. Если паспорт не разделил массу, вся она считается
    насыпной — это видно в `lineage`.
    """

    explosive_kg = context.value("explosive_kg")
    cartridge_kg = context.value("cartridge_kg")
    if "bulk_kg" not in context.values:
        context.set_value(
            "bulk_kg",
            max(explosive_kg - cartridge_kg, Decimal("0")),
            "explosive_kg − cartridge_kg",
        )
    if "cartridge_kg" not in context.values:
        context.set_value("cartridge_kg", Decimal("0"), "паспорт не разделил массу ВВ")


def _szm(context: ModelContext) -> None:
    if not context.has_operation(SZM_OPERATION):
        return
    bulk_kg = context.value("bulk_kg")
    if bulk_kg <= 0:
        return
    szm = context.item("equipment_types", context.params.szm_code)
    capacity = payload_number(szm, "capacity")
    if szm is None or capacity <= 0:
        context.warn(
            "Не задана СЗМ с грузоподъёмностью: смены заряжания не выведены из массы ВВ."
        )
        return
    trips = _ceil(bulk_kg / capacity)
    context.set_value("szm_trips", trips, f"⌈{bulk_kg} кг / {capacity} кг⌉")
    # Один рейс СЗМ — одна смена заряжания: машина за смену заряжает свой объём
    # и возвращается на пункт изготовления.
    context.set_value("szm_shifts", trips, "1 рейс = 1 смена СЗМ")
    _vehicle_fuel(context, szm, trips, SZM_OPERATION, "SZM_FUEL", "ДТ СЗМ")


def _delivery(context: ModelContext) -> None:
    cartridge_kg = context.value("cartridge_kg")
    bulk_kg = context.value("bulk_kg")
    warehouse_km = context.site_number("distance_from_warehouse_km")
    base_km = context.site_number("distance_from_base_km")

    if context.has_operation(DELIVERY_OPERATION) and cartridge_kg > 0:
        tkm = cartridge_kg / Decimal("1000") * warehouse_km
        context.set_value(
            "vm_tkm", tkm, f"{cartridge_kg} кг / 1000 × {warehouse_km} км (склад → объект)"
        )
        truck = context.item("equipment_types", context.params.delivery_truck_code)
        capacity = payload_number(truck, "capacity")
        if truck is not None and capacity > 0:
            trips = _ceil(cartridge_kg / capacity)
            context.set_value("delivery_trips", trips, f"⌈{cartridge_kg} кг / {capacity} кг⌉")
            context.set_value("delivery_shifts", trips, "1 рейс = 1 смена доставщика")
            _vehicle_fuel(
                context,
                truck,
                trips,
                DELIVERY_OPERATION,
                "VM_TRANSPORT_FUEL",
                "ДТ доставки ВМ",
                distance_km=warehouse_km,
            )
        else:
            context.warn(
                "Не задан доставщик ВМ с грузоподъёмностью: рейсы и ДТ доставки не посчитаны."
            )

    if context.has_operation(COMPONENT_DELIVERY_OPERATION) and bulk_kg > 0:
        distance = base_km or warehouse_km
        context.set_value(
            "component_tkm",
            bulk_kg / Decimal("1000") * distance,
            f"{bulk_kg} кг / 1000 × {distance} км (компоненты напрямую на объект)",
        )


def _vehicle_fuel(
    context: ModelContext,
    vehicle: ReferenceItem,
    trips: Decimal,
    operation_code: str,
    cost_item_code: str,
    cost_item_name: str,
    distance_km: Decimal | None = None,
) -> None:
    price = context.diesel_price_l()
    if price <= 0:
        return
    if distance_km is not None and distance_km > 0:
        fuel_l_per_km = payload_number(vehicle, "fuel_l_per_km")
        if fuel_l_per_km <= 0:
            return
        km = trips * distance_km * Decimal("2")
        litres = km * fuel_l_per_km
        formula = f"{trips} рейсов × {distance_km} км × 2 × {fuel_l_per_km} л/км × {price} ₽/л"
        context.set_value(f"{cost_item_code.lower()}_km", km, "рейсы × плечо × 2")
    else:
        fuel_l_per_h = payload_number(vehicle, "fuel_l_per_h")
        if fuel_l_per_h <= 0:
            return
        hours = trips * context.rates.shift_hours
        litres = hours * fuel_l_per_h
        formula = f"{trips} см × {context.rates.shift_hours} ч × {fuel_l_per_h} л/ч × {price} ₽/л"
    context.set_value(f"{cost_item_code.lower()}_l", litres, "расход по норме техники")
    context.add_line(
        operation_code=operation_code,
        cost_item_code=cost_item_code,
        cost_item_name=cost_item_name,
        layer=CostLayer.VARIABLE,
        amount_rub=litres * price,
        formula=formula,
    )


def _mobilization(context: ModelContext) -> None:
    if not context.has_operation(MOBILIZATION_OPERATION):
        return
    distance = context.site_number("mobilization_km") or context.site_number("distance_from_base_km")
    rate = context.site_number("mobilization_rate_rub_per_km")
    blocks = context.site_number("blocks_per_mobilization", Decimal("1"))
    if distance <= 0 or rate <= 0:
        return
    if blocks <= 0:
        blocks = Decimal("1")
    trip_km = distance * Decimal("2") / blocks
    context.set_value(
        "mobilization_trip_km", trip_km, f"{distance} км × 2 / {blocks} блоков на мобилизацию"
    )
    context.add_line(
        operation_code=MOBILIZATION_OPERATION,
        cost_item_code="MOBILIZATION",
        cost_item_name="Мобилизация и демобилизация",
        layer=CostLayer.PROJECT_DIRECT,
        amount_rub=trip_km * rate,
        formula=f"{trip_km} км × {rate} ₽/км",
    )


def _ceil(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_CEILING)
