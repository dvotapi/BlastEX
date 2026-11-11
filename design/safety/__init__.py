"""Безопасные расстояния массового взрыва по ФНП 494, глава XII (TASK-018, PR 1).

Чистые функции без БД и HTTP: разлёт кусков (пп. 784–786, прил. 21),
сейсмика (пп. 792–795), ударная воздушная волна на застекление (пп. 803–807)
и на здания (пп. 796–801), сводка опасных зон (пп. 779, 783, 786) и оценка
охраняемых объектов. Каждая величина — `SafetyValue`: значение, формула,
подстановка для печати, пункт ФНП и происхождение (`FIELD_SOURCES`).

Сборка по проекту блока — `design.safety.design.safety_for_design`.
Версия формул `SAFETY_FORMULA_VERSION` пишется в результат: другой набор
формул — другая версия.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

__all__ = [
    "SAFETY_FORMULA_VERSION",
    "SafetyIssue",
    "SafetyValue",
    "ceil_to",
    "num",
]

SAFETY_FORMULA_VERSION = "safety-v1"

# Шаг округления принятых расстояний: п. 786 — вверх до кратного 50 м; тот
# же шаг проект принимает для механизмов, r_в и r_с (решение владельца В5).
ROUND_STEP_M = 50.0


@dataclass(frozen=True)
class SafetyValue:
    """Одна величина расчёта с тем, что нужно для печати и проверки."""

    value: float | None
    unit: str
    formula: str = ""
    substitution: str = ""
    basis: str = ""
    source: str = "CALCULATED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "formula": self.formula,
            "substitution": self.substitution,
            "basis": self.basis,
            "source": self.source,
        }


@dataclass(frozen=True)
class SafetyIssue:
    """Замечание расчёта. `error` выпуск проекта блокирует (PR 2), `warning` — нет."""

    level: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "code": self.code, "message": self.message}


def ceil_to(value: float, step: float = ROUND_STEP_M) -> float:
    """Вверх до кратного `step`; ровно кратное остаётся (700 → 700, 709 → 750).

    Допуск 1e-9 гасит шум плавающей точки: 700,0000000001 — это 700.
    """

    if value <= 0:
        return 0.0
    return float(math.ceil(value / step - 1e-9) * step)


def num(value: float, digits: int = 0) -> str:
    """Число для подстановки: запятая, тысячи через неразрывный пробел («32 830»)."""

    if round(value, digits) == 0:
        value = 0.0  # «-0» в подстановке не печатаем
    return f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")
