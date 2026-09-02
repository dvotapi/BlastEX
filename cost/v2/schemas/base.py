"""Базовые типы схем payload справочников Cost V2.

Схема раздела — pydantic-модель полей payload плюс метаданные для интерфейса.
Фронт не хранит знания о полях: он получает JSON Schema и рисует форму по ней,
поэтому единица измерения, подсказка и ссылка на другой раздел живут здесь, а
не в тексте компонентов.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, NoReturn

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_core import InitErrorDetails, PydanticCustomError

__all__ = [
    "ReferencePayload",
    "RefField",
    "UnitField",
    "RateField",
    "field_error",
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


def field_error(model: type[BaseModel], field: str, message: str, value: Any = None) -> NoReturn:
    """Ошибка перекрёстной проверки, привязанная к полю.

    `raise ValueError` в `model_validator` даёт ошибку без имени поля, и
    интерфейс показывает её общим списком над формой. Сметчику нужно видеть
    ошибку под тем полем, которое он забыл заполнить, поэтому собираем ошибку
    с явным `loc`.
    """

    raise ValidationError.from_exception_data(
        model.__name__,
        [
            InitErrorDetails(
                # Текст подставляется через контекст: шаблон должен быть литералом.
                type=PydanticCustomError("value_error", "{message}", {"message": message}),
                loc=(field,),
                input=value,
            )
        ],
    )


Number = Decimal
