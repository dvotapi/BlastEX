"""Pydantic-схемы проекта БВР — поля 1:1 со словарями `design.models.*.to_dict()`."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.blast import ExplosivePropertiesSchema
from api.schemas.cost import CalculationContextInputSchema, MaterialsSelectionSchema


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


class DataProvenanceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str = ""
    method: str = ""
    timestamp: str = ""
    role: str = "designed"


class RockPropertySetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    density_kg_m3: float | None = None
    ucs_mpa: float | None = None
    fracturing: str = ""
    rqd_pct: float | None = None
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None
    p_wave_velocity_m_s: float | None = None
    joint_spacing_m: float | None = None
    joint_dip_deg: float | None = None
    joint_dip_direction_deg: float | None = None
    blastability: str = ""
    water_condition: str = ""


class BlastDomainSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    polygon: list[Point3Schema] = Field(default_factory=list)
    properties: RockPropertySetSchema = Field(default_factory=RockPropertySetSchema)
    provenance: DataProvenanceSchema = Field(default_factory=DataProvenanceSchema)
    z_top_m: float | None = None
    z_bottom_m: float | None = None
    priority: int = 0
    color: str = ""
    notes: str = ""
    spacing_a_m: float | None = None
    burden_b_m: float | None = None


class HoleIntervalSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_m: float = Field(..., ge=0)
    to_m: float = Field(..., ge=0)
    domain_id: str = ""
    domain_name: str = ""
    properties: RockPropertySetSchema = Field(default_factory=RockPropertySetSchema)
    provenance: DataProvenanceSchema = Field(default_factory=DataProvenanceSchema)
    role: str = "designed"


class WaterIntervalSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_m: float = Field(..., ge=0)
    to_m: float = Field(..., ge=0)
    condition: str = "wet"
    provenance: DataProvenanceSchema = Field(default_factory=DataProvenanceSchema)
    role: str = "designed"
    notes: str = ""


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
    intervals: list[HoleIntervalSchema] = Field(default_factory=list)
    water_intervals: list[WaterIntervalSchema] = Field(default_factory=list)
    measured_intervals: list[HoleIntervalSchema] = Field(default_factory=list)
    measured_water_intervals: list[WaterIntervalSchema] = Field(default_factory=list)


class DeckSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    from_m: float = Field(..., ge=0)
    to_m: float = Field(..., ge=0)
    explosive_key: str = ""
    mass_kg: float = Field(0.0, ge=0)
    product: str = ""


class PrimerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position_m: float = Field(..., ge=0)
    product: str = ""
    mass_kg: float = Field(0.0, ge=0)
    kind: str = "primer"


class ChargeConditionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hole_kinds: list[str] = Field(default_factory=list)
    rows: list[int] = Field(default_factory=list)
    depth_min_m: float | None = None
    depth_max_m: float | None = None
    diameter_min_mm: float | None = None
    diameter_max_mm: float | None = None
    burden_min_m: float | None = None
    burden_max_m: float | None = None
    spacing_min_m: float | None = None
    spacing_max_m: float | None = None
    rock_domain_ids: list[str] = Field(default_factory=list)
    geological_interval: str = ""
    water: str = ""
    distance_to_face_min_m: float | None = None
    distance_to_face_max_m: float | None = None
    target_pf_min: float | None = None
    target_pf_max: float | None = None


class ChargeActionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str = "bulk_explosive"
    explosive_key: str = ""
    product: str = ""
    region: str = "interval"
    length_m: float | None = None
    mass_kg: float | None = None
    place_primer: bool = False
    primer_offset_m: float | None = None
    primer_product: str = ""
    primer_mass_kg: float = 0.0
    primer_kind: str = "primer"


class ChargeTemplateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str = ""
    conditions: ChargeConditionSchema = Field(default_factory=ChargeConditionSchema)
    actions: list[ChargeActionSchema] = Field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    notes: str = ""


class HoleLoadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hole_id: str
    decks: list[DeckSchema] = Field(default_factory=list)
    total_charge_kg: float = Field(0.0, ge=0)
    influence_volume_m3: float = Field(0.0, ge=0)
    specific_q_kg_m3: float = Field(0.0, ge=0)
    primers: list[float] = Field(default_factory=list)
    primer_items: list[PrimerSchema] = Field(default_factory=list)


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


class CoordinateSystemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = "local"
    epsg: int | None = None
    origin_x: float = 0.0
    origin_y: float = 0.0
    origin_z: float = 0.0
    units: str = "m"


class TINSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    vertices: list[Point3Schema] = Field(default_factory=list)
    triangles: list[list[int]] = Field(default_factory=list)


class SurfaceModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    name: str = ""
    source_format: str = ""
    source_name: str = ""
    created_at: str = ""
    coordinate_system: CoordinateSystemSchema = Field(default_factory=CoordinateSystemSchema)
    points: list[Point3Schema] = Field(default_factory=list)
    polylines: list[list[Point3Schema]] = Field(default_factory=list)
    tin: TINSchema = Field(default_factory=TINSchema)


class SurfaceSetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    top: SurfaceModelSchema | None = None
    floor: SurfaceModelSchema | None = None
    face: SurfaceModelSchema | None = None
    post_blast: SurfaceModelSchema | None = None


class SurfaceStatsSchema(BaseModel):
    kind: str
    name: str
    source_format: str = ""
    source_name: str = ""
    point_count: int = 0
    triangle_count: int = 0
    polyline_count: int = 0
    z_min: float | None = None
    z_max: float | None = None
    bounds: dict[str, float] | None = None


class SurfaceImportRequest(BaseModel):
    content: str
    filename: str = ""
    format: str | None = None
    kind: str = "top"
    name: str = ""
    coordinate_system: CoordinateSystemSchema = Field(default_factory=CoordinateSystemSchema)


class SurfaceImportResponse(BaseModel):
    surface: SurfaceModelSchema
    stats: SurfaceStatsSchema


class SurfaceSampleRequest(BaseModel):
    surface: SurfaceModelSchema
    points: list[list[float]] = Field(default_factory=list)


class SurfaceSampleResponse(BaseModel):
    elevations: list[float | None]


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
    coordinate_system: CoordinateSystemSchema = Field(default_factory=CoordinateSystemSchema)
    surfaces: SurfaceSetSchema = Field(default_factory=SurfaceSetSchema)
    domains: list[BlastDomainSchema] = Field(default_factory=list)
    water_table_z_m: float | None = None


class PatternGenerateRequest(BaseModel):
    contour: BlockContourSchema
    params: dict[str, Any] = Field(default_factory=dict)
    existing_holes: list[HoleSchema] = Field(default_factory=list)
    surfaces: SurfaceSetSchema | None = None
    domains: list[BlastDomainSchema] = Field(default_factory=list)


class PatternGenerateResponse(BaseModel):
    holes: list[HoleSchema]
    hole_count: int
    block_volume_m3: float


class ChargeGenerateRequest(BaseModel):
    holes: list[HoleSchema]
    rules: dict[str, Any] = Field(default_factory=dict)
    explosive: ExplosivePropertiesSchema
    contour: BlockContourSchema | None = None
    explosives: list[ExplosivePropertiesSchema] = Field(default_factory=list)


class ChargeGenerateResponse(BaseModel):
    loads: list[HoleLoadSchema]
    total_charge_kg: float
    total_holes_charged: int


class TieGenerateRequest(BaseModel):
    holes: list[HoleSchema]
    scheme: str
    params: dict[str, Any] = Field(default_factory=dict)


class TieGenerateResponse(BaseModel):
    network: InitiationNetworkSchema
    starters_count: int
    connectors_count: int


class ValidationWarningSchema(BaseModel):
    code: str
    hole_id: str | None = None
    message: str


class SummarySchema(BaseModel):
    hole_count: int
    production_hole_count: int
    contour_hole_count: int
    drilling_footage_m: float
    block_volume_m3: float
    total_charge_kg: float
    avg_specific_q_kg_m3: float
    explosive_breakdown_kg: dict[str, float]
    charged_hole_count: int
    loads_by_hole_count: int
    hole_counts_by_kind: dict[str, int] = Field(default_factory=dict)


class HoleMapSampleSchema(BaseModel):
    hole_id: str
    kind: str = "production"
    x: float
    y: float
    burden: float | None = None
    spacing: float | None = None
    hole_depth: float = 0.0
    subdrill: float = 0.0
    bench_height: float = 0.0
    toe_burden: float | None = None
    collar_burden: float | None = None
    true_face_burden: float | None = None


class EngineeringMapsSchema(BaseModel):
    metrics: list[str] = Field(default_factory=list)
    holes: list[HoleMapSampleSchema] = Field(default_factory=list)
    stats: dict[str, dict[str, float]] = Field(default_factory=dict)


class EngineeringMapsRequest(BaseModel):
    design: BlastDesignSchema


class HoleGeometryEditRequest(BaseModel):
    hole: HoleSchema
    patch: dict[str, Any] = Field(default_factory=dict)
    contour: BlockContourSchema | None = None
    surfaces: SurfaceSetSchema | None = None


class HoleGeometryEditResponse(BaseModel):
    hole: HoleSchema


class HoleInsertRequest(BaseModel):
    contour: BlockContourSchema
    x: float
    y: float
    params: dict[str, Any] = Field(default_factory=dict)
    existing_holes: list[HoleSchema] = Field(default_factory=list)
    surfaces: SurfaceSetSchema | None = None


class HoleInsertResponse(BaseModel):
    hole: HoleSchema


class MicSchema(BaseModel):
    mic_kg: float
    window_start_ms: float
    hole_ids: list[str]


class IsolineSchema(BaseModel):
    time_ms: float
    segments: list[list[list[float]]]


class PpvRequestSchema(BaseModel):
    distance_m: float = Field(..., gt=0)
    k: float = 200.0
    n: float = 1.6


class AnalyzeRequest(BaseModel):
    design: BlastDesignSchema
    isoline_step_ms: float = Field(25.0, gt=0)
    mic_window_ms: float = Field(8.0, gt=0)
    ppv: PpvRequestSchema | None = None


class AnalyzeResponse(BaseModel):
    times_ms: dict[str, float]
    timing_warnings: list[str]
    validation_warnings: list[ValidationWarningSchema]
    summary: SummarySchema
    mic: MicSchema
    isolines: list[IsolineSchema]
    ppv_mm_s: float | None = None
    maps: EngineeringMapsSchema | None = None


class DesignCostRequest(BaseModel):
    design: BlastDesignSchema
    scenario_id: str = Field(..., examples=["drill_blast"])
    work_object_name: str | None = None
    context: CalculationContextInputSchema | None = None
    materials_selection: MaterialsSelectionSchema | None = None


class DesignSummarySchema(BaseModel):
    design_id: str
    name: str
    updated_at: str
    hole_count: int


class DesignListResponse(BaseModel):
    items: list[DesignSummarySchema]


class DesignRenameRequest(BaseModel):
    name: str = Field(..., min_length=1)


class GeologyAssignRequest(BaseModel):
    domain: BlastDomainSchema
    polygon: list[Point3Schema] = Field(default_factory=list)


class GeologyAssignResponse(BaseModel):
    domain: BlastDomainSchema


class GeologyInterceptRequest(BaseModel):
    holes: list[HoleSchema] = Field(default_factory=list)
    domains: list[BlastDomainSchema] = Field(default_factory=list)
    water_table_z_m: float | None = None


class GeologyInterceptResponse(BaseModel):
    holes: list[HoleSchema]
    interval_count: int
    water_interval_count: int
