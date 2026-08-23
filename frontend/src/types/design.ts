// Поля 1:1 с api/schemas/design.py — сервер остаётся источником истины.

export type Point3 = { x: number; y: number; z: number };

export type BenchSurface = {
  crest_z_m: number;
  toe_z_m: number;
  face_angle_deg: number;
};

export type CoordinateSystem = {
  name: string;
  epsg: number | null;
  origin_x: number;
  origin_y: number;
  origin_z: number;
  units: string;
};

export type SurfaceKind = "top" | "floor" | "face" | "post_blast";

export type TIN = {
  vertices: Point3[];
  triangles: number[][];
};

export type SurfaceModel = {
  kind: SurfaceKind;
  name: string;
  source_format: string;
  source_name: string;
  created_at: string;
  coordinate_system: CoordinateSystem;
  points: Point3[];
  polylines: Point3[][];
  tin: TIN;
};

export type SurfaceSet = {
  top: SurfaceModel | null;
  floor: SurfaceModel | null;
  face: SurfaceModel | null;
  post_blast: SurfaceModel | null;
};

export type SurfaceStats = {
  kind: SurfaceKind;
  name: string;
  source_format: string;
  source_name: string;
  point_count: number;
  triangle_count: number;
  polyline_count: number;
  z_min: number | null;
  z_max: number | null;
  bounds: {
    min_x: number;
    min_y: number;
    min_z: number;
    max_x: number;
    max_y: number;
    max_z: number;
  } | null;
};

export type BlockContour = {
  vertices: Point3[];
  free_faces: number[][];
  bench: BenchSurface;
  name: string;
};

export type HoleKind =
  | "production"
  | "buffer"
  | "trim"
  | "presplit"
  | "contour"
  | "stab"
  | "satellite"
  | "infill";
export type HoleSource = "generated" | "manual";
export type DataRole = "designed" | "executed" | "predicted" | "measured";
export type WaterCondition = "dry" | "moist" | "wet" | "flowing" | "";

export type DataProvenance = {
  source: string;
  method: string;
  timestamp: string;
  role: DataRole;
};

export type RockPropertySet = {
  density_kg_m3: number | null;
  ucs_mpa: number | null;
  fracturing: string;
  rqd_pct: number | null;
  youngs_modulus_gpa: number | null;
  poisson_ratio: number | null;
  p_wave_velocity_m_s: number | null;
  joint_spacing_m: number | null;
  joint_dip_deg: number | null;
  joint_dip_direction_deg: number | null;
  blastability: string;
  water_condition: WaterCondition;
};

export type BlastDomain = {
  id: string;
  name: string;
  polygon: Point3[];
  properties: RockPropertySet;
  provenance: DataProvenance;
  z_top_m: number | null;
  z_bottom_m: number | null;
  priority: number;
  color: string;
  notes: string;
  spacing_a_m: number | null;
  burden_b_m: number | null;
};

export type HoleInterval = {
  from_m: number;
  to_m: number;
  domain_id: string;
  domain_name: string;
  properties: RockPropertySet;
  provenance: DataProvenance;
  role: DataRole;
};

export type WaterInterval = {
  from_m: number;
  to_m: number;
  condition: Exclude<WaterCondition, "">;
  provenance: DataProvenance;
  role: DataRole;
  notes: string;
};

export type Hole = {
  id: string;
  row: number;
  col: number;
  collar: Point3;
  toe: Point3;
  diameter_mm: number;
  subdrill_m: number;
  kind: HoleKind;
  source: HoleSource;
  enabled: boolean;
  intervals: HoleInterval[];
  water_intervals: WaterInterval[];
  measured_intervals: HoleInterval[];
  measured_water_intervals: WaterInterval[];
};

export type DeckKind =
  | "stemming"
  | "charge"
  | "bulk_explosive"
  | "packaged_explosive"
  | "air"
  | "air_deck"
  | "inert_deck"
  | "water_deck"
  | "primer"
  | "booster"
  | "detonator";

export type Deck = {
  kind: DeckKind | string;
  from_m: number;
  to_m: number;
  explosive_key: string;
  mass_kg: number;
  product?: string;
};

export type PrimerKind = "primer" | "booster" | "detonator";

export type PrimerItem = {
  position_m: number;
  product: string;
  mass_kg: number;
  kind: PrimerKind | string;
};

export type HoleLoad = {
  hole_id: string;
  decks: Deck[];
  total_charge_kg: number;
  influence_volume_m3: number;
  specific_q_kg_m3: number;
  primers: number[];
  primer_items?: PrimerItem[];
};

export type Connector = {
  from_hole: string;
  to_hole: string;
  delay_ms: number;
  kind: "surface_nsi" | "ds_relay" | "electronic" | "detonating_cord" | string;
};

export type Detonator = {
  id: string;
  hole_id: string;
  delay_ms: number;
  product: string;
  kind: "electronic" | "nonel" | "detonating_cord" | string;
  deck_index: number | null;
  primer_index: number | null;
  channel_id: string;
};

export type SurfaceConnector = {
  id: string;
  from_hole: string;
  to_hole: string;
  delay_ms: number;
  kind: "surface_nsi" | "ds_relay" | "electronic" | "detonating_cord" | string;
  product: string;
};

export type DownholeConnector = {
  id: string;
  hole_id: string;
  delay_ms: number;
  kind: "downhole_nsi" | "electronic" | "detonating_cord" | string;
  deck_index: number | null;
  primer_index: number | null;
  product: string;
};

export type DetonatingCord = {
  id: string;
  hole_ids: string[];
  velocity_m_s: number;
  relay_delay_ms: number;
  product: string;
};

export type Starter = {
  id: string;
  hole_id: string;
  delay_ms: number;
  kind: string;
};

export type ElectronicChannel = {
  id: string;
  hole_id: string;
  time_ms: number;
  deck_index: number | null;
  primer_index: number | null;
  label: string;
};

export type FiringLevel = "hole" | "deck" | "primer";

export type FiringEvent = {
  id: string;
  hole_id: string;
  time_ms: number;
  level: FiringLevel | string;
  deck_index: number | null;
  primer_index: number | null;
  mass_kg: number;
};

export type ElectronicTimingMode =
  | "row"
  | "selection"
  | "direction"
  | "gradient"
  | "v_pattern"
  | "diagonal"
  | "expression";

