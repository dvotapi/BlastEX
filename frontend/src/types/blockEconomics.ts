/** Контракты вкладки «Экономика»: модель себестоимости блока. */

export type Numeric = number | string;

export type CrewMemberInput = {
  position_code: string;
  headcount: Numeric;
  /** Пусто — норматив должности либо смены техники. */
  shifts_per_block: Numeric | null;
};

export type ServiceLayer = "variable" | "project_direct" | "production";

/** Услуга, введённая на вкладке: сумма живёт в параметрах прогона. */
export type ServiceChargeInput = {
  name: string;
  amount_rub: Numeric;
  layer: ServiceLayer;
  operation_code: string;
  /** Сумма за смену операции, а не на блок целиком. */
  per_shift: boolean;
};

/** Происхождение величины в строке сметы: паспорт, расчёт модели, справочник,
 * норматив справочника или ручной ввод на вкладке. Пусто — не применимо. */
export type ValueOrigin = "PASSPORT" | "CALC" | "REFERENCE" | "NORM" | "MANUAL" | "";

export type ServiceToReference = {
  section: "cost_rules";
  code: string;
  created: boolean;
  reference_revision_id: string;
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
  emulsion_truck_code: string | null;
  /** Код типа техники → плановые смены в месяц; нет ключа — норматив справочника. */
  machine_plan_shifts: Record<string, Numeric>;
  crew: CrewMemberInput[];
  services: ServiceChargeInput[];
  drilling_executor: "OWN" | "SUBCONTRACTOR";
  /** Код тарифа субподряда бурения из справочника `subcontract_rates`. */
  subcontract_rate_code: string | null;
  /** Ручная ставка за метр: проверить предложение подрядчика без справочника. */
  subcontract_rate_rub: Numeric | null;
  /** Роль номенклатуры → код материала; количество приходит из паспорта. */
  nomenclature: Record<string, string>;
  electric_detonators_qty: Numeric;
  overhead_rate: Numeric | null;
  target_margin_rate: Numeric | null;
  vat_rate: Numeric | null;
};

export type CostLayer = "variable" | "project_direct" | "production" | "full";

/** Разделы бумажной сметы в порядке чтения. */
export type EstimateSection =
  | "EXPLOSIVES"
  | "DRILLING"
  | "VM_LOGISTICS"
  | "PER_DIEM"
  | "LABOR"
  | "FUEL"
  | "DEPRECIATION"
  | "OVERHEAD";

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
  section: EstimateSection;
  /** Количество в единицах цены; null — считать нечего. */
  quantity: number | null;
  unit: string;
  /** null у ФОТ: одной ставки за смену не существует. */
  unit_price_rub: number | null;
  /**
   * Роль номенклатуры («основное ВВ», «скважинное НСИ») — постоянна для
   * статьи, в отличие от `cost_item_name`, которое называет то, что выбрали
   * в справочнике. Null у строк без выбора номенклатуры.
   */
  role_label: string | null;
  /** Происхождение количества и цены строки — см. `ValueOrigin`. */
  quantity_origin: ValueOrigin;
  price_origin: ValueOrigin;
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
  price_per_m3: Record<"marginal" | "full" | "with_overhead" | "with_margin" | "with_vat", number>;
  markup: Record<string, number>;
  natural: NaturalDrivers;
  capacity: CapacityWarning[];
  warnings: string[];
  /** Ревизия справочников, на которой посчитано. */
  reference_revision_id: string;
};

/** Один столбец сметы, посланный на расчёт: имя и свой набор параметров. */
export type VariantRequest = {
  name: string;
  parameters: ModelParameters;
};

export type VariantResult = {
  name: string;
  economics: BlockEconomics;
};

export type VariantsResponse = {
  /** Одна на все столбцы: см. `VariantsRequest` на бэкенде. */
  reference_revision_id: string;
  variants: VariantResult[];
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

export type MaterialOption = {
  code: string;
  name: string;
  /** Единица цены: «кг», «шт». */
  unit: string;
  price_rub: number;
  length_m: number;
  /** Количество на блок в единицах цены; null — задаётся вручную. */
  quantity: number | null;
  /** Происхождение количества: «1224 шт × 0.8 кг». Пусто для простых ролей. */
  quantity_label: string;
};

/** Тариф субподряда бурения для выбора на вкладке: справочник `subcontract_rates`. */
export type SubcontractRateOption = {
  code: string;
  name: string;
  counterparty_code: string;
  counterparty_name: string;
  operation_code: string;
  unit: string;
  rate_rub: number;
};

/** Должность для состава бригады: норматив из `positions`, ставка — из `labor_rates`. */
export type PositionOption = {
  code: string;
  name: string;
  fixed_monthly_rub: number;
  norm_shifts_per_month: number;
  category: "DIRECT" | "INDIRECT";
};

export type ModelDefaults = {
  parameters: ModelParameters;
  passport: TechnicalPassport;
  package_operations: string[];
  /** Операции пакета с подписями — селект услуги показывает название, не код. */
  operations: CodeName[];
  /** Номенклатура блока по ролям: списки для выбора с ценами. */
  nomenclature: Record<string, MaterialOption[]>;
  rigs: CodeName[];
  szm: CodeName[];
  delivery_trucks: CodeName[];
  emulsion_trucks: CodeName[];
  positions: PositionOption[];
  /** Тарифы субподряда бурения и подрядчики, готовые к выбору на вкладке. */
  subcontract_rates: SubcontractRateOption[];
  counterparties: CodeName[];
  packages: CodeName[];
  sites: CodeName[];
  reference_revision_id: string;
};
