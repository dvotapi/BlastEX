"""Слой норм BlastEX: нормы — в коде, цены — в справочниках.

Пакет превращает драйверы технического паспорта в натуральные величины
(смены станка, человеко-смены, литры, тонно-километры) и умножает их на
ставки справочников Cost V2. Ни один модуль пакета не обращается к БД и HTTP.
"""
from cost.model.engine import compute_block_economics
from cost.model.inputs import (
    BlockEconomics,
    CapacityWarning,
    CrewMember,
    MODEL_VERSION,
    ModelParameters,
    NaturalDrivers,
    OrganizationRates,
)

__all__ = [
    "BlockEconomics",
    "CapacityWarning",
    "CrewMember",
    "MODEL_VERSION",
    "ModelParameters",
    "NaturalDrivers",
    "OrganizationRates",
    "compute_block_economics",
]
