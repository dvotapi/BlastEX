"""Справочники для расчёта стоимости бурения (листы «ОС Буровые», «Объекты работ»)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


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


def work_objects_to_records(objects: Iterable[WorkObject]) -> list[dict]:
    return [asdict(obj) for obj in objects]


def work_objects_from_records(records: list[dict]) -> list[WorkObject]:
    objects: list[WorkObject] = []
    for row in records:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        diesel = row.get("diesel_price_ton_rub")
        objects.append(
            WorkObject(
                name=name,
                mobilization_km=float(row.get("mobilization_km", 0) or 0),
                diesel_price_ton_rub=float(diesel) if diesel not in (None, "") else None,
            )
        )
    return objects


def drill_rigs_to_records(rigs: Iterable[DrillRig]) -> list[dict]:
    return [asdict(rig) for rig in rigs]


def drill_rigs_from_records(records: list[dict]) -> list[DrillRig]:
    rigs: list[DrillRig] = []
    for row in records:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        rigs.append(
            DrillRig(
                name=name,
                depreciation_per_shift_rub=float(row.get("depreciation_per_shift_rub", 0) or 0),
                fuel_l_per_h=float(row.get("fuel_l_per_h", 0) or 0),
            )
        )
    return rigs


def find_rig(name: str, rigs: Iterable[DrillRig] | None = None) -> DrillRig:
    source = rigs if rigs is not None else DEFAULT_DRILL_RIGS
    for rig in source:
        if rig.name == name:
            return rig
    return next(iter(source if rigs is not None else DEFAULT_DRILL_RIGS))


def find_object(name: str, objects: Iterable[WorkObject] | None = None) -> WorkObject | None:
    source = objects if objects is not None else DEFAULT_WORK_OBJECTS
    for obj in source:
        if obj.name == name:
            return obj
    return None
