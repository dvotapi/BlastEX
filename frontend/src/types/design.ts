// Поля 1:1 с api/schemas/design.py — сервер остаётся источником истины.

export type Point3 = { x: number; y: number; z: number };

export type BenchSurface = {
  crest_z_m: number;
  toe_z_m: number;
  face_angle_deg: number;
};

export type BlockContour = {
  vertices: Point3[];
  free_faces: number[][];
  bench: BenchSurface;
  name: string;
};

export type HoleKind = "production" | "contour" | "presplit" | "trim";
export type HoleSource = "generated" | "manual";

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
};

export type Deck = {
  kind: "charge" | "stemming" | "air";
  from_m: number;
  to_m: number;
  explosive_key: string;
  mass_kg: number;
};

export type HoleLoad = {
  hole_id: string;
  decks: Deck[];
  total_charge_kg: number;
  influence_volume_m3: number;
  specific_q_kg_m3: number;
  primers: number[];
};

export type Connector = {
  from_hole: string;
  to_hole: string;
  delay_ms: number;
  kind: "surface_nsi" | "ds_relay" | "electronic";
};

export type InitiationNetwork = {
  system: "nonel" | "electronic" | "detcord";
  starters: string[];
  connectors: Connector[];
  downhole_delay_ms: Record<string, number>;
  electronic_times_ms: Record<string, number>;
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
};

export type PatternType = "square" | "rectangular" | "staggered";

export type PatternParams = {
  pattern: PatternType;
  spacing_a_m: number;
  burden_b_m: number;
  row_shift_ratio: number;
  row_azimuth_deg: number;
  offset_from_face_m: number;
  edge_margin_m: number;
  diameter_mm: number;
  subdrill_m: number;
  angle_deg: number;
  azimuth_deg: number;
};

export type PatternGenerateResponse = {
  holes: Hole[];
  hole_count: number;
  block_volume_m3: number;
};

export type DeckingType = "continuous" | "spaced";

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
};

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
    version: 1,
    updated_at: "",
    contour: emptyContour(),
    holes: [],
    loads: [],
    network: { system: "nonel", starters: [], connectors: [], downhole_delay_ms: {}, electronic_times_ms: {} },
    pattern_params: {},
    charge_rules: {},
    rock_name: "",
    explosive_key: "",
  };
}

export const DEFAULT_TIE_PARAMS: TieParams = {
  system: "nonel",
  interval_ms: 25,
  downhole_delay_ms: 500,
  include_contour: false,
};

export const DEFAULT_PPV_REQUEST: PpvRequest = {
  distance_m: 200,
  k: 200,
  n: 1.6,
};

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
};

export const DEFAULT_PATTERN_PARAMS: PatternParams = {
  pattern: "staggered",
  spacing_a_m: 5,
  burden_b_m: 4,
  row_shift_ratio: 0.5,
  row_azimuth_deg: 0,
  offset_from_face_m: 2,
  edge_margin_m: 1,
  diameter_mm: 152,
  subdrill_m: 1,
  angle_deg: 0,
  azimuth_deg: 0,
};
