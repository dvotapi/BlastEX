"""Pydantic-схемы проекта БВР — поля 1:1 со словарями `design.models.*.to_dict()`."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.blast import ExplosivePropertiesSchema, RockPropertiesSchema
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


class DetonatorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    hole_id: str
    delay_ms: float = 0.0
    product: str = ""
    kind: str = "electronic"
    deck_index: int | None = None
    primer_index: int | None = None
    channel_id: str = ""


class SurfaceConnectorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    from_hole: str
    to_hole: str
    delay_ms: float = 0.0
    kind: str = "surface_nsi"
    product: str = ""


class DownholeConnectorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    hole_id: str
    delay_ms: float = 0.0
    kind: str = "downhole_nsi"
    deck_index: int | None = None
    primer_index: int | None = None
    product: str = ""


class DetonatingCordSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    hole_ids: list[str] = Field(default_factory=list)
    velocity_m_s: float = 7000.0
    relay_delay_ms: float = 0.0
    product: str = ""


class StarterSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    hole_id: str
    delay_ms: float = 0.0
    kind: str = "starter"


class ElectronicChannelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    hole_id: str
    time_ms: float = 0.0
    deck_index: int | None = None
    primer_index: int | None = None
    label: str = ""


class FiringEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    hole_id: str
    time_ms: float = 0.0
    level: str = "hole"
    deck_index: int | None = None
    primer_index: int | None = None
    mass_kg: float = 0.0


class InitiationNetworkSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    system: str = "nonel"
    starters: list[str] = Field(default_factory=list)
    connectors: list[ConnectorSchema] = Field(default_factory=list)
    downhole_delay_ms: dict[str, float] = Field(default_factory=dict)
    electronic_times_ms: dict[str, float] = Field(default_factory=dict)
    detonators: list[DetonatorSchema] = Field(default_factory=list)
    surface_connectors: list[SurfaceConnectorSchema] = Field(default_factory=list)
    downhole_connectors: list[DownholeConnectorSchema] = Field(default_factory=list)
    detonating_cords: list[DetonatingCordSchema] = Field(default_factory=list)
    starter_items: list[StarterSchema] = Field(default_factory=list)
    electronic_channels: list[ElectronicChannelSchema] = Field(default_factory=list)
    firing_events: list[FiringEventSchema] = Field(default_factory=list)
    timing_mode: str = ""
    timing_expression: str = ""
    timing_params: dict[str, Any] = Field(default_factory=dict)
    selected_hole_ids: list[str] = Field(default_factory=list)


class CoordinateSystemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = "local"
    epsg: int | None = None
    origin_x: float = 0.0
    origin_y: float = 0.0
    origin_z: float = 0.0
    units: str = "m"
    confirmed: bool = False


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


class BenchDxfImportRequest(BaseModel):
    content: str
    filename: str = ""
    coordinate_system: CoordinateSystemSchema = Field(default_factory=CoordinateSystemSchema)


class BenchDxfImportResponse(BaseModel):
    contour: BlockContourSchema
    surfaces: SurfaceSetSchema
    crest_layer: str
    toe_layer: str
    crest_z_m: float
    toe_z_m: float
    vertex_count: int


class SurfaceSampleRequest(BaseModel):
    surface: SurfaceModelSchema
    points: list[list[float]] = Field(default_factory=list)


class SurfaceSampleResponse(BaseModel):
    elevations: list[float | None]


class ReceptorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    name: str = ""
    kind: str = "building"
    location: Point3Schema = Field(default_factory=lambda: Point3Schema(x=0.0, y=0.0, z=0.0))
    ppv_limit_mm_s: float | None = None
    notes: str = ""


class VibrationModelSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    name: str = ""
    k: float = 200.0
    n: float = 1.6
    scaled_distance: str = "q_cube_over_r"
    calibration_source: str = ""
    confidence: float = Field(0.3, ge=0.0, le=1.0)
    notes: str = ""


class VibrationMeasurementSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = ""
    receptor_id: str = ""
    ppv_mm_s: float = 0.0
    frequency_hz: float | None = None
    role: str = "measured"
    distance_m: float | None = None
    mic_kg: float | None = None
    scaled_distance: str = ""
    source: str = ""
    method: str = ""
    timestamp: str = ""
    event_label: str = ""
    notes: str = ""


class SurveyPointSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    depth_m: float = Field(0.0, ge=0)
    x: float | None = None
    y: float | None = None
    z: float | None = None


class MwdSampleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    depth_m: float = Field(0.0, ge=0)
    penetration_rate: float | None = None
    rotation_pressure: float | None = None
    feed_pressure: float | None = None
    torque: float | None = None
    air_pressure: float | None = None


class AsDrilledHoleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    design_hole_id: str
    actual_collar: Point3Schema
    actual_toe: Point3Schema
    actual_depth: float = Field(0.0, ge=0)
    actual_diameter: float = Field(0.0, ge=0)
    survey_points: list[SurveyPointSchema] = Field(default_factory=list)
    mwd_samples: list[MwdSampleSchema] = Field(default_factory=list)
    role: str = "executed"
    provenance: DataProvenanceSchema = Field(default_factory=DataProvenanceSchema)


class AsChargedHoleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    design_hole_id: str
    decks: list[DeckSchema] = Field(default_factory=list)
    primers: list[float] = Field(default_factory=list)
    primer_items: list[PrimerSchema] = Field(default_factory=list)
    explosive_product: str = ""
    charge_mass_kg: float = Field(0.0, ge=0)
    stemming_length_m: float = Field(0.0, ge=0)
    loading_timestamp: str = ""
    role: str = "executed"
    provenance: DataProvenanceSchema = Field(default_factory=DataProvenanceSchema)


class AsFiredHoleSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    design_hole_id: str
    detonator: DetonatorSchema = Field(default_factory=lambda: DetonatorSchema(id="", hole_id=""))
    detonator_id: str = ""
    detonator_product: str = ""
    detonator_kind: str = "electronic"
    programmed_time_ms: float = 0.0
    verified_time_ms: float | None = None
    firing_timestamp: str = ""
    role: str = "executed"
    provenance: DataProvenanceSchema = Field(default_factory=DataProvenanceSchema)


class HoleDeviationSchema(BaseModel):
    design_hole_id: str
    role: str = "executed"
    collar_offset_m: float
    toe_offset_m: float
    depth_deviation_m: float
    angle_deviation_deg: float
    azimuth_deviation_deg: float
    actual_burden_m: float | None = None
    actual_spacing_m: float | None = None
    designed_burden_m: float | None = None
    designed_spacing_m: float | None = None
    actual_depth_m: float = 0.0
    designed_depth_m: float = 0.0
    actual_diameter_mm: float = 0.0
    designed_diameter_mm: float = 0.0


class MwdFieldSchema(BaseModel):
    id: str
    aliases: list[str] = Field(default_factory=list)
    unit: str = ""
    required: bool = False
    description: str = ""


class MwdSchemaResponse(BaseModel):
    kind: str = "mwd"
    role: str = "executed"
    manufacturer: str | None = None
    vendor_format: str | None = None
    note: str = ""
    fields: list[MwdFieldSchema] = Field(default_factory=list)


class LifecycleEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    at: str = ""
    actor: str = ""
    from_status: str = ""
    to_status: str = ""
    note: str = ""
    confirm: bool = False
    revision: int = 0
    designed_sha256: str = ""
    mutations: list[str] = Field(default_factory=list)


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
    receptors: list[ReceptorSchema] = Field(default_factory=list)
    vibration_models: list[VibrationModelSchema] = Field(default_factory=list)
    vibration_measurements: list[VibrationMeasurementSchema] = Field(default_factory=list)
    as_drilled_holes: list[AsDrilledHoleSchema] = Field(default_factory=list)
    as_charged_holes: list[AsChargedHoleSchema] = Field(default_factory=list)
    as_fired_holes: list[AsFiredHoleSchema] = Field(default_factory=list)
    blast_result: BlastResultSchema | None = None
    lifecycle_status: str = "draft"
    revision: int = 0
    parent_design_id: str = ""
    designed_sha256: str = ""
    lifecycle_events: list[LifecycleEventSchema] = Field(default_factory=list)


class AsDrilledRecordRequest(BaseModel):
    design: BlastDesignSchema
    holes: list[AsDrilledHoleSchema] = Field(default_factory=list)
    replace: bool = False


class AsDrilledCompareRequest(BaseModel):
    design: BlastDesignSchema


class AsDrilledCompareResponse(BaseModel):
    role: str = "executed"
    compared_count: int = 0
    designed_count: int = 0
    as_drilled_count: int = 0
    pattern_basis: str = "none"
    deviations: list[HoleDeviationSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    as_drilled_holes: list[AsDrilledHoleSchema] = Field(default_factory=list)


class AsDrilledRecordResponse(AsDrilledCompareResponse):
    holes: list[HoleSchema] = Field(default_factory=list)


class MwdImportRequest(BaseModel):
    design: BlastDesignSchema
    design_hole_id: str
    samples: list[dict[str, Any]] = Field(default_factory=list)
    source: str = ""


class ChargeDeviationSchema(BaseModel):
    design_hole_id: str
    role: str = "executed"
    comparison: str = "design_vs_charged"
    designed_product: str = ""
    actual_product: str = ""
    product_mismatch: bool = False
    designed_charge_kg: float = 0.0
    actual_charge_kg: float = 0.0
    charge_mass_delta_kg: float = 0.0
    designed_stemming_m: float = 0.0
    actual_stemming_m: float = 0.0
    stemming_delta_m: float = 0.0
    designed_primer_m: float | None = None
    actual_primer_m: float | None = None
    primer_position_delta_m: float | None = None
    designed_deck_from_m: float | None = None
    designed_deck_to_m: float | None = None
    actual_deck_from_m: float | None = None
    actual_deck_to_m: float | None = None
    deck_from_delta_m: float | None = None
    deck_to_delta_m: float | None = None
    actual_hole_depth_m: float = 0.0
    depth_basis: str = "designed"
    leftover_unloaded_m: float | None = None
    overcharge_m: float | None = None
    loading_timestamp: str = ""
    deck_count: int = 0
    designed_deck_count: int = 0


class FiredDeviationSchema(BaseModel):
    design_hole_id: str
    role: str = "executed"
    comparison: str = "design_vs_fired"
    designed_time_ms: float | None = None
    programmed_time_ms: float = 0.0
    verified_time_ms: float | None = None
    programmed_time_delta_ms: float | None = None
    verified_time_delta_ms: float | None = None
    timing_error_ms: float | None = None
    designed_detonator_id: str = ""
    actual_detonator_id: str = ""
    designed_detonator_product: str = ""
    actual_detonator_product: str = ""
    designed_detonator_kind: str = ""
    actual_detonator_kind: str = ""
    detonator_product_mismatch: bool = False
    detonator_kind_mismatch: bool = False
    firing_timestamp: str = ""


class AsChargedRecordRequest(BaseModel):
    design: BlastDesignSchema
    holes: list[AsChargedHoleSchema] = Field(default_factory=list)
    replace: bool = False


class AsChargedCompareRequest(BaseModel):
    design: BlastDesignSchema


class AsChargedCompareResponse(BaseModel):
    role: str = "executed"
    comparison: str = "design_vs_charged"
    compared_count: int = 0
    designed_count: int = 0
    as_charged_count: int = 0
    deviations: list[ChargeDeviationSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    as_charged_holes: list[AsChargedHoleSchema] = Field(default_factory=list)


class AsChargedRecordResponse(AsChargedCompareResponse):
    holes: list[HoleSchema] = Field(default_factory=list)
    loads: list[HoleLoadSchema] = Field(default_factory=list)


class AsFiredRecordRequest(BaseModel):
    design: BlastDesignSchema
    holes: list[AsFiredHoleSchema] = Field(default_factory=list)
    replace: bool = False


class AsFiredCompareRequest(BaseModel):
    design: BlastDesignSchema


class AsFiredCompareResponse(BaseModel):
    role: str = "executed"
    comparison: str = "design_vs_fired"
    compared_count: int = 0
    designed_count: int = 0
    as_fired_count: int = 0
    deviations: list[FiredDeviationSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    as_fired_holes: list[AsFiredHoleSchema] = Field(default_factory=list)


class AsFiredRecordResponse(AsFiredCompareResponse):
    holes: list[HoleSchema] = Field(default_factory=list)
    network: InitiationNetworkSchema = Field(default_factory=InitiationNetworkSchema)


class ExecutionCompareRequest(BaseModel):
    design: BlastDesignSchema


class ExecutionCompareResponse(BaseModel):
    role: str = "executed"
    designed_count: int = 0
    design_vs_drilled: AsDrilledCompareResponse = Field(default_factory=AsDrilledCompareResponse)
    design_vs_charged: AsChargedCompareResponse = Field(default_factory=AsChargedCompareResponse)
    design_vs_fired: AsFiredCompareResponse = Field(default_factory=AsFiredCompareResponse)
    as_drilled_count: int = 0
    as_charged_count: int = 0
    as_fired_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class PredictedVibrationSnapshotSchema(BaseModel):
    receptor_id: str = ""
    ppv_mm_s: float = 0.0
    frequency_hz: float | None = None
    receptor_name: str = ""
    role: str = "predicted"


class MeasuredVibrationSchema(BaseModel):
    role: str = "measured"
    ppv_mm_s: float | None = None
    frequency_hz: float | None = None
    receptor_id: str = ""
    measurements: list[VibrationMeasurementSchema] = Field(default_factory=list)
    source: str = ""
    method: str = ""
    timestamp: str = ""
    notes: str = ""


class MeasuredMuckpileSchema(BaseModel):
    role: str = "measured"
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    volume_m3: float | None = None
    throw_m: float | None = None
    notes: str = ""


class DesignedMuckpileSchema(BaseModel):
    role: str = "designed"
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    volume_m3: float | None = None
    throw_m: float | None = None
    notes: str = ""


class MeasuredBackbreakSchema(BaseModel):
    role: str = "measured"
    max_m: float | None = None
    mean_m: float | None = None
    crest_loss_m: float | None = None
    notes: str = ""


class DesignedBackbreakSchema(BaseModel):
    role: str = "designed"
    max_m: float | None = None
    mean_m: float | None = None
    crest_loss_m: float | None = None
    notes: str = ""


class MeasuredToeConditionSchema(BaseModel):
    role: str = "measured"
    condition: str = ""
    leftover_height_m: float | None = None
    notes: str = ""


class FlyrockObservationSchema(BaseModel):
    role: str = "measured"
    max_range_m: float | None = None
    count: int | None = None
    notes: str = ""


class SecondaryBreakingSchema(BaseModel):
    role: str = "measured"
    volume_m3: float | None = None
    hours: float | None = None
    cost_rub: float | None = None
    method: str = ""
    notes: str = ""


class ActualCostSchema(BaseModel):
    role: str = "measured"
    total_amount_rub: float | None = None
    cost_per_m3: float | None = None
    variable_total_rub: float | None = None
    labor_total_rub: float | None = None
    fixed_total_rub: float | None = None
    secondary_breaking_rub: float | None = None
    notes: str = ""


class PlannedCostSchema(BaseModel):
    role: str = "designed"
    total_amount_rub: float | None = None
    cost_per_m3: float | None = None
    variable_total_rub: float | None = None
    labor_total_rub: float | None = None
    fixed_total_rub: float | None = None
    secondary_breaking_rub: float | None = None
    notes: str = ""


class ComparisonBasisSchema(BaseModel):
    predicted_fragmentation: PredictedFragmentationSchema | None = None
    predicted_vibration: list[PredictedVibrationSnapshotSchema] = Field(default_factory=list)
    planned_cost: PlannedCostSchema | None = None
    designed_fragmentation: DesignedFragmentationTargetSchema | None = None
    designed_muckpile: DesignedMuckpileSchema | None = None
    designed_backbreak: DesignedBackbreakSchema | None = None
    designed_toe_condition: str = "clean"


class BlastResultSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    design_id: str = ""
    role: str = "measured"
    fragmentation: MeasuredFragmentationSchema | None = None
    vibration: MeasuredVibrationSchema | None = None
    muckpile: MeasuredMuckpileSchema | None = None
    backbreak: MeasuredBackbreakSchema | None = None
    toe_condition: MeasuredToeConditionSchema | None = None
    flyrock_observations: list[FlyrockObservationSchema] = Field(default_factory=list)
    secondary_breaking: SecondaryBreakingSchema | None = None
    cost_actual: ActualCostSchema | None = None
    basis: ComparisonBasisSchema | None = None
    recorded_at: str = ""
    provenance: DataProvenanceSchema = Field(default_factory=DataProvenanceSchema)


class ComparisonRowSchema(BaseModel):
    metric: str
    label: str
    unit: str = ""
    predicted: float | None = None
    measured: float | str | None = None
    designed: float | str | None = None
    actual: float | str | None = None
    predicted_minus_measured: float | None = None
    measured_minus_predicted: float | None = None
    relative_error_pct: float | None = None
    designed_minus_actual: float | None = None
    actual_minus_designed: float | None = None
    receptor_id: str | None = None
    designed_label: str | None = None
    actual_label: str | None = None
    mismatch: bool | None = None


class BlastResultRecordRequest(BaseModel):
    design: BlastDesignSchema
    result: BlastResultSchema
    predicted_fragmentation: PredictedFragmentationSchema | None = None
    predicted_vibration: list[PredictedVibrationSnapshotSchema] = Field(default_factory=list)
    planned_cost: PlannedCostSchema | None = None
    designed_fragmentation: DesignedFragmentationTargetSchema | None = None
    designed_muckpile: DesignedMuckpileSchema | None = None
    designed_backbreak: DesignedBackbreakSchema | None = None
    designed_toe_condition: str = "clean"


class BlastResultCompareRequest(BaseModel):
    design: BlastDesignSchema
    predicted_fragmentation: PredictedFragmentationSchema | None = None
    predicted_vibration: list[PredictedVibrationSnapshotSchema] = Field(default_factory=list)
    planned_cost: PlannedCostSchema | None = None
    designed_fragmentation: DesignedFragmentationTargetSchema | None = None
    designed_muckpile: DesignedMuckpileSchema | None = None
    designed_backbreak: DesignedBackbreakSchema | None = None
    designed_toe_condition: str = "clean"


class BlastResultCompareResponse(BaseModel):
    role: str = "measured"
    comparison: str = "post_blast"
    has_result: bool = False
    predicted_vs_measured: list[ComparisonRowSchema] = Field(default_factory=list)
    designed_vs_actual: list[ComparisonRowSchema] = Field(default_factory=list)
    planned_vs_actual_cost: list[ComparisonRowSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: BlastResultSchema | None = None


class BlastResultRecordResponse(BlastResultCompareResponse):
    holes: list[HoleSchema] = Field(default_factory=list)
    loads: list[HoleLoadSchema] = Field(default_factory=list)
    network: InitiationNetworkSchema = Field(default_factory=InitiationNetworkSchema)


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
    firing_events: list[FiringEventSchema] = Field(default_factory=list)


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
    lifecycle_status: str = "draft"
    revision: int = 0
    designed_sha256: str = ""
    parent_design_id: str = ""


class LifecycleStatusSchema(BaseModel):
    name: str
    label: str
    allowed_transitions: list[str] = Field(default_factory=list)
    allowed_mutations: list[str] = Field(default_factory=list)
    frozen_designed: bool = False
    frozen_record: bool = False


class LifecycleMetaResponse(BaseModel):
    statuses: list[LifecycleStatusSchema] = Field(default_factory=list)
    data_roles: dict[str, str] = Field(default_factory=dict)
    auto_transition: bool = False


class WorkstationRoleSchema(BaseModel):
    name: str
    code: str
    label_ru: str
    label_en: str


class WorkstationStageSchema(BaseModel):
    id: str
    label: str
    role: str
    role_code: str
    mutation: str = ""
    panels: list[str] = Field(default_factory=list)
    order: int


class WorkstationTransitionSchema(BaseModel):
    from_status: str
    to_status: str
    label: str


class WorkstationMetaResponse(BaseModel):
    workflow: list[str] = Field(default_factory=list)
    stages: list[WorkstationStageSchema] = Field(default_factory=list)
    statuses: list[LifecycleStatusSchema] = Field(default_factory=list)
    status_labels: dict[str, str] = Field(default_factory=dict)
    transitions: list[WorkstationTransitionSchema] = Field(default_factory=list)
    data_roles: dict[str, str] = Field(default_factory=dict)
    role_codes: dict[str, str] = Field(default_factory=dict)
    role_labels_ru: dict[str, str] = Field(default_factory=dict)
    role_labels_en: dict[str, str] = Field(default_factory=dict)
    roles: list[WorkstationRoleSchema] = Field(default_factory=list)
    overlay_roles: dict[str, str | list[str]] = Field(default_factory=dict)
    display_units: dict[str, str] = Field(default_factory=dict)
    mutations: dict[str, list[str]] = Field(default_factory=dict)
    auto_transition: bool = False
    silent_unit_conversion: bool = False


class LifecycleTransitionRequest(BaseModel):
    to_status: str
    confirm: bool = False
    note: str = ""


class LifecycleStateSchema(BaseModel):
    design_id: str
    name: str = ""
    lifecycle_status: str
    revision: int = 0
    parent_design_id: str = ""
    designed_sha256: str = ""
    allowed_transitions: list[str] = Field(default_factory=list)
    allowed_mutations: list[str] = Field(default_factory=list)
    frozen_designed: bool = False
    frozen_record: bool = False
    events: list[LifecycleEventSchema] = Field(default_factory=list)


class DesignForkRequest(BaseModel):
    name: str = ""


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


class DistributionPointSchema(BaseModel):
    size_mm: float
    passing_pct: float


class ModelProvenanceSchema(BaseModel):
    model: str
    model_version: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)


class PredictedFragmentationSchema(BaseModel):
    role: str = "predicted"
    x20_mm: float
    x50_mm: float
    x80_mm: float
    oversize_pct: float
    powder_factor_kg_m3: float
    curve: list[DistributionPointSchema] = Field(default_factory=list)
    provenance: ModelProvenanceSchema


class MeasuredFragmentationSchema(BaseModel):
    role: str = "measured"
    x20_mm: float | None = None
    x50_mm: float | None = None
    x80_mm: float | None = None
    p20_mm: float | None = None
    p50_mm: float | None = None
    p80_mm: float | None = None
    oversize_pct: float | None = None
    curve: list[DistributionPointSchema] = Field(default_factory=list)
    source: str = ""
    method: str = ""
    timestamp: str = ""
    notes: str = ""


class DesignedFragmentationTargetSchema(BaseModel):
    role: str = "designed"
    lump_size_mm: float
    max_oversize_pct: float = 5.0


class FragmentationInputsSchema(BaseModel):
    burden_m: float = 0.0
    spacing_m: float = 0.0
    bench_height_m: float = 0.0
    diameter_mm: float = 0.0
    charge_mass_kg: float = 0.0
    powder_factor_kg_m3: float = 0.0
    stemming_m: float = 0.0
    explosive_name: str = ""
    explosive_density_t_m3: float = 0.0
    explosive_energy_mj_kg: float = 0.0
    rock_name: str = ""
    rock_density_t_m3: float = 0.0
    rock_ucs_mpa: float = 0.0
    rock_fissuring: float = 0.0
    lump_size_mm: float = 0.0
    hole_oversize_coeff: float = 1.05
    influence_volume_m3: float = 0.0


class FragmentationRegionSchema(BaseModel):
    id: str
    kind: str
    hole_ids: list[str] = Field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    hole_kind: str = "production"
    inputs: FragmentationInputsSchema
    prediction: PredictedFragmentationSchema
    warnings: list[str] = Field(default_factory=list)


class FragmentationMapSampleSchema(BaseModel):
    hole_id: str
    kind: str = "production"
    x: float
    y: float
    x50: float | None = None
    x80: float | None = None
    oversize: float | None = None
    powder_factor: float | None = None


class FragmentationMapsSchema(BaseModel):
    metrics: list[str] = Field(default_factory=list)
    holes: list[FragmentationMapSampleSchema] = Field(default_factory=list)
    stats: dict[str, dict[str, float]] = Field(default_factory=dict)


class FragmentationModelInfoSchema(BaseModel):
    id: str
    version: str
    label: str
    distribution: str


class FragmentationModelsResponse(BaseModel):
    models: list[FragmentationModelInfoSchema]


class FragmentationPredictRequest(BaseModel):
    design: BlastDesignSchema
    model: str = "kuzram"
    lump_size_mm: float = Field(400.0, gt=0)
    max_oversize_pct: float = Field(5.0, gt=0, le=100)
    calibration: dict[str, Any] = Field(default_factory=dict)
    rock: RockPropertiesSchema | None = None
    explosive: ExplosivePropertiesSchema | None = None
    explosives: list[ExplosivePropertiesSchema] = Field(default_factory=list)
    hole_oversize_coeff: float | None = Field(None, ge=1.0, le=1.5)
    measured: list[MeasuredFragmentationSchema] = Field(default_factory=list)


class FragmentationPredictResponse(BaseModel):
    model: str
    model_version: str
    target: DesignedFragmentationTargetSchema
    site: FragmentationRegionSchema
    holes: list[FragmentationRegionSchema] = Field(default_factory=list)
    regions: list[FragmentationRegionSchema] = Field(default_factory=list)
    maps: FragmentationMapsSchema
    warnings: list[str] = Field(default_factory=list)
    measured: list[MeasuredFragmentationSchema] = Field(default_factory=list)
    calibration: dict[str, Any] = Field(default_factory=dict)


class ReceptorAttachRequest(BaseModel):
    design: BlastDesignSchema
    receptor: ReceptorSchema


class ReceptorAttachResponse(BaseModel):
    receptor: ReceptorSchema
    receptors: list[ReceptorSchema]


class VibrationConventionSchema(BaseModel):
    id: str
    label: str
    formula: str


class VibrationConventionsResponse(BaseModel):
    conventions: list[VibrationConventionSchema]
    law: str = "PPV = K × SD^n"


class VibrationPredictRequest(BaseModel):
    design: BlastDesignSchema
    model_id: str = ""
    mic_window_ms: float = Field(8.0, gt=0)
    measured: list[VibrationMeasurementSchema] = Field(default_factory=list)


class VibrationPredictionSchema(BaseModel):
    receptor_id: str
    receptor_name: str = ""
    receptor_kind: str = ""
    role: str = "predicted"
    ppv_mm_s: float
    distance_m: float
    nearest_hole_id: str = ""
    mic_kg: float
    mic_window_ms: float
    mic_hole_ids: list[str] = Field(default_factory=list)
    scaled_distance: str
    scaled_distance_value: float
    scaled_distance_formula: str = ""
    k: float
    n: float
    model_id: str
    ppv_limit_mm_s: float | None = None
    exceeds_limit: bool = False
    measured: list[dict[str, Any]] = Field(default_factory=list)


class VibrationPredictResponse(BaseModel):
    model: VibrationModelSchema
    convention: str
    convention_formula: str
    mic: MicSchema
    mic_window_ms: float
    predictions: list[VibrationPredictionSchema] = Field(default_factory=list)
    measured: list[VibrationMeasurementSchema] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    receptor_count: int = 0