export type InitiationNetwork = {
  system: "nonel" | "electronic" | "detcord";
  starters: string[];
  connectors: Connector[];
  downhole_delay_ms: Record<string, number>;
  electronic_times_ms: Record<string, number>;
  detonators: Detonator[];
  surface_connectors: SurfaceConnector[];
  downhole_connectors: DownholeConnector[];
  detonating_cords: DetonatingCord[];
  starter_items: Starter[];
  electronic_channels: ElectronicChannel[];
  firing_events: FiringEvent[];
  timing_mode: ElectronicTimingMode | "";
  timing_expression: string;
  timing_params: Record<string, unknown>;
  selected_hole_ids: string[];
};

export type ReceptorKind =
  | "building"
  | "pipeline"
  | "crusher"
  | "highwall"
  | "power_line"
  | "monitoring_station";

export type ScaledDistanceConvention =
  | "q_cube_over_r"
  | "r_over_q_cube"
  | "q_sqrt_over_r"
  | "r_over_q_sqrt";

export type Receptor = {
  id: string;
  name: string;
  kind: ReceptorKind;
  location: Point3;
  ppv_limit_mm_s: number | null;
  notes: string;
};

export type VibrationModel = {
  id: string;
  name: string;
  k: number;
  n: number;
  scaled_distance: ScaledDistanceConvention;
  calibration_source: string;
  confidence: number;
  notes: string;
};

export type VibrationMeasurement = {
  id: string;
  receptor_id: string;
  ppv_mm_s: number;
  frequency_hz: number | null;
  role: "measured";
  distance_m: number | null;
  mic_kg: number | null;
  scaled_distance: ScaledDistanceConvention | "";
  source: string;
  method: string;
  timestamp: string;
  event_label: string;
  notes: string;
};

export type VibrationPrediction = {
  receptor_id: string;
  receptor_name: string;
  receptor_kind: ReceptorKind | string;
  role: "predicted";
  ppv_mm_s: number;
  distance_m: number;
  nearest_hole_id: string;
  mic_kg: number;
  mic_window_ms: number;
  mic_hole_ids: string[];
  scaled_distance: ScaledDistanceConvention | string;
  scaled_distance_value: number;
  scaled_distance_formula: string;
  k: number;
  n: number;
  model_id: string;
  ppv_limit_mm_s: number | null;
  exceeds_limit: boolean;
  measured: VibrationMeasurement[];
};

export type VibrationPredictResponse = {
  model: VibrationModel;
  convention: string;
  convention_formula: string;
  mic: MicResult;
  mic_window_ms: number;
  predictions: VibrationPrediction[];
  measured: VibrationMeasurement[];
  warnings: string[];
  receptor_count: number;
};

export type SurveyPoint = {
  depth_m: number;
  x: number | null;
  y: number | null;
  z: number | null;
};

export type MwdSample = {
  depth_m: number;
  penetration_rate: number | null;
  rotation_pressure: number | null;
  feed_pressure: number | null;
  torque: number | null;
  air_pressure: number | null;
};

export type AsDrilledHole = {
  design_hole_id: string;
  actual_collar: Point3;
  actual_toe: Point3;
  actual_depth: number;
  actual_diameter: number;
  survey_points: SurveyPoint[];
  mwd_samples: MwdSample[];
  role: "executed";
  provenance: DataProvenance;
};

export type HoleDeviation = {
  design_hole_id: string;
  role: "executed" | string;
  collar_offset_m: number;
  toe_offset_m: number;
  depth_deviation_m: number;
  angle_deviation_deg: number;
  azimuth_deviation_deg: number;
  actual_burden_m: number | null;
  actual_spacing_m: number | null;
  designed_burden_m: number | null;
  designed_spacing_m: number | null;
  actual_depth_m: number;
  designed_depth_m: number;
  actual_diameter_mm: number;
  designed_diameter_mm: number;
};

export type AsDrilledCompareResponse = {
  role: "executed" | string;
  compared_count: number;
  designed_count: number;
  as_drilled_count: number;
  pattern_basis: "executed" | "mixed" | "none" | string;
  deviations: HoleDeviation[];
  warnings: string[];
  as_drilled_holes: AsDrilledHole[];
};

export type AsChargedHole = {
  design_hole_id: string;
  decks: Deck[];
  primers: number[];
  primer_items: PrimerItem[];
  explosive_product: string;
  charge_mass_kg: number;
  stemming_length_m: number;
  loading_timestamp: string;
  role: "executed";
  provenance: DataProvenance;
};

export type ChargeDeviation = {
  design_hole_id: string;
  role: "executed" | string;
  comparison: "design_vs_charged" | string;
  designed_product: string;
  actual_product: string;
  product_mismatch: boolean;
  designed_charge_kg: number;
  actual_charge_kg: number;
  charge_mass_delta_kg: number;
  designed_stemming_m: number;
  actual_stemming_m: number;
  stemming_delta_m: number;
  designed_primer_m: number | null;
  actual_primer_m: number | null;
  primer_position_delta_m: number | null;
  designed_deck_from_m: number | null;
  designed_deck_to_m: number | null;
  actual_deck_from_m: number | null;
  actual_deck_to_m: number | null;
  deck_from_delta_m: number | null;
  deck_to_delta_m: number | null;
  actual_hole_depth_m: number;
  depth_basis: "drilled" | "designed" | string;
  leftover_unloaded_m: number | null;
  overcharge_m: number | null;
  loading_timestamp: string;
  deck_count: number;
  designed_deck_count: number;
};

export type AsChargedCompareResponse = {
  role: "executed" | string;
  comparison: "design_vs_charged" | string;
  compared_count: number;
  designed_count: number;
  as_charged_count: number;
  deviations: ChargeDeviation[];
  warnings: string[];
  as_charged_holes: AsChargedHole[];
};

export type AsFiredHole = {
  design_hole_id: string;
  detonator: Detonator;
  detonator_id?: string;
  detonator_product?: string;
  detonator_kind?: string;
  programmed_time_ms: number;
  verified_time_ms: number | null;
  firing_timestamp: string;
  role: "executed";
  provenance: DataProvenance;
};

