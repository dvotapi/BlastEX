"""Сумма блока 1.2 сметы: погонаж бурения × цена метра.

Цену метра считает модель блока (`cost/model/drilling_price.py`); здесь
только умножение на потребность в п.м. из технического расчёта.
"""
from __future__ import annotations

from dataclasses import dataclass

from cost.models import BlockGeometry


@dataclass
class DrillingCostResult:
    total_holes: float
    hole_depth_m: float
    drilling_footage_m: float
    yield_per_meter_m3: float
    price_per_m: float
    amount: float


def calculate_drilling_cost(
    *,
    block: BlockGeometry,
    hole_depth_m: float,
    price_per_m: float,
) -> DrillingCostResult:
    """Стоимость бурения по потребности в п.м. из технического расчёта."""
    footage = block.drilling_footage_m
    yield_per_meter = block.block_volume_m3 / footage if footage > 0 else 0.0
    amount = footage * price_per_m

    return DrillingCostResult(
        total_holes=block.total_holes,
        hole_depth_m=hole_depth_m,
        drilling_footage_m=footage,
        yield_per_meter_m3=yield_per_meter,
        price_per_m=price_per_m,
        amount=amount,
    )

