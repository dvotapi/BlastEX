"""Ответ `GET /economics/references/schema`.

Фронт рисует формы справочников по этому ответу и не хранит собственных знаний
о полях: состав, единицы, ссылки и группировка приходят с сервера.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = ["ReferenceGroupSchema", "ReferenceSectionSchema", "ReferenceSchemaResponse"]


class ReferenceGroupSchema(BaseModel):
    code: str
    label: str


class ReferenceFieldsetSchema(BaseModel):
    title: str
    fields: list[str] = Field(default_factory=list)


class ReferenceSectionSchema(BaseModel):
    code: str
    label: str
    group: str
    view: str = "table"
    deprecated: bool = False
    list_columns: list[str] = Field(default_factory=list)
    fieldsets: list[ReferenceFieldsetSchema] = Field(default_factory=list)
    json_schema: dict[str, Any] = Field(default_factory=dict)


class ReferenceSchemaResponse(BaseModel):
    groups: list[ReferenceGroupSchema] = Field(default_factory=list)
    sections: dict[str, ReferenceSectionSchema] = Field(default_factory=dict)
