"""Pydantic-схемы справочников."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CatalogCategory = Literal[
    "explosive", "detonator", "downhole_nsi", "surface_nsi", "start_nsi"
]


class WorkObjectSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    mobilization_km: float = Field(..., ge=0)
    diesel_price_ton_rub: float | None = None


class DrillRigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    depreciation_per_shift_rub: float = Field(..., ge=0)
    fuel_l_per_h: float = Field(..., ge=0)


class CatalogItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: CatalogCategory
    unit: str
    price: float = Field(..., ge=0)
    mass_kg: float | None = None
    length_m: float | None = None
    note: str = ""


class WorkObjectListResponse(BaseModel):
    items: list[WorkObjectSchema]
    default_name: str


class DrillRigListResponse(BaseModel):
    items: list[DrillRigSchema]
    default_name: str


class CatalogListResponse(BaseModel):
    items: list[CatalogItemSchema]
