export type User = {
  email: string;
  display_name: string;
  role: "admin" | "reference_editor" | "user";
  organization_id: string;
  organization_name: string;
};

// --- Справочники ---

export type Rock = {
  name: string;
  density_t_m3: number;
  ucs_mpa: number;
  fissuring_ff: number;
};

export type Explosive = {
  key: string;
  name: string;
  density_t_m3: number;
  power_mj_kg: number;
  chart_label: string;
};

export type WorkObject = {
  name: string;
  mobilization_km: number;
  diesel_price_ton_rub: number | null;
};

export type DrillRig = {
  name: string;
  depreciation_per_shift_rub: number;
  fuel_l_per_h: number;
};

export type CatalogCategory = "explosive" | "detonator" | "downhole_nsi" | "surface_nsi" | "start_nsi";

export type CatalogItem = {
  id: string;
  name: string;
  category: CatalogCategory;
  unit: string;
  price: number;
  mass_kg?: number | null;
  length_m?: number | null;
  note: string;
};

export type FixedAssetDepreciation = {
  name: string;
  initial_cost_rub: number;
  useful_life_months: number;
  productive_shifts_per_month: number;
  depreciation_per_shift_rub: number;
};

export type FixedCostItem = {
  id: string;
  section: string;
  name: string;
  amount_rub: number;
  note: string;
  enabled: boolean;
};

export const FIXED_COST_SECTIONS: [string, string][] = [
  ["2.1", "Хранение, производство и доставка ВМ и СИ"],
  ["2.2", "Суточные, вахтовые, проживание"],
  ["2.3", "Фонд оплаты труда"],
  ["2.4", "ГСМ на бурение"],
  ["2.5", "Амортизация"],
  ["2.6", "Общепроизводственные затраты"],
];

export type JobPosition = {
  id: string;
  name: string;
  fixed_salary_monthly: number;
  piece_rate_per_m3: number;
};

export type LaborAssignment = {
  id: string;
  position_id: string;
  headcount: number;
  volume_m3: number;
  employee_shifts: number;
};

export type LaborFOTSettings = {
  shifts_per_month: number;
  net_to_gross_factor: number;
  accident_rate: number;
  social_rate: number;
  vacation_reserve_divisor: number;
};

// --- Сценарии и рабочее пространство ---

export type ScenarioPhase = {
  id: string;
  name: string;
  enabled: boolean;
  modules: string[];
  volume_source: string;
};

export type ScenarioCalcProfile = {
  mode: "full_bvr" | "contour_bvr" | "drilling_geometry" | "manual";
  explosive_basis: "per_m3" | "per_m" | "none";
  manual_type: "" | "pvv" | "evv" | "rc";
  ui_caption: string;
  needs_blast_optimization: boolean;
  needs_bvr_geometry: boolean;
  needs_charge_design: boolean;
  is_manual_input: boolean;
};

export type ScenarioListItem = {
  id: string;
  name: string;
  description: string;
  phases: ScenarioPhase[];
  calc_profile: ScenarioCalcProfile;
};

export type TeamSettings = {
  team_id: string;
  team_name: string;
  active_scenario_id: string;
  active_work_object_name: string;
};

export type WorkspaceSnapshot = {
  scenario_id: string;
  updated_at: string;
  cost_catalog_records: CatalogItem[];
  fixed_cost_records: FixedCostItem[];
  labor_catalog_records: JobPosition[];
  labor_assignment_records: LaborAssignment[];
  labor_shifts_per_month: number;
  drilling_calculator_input: Record<string, unknown>;
  scenario_phase_overrides: Record<string, boolean>;
};

export type TeamReferences = {
  work_object_records: WorkObject[];
  drill_rig_records: DrillRig[];
  rock_records: Rock[];
  explosive_records: Explosive[];
  depreciation_asset_records: FixedAssetDepreciation[];
};

export type WorkspaceState = {
  settings: TeamSettings;
  snapshot: WorkspaceSnapshot;
  references: TeamReferences;
  drilling_price_per_m: number;
};

export type DefaultReferences = {
  rocks: Rock[];
  explosives: Explosive[];
  depreciation_assets: FixedAssetDepreciation[];
  work_objects: WorkObject[];
  drill_rigs: DrillRig[];
  catalog: CatalogItem[];
  fixed_costs: FixedCostItem[];
  labor_catalog: JobPosition[];
  labor_assignments: LaborAssignment[];
  drilling_unit_cost_input: DrillingUnitCostInput;
};

// --- Технологический расчёт БВР ---

export type BlastVariant = {
  crown_mm: number;
  specific_q_kg_m3: number;
  line_of_least_resistance_m: number;
  grid_a_m: number;
  grid_b_m: number;
  grid_label: string;
  x50_mm: number;
  oversize_pct: number;
  target_q_kg_m3: number | null;
};

export type InitiationConfig = {
  intermediate_detonators_per_hole: number;
  nsi_per_hole: number;
  nsi_length_1_m: number;
  nsi_length_2_m: number;
  detonator_delay_ms: number;
};

