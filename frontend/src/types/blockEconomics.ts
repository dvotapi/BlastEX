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
export type ValueOrigin = "PASSPORT" | "CALC" | "REFERENCE" | "NORM" | "MANUAL" | "PAYROLL" | "";

export type ServiceToReference = {
  section: "cost_rules";
  code: string;
  created: boolean;
  reference_revision_id: string;
};

/** Тариф субподряда бурения, опубликованный со вкладки в справочник `subcontract_rates`. */
export type SubcontractRateToReference = {
  section: "subcontract_rates";
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
  /** Откуда брать ФОТ экипажа бурения: методика ФОТ (умолчание) или ставки справочников. */
  payroll_source: "RATES" | "PAYROLL";
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

export type PayrollPace = {
  m_plan: number;
  k_hardness: number;
  k_diameter: number;
  diameter_mm: number | null;
  condition_code: string;
  /** Название записи условий бурения; прогоны до PR 3b его не несут. */
  condition_name?: string;
};

export type PayrollPosition = {
  position_code: string;
  /** Название из справочника; прогоны до PR 3b его не несут. */
  position_name: string;
  headcount: number;
  /** ₽ на приведённый метр на человека; повременщику — 0. */
  c_var: number;
  fixed_rub: number;
  variable_rub: number;
  amount_rub: number;
};

/** Шкала сдельной премии основной должности. У «Ступеней» нормы и потолка нет. */
export type PayrollScale = {
  scale_type: string;
  gamma: number | null;
  norm_per_shift: number | null;
  rate_norm: number | null;
  ceiling_per_shift: number | null;
  rate_ceiling: number | null;
};

export type PayrollSeriesPoint = { pace: number; rate: number; per_shift: number };

export type PayrollSharePoint = { pace: number; crew_share: number; main_share: number };

export type PayrollFlag = { code: string; message: string };

export type PayrollMarginStatus = "CHECKED" | "NOT_CHECKED" | "NO_MARGIN" | "NOT_APPLICABLE";

export type PayrollMargin = {
  status: PayrollMarginStatus;
  margin_rub_per_m: number | null;
  plan: PayrollSharePoint | null;
  /** У шкалы «Ступени» потолка нет — null. */
  ceiling: PayrollSharePoint | null;
  /** Доля, выше которой показывается предупреждение; может быть больше 1. */
  threshold: number;
  flags: PayrollFlag[];
  lineage: Record<string, string>;
};

/** ФОТ экипажа бурения по методике: темп, строки, цена метра и доля в марже. */
export type BlockPayroll = {
  pace: PayrollPace;
  normalized_meters: number;
  effective_shifts: number;
  positions: PayrollPosition[];
  main_position_code: string | null;
  scale: PayrollScale | null;
  series: PayrollSeriesPoint[];
  price_rub_per_m: number | null;
  variable_rub_per_m: number | null;
  margin: PayrollMargin;
  lineage: Record<string, string>;
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
  /** null — режим ставок; прогоны до блока ключа не несут. */
  payroll?: BlockPayroll | null;
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

/** Две цены метра собственного бурения (себестоимость): null — бурение не посчитано. */
export type DrillingPrices = {
  without_payroll_rub_per_m: number | null;
  with_payroll_rub_per_m: number | null;
  drilling_m: number;
  payroll_source: "RATES" | "PAYROLL";
  /** Методика ФОТ реально применилась к экипажу. */
  payroll_applied: boolean;
  warnings: string[];
  /** Слагаемые метра для кольца: статьи строк бурения и ФОТ экипажа, ₽/м. */
  components: DrillingComponent[];
  /** Кривая премии машиниста по шкале с подменами; null — шкалы нет. */
  premium_curve: DrillingPremiumCurve | null;
};

export type DrillingComponent = {
  code: string;
  label: string;
  rub_per_m: number;
  /** Сумма на блок, ₽. */
  rub?: number;
  /** Пояснение под подписью: у должности — люди в смене, штат и смены блока, у оклада — оклад одного человека. */
  note?: string;
  /** Подстатьи: у ФОТ экипажа и ИТР — должности, у должности — статьи ФОТ (оклад, межвахта, отчисления…). */
  parts?: DrillingComponent[];
};

export type DrillingPremiumCurve = {
  scale: PayrollScale;
  series: PayrollSeriesPoint[];
  /** Плановый темп блока; null — методика не применилась. */
  pace: number | null;
};

/** Ручка цены метра: текущее значение справочника и эффект ±10 % на цену с ФОТ экипажа. */
export type DrillingKnob = {
  code: string;
  label: string;
  unit: string;
  base_value: number;
  source: string;
  /** Настоящий параметр черновика (плановые смены): у него свой бегунок, «что если» не нужно. */
  draft_param: boolean;
  /** «cost» — ранжируемые ручки станка; «site» — услуги, оклады ИТР и ремонтного персонала,
   * проживание и питание: показываются все. Нет поля — «cost». */
  group?: string;
  /** Шаг и размах бегунка (доля от значения в каждую сторону); нет — ±30 % с «круглым» шагом. */
  step?: number | null;
  span?: number | null;
  price_minus_rub_per_m: number | null;
  price_plus_rub_per_m: number | null;
  delta_rub_per_m: number;
};

export type DrillingPremium = {
  position_code: string;
  position_name: string;
  scale_type: string;
  /** Шкала двигает цену метра только при методике ФОТ. */
  applies: boolean;
  note: string;
  knobs: DrillingKnob[];
};

export type DrillingSensitivity = {
  base: DrillingPrices;
  /** По убыванию |Δ|. */
  knobs: DrillingKnob[];
  premium: DrillingPremium | null;
  reference_revision_id: string;
};

export type DrillingWhatIf = {
  base: DrillingPrices;
  result: DrillingPrices;
  reference_revision_id: string;
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
  /** Заполнено у удалённого паспорта: в списках такие не приходят, но
   * сохранённый прогон экономики открывает свой паспорт и после удаления. */
  deleted_at?: string | null;
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
  /** Происхождение количества: «1 224 шт × 0,8 кг». Пусто для простых ролей. */
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
  /** Код станка → экипаж его класса из шаблонов; при смене станка заменяет прежний экипаж бурения. */
  rig_crews?: Record<string, CrewMemberInput[]>;
  /** Код станка → норматив плановых смен в месяц; null — у типа норматива нет. */
  rig_shift_norms?: Record<string, Numeric | null>;
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
