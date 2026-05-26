"""Справочники для расчёта стоимости бурения (листы «ОС Буровые», «Объекты работ»)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DrillRig:
    name: str
    depreciation_per_shift_rub: float
    fuel_l_per_h: float


@dataclass(frozen=True)
class WorkObject:
    name: str
    mobilization_km: float
    diesel_price_ton_rub: float | None = None


DEFAULT_DRILL_RIGS: tuple[DrillRig, ...] = (
    DrillRig("Soosan JD-2000", 14_250.0, 55.0),
    DrillRig("ZEGA D480A", 12_500.0, 55.0),
    DrillRig("JK 830-3", 11_854.166666666668, 50.0),
    DrillRig("TM255-T", 7_500.0, 26.0),
    DrillRig("УРБ-2А2 + компрессор", 3_541.6666666666665, 45.0),
    DrillRig("УРБ-2А2 + компрессор (2)", 2_291.666666666667, 30.0),
)

DEFAULT_WORK_OBJECTS: tuple[WorkObject, ...] = (
    WorkObject('"карьер м-ия Анна" ООО "СУПБ"', 650),
    WorkObject('"карьер м-ия С-Саркаевское" ООО "Ергач"', 350),
    WorkObject('"карьер м-ия В-Вильвенское" ООО "ГХК"', 270),
    WorkObject('"карьер м-ия Заготовкинское" ООО "ГДК"', 100),
    WorkObject('"карьер м-ия Ломовское" АО "ТК"', 220, 52_200.0),
    WorkObject('"карьер Ломовского месторождения" АО "Теплогорский карьер"', 300, 80_000.0),
    WorkObject('"карьер Чаньвинского месторождения известняков" АО "БСЗ"', 320, 68_000.0),
    WorkObject('"карьер Пушкинского месторождения" Карьер АО', 70),
    WorkObject('"карьер месторождения Жуков Камень" ООО "МЖК"', 310),
)

DEFAULT_OBJECT_NAME = '"карьер Ломовского месторождения" АО "Теплогорский карьер"'
DEFAULT_RIG_NAME = "JK 830-3"
DEFAULT_DIESEL_PRICE_TON_RUB = 80_000.0

SHIFT_HOURS = 11


def find_rig(name: str) -> DrillRig:
    for rig in DEFAULT_DRILL_RIGS:
        if rig.name == name:
            return rig
    return DEFAULT_DRILL_RIGS[0]


def find_object(name: str) -> WorkObject | None:
    for obj in DEFAULT_WORK_OBJECTS:
        if obj.name == name:
            return obj
    return None