export type FiredDeviation = {
  design_hole_id: string;
  role: "executed" | string;
  comparison: "design_vs_fired" | string;
  designed_time_ms: number | null;
  programmed_time_ms: number;
  verified_time_ms: number | null;
  programmed_time_delta_ms: number | null;
  verified_time_delta_ms: number | null;
  timing_error_ms: number | null;
  designed_detonator_id: string;
  actual_detonator_id: string;
  designed_detonator_product: string;
  actual_detonator_product: string;
  designed_detonator_kind: string;
  actual_detonator_kind: string;
  detonator_product_mismatch: boolean;
  detonator_kind_mismatch: boolean;
  firing_timestamp: string;
};

export type AsFiredCompareResponse = {
  role: "executed" | string;
  comparison: "design_vs_fired" | string;
  compared_count: number;
  designed_count: number;
  as_fired_count: number;
  deviations: FiredDeviation[];
  warnings: string[];
  as_fired_holes: AsFiredHole[];
};

export type ExecutionCompareResponse = {
  role: "executed" | string;
  designed_count: number;
  design_vs_drilled: AsDrilledCompareResponse;
  design_vs_charged: AsChargedCompareResponse;
  design_vs_fired: AsFiredCompareResponse;
  as_drilled_count: number;
  as_charged_count: number;
  as_fired_count: number;
  warnings: string[];
};

export type MwdFieldInfo = {
  id: string;
  aliases: string[];
  unit: string;
  required: boolean;
  description: string;
};

export type MwdSchemaResponse = {
  kind: string;
  role: string;
  manufacturer: string | null;
  vendor_format: string | null;
  note: string;
  fields: MwdFieldInfo[];
};

export type BlastDesign = {
  design_id: string;
  name: string;
  version: number;
  updated_at: string;
  contour: BlockContour;
  holes: Hole[];
  loads: HoleLoad[];
  network: InitiationNetwork;
  pattern_params: Record<string, unknown>;
  charge_rules: Record<string, unknown>;
  rock_name: string;
  explosive_key: string;
  coordinate_system: CoordinateSystem;
  surfaces: SurfaceSet;
  domains: BlastDomain[];
  water_table_z_m: number | null;
  receptors: Receptor[];
  vibration_models: VibrationModel[];
  vibration_measurements: VibrationMeasurement[];
  as_drilled_holes: AsDrilledHole[];
  as_charged_holes: AsChargedHole[];
  as_fired_holes: AsFiredHole[];
  blast_result: BlastResult | null;
};

export type PatternType = "square" | "rectangular" | "staggered" | "variable" | "domain_dependent";

export type RowPatternParams = {
  spacing_a_m: number;
  burden_b_m: number;
  shift_ratio: number;
  kind: HoleKind;
};

export type PatternParams = {
  pattern: PatternType;
  spacing_a_m: number;
  burden_b_m: number;
  row_shift_ratio: number;
  row_azimuth_deg: number;
  offset_from_face_m: number;
  first_row_burden_m: number | null;
  first_row_follow_face: boolean;
  edge_margin_m: number;
  diameter_mm: number;
  subdrill_m: number;
  angle_deg: number;
  azimuth_deg: number;
  default_kind: HoleKind;
  row_params: RowPatternParams[];
  contour_row: boolean;
  presplit_row: boolean;
  trim_row: boolean;
  buffer_row: boolean;
  stab_row: boolean;
  satellite_holes: boolean;
  infill_holes: boolean;
  contour_spacing_m: number;
  presplit_spacing_m: number;
  trim_spacing_m: number;
  buffer_offset_m: number;
  buffer_spacing_m: number;
  stab_depth_m: number;
  satellite_radius_m: number;
  infill_gap_factor: number;
};

export type MapMetric =
  | "burden"
  | "spacing"
  | "hole_depth"
  | "subdrill"
  | "bench_height"
  | "toe_burden"
  | "collar_burden";

export type FragmentationMapMetric = "x50" | "x80" | "oversize" | "powder_factor";
export type OverlayMetric = MapMetric | FragmentationMapMetric;

export type HoleMapSample = {
  hole_id: string;
  kind: HoleKind | string;
  x: number;
  y: number;
  burden: number | null;
  spacing: number | null;
  hole_depth: number;
  subdrill: number;
  bench_height: number;
  toe_burden: number | null;
  collar_burden: number | null;
  true_face_burden: number | null;
};

export type EngineeringMaps = {
  metrics: MapMetric[];
  holes: HoleMapSample[];
  stats: Record<string, { min: number; avg: number; max: number; count: number }>;
};

export type PatternGenerateResponse = {
  holes: Hole[];
  hole_count: number;
  block_volume_m3: number;
};

export type DeckingType = "continuous" | "spaced";

export type GeologicalInterval = "" | "any" | "bottom" | "column" | "collar";
export type ChargeActionRegion = "interval" | "bottom" | "column" | "collar" | "remaining";

export type ChargeCondition = {
  hole_kinds: string[];
  rows: number[];
  depth_min_m: number | null;
  depth_max_m: number | null;
  diameter_min_mm: number | null;
  diameter_max_mm: number | null;
  burden_min_m: number | null;
  burden_max_m: number | null;
  spacing_min_m: number | null;
  spacing_max_m: number | null;
  rock_domain_ids: string[];
  geological_interval: GeologicalInterval | string;
  water: WaterCondition | string;
  distance_to_face_min_m: number | null;
  distance_to_face_max_m: number | null;
  target_pf_min: number | null;
  target_pf_max: number | null;
};

export type ChargeAction = {
  kind: DeckKind | string;
  explosive_key: string;
  product: string;
  region: ChargeActionRegion | string;
  length_m: number | null;
  mass_kg: number | null;
  place_primer: boolean;
  primer_offset_m: number | null;
  primer_product: string;
  primer_mass_kg: number;
  primer_kind: PrimerKind | string;
};

export type ChargeTemplate = {
  id: string;
  name: string;
  conditions: ChargeCondition;
  actions: ChargeAction[];
  priority: number;
  enabled: boolean;
  notes: string;
};

export type ChargeRules = {
  hole_oversize_coeff: number;
  stemming_m: number | null;
  stemming_k: number;
  decking: DeckingType;
  deck_count: number;
  air_gap_m: number;
  primer_offset_m: number;
  grid_a_m: number;
  grid_b_m: number;
  bottom_length_m: number;
  target_pf: number | null;
  templates: ChargeTemplate[];
};

