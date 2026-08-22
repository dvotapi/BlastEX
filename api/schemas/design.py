"""Pydantic-схемы проекта БВР — поля 1:1 со словарями `design.models.*.to_dict()`."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.blast import ExplosivePropertiesSchema


class Point3Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    x: float
    y: float
    z: float


class BenchSurfaceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    crest_z_m: float = 0.0
    toe_z_m: float = -10.0
    face_angle_deg: float = Field(90.0, gt=0, le=90)


class BlockContourSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vertices: list[Point3Schema] = Field(default_factory=list)
    free_faces: list[list[int]] = Field(default_factory=list)
    bench: BenchSurfaceSchema = Field(default_factory=BenchSurfaceSchema)
    name: str = "Блок"


class HoleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    row: int
    col: int
    collar: Point3Schema
    toe: Point3Schema
    diameter_mm: float = Field(..., ge=0)
    subdrill_m: float = Field(0.0, ge=0)
    kind: str = "production"
    source: str = "generated"
    enabled: bool = True


class DeckSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    from_m: float = Field(..., ge=0)
    to_m: float = Field(..., ge=0)
    explosive_key: str = ""
    mass_kg: float = Field(0.0, ge=0)


class HoleLoadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hole_id: str
    decks: list[DeckSchema] = Field(default_factory=list)
    total_charge_kg: float = Field(0.0, ge=0)
    influence_volume_m3: float = Field(0.0, ge=0)
    specific_q_kg_m3: float = Field(0.0, ge=0)
    primers: list[float] = Field(default_factory=list)


class ConnectorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_hole: str
    to_hole: str
    delay_ms: float = 0.0
    kind: str = "surface_nsi"


class InitiationNetworkSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    system: str = "nonel"
    starters: list[str] = Field(default_factory=list)
    connectors: list[ConnectorSchema] = Field(default_factory=list)
    downhole_delay_ms: dict[str, float] = Field(default_factory=dict)
    electronic_times_ms: dict[str, float] = Field(default_factory=dict)


class BlastDesignSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    design_id: str = ""
    name: str = "Новый паспорт"
    version: int = 1
    updated_at: str = ""
    contour: BlockContourSchema = Field(default_factory=BlockContourSchema)
    holes: list[HoleSchema] = Field(default_factory=list)
    loads: list[HoleLoadSchema] = Field(default_factory=list)
    network: InitiationNetworkSchema = Field(default_factory=InitiationNetworkSchema)
    pattern_params: dict[str, Any] = Field(default_factory=dict)
    charge_rules: dict[str, Any] = Field(default_factory=dict)
    rock_name: str = ""
    explosive_key: str = ""


class PatternGenerateRequest(BaseModel):
    contour: BlockContourSchema
    params: dict[str, Any] = Field(default_factory=dict)
    existing_holes: list[HoleSchema] = Field(default_factory=list)


class PatternGenerateResponse(BaseModel):
    holes: list[HoleSchema]
    hole_count: int
    block_volume_m3: float


class ChargeGenerateRequest(BaseModel):
    holes: list[HoleSchema]
    rules: dict[str, Any] = Field(default_factory=dict)
    explosive: ExplosivePropertiesSchema


class ChargeGenerateResponse(BaseModel):
    loads: list[HoleLoadSchema]
    total_charge_kg: float
    total_holes_charged: int


class DesignSummarySchema(BaseModel):
    design_id: str
    name: str
    updated_at: str
    hole_count: int


class DesignListResponse(BaseModel):
    items: list[DesignSummarySchema]


class DesignRenameRequest(BaseModel):
    name: str = Field(..., min_length=1)
