"""Схемы API импорта чертежа маркшейдера (TASK-013)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CadWarningSchema(BaseModel):
    code: str
    message: str
    level: str = "warning"


class CadRoleSchema(BaseModel):
    code: str
    label: str
    applies_to: list[str] = Field(default_factory=list)


class CadOriginSchema(BaseModel):
    code: str
    label: str


class CadDefaultsSchema(BaseModel):
    label_radius_m: float
    closure_tolerance_m: float
    bench_height_m: float
    max_file_mb: int
    max_files: int


class CadMetaResponse(BaseModel):
    roles: list[CadRoleSchema]
    layer_roles: list[CadRoleSchema]
    origins: list[CadOriginSchema]
    defaults: CadDefaultsSchema


class CadParamsSchema(BaseModel):
    """Параметры разбора: масштаб координат, радиус подписей, подошва для бровок."""

    scale: float = Field(default=1.0, gt=0, le=1000)
    label_radius_m: float = Field(default=3.0, ge=0, le=50)
    floor_z_m: float | None = None
    bench_height_m: float = Field(default=10.0, gt=0, le=100)


class CadEntitySchema(BaseModel):
    handle: str
    layer: str
    kind: str
    geometry_type: str
    points: list[list[float]]
    closed: bool = False
    closed_by_gap: bool = False
    vertex_count: int
    length_m: float
    area_m2: float
    z_kind: str
    z_min: float
    z_max: float
    z_from_label: bool = False
    text: str = ""
    color: str | None = None
    role: str
    role_origin: str


class CadLayerSchema(BaseModel):
    name: str
    role: str
    origin: str
    entity_count: int
    kinds: dict[str, int] = Field(default_factory=dict)
    z_min: float | None = None
    z_max: float | None = None
    color: str | None = None
    counts_by_role: dict[str, int] = Field(default_factory=dict)


class CadSourceSchema(BaseModel):
    id: str
    file_name: str
    format: str
    site_code: str = ""
    work_object_name: str = ""
    uploaded_at: str
    uploaded_by: str = ""
    survey_date: str | None = None
    params: CadParamsSchema
    insunits: int | None = None
    suggested_scale: float | None = None
    extent: list[float] | None = None
    floor_z_m: float | None = None
    template_saved: bool = False
    warnings: list[CadWarningSchema] = Field(default_factory=list)
    layers: list[CadLayerSchema] = Field(default_factory=list)
    entities: list[CadEntitySchema] = Field(default_factory=list)


class CadImportResponse(BaseModel):
    sources: list[CadSourceSchema]


class CadRolesRequest(BaseModel):
    """Ручные роли: слою — роль, сущности — роль или null (вернуть роль слоя)."""

    layers: dict[str, str] = Field(default_factory=dict)
    entities: dict[str, str | None] = Field(default_factory=dict)