export type ChargeExplosive = { name: string; density_t_m3: number; power_mj_kg: number };

export type ChargeGenerateResponse = {
  loads: HoleLoad[];
  total_charge_kg: number;
  total_holes_charged: number;
};

export type DesignSummary = {
  design_id: string;
  name: string;
  updated_at: string;
  hole_count: number;
};

export type SchemeType = "row" | "echelon" | "diagonal_v" | "trapezoid";
export type SystemType = InitiationNetwork["system"];

export type TieParams = {
  system: SystemType;
  interval_ms: number;
  downhole_delay_ms: number;
  include_contour: boolean;
  timing_mode: ElectronicTimingMode | "";
  timing_expression: string;
  direction_azimuth_deg: number;
  gradient_from_ms: number;
  gradient_to_ms: number;
  base_ms: number;
  selected_hole_ids: string[];
};

export type TieGenerateResponse = {
  network: InitiationNetwork;
  starters_count: number;
  connectors_count: number;
};

export type ValidationWarning = {
  code: string;
  hole_id: string | null;
  message: string;
};

export type DesignSummaryStats = {
  hole_count: number;
  production_hole_count: number;
  contour_hole_count: number;
  drilling_footage_m: number;
  block_volume_m3: number;
  total_charge_kg: number;
  avg_specific_q_kg_m3: number;
  explosive_breakdown_kg: Record<string, number>;
  charged_hole_count: number;
  loads_by_hole_count: number;
  hole_counts_by_kind?: Record<string, number>;
};

export type MicResult = {
  mic_kg: number;
  window_start_ms: number;
  hole_ids: string[];
};

export type Isoline = {
  time_ms: number;
  segments: number[][][];
};

export type PpvRequest = {
  distance_m: number;
  k: number;
  n: number;
};

export type AnalyzeResponse = {
  times_ms: Record<string, number>;
  timing_warnings: string[];
  validation_warnings: ValidationWarning[];
  summary: DesignSummaryStats;
  mic: MicResult;
  isolines: Isoline[];
  ppv_mm_s: number | null;
  maps?: EngineeringMaps | null;
  firing_events?: FiringEvent[];
};

export type CostScenarioId = "drill_blast" | "drilling" | "blasting" | "contour_blasting";

export type DesignCostResult = {
  scenario_id: string;
  work_object_name: string;
  total_amount_rub: number;
  cost_per_m3: number;
  cost_per_ton: number;
  variable_total_rub: number;
  fixed_total_rub: number;
  labor_total_rub: number;
  notes: string[];
};

export type GeologyInterceptResponse = {
  holes: Hole[];
  interval_count: number;
  water_interval_count: number;
};

export function emptyProvenance(role: DataRole = "designed"): DataProvenance {
  return { source: "engineer", method: "manual", timestamp: "", role };
}

export function emptyRockProperties(): RockPropertySet {
  return {
    density_kg_m3: null,
    ucs_mpa: null,
    fracturing: "",
    rqd_pct: null,
    youngs_modulus_gpa: null,
    poisson_ratio: null,
    p_wave_velocity_m_s: null,
    joint_spacing_m: null,
    joint_dip_deg: null,
    joint_dip_direction_deg: null,
    blastability: "",
    water_condition: "",
  };
}

export function emptyHoleGeology(): Pick<Hole, "intervals" | "water_intervals" | "measured_intervals" | "measured_water_intervals"> {
  return { intervals: [], water_intervals: [], measured_intervals: [], measured_water_intervals: [] };
}

export function emptyCoordinateSystem(): CoordinateSystem {
  return { name: "local", epsg: null, origin_x: 0, origin_y: 0, origin_z: 0, units: "m" };
}

export function emptySurfaces(): SurfaceSet {
  return { top: null, floor: null, face: null, post_blast: null };
}

export function emptyContour(): BlockContour {
  return {
    vertices: [],
    free_faces: [],
    bench: { crest_z_m: 0, toe_z_m: -10, face_angle_deg: 75 },
    name: "Блок",
  };
}

export function emptyDesign(): BlastDesign {
  return {
    design_id: "",
    name: "Новый паспорт",
    version: 8,
    updated_at: "",
    contour: emptyContour(),
    holes: [],
    loads: [],
    network: emptyNetwork(),
    pattern_params: {},
    charge_rules: {},
    rock_name: "",
    explosive_key: "",
    coordinate_system: emptyCoordinateSystem(),
    surfaces: emptySurfaces(),
    domains: [],
    water_table_z_m: null,
    receptors: [],
    vibration_models: [defaultVibrationModel()],
    vibration_measurements: [],
    as_drilled_holes: [],
    as_charged_holes: [],
    as_fired_holes: [],
    blast_result: null,
  };
}

export function defaultVibrationModel(): VibrationModel {
  return {
    id: "vm-site",
    name: "Площадочный закон",
    k: 200,
    n: 1.6,
    scaled_distance: "q_cube_over_r",
    calibration_source: "ориентировочно",
    confidence: 0.3,
    notes: "PPV = K × SD^n. Коэффициенты ориентировочные, не норматив.",
  };
}

export function emptyReceptor(existing: Receptor[], kind: ReceptorKind = "building"): Receptor {
  const used = new Set(existing.map((item) => item.id));
  let index = existing.length + 1;
  while (used.has(`R-${index}`)) index += 1;
  return {
    id: `R-${index}`,
    name: RECEPTOR_KIND_LABELS[kind],
    kind,
    location: { x: 0, y: 0, z: 0 },
    ppv_limit_mm_s: null,
    notes: "",
  };
}

export function emptyVibrationMeasurement(receptorId: string, existing: VibrationMeasurement[]): VibrationMeasurement {
  const used = new Set(existing.map((item) => item.id));
  let index = existing.length + 1;
  while (used.has(`VM-${index}`)) index += 1;
  return {
    id: `VM-${index}`,
    receptor_id: receptorId,
    ppv_mm_s: 0,
    frequency_hz: null,
    role: "measured",
    distance_m: null,
    mic_kg: null,
    scaled_distance: "",
    source: "",
    method: "",
    timestamp: "",
    event_label: "",
    notes: "",
  };
}

