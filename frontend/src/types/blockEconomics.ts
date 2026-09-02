/** Контракты вкладки «Экономика»: модель себестоимости блока. */

export type Numeric = number | string;

export type CrewMemberInput = {
  position_code: string;
  headcount: Numeric;
  /** Пусто — норматив должности либо смены техники. */
  shifts_per_block: Numeric | null;
};

export type ModelParameters = {
  package_code: string;
  site_code: string;
  reference_revision_id: string;
  unit_plan_volume_m3: Numeric;
  rig_code: string | null;
  rig_plan_shifts: Numeric | null;
  szm_code: string | null;
  delivery_truck_code: string | null;
  crew: CrewMemberInput[];
  drilling_executor: "OWN" | "SUBCONTRACTOR";
  overhead_rate: Numeric | null;
  target_margin_rate: Numeric | null;
  vat_rate: Numeric | null;
};

export type CostLayer = "variable" | "project_direct" | "production" | "full";

export type BlockCostLine = {
  month: string;
  service_line_id: string;
  service_line_name: string;
  operation_code: string;
  cost_item_code: string;
  cost_item_name: string;
  layer: CostLayer;
  amount_rub: number;
  formula: string;
  resource_code: string;
};

export type NaturalDrivers = {
  values: Record<string, string>;
  lineage: Record<string, string>;
  warnings: string[];
};

export type CapacityWarning = {
  resource_code: string;
  resource_name: string;
  required: number;
  available: number | null;
  unit: string;
  message: string;
};

export type BlockEconomics = {
  model_version: string;
  block_volume_m3: number;
  lines: BlockCostLine[];
  layer_totals: Record<CostLayer, number>;
  price_per_m3: Record<"marginal" | "full" | "with_margin" | "with_vat", number>;
  markup: Record<string, number>;
  natural: NaturalDrivers;
  capacity: CapacityWarning[];
  warnings: string[];
};

export type EconomicsRun = {
  id: string;
  organization_id: string;
  name: string;
  technical_passport_id: string;
  package_code: string;
  reference_revision_id: string;
  parameters: Record<string, unknown>;
  result: BlockEconomics;
  created_at: string;
  created_by: string;
};

export type EconomicsRunSummary = {
  id: string;
  name: string;
  technical_passport_id: string;
  package_code: string;
  reference_revision_id: string;
  created_at: string;
  created_by: string;
  price_per_m3: Record<string, number>;
};

export type CompareRow = {
  cost_item_code: string;
  cost_item_name: string;
  layer: CostLayer;
  amounts: { run_id: string; amount_rub: number }[];
  delta_rub: number;
};

export type RunCompare = {
  runs: EconomicsRunSummary[];
  rows: CompareRow[];
  price_per_m3: Record<string, number[]>;
  delta_price_per_m3: Record<string, number>;
};

export type SensitivityRow = {
  code: string;
  label: string;
  base_price_rub_m3: number;
  price_minus_rub_m3: number;
  price_plus_rub_m3: number;
  delta_rub_m3: number;
};

export type CodeName = { code: string; name: string };

export type TechnicalPassport = {
  id: string;
  organization_id: string;
  site_code: string;
  object_name: string;
  version_no: number;
  previous_passport_id: string | null;
  reference_revision_id: string;
  formula_version: string;
  input_snapshot: Record<string, unknown>;
  selected_variant: Record<string, unknown>;
  block_snapshot: Record<string, unknown>;
  physical: Record<string, Numeric>;
  lineage: Record<string, string>;
  created_at: string;
  created_by: string;
};

export type ModelDefaults = {
  parameters: ModelParameters;
  passport: TechnicalPassport;
  package_operations: string[];
  rigs: CodeName[];
  szm: CodeName[];
  delivery_trucks: CodeName[];
  positions: CodeName[];
  packages: CodeName[];
  sites: CodeName[];
  reference_revision_id: string;
};