export type HoleGeometry = {
  grid_a_m: number;
  grid_b_m: number;
  depth_m: number;
  overdrill_m: number;
  undercharge_m: number;
  charge_length_m: number;
  charge_diameter_m: number;
  capacity_kg_per_m: number;
  charge_mass_kg: number;
  yield_m3: number;
  specific_q_kg_m3: number;
  explosive_name: string;
  explosive_label: string;
};

export type BlockGeometry = {
  block_volume_m3: number;
  yield_per_hole_m3: number;
  hole_count: number;
  additional_holes_pct: number;
  additional_holes: number;
  total_holes: number;
  drilling_footage_m: number;
  total_charge_mass_kg: number;
  specific_q_kg_m3: number;
  intermediate_detonators_per_hole: number;
  nsi_per_hole: number;
  nsi_length_1_m: number;
  nsi_length_2_m: number;
  detonator_delay_ms: number;
  total_intermediate_detonators: number;
  total_downhole_nsi: number;
  total_nsi_length_m: number;
  total_boosters: number;
  total_surface_nsi: number;
  total_start_nsi: number;
};

export type BlastGeometryResponse = {
  hole: HoleGeometry;
  block: BlockGeometry;
  initiation: InitiationConfig;
  label: string;
  hole_rows: [string, string][];
  block_rows: [string, string][];
};

export type MaterialsSelection = {
  explosive_id: string;
  detonator_id: string;
  downhole_nsi1_id: string;
  downhole_nsi2_id: string | null;
  surface_nsi_id: string;
  start_nsi_id: string;
};

// --- Смета ---

export type MaterialLine = {
  section: string;
  nomenclature: string;
  unit: string;
  quantity: number;
  price: number;
  amount: number;
  source: string;
};

export type VariableMaterialsResult = {
  lines: MaterialLine[];
  total_amount: number;
};

export type DrillingCostResult = {
  total_holes: number;
  hole_depth_m: number;
  drilling_footage_m: number;
  yield_per_meter_m3: number;
  price_per_m: number;
  amount: number;
};

export type LaborLineResult = {
  assignment_id: string;
  position_id: string;
  position_name: string;
  headcount: number;
  volume_m3: number;
  employee_shifts: number;
  fixed_part: number;
  piece_part: number;
  line_amount: number;
};

export type LaborFOTResult = {
  lines: LaborLineResult[];
  gross_salary: number;
  accident_contribution: number;
  social_contribution: number;
  vacation_reserve: number;
  contributions_total: number;
  total_fot: number;
};

export type FixedCostLine = {
  section: string;
  section_title: string;
  name: string;
  amount: number;
};

export type FixedCostsResult = {
  lines: FixedCostLine[];
  section_totals: Record<string, number>;
  total_amount: number;
  block_volume_m3: number;
  total_per_m3: number;
};

export type DrillingCostLine = {
  section: string;
  name: string;
  quantity: number | null;
  unit: string;
  total_rub: number | null;
  price_per_m: number;
  note: string;
};

export type DrillingUnitCostResult = {
  commercial_speed_m_per_shift: number;
  fuel_l_per_m: number;
  direct_cost_per_m: number;
  cost_per_m: number;
  price_per_m: number;
  diesel_share: number;
  lines: DrillingCostLine[];
};

export type AggregatedCostResult = {
  scenario_id: string;
  work_object_name: string;
  block_geometry: BlockGeometry | null;
  drilling_unit_cost: DrillingUnitCostResult | null;
  drilling_total_cost: DrillingCostResult | null;
  materials_cost: VariableMaterialsResult | null;
  labor_fot: LaborFOTResult | null;
  fixed_costs: FixedCostsResult | null;
  total_amount_rub: number;
  cost_per_m3: number;
  cost_per_ton: number;
  variable_total_rub: number;
  fixed_total_rub: number;
  labor_total_rub: number;
  child_results: AggregatedCostResult[];
  notes: string[];
};

export type DrillingUnitCostInput = {
  volume_m: number;
  crown_mm: number;
  rig_name: string;
  tech_speed_m_h: number;
  nonproductive_h_per_shift: number;
  crown_m_per_piece: number;
  crown_price_rub: number;
  ppu_m_per_piece: number;
  ppu_price_rub: number;
  rig_tools_m_per_set: number;
  rig_tools_set_price_rub: number;
  casing_m_per_drill_m: number;
  casing_price_rub_per_m: number;
  shifts_toir: number;
  shifts_cleaning: number;
  spares_rub_per_m: number;
  consumables_rub_per_m: number;
  fot_rub_per_m: number;
  object_name: string;
  mobilization_km: number | null;
  diesel_price_ton_rub: number | null;
  mobilization_rub_per_km: number;
  mobilization_divisor: number;
  line_release_rub_per_shift: number;
  include_med_exams: boolean;
  overhead_production_rub: number;
  overhead_admin_rub: number;
  profit_factor: number;
};