export function emptyAsDrilled(hole: Hole): AsDrilledHole {
  return {
    design_hole_id: hole.id,
    actual_collar: { ...hole.collar },
    actual_toe: { ...hole.toe },
    actual_depth: Math.hypot(
      hole.toe.x - hole.collar.x,
      hole.toe.y - hole.collar.y,
      hole.toe.z - hole.collar.z,
    ),
    actual_diameter: hole.diameter_mm,
    survey_points: [],
    mwd_samples: [],
    role: "executed",
    provenance: emptyProvenance("executed"),
  };
}

export function emptyAsCharged(load: HoleLoad | null, holeId: string, explosiveKey = ""): AsChargedHole {
  const decks = load?.decks ? load.decks.map((deck) => ({ ...deck })) : [];
  const primerItems = load?.primer_items ? load.primer_items.map((item) => ({ ...item })) : [];
  const primers = load?.primers ? [...load.primers] : primerItems.map((item) => item.position_m);
  const explosiveDecks = decks.filter((deck) => deck.kind === "charge" || deck.kind === "bulk_explosive" || deck.kind === "packaged_explosive");
  const stemming = decks.filter((deck) => deck.kind === "stemming").reduce((sum, deck) => sum + Math.abs(deck.to_m - deck.from_m), 0);
  const best = explosiveDecks.reduce<Deck | null>((acc, deck) => (!acc || deck.mass_kg > acc.mass_kg ? deck : acc), null);
  return {
    design_hole_id: holeId,
    decks,
    primers,
    primer_items: primerItems,
    explosive_product: best?.product || best?.explosive_key || explosiveKey,
    charge_mass_kg: load?.total_charge_kg ?? explosiveDecks.reduce((sum, deck) => sum + deck.mass_kg, 0),
    stemming_length_m: stemming,
    loading_timestamp: "",
    role: "executed",
    provenance: emptyProvenance("executed"),
  };
}

export function emptyAsFired(holeId: string, network: InitiationNetwork, designedTimeMs = 0): AsFiredHole {
  const detonator = network.detonators.find((item) => item.hole_id === holeId) ?? {
    id: `det-${holeId}`,
    hole_id: holeId,
    delay_ms: 0,
    product: "",
    kind: "electronic",
    deck_index: null,
    primer_index: null,
    channel_id: "",
  };
  const programmed = network.electronic_times_ms[holeId]
    ?? network.electronic_channels.find((item) => item.hole_id === holeId)?.time_ms
    ?? designedTimeMs;
  return {
    design_hole_id: holeId,
    detonator: { ...detonator },
    programmed_time_ms: programmed,
    verified_time_ms: null,
    firing_timestamp: "",
    role: "executed",
    provenance: emptyProvenance("executed"),
  };
}

export const AS_DRILLED_METRIC_LABELS: Record<string, string> = {
  collar_offset_m: "Смещение устья",
  toe_offset_m: "Смещение забоя",
  depth_deviation_m: "Отклонение глубины",
  angle_deviation_deg: "Отклонение угла",
  azimuth_deviation_deg: "Отклонение азимута",
  actual_burden_m: "Фактическая ЛНС",
  actual_spacing_m: "Фактический шаг",
};

export const AS_CHARGED_METRIC_LABELS: Record<string, string> = {
  charge_mass_delta_kg: "Δ массы заряда",
  stemming_delta_m: "Δ забойки",
  primer_position_delta_m: "Δ боевика",
  leftover_unloaded_m: "Недозаряд",
  overcharge_m: "Перезаряд",
};

export const AS_FIRED_METRIC_LABELS: Record<string, string> = {
  programmed_time_delta_ms: "Δ программного времени",
  verified_time_delta_ms: "Δ проверенного времени",
  timing_error_ms: "Ошибка таймера",
};

export type ToeCondition = "clean" | "minor" | "heavy" | "unbroken" | "";

export const TOE_CONDITION_LABELS: Record<string, string> = {
  clean: "Чистый забой",
  minor: "Небольшой недобур",
  heavy: "Сильный недобур",
  unbroken: "Не взорвано",
};

export type PredictedVibrationSnapshot = {
  receptor_id: string;
  ppv_mm_s: number;
  frequency_hz: number | null;
  receptor_name: string;
  role: "predicted";
};

export type MeasuredVibration = {
  role: "measured";
  ppv_mm_s: number | null;
  frequency_hz: number | null;
  receptor_id: string;
  measurements: VibrationMeasurement[];
  source: string;
  method: string;
  timestamp: string;
  notes: string;
};

export type MeasuredMuckpile = {
  role: "measured";
  length_m: number | null;
  width_m: number | null;
  height_m: number | null;
  volume_m3: number | null;
  throw_m: number | null;
  notes: string;
};

export type DesignedMuckpile = {
  role: "designed";
  length_m: number | null;
  width_m: number | null;
  height_m: number | null;
  volume_m3: number | null;
  throw_m: number | null;
  notes: string;
};

export type MeasuredBackbreak = {
  role: "measured";
  max_m: number | null;
  mean_m: number | null;
  crest_loss_m: number | null;
  notes: string;
};

export type DesignedBackbreak = {
  role: "designed";
  max_m: number | null;
  mean_m: number | null;
  crest_loss_m: number | null;
  notes: string;
};

export type MeasuredToeCondition = {
  role: "measured";
  condition: ToeCondition | string;
  leftover_height_m: number | null;
  notes: string;
};

export type FlyrockObservation = {
  role: "measured";
  max_range_m: number | null;
  count: number | null;
  notes: string;
};

export type SecondaryBreaking = {
  role: "measured";
  volume_m3: number | null;
  hours: number | null;
  cost_rub: number | null;
  method: string;
  notes: string;
};

export type ActualCost = {
  role: "measured";
  total_amount_rub: number | null;
  cost_per_m3: number | null;
  variable_total_rub: number | null;
  labor_total_rub: number | null;
  fixed_total_rub: number | null;
  secondary_breaking_rub: number | null;
  notes: string;
};

export type PlannedCost = {
  role: "designed";
  total_amount_rub: number | null;
  cost_per_m3: number | null;
  variable_total_rub: number | null;
  labor_total_rub: number | null;
  fixed_total_rub: number | null;
  secondary_breaking_rub: number | null;
  notes: string;
};

export type ComparisonBasis = {
  predicted_fragmentation: PredictedFragmentation | null;
  predicted_vibration: PredictedVibrationSnapshot[];
  planned_cost: PlannedCost | null;
  designed_fragmentation: DesignedFragmentationTarget | null;
  designed_muckpile: DesignedMuckpile | null;
  designed_backbreak: DesignedBackbreak | null;
  designed_toe_condition: string;
};

