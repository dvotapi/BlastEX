"""Базовые типы схем payload справочников Cost V2.

Схема раздела — pydantic-модель полей payload плюс метаданные для интерфейса.
Фронт не хранит знания о полях: он получает JSON Schema и рисует форму по ней,
поэтому единица измерения, подсказка и ссылка на другой раздел живут здесь, а
не в тексте компонентов.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ReferencePayload",
    "RefField",
    "UnitField",
    "RateField",
    "RUB",
    "SHARE",
]

# Часто используемые единицы: держим строками в одном месте, чтобы фронт
# форматировал одинаково, а не по написанию в каждой схеме.
RUB = "₽"
SHARE = "доля"


class ReferencePayload(BaseModel):
    """Payload записи справочника.

    `extra="forbid"`: лишнее поле — ошибка публикации, а не тихо сохранённый
    мусор. Именно это отличает схему от прежнего свободного JSON.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Ключ строки в источнике импорта. Объявлен явно, а не приходит «лишним
    # полем»: записи, перенесённые из Cost V1 и Excel, должны показывать,
    # откуда взялись, но пользователь этого поля не заполняет.
    legacy_ref: str | None = Field(
        default=None, description="Идентификатор записи в источнике импорта", json_schema_extra={"x-internal": True}
    )


def RefField(  # noqa: N802 — фабрика поля, а не класс
    section: str,
    *,
    description: str,
    default: Any = ...,
    title: str | None = None,
) -> Any:
    """Ссылка на запись другого раздела.

    Фронт рисует такое поле селектом по активным записям раздела из текущего
    черновика; валидация проверяет, что запись существует.
    """

    extra: dict[str, Any] = {"x-ref": section}
    return Field(default, description=description, title=title, json_schema_extra=extra)


def UnitField(  # noqa: N802
    unit: str,
    *,
    description: str,
    default: Any = ...,
    ge: float | None = 0,
    le: float | None = None,
    title: str | None = None,
) -> Any:
    """Число с единицей измерения.

    Единица обязательна: без неё сметчик не понимает, руб/смену перед ним или
    руб/месяц. Для безразмерных величин передаётся пустая строка.
    """

    extra: dict[str, Any] = {"x-unit": unit}
    return Field(default, description=description, title=title, ge=ge, le=le, json_schema_extra=extra)


def RateField(  # noqa: N802
    *,
    description: str,
    default: Any = ...,
    title: str | None = None,
) -> Any:
    """Доля от 0 до 1 (ставка налога, взносов, рентабельности)."""

    extra: dict[str, Any] = {"x-unit": SHARE}
    return Field(default, description=description, title=title, ge=0, le=1, json_schema_extra=extra)


Number = Decimal
