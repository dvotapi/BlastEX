export type Numeric = number | string;

export type EconomicsReferenceItem = {
  code: string;
  name: string;
  payload: Record<string, unknown>;
  is_active: boolean;
  valid_from: string | null;
  valid_to: string | null;
  source: string;
  comment: string;
  revision: number;
};

export type ReferenceSectionMeta = {
  code: string;
  label: string;
  group: string;
};

export type ReferenceGroupMeta = {
  code: string;
  label: string;
};

export type EconomicsReferenceSnapshot = {
  revision_id: string;
  published_at: string | null;
  published_by: string;
  sections: Record<string, EconomicsReferenceItem[]>;
  section_catalog: ReferenceSectionMeta[];
  group_catalog: ReferenceGroupMeta[];
};

export type ReferenceValidationIssue = {
  level: "error" | "warning";
  section: string;
  code: string;
  message: string;
  /** Поле payload, к которому относится ошибка: форма покажет её под полем. */
  field?: string;
};

export type ReferenceValidation = {
  valid: boolean;
  issues: ReferenceValidationIssue[];
};

export type ReferenceImportResult = {
  file_name: string;
  counts: Record<string, number>;
  sections: Record<string, EconomicsReferenceItem[]>;
};

/** Одно расхождение записи журнала с черновиком: ключ поля и два значения. */
export type PublicFieldChange = {
  key: string;
  old: unknown;
  new: unknown;
};

export type PublicDeltaEntry = {
  /** `new` — записи нет в черновике, `changed`/`deactivated` — есть и расходится. */
  kind: "new" | "changed" | "deactivated";
  section: string;
  public_table: string;
  public_id: number;
  code: string;
  name: string;
  /** Готовая запись справочника: страница подставляет её в черновик как есть. */
  item: EconomicsReferenceItem;
  changes: PublicFieldChange[];
};

export type PublicDelta = {
  /** `false` — журнал project1 недоступен, текст причины в `error`. */
  available: boolean;
  error: string;
  counts: { new: number; changed: number; deactivated: number };
  entries: PublicDeltaEntry[];
};

/** Связь записи справочника со строкой журнала project1. */
export type PublicLink = {
  section: string;
  code: string;
  public_table: string;
  public_id: number;
  synced_at: string | null;
};

export type ReferenceRevision = {
  id: string;
  organization_id: string;
  sequence_no: number;
  published_at: string;
  published_by: string;
  comment: string;
};

export type TechnicalDriverSnapshot = {
  source_type: "BLAST_GEOMETRY";
  source_id: string | null;
  physical: Record<string, Numeric>;
  lineage: Record<string, string>;
};

export type MonthlyEconomicPlan = {
  row_id?: string;
  month: string;
  billed_quantity: Numeric;
  physical: Record<string, Numeric>;
};

export type OperationExecutor =
  | "OWN"
  | "CUSTOMER"
  | "SUBCONTRACTOR"
  | "THIRD_PARTY_SUPPLIER"
  | "OUT_OF_SCOPE";

export type OperationOverride = {
  operation_code: string;
  executor: OperationExecutor;
  enabled: boolean | null;
  quantity: Numeric | null;
  subcontract_rate_rub: Numeric | null;
  supervision_cost_rub: Numeric;
};

export type SiteConditions = {
  bench_surface_condition_code: string;
  uncleared_rock_share_pct: Numeric;
  drilling_productivity_factor: Numeric;
  stakeout_mode:
    | "CUSTOMER_CONTROL_POINTS"
    | "CUSTOMER_ALL_HOLES"
    | "CONTRACTOR_ALL_HOLES";
  refueling_available: boolean;
  customer_provides_fuel: boolean;
  maintenance_box_available: boolean;
  canteen_available: boolean;
  accommodation_available: boolean;
  meal_cost_rub_person_day: Numeric;
  accommodation_cost_rub_person_night: Numeric;
  own_fuel_delivery_cost_rub_trip: Numeric;
  mobile_maintenance_cost_rub_shift: Numeric;
  infrastructure_comment: string;
};

export type EconomicServiceLine = {
  id: string;
  name: string;
  package_code: string;
  customer_code: string;
  site_code: string;
  billing_unit: string;
  market_price_rub: Numeric;
  monthly_plans: MonthlyEconomicPlan[];
  operation_overrides: OperationOverride[];
  site_conditions: SiteConditions;
  options: Record<string, unknown>;
  replaces_service_line_id: string | null;
};

export type CapacityChoice = {
  resource_code: string;
  mode: "OVERTIME" | "RENT" | "SUBCONTRACT" | "NEW_ASSET";
  excess_rate_rub: Numeric;
  step_capacity: Numeric;
  step_cost_rub: Numeric;
};

export type EconomicScenario = {
  id: string;
  name: string;
  description: string;
  production_unit_code: string;
  baseline_service_lines: EconomicServiceLine[];
  candidate_service_lines: EconomicServiceLine[];
  capacity_choices: CapacityChoice[];
  reference_revision_id: string | null;
};

export type StoredEconomicScenario = EconomicScenario & {
  organization_id: string;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
};

export type EconomicMetrics = {
  billed_quantity: number;
  revenue_rub: number;
  variable_cost: number;
  project_direct_cost: number;
  production_cost: number;
  full_internal_cost: number;
  contribution_margin: number;
  project_margin: number;
  production_margin: number;
  full_cost_margin: number;
  cost_market_gap: number;
};

export type ResourceUtilization = {
  month: string;
  resource_code: string;
  resource_name: string;
  demand: number;
  available: number | null;
  utilization_pct: number | null;
  excess: number;
};

export type EconomicPortfolioView = {
  totals: EconomicMetrics;
  periods: Array<EconomicMetrics & { month: string }>;
  service_lines: Array<EconomicMetrics & {
    id: string;
    name: string;
    customer_code: string;
    site_code: string;
    package_code: string;
    billing_unit: string;
    break_even_price_rub: number | null;
  }>;
  resource_utilization: ResourceUtilization[];
  cost_lines: Array<Record<string, string | number>>;
  warnings: string[];
};

export type EconomicCalculationResult = {
  scenario_id: string;
  scenario_name: string;
  production_unit_code: string;
  formula_version: string;
  reference_revision_id: string;
  before: EconomicPortfolioView;
  after: EconomicPortfolioView;
  delta: {
    totals: EconomicMetrics;
    periods: Array<EconomicMetrics & { month: string }>;
    resource_utilization: Array<Record<string, string | number | null>>;
  };
  warnings: string[];
};

export type CalculationRun = {
  id: string;
  organization_id: string;
  scenario_id: string;
  reference_revision_id: string;
  formula_version: string;
  input_snapshot: Record<string, unknown>;
  result: EconomicCalculationResult;
  created_at: string;
  created_by: string;
};