export type BlastResult = {
  design_id: string;
  role: "measured";
  fragmentation: MeasuredFragmentation | null;
  vibration: MeasuredVibration | null;
  muckpile: MeasuredMuckpile | null;
  backbreak: MeasuredBackbreak | null;
  toe_condition: MeasuredToeCondition | null;
  flyrock_observations: FlyrockObservation[];
  secondary_breaking: SecondaryBreaking | null;
  cost_actual: ActualCost | null;
  basis: ComparisonBasis | null;
  recorded_at: string;
  provenance: DataProvenance;
};

export type ComparisonRow = {
  metric: string;
  label: string;
  unit: string;
  predicted: number | null;
  measured: number | string | null;
  designed: number | string | null;
  actual: number | string | null;
  predicted_minus_measured: number | null;
  measured_minus_predicted: number | null;
  relative_error_pct: number | null;
  designed_minus_actual: number | null;
  actual_minus_designed: number | null;
  receptor_id?: string | null;
  designed_label?: string | null;
  actual_label?: string | null;
  mismatch?: boolean | null;
};

export type BlastResultCompareResponse = {
  role: string;
  comparison: string;
  has_result: boolean;
  predicted_vs_measured: ComparisonRow[];
  designed_vs_actual: ComparisonRow[];
  planned_vs_actual_cost: ComparisonRow[];
  warnings: string[];
  result: BlastResult | null;
};

export function emptyMeasuredFragmentation(): MeasuredFragmentation {
  return {
    role: "measured",
    x20_mm: null,
    x50_mm: null,
    x80_mm: null,
    oversize_pct: null,
    curve: [],
    source: "",
    method: "",
  };
}

export function emptyMeasuredVibration(): MeasuredVibration {
  return {
    role: "measured",
    ppv_mm_s: null,
    frequency_hz: null,
    receptor_id: "",
    measurements: [],
    source: "",
    method: "",
    timestamp: "",
    notes: "",
  };
}

export function emptyMeasuredMuckpile(): MeasuredMuckpile {
  return { role: "measured", length_m: null, width_m: null, height_m: null, volume_m3: null, throw_m: null, notes: "" };
}

export function emptyMeasuredBackbreak(): MeasuredBackbreak {
  return { role: "measured", max_m: null, mean_m: null, crest_loss_m: null, notes: "" };
}

export function emptyMeasuredToe(): MeasuredToeCondition {
  return { role: "measured", condition: "clean", leftover_height_m: null, notes: "" };
}

export function emptyFlyrock(): FlyrockObservation {
  return { role: "measured", max_range_m: null, count: null, notes: "" };
}

export function emptySecondaryBreaking(): SecondaryBreaking {
  return { role: "measured", volume_m3: null, hours: null, cost_rub: null, method: "", notes: "" };
}

export function emptyActualCost(): ActualCost {
  return {
    role: "measured",
    total_amount_rub: null,
    cost_per_m3: null,
    variable_total_rub: null,
    labor_total_rub: null,
    fixed_total_rub: null,
    secondary_breaking_rub: null,
    notes: "",
  };
}

export function emptyBlastResult(designId = ""): BlastResult {
  return {
    design_id: designId,
    role: "measured",
    fragmentation: emptyMeasuredFragmentation(),
    vibration: emptyMeasuredVibration(),
    muckpile: emptyMeasuredMuckpile(),
    backbreak: emptyMeasuredBackbreak(),
    toe_condition: emptyMeasuredToe(),
    flyrock_observations: [emptyFlyrock()],
    secondary_breaking: emptySecondaryBreaking(),
    cost_actual: emptyActualCost(),
    basis: null,
    recorded_at: "",
    provenance: emptyProvenance("measured"),
  };
}

export const POST_BLAST_METRIC_LABELS: Record<string, string> = {
  p20_mm: "P20",
  p50_mm: "P50",
  p80_mm: "P80",
  oversize_pct: "Негабарит",
  ppv_mm_s: "PPV",
  frequency_hz: "Частота",
  length_m: "Длина развала",
  width_m: "Ширина развала",
  height_m: "Высота развала",
  volume_m3: "Объём развала",
  throw_m: "Отброс",
  max_m: "Вывал, макс.",
  mean_m: "Вывал, среднее",
  crest_loss_m: "Потеря бровки",
  leftover_height_m: "Остаток на почве",
  total_amount_rub: "Итого",
  cost_per_m3: "Цена за м³",
};

export const RECEPTOR_KIND_LABELS: Record<ReceptorKind, string> = {
  building: "Здание",
  pipeline: "Трубопровод",
  crusher: "Дробилка",
  highwall: "Борт / уступ",
  power_line: "ЛЭП",
  monitoring_station: "Сейсмопост",
};

export const SCALED_DISTANCE_LABELS: Record<ScaledDistanceConvention, string> = {
  q_cube_over_r: "Q⅓ / R",
  r_over_q_cube: "R / Q⅓",
  q_sqrt_over_r: "√Q / R",
  r_over_q_sqrt: "R / √Q",
};

export const SCALED_DISTANCE_FORMULAS: Record<ScaledDistanceConvention, string> = {
  q_cube_over_r: "SD = Q^(1/3) / R",
  r_over_q_cube: "SD = R / Q^(1/3)",
  q_sqrt_over_r: "SD = Q^(1/2) / R",
  r_over_q_sqrt: "SD = R / Q^(1/2)",
};

export function emptyNetwork(): InitiationNetwork {
  return {
    system: "nonel",
    starters: [],
    connectors: [],
    downhole_delay_ms: {},
    electronic_times_ms: {},
    detonators: [],
    surface_connectors: [],
    downhole_connectors: [],
    detonating_cords: [],
    starter_items: [],
    electronic_channels: [],
    firing_events: [],
    timing_mode: "",
    timing_expression: "",
    timing_params: {},
    selected_hole_ids: [],
  };
}

export function normalizeNetwork(raw?: Partial<InitiationNetwork> | null): InitiationNetwork {
  const base = emptyNetwork();
  if (!raw) return base;
  return {
    ...base,
    ...raw,
    starters: raw.starters ?? [],
    connectors: raw.connectors ?? [],
    downhole_delay_ms: raw.downhole_delay_ms ?? {},
    electronic_times_ms: raw.electronic_times_ms ?? {},
    detonators: raw.detonators ?? [],
    surface_connectors: raw.surface_connectors ?? [],
    downhole_connectors: raw.downhole_connectors ?? [],
    detonating_cords: raw.detonating_cords ?? [],
    starter_items: raw.starter_items ?? [],
    electronic_channels: raw.electronic_channels ?? [],
    firing_events: raw.firing_events ?? [],
    timing_mode: raw.timing_mode ?? "",
    timing_expression: raw.timing_expression ?? "",
    timing_params: raw.timing_params ?? {},
    selected_hole_ids: raw.selected_hole_ids ?? [],
  };
}

export function networkTies(network: InitiationNetwork): SurfaceConnector[] {
  if (network.surface_connectors && network.surface_connectors.length) {
    return network.surface_connectors;
  }
  return (network.connectors ?? []).map((item) => ({
    id: `sc-${item.from_hole}-${item.to_hole}`,
    from_hole: item.from_hole,
    to_hole: item.to_hole,
    delay_ms: item.delay_ms,
    kind: item.kind,
    product: "",
  }));
}

export const DEFAULT_TIE_PARAMS: TieParams = {
  system: "nonel",
  interval_ms: 25,
  downhole_delay_ms: 500,
  include_contour: false,
  timing_mode: "",
  timing_expression: "",
  direction_azimuth_deg: 0,
  gradient_from_ms: 0,
  gradient_to_ms: 250,
  base_ms: 0,
  selected_hole_ids: [],
};

export const ELECTRONIC_MODE_OPTIONS: { value: ElectronicTimingMode; label: string; hint: string }[] = [
  { value: "row", label: "По рядам", hint: "ряд × интервал" },
  { value: "selection", label: "По выбору", hint: "порядок выделения" },
  { value: "direction", label: "По направлению", hint: "проекция на азимут" },
  { value: "gradient", label: "Градиент", hint: "от–до по блоку" },
  { value: "v_pattern", label: "V-схема", hint: "от центра ряда" },
  { value: "diagonal", label: "Диагональ", hint: "ряд + колонка" },
  { value: "expression", label: "Выражение", hint: "row, col, interval" },
];

export const DEFAULT_PPV_REQUEST: PpvRequest = {
  distance_m: 200,
  k: 200,
  n: 1.6,
};

export function emptyChargeCondition(): ChargeCondition {
  return {
    hole_kinds: [],
    rows: [],
    depth_min_m: null,
    depth_max_m: null,
    diameter_min_mm: null,
    diameter_max_mm: null,
    burden_min_m: null,
    burden_max_m: null,
    spacing_min_m: null,
    spacing_max_m: null,
    rock_domain_ids: [],
    geological_interval: "",
    water: "",
    distance_to_face_min_m: null,
    distance_to_face_max_m: null,
    target_pf_min: null,
    target_pf_max: null,
  };
}

export function emptyChargeAction(): ChargeAction {
  return {
    kind: "bulk_explosive",
    explosive_key: "",
    product: "",
    region: "interval",
    length_m: null,
    mass_kg: null,
    place_primer: false,
    primer_offset_m: null,
    primer_product: "",
    primer_mass_kg: 0,
    primer_kind: "primer",
  };
}

export function emptyChargeTemplate(existing: ChargeTemplate[] = []): ChargeTemplate {
  const used = new Set(existing.map((item) => item.id));
  let index = existing.length + 1;
  while (used.has(`T-${index}`)) index += 1;
  return {
    id: `T-${index}`,
    name: "Новый шаблон",
    conditions: emptyChargeCondition(),
    actions: [emptyChargeAction()],
    priority: existing.length ? Math.max(...existing.map((item) => item.priority)) + 10 : 10,
    enabled: true,
    notes: "",
  };
}

export function exampleChargeTemplates(): ChargeTemplate[] {
  return [
    {
      id: "T-bottom",
      name: "Дно — плотная эмульсия",
      priority: 30,
      enabled: true,
      notes: "Нижняя часть скважины: высокое давление",
      conditions: { ...emptyChargeCondition(), geological_interval: "bottom" },
      actions: [{ ...emptyChargeAction(), explosive_key: "Эмульсия плотная", region: "bottom", length_m: 2, place_primer: true }],
    },
    {
      id: "T-wet",
      name: "Обводнение — водоустойчивая эмульсия",
      priority: 20,
      enabled: true,
      notes: "Мокрый интервал нельзя заряжать АНФО",
      conditions: { ...emptyChargeCondition(), water: "wet" },
      actions: [{ ...emptyChargeAction(), explosive_key: "Эмульсия водоустойчивая", region: "interval", place_primer: true }],
    },
    {
      id: "T-dry",
      name: "Сухая колонна — АНФО",
      priority: 10,
      enabled: true,
      notes: "Сухой столб между забойкой и дном",
      conditions: { ...emptyChargeCondition(), water: "dry" },
      actions: [{ ...emptyChargeAction(), explosive_key: "АНФО", region: "interval" }],
    },
  ];
}

export const EXPLOSIVE_DECK_KINDS = new Set<string>(["charge", "bulk_explosive", "packaged_explosive"]);

export function isExplosiveDeckKind(kind: string): boolean {
  return EXPLOSIVE_DECK_KINDS.has(kind);
}

export function primerDepths(load: HoleLoad): number[] {
  if (load.primer_items && load.primer_items.length) {
    return load.primer_items.map((item) => item.position_m);
  }
  return load.primers ?? [];
}

export const DEFAULT_CHARGE_RULES: ChargeRules = {
  hole_oversize_coeff: 1.05,
  stemming_m: null,
  stemming_k: 20,
  decking: "continuous",
  deck_count: 2,
  air_gap_m: 1,
  primer_offset_m: 0.3,
  grid_a_m: 5,
  grid_b_m: 4,
  bottom_length_m: 2,
  target_pf: null,
  templates: [],
};

export const DECK_KIND_LABELS: Record<string, string> = {
  stemming: "Забойка",
  charge: "Заряд",
  bulk_explosive: "Россыпное ВВ",
  packaged_explosive: "Патронированное ВВ",
  air: "Воздушный промежуток",
  air_deck: "Воздушный промежуток",
  inert_deck: "Инертный промежуток",
  water_deck: "Водяной промежуток",
  primer: "Боевик",
  booster: "Бустер",
  detonator: "Детонатор",
};

export const CHARGE_REGION_LABELS: Record<string, string> = {
  interval: "Интервал",
  bottom: "Дно",
  column: "Колонна",
  collar: "Устье",
  remaining: "Остаток",
};

export const GEOLOGICAL_INTERVAL_LABELS: Record<string, string> = {
  "": "любой",
  any: "любой",
  bottom: "дно",
  column: "колонна",
  collar: "устье",
};

export const DEFAULT_PATTERN_PARAMS: PatternParams = {
  pattern: "staggered",
  spacing_a_m: 5,
  burden_b_m: 4,
  row_shift_ratio: 0.5,
  row_azimuth_deg: 0,
  offset_from_face_m: 2,
  first_row_burden_m: null,
  first_row_follow_face: false,
  edge_margin_m: 1,
  diameter_mm: 152,
  subdrill_m: 1,
  angle_deg: 0,
  azimuth_deg: 0,
  default_kind: "production",
  row_params: [
    { spacing_a_m: 5, burden_b_m: 3.5, shift_ratio: 0, kind: "production" },
    { spacing_a_m: 5, burden_b_m: 4, shift_ratio: 0.5, kind: "production" },
  ],
  contour_row: false,
  presplit_row: false,
  trim_row: false,
  buffer_row: false,
  stab_row: false,
  satellite_holes: false,
  infill_holes: false,
  contour_spacing_m: 2,
  presplit_spacing_m: 1.5,
  trim_spacing_m: 2.5,
  buffer_offset_m: 1.5,
  buffer_spacing_m: 4,
  stab_depth_m: 3,
  satellite_radius_m: 1.5,
  infill_gap_factor: 1.6,
};

export const HOLE_KIND_LABELS: Record<HoleKind, string> = {
  production: "Рабочая",
  buffer: "Буферная",
  trim: "Оконтуривающая",
  presplit: "Предщелевая",
  contour: "Контурная",
  stab: "Короткая",
  satellite: "Сателлит",
  infill: "Дополнительная",
};

export const MAP_METRIC_LABELS: Record<MapMetric, string> = {
  burden: "ЛНС",
  spacing: "Шаг",
  hole_depth: "Глубина",
  subdrill: "Перебур",
  bench_height: "Высота уступа",
  toe_burden: "ЛНС по забою",
  collar_burden: "ЛНС по устью",
};

export const FRAGMENTATION_MAP_METRIC_LABELS: Record<FragmentationMapMetric, string> = {
  x50: "X50 (прогноз)",
  x80: "X80 (прогноз)",
  oversize: "Негабарит (прогноз)",
  powder_factor: "Уд. расход (прогноз)",
};

export const MAP_METRIC_UNITS: Record<OverlayMetric, string> = {
  burden: "м",
  spacing: "м",
  hole_depth: "м",
  subdrill: "м",
  bench_height: "м",
  toe_burden: "м",
  collar_burden: "м",
  x50: "мм",
  x80: "мм",
  oversize: "%",
  powder_factor: "кг/м³",
};

export const FRAGMENTATION_MODELS: { value: FragmentationModelId; label: string }[] = [
  { value: "kuznetsov", label: "Кузнецов" },
  { value: "kuzram", label: "Kuz-Ram" },
  { value: "swebrec", label: "Swebrec" },
];

export type FragmentationModelId = "kuznetsov" | "kuzram" | "swebrec";

export type DistributionPoint = {
  size_mm: number;
  passing_pct: number;
};

export type ModelProvenance = {
  model: string;
  model_version: string;
  inputs: Record<string, unknown>;
  parameters: Record<string, unknown>;
  calibration: Record<string, unknown>;
};

export type PredictedFragmentation = {
  role: "predicted";
  x20_mm: number;
  x50_mm: number;
  x80_mm: number;
  oversize_pct: number;
  powder_factor_kg_m3: number;
  curve: DistributionPoint[];
  provenance: ModelProvenance;
};

export type MeasuredFragmentation = {
  role: "measured";
  x20_mm: number | null;
  x50_mm: number | null;
  x80_mm: number | null;
  oversize_pct: number | null;
  curve: DistributionPoint[];
  source: string;
  method: string;
  timestamp?: string;
  notes?: string;
};

export type DesignedFragmentationTarget = {
  role: "designed";
  lump_size_mm: number;
  max_oversize_pct: number;
};

export type FragmentationInputs = {
  burden_m: number;
  spacing_m: number;
  bench_height_m: number;
  diameter_mm: number;
  charge_mass_kg: number;
  powder_factor_kg_m3: number;
  stemming_m: number;
  explosive_name: string;
  explosive_density_t_m3: number;
  explosive_energy_mj_kg: number;
  rock_name: string;
  rock_density_t_m3: number;
  rock_ucs_mpa: number;
  rock_fissuring: number;
  lump_size_mm: number;
  hole_oversize_coeff: number;
  influence_volume_m3: number;
};

export type FragmentationRegion = {
  id: string;
  kind: string;
  hole_ids: string[];
  x: number;
  y: number;
  hole_kind: string;
  inputs: FragmentationInputs;
  prediction: PredictedFragmentation;
  warnings: string[];
};

export type FragmentationMapSample = {
  hole_id: string;
  kind: string;
  x: number;
  y: number;
  x50: number | null;
  x80: number | null;
  oversize: number | null;
  powder_factor: number | null;
};

export type FragmentationMaps = {
  metrics: FragmentationMapMetric[];
  holes: FragmentationMapSample[];
  stats: Record<string, { min: number; avg: number; max: number; count: number }>;
};

export type FragmentationPredictResponse = {
  model: string;
  model_version: string;
  target: DesignedFragmentationTarget;
  site: FragmentationRegion;
  holes: FragmentationRegion[];
  regions: FragmentationRegion[];
  maps: FragmentationMaps;
  warnings: string[];
  measured: MeasuredFragmentation[];
  calibration: Record<string, unknown>;
};

export function isFragmentationMapMetric(metric: string): metric is FragmentationMapMetric {
  return metric === "x50" || metric === "x80" || metric === "oversize" || metric === "powder_factor";
}
