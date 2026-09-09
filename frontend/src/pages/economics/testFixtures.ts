/**
 * Общие тестовые фикстуры вкладки «Экономика блока».
 *
 * Используются тестами разделов конструктора сметы (задача 7 и её вторая
 * часть про бурение) — единый набор кодов материалов, должностей и техники,
 * чтобы тесты разных разделов не заводили каждый свой набор с нуля и не
 * расходились в кодах.
 *
 * `defaultsFixture().parameters` всегда равны `paramsFixture()`: это
 * означает, что состав бригады и выбор техники по умолчанию совпадает с
 * шаблоном пакета — бейджи «Норматив»/«Ручной» (см. `origin.ts`) в тестах
 * стартуют с «Норматив», пока тест не поправит значение вручную.
 */
import type {
  BlockCostLine,
  BlockEconomics,
  CostLayer,
  ModelDefaults,
  ModelParameters,
  TechnicalPassport,
} from "../../types/blockEconomics";

/** Коды материалов основного ВВ — те же, что в примерах `CatalogSelect.test.tsx`. */
export const EXPLOSIVE_CODES = { GRANULIT: "GRANULIT", SFERIT: "SFERIT", BEREZIT: "BEREZIT" } as const;

export function paramsFixture(): ModelParameters {
  return {
    package_code: "DRILL_AND_BLAST",
    site_code: "SITE_1",
    reference_revision_id: "REV-1",
    unit_plan_volume_m3: "50000",
    rig_code: "RIG_SOLO",
    rig_plan_shifts: null,
    szm_code: "SZM_MZ",
    delivery_truck_code: "TRUCK_KAMAZ",
    emulsion_truck_code: "EMULSION_MAN",
    machine_plan_shifts: {},
    crew: [
      { position_code: "MASTER_BVR", headcount: 1, shifts_per_block: null },
      { position_code: "VZRYVNIK", headcount: 2, shifts_per_block: null },
    ],
    services: [
      {
        name: "Проживание и питание",
        amount_rub: "15000",
        layer: "project_direct",
        operation_code: "BLAST_EXECUTION",
        per_shift: false,
      },
    ],
    drilling_executor: "OWN",
    subcontract_rate_code: null,
    subcontract_rate_rub: null,
    nomenclature: {
      EXPLOSIVE: "GRANULIT",
      BOOSTER: "BOOSTER_STD",
      NSI_DOWNHOLE: "NSI_DOWNHOLE_STD",
      NSI_SURFACE: "NSI_SURFACE_STD",
      NSI_START: "",
      DETONATOR_ELECTRIC: "ED_STD",
    },
    electric_detonators_qty: "24",
    overhead_rate: "0.15",
    target_margin_rate: "0.2",
    vat_rate: "0.2",
  };
}

function passportFixture(): TechnicalPassport {
  return {
    id: "PASSPORT-1",
    organization_id: "ORG-1",
    site_code: "SITE_1",
    object_name: "Блок №12",
    version_no: 1,
    previous_passport_id: null,
    reference_revision_id: "REV-1",
    formula_version: "v1",
    input_snapshot: {},
    selected_variant: {},
    block_snapshot: {},
    physical: {
      // Соответствуют драйверам `NOMENCLATURE_ROLES` (см. `nomenclature.ts`).
      explosive_kg: "29038.86",
      intermediate_detonators: "48",
      downhole_nsi: "189",
      surface_nsi: "96",
      // Нулевое количество — роль скрыта по умолчанию (тест «+ Добавить материал»).
      start_nsi: "0",
      drilling_m: "1450",
    },
    lineage: {},
    created_at: "2026-01-01T00:00:00Z",
    created_by: "tester@blastex.local",
  };
}

export function defaultsFixture(): ModelDefaults {
  return {
    parameters: paramsFixture(),
    passport: passportFixture(),
    package_operations: ["BLAST_EXECUTION", "DRILLING"],
    operations: [
      { code: "BLAST_EXECUTION", name: "Производство взрывных работ" },
      { code: "DRILLING", name: "Бурение" },
    ],
    nomenclature: {
      EXPLOSIVE: [
        { code: "GRANULIT", name: "Гранулит РП", unit: "кг", price_rub: 46, length_m: 0, quantity: 29038.86, quantity_label: "" },
        { code: "SFERIT", name: "Сферит ДТ", unit: "кг", price_rub: 150, length_m: 0, quantity: 29038.86, quantity_label: "" },
        { code: "BEREZIT", name: "Березит Э-100", unit: "кг", price_rub: 54.2, length_m: 0, quantity: 29038.86, quantity_label: "" },
      ],
      BOOSTER: [
        { code: "BOOSTER_STD", name: "Сферит боевик", unit: "кг", price_rub: 150, length_m: 0, quantity: 38.4, quantity_label: "48 шт × 0.8 кг" },
      ],
      NSI_DOWNHOLE: [
        { code: "NSI_DOWNHOLE_STD", name: "СИНВ-С", unit: "шт", price_rub: 210, length_m: 0, quantity: 189, quantity_label: "" },
      ],
      NSI_SURFACE: [
        { code: "NSI_SURFACE_STD", name: "СИНВ-П", unit: "шт", price_rub: 95, length_m: 0, quantity: 96, quantity_label: "" },
      ],
      NSI_START: [
        { code: "NSI_START_STD", name: "СИНВ-Старт", unit: "шт", price_rub: 260, length_m: 0, quantity: 0, quantity_label: "" },
      ],
      DETONATOR_ELECTRIC: [
        { code: "ED_STD", name: "ЭД-1-Н", unit: "шт", price_rub: 45, length_m: 0, quantity: null, quantity_label: "" },
      ],
    },
    rigs: [
      { code: "RIG_SOLO", name: "Sandvik DX800" },
      { code: "RIG_ATLAS", name: "Atlas Copco ROC L8" },
    ],
    szm: [
      { code: "SZM_MZ", name: "МЗ-3" },
      { code: "SZM_MTZ", name: "МТЗ-320" },
    ],
    delivery_trucks: [{ code: "TRUCK_KAMAZ", name: "КамАЗ-65225" }],
    emulsion_trucks: [{ code: "EMULSION_MAN", name: "MAN TGS 33.400" }],
    positions: [
      { code: "MASTER_BVR", name: "Мастер БВР", fixed_monthly_rub: 120000, norm_shifts_per_month: 22, category: "DIRECT" },
      { code: "VZRYVNIK", name: "Взрывник", fixed_monthly_rub: 95000, norm_shifts_per_month: 22, category: "DIRECT" },
      { code: "MASHINIST_SZM", name: "Машинист СЗМ", fixed_monthly_rub: 90000, norm_shifts_per_month: 22, category: "DIRECT" },
      { code: "NACHALNIK_UCHASTKA", name: "Начальник участка", fixed_monthly_rub: 150000, norm_shifts_per_month: 22, category: "INDIRECT" },
    ],
    subcontract_rates: [
      { code: "RATE_A", name: "Тариф А: шарошечное бурение", counterparty_code: "CONTR_A", counterparty_name: "ООО «Буровик»", operation_code: "DRILLING", unit: "м", rate_rub: 210 },
      { code: "RATE_B", name: "Тариф Б: DTH-бурение", counterparty_code: "CONTR_A", counterparty_name: "ООО «Буровик»", operation_code: "DRILLING", unit: "м", rate_rub: 195 },
    ],
    counterparties: [{ code: "CONTR_A", name: "ООО «Буровик»" }],
    packages: [{ code: "DRILL_AND_BLAST", name: "Бурение и взрывание" }],
    sites: [{ code: "SITE_1", name: "Карьер №1" }],
    reference_revision_id: "REV-1",
  };
}

function makeLine(patch: Partial<BlockCostLine> & Pick<BlockCostLine, "cost_item_code" | "cost_item_name">): BlockCostLine {
  return {
    month: "2026-01",
    service_line_id: "SL-1",
    service_line_name: "Блок №12",
    operation_code: "BLAST_EXECUTION",
    layer: "variable",
    amount_rub: 0,
    formula: "",
    resource_code: "",
    section: "OVERHEAD",
    quantity: null,
    unit: "",
    unit_price_rub: null,
    role_label: null,
    quantity_origin: "",
    price_origin: "",
    ...patch,
  };
}

export function economicsFixture(): BlockEconomics {
  const lines: BlockCostLine[] = [
    // Взрывчатые материалы — роли сопоставляются по `role_label`, не по коду статьи.
    makeLine({
      cost_item_code: "MATERIAL_EXPLOSIVE", cost_item_name: "Гранулит РП", section: "EXPLOSIVES",
      role_label: "Основное ВВ", layer: "variable", amount_rub: 1335788.36,
      quantity: 29038.86, unit: "кг", unit_price_rub: 46, quantity_origin: "PASSPORT", price_origin: "REFERENCE",
    }),
    makeLine({
      cost_item_code: "MATERIAL_BOOSTER", cost_item_name: "Сферит боевик", section: "EXPLOSIVES",
      role_label: "Промежуточные детонаторы", layer: "variable", amount_rub: 5760,
      quantity: 38.4, unit: "кг", unit_price_rub: 150, quantity_origin: "PASSPORT", price_origin: "REFERENCE",
    }),
    makeLine({
      cost_item_code: "MATERIAL_NSI_DOWNHOLE", cost_item_name: "СИНВ-С", section: "EXPLOSIVES",
      role_label: "Скважинные НСИ", layer: "variable", amount_rub: 39690,
      quantity: 189, unit: "шт", unit_price_rub: 210, quantity_origin: "PASSPORT", price_origin: "REFERENCE",
    }),
    makeLine({
      cost_item_code: "MATERIAL_NSI_SURFACE", cost_item_name: "СИНВ-П", section: "EXPLOSIVES",
      role_label: "Поверхностные НСИ", layer: "variable", amount_rub: 9120,
      quantity: 96, unit: "шт", unit_price_rub: 95, quantity_origin: "PASSPORT", price_origin: "REFERENCE",
    }),
    makeLine({
      cost_item_code: "MATERIAL_DETONATOR_ELECTRIC", cost_item_name: "ЭД-1-Н", section: "EXPLOSIVES",
      role_label: "Электродетонаторы", layer: "variable", amount_rub: 1080,
      quantity: 24, unit: "шт", unit_price_rub: 45, quantity_origin: "MANUAL", price_origin: "REFERENCE",
    }),

    // Бурение — на будущее (задача 7б); ExplosivesSection/LaborSection/EquipmentSection их не используют.
    makeLine({
      cost_item_code: "DRILL_TOOLING", cost_item_name: "Расходный буровой инструмент", section: "DRILLING",
      layer: "variable", amount_rub: 87000, quantity: 1450, unit: "м", unit_price_rub: 60,
      quantity_origin: "PASSPORT", price_origin: "REFERENCE",
    }),
    makeLine({
      cost_item_code: "DRILL_SUBCONTRACT", cost_item_name: "Субподряд бурения", section: "DRILLING",
      layer: "variable", amount_rub: 0, quantity: null, unit: "м", unit_price_rub: null,
    }),

    // ФОТ — строки `LABOR_<код должности>`; суточные — только для чтения.
    makeLine({
      cost_item_code: "LABOR_MASTER_BVR", cost_item_name: "Мастер БВР", section: "LABOR",
      layer: "project_direct", amount_rub: 120000,
    }),
    makeLine({
      cost_item_code: "LABOR_VZRYVNIK", cost_item_name: "Взрывник", section: "LABOR",
      layer: "project_direct", amount_rub: 190000,
    }),
    makeLine({
      cost_item_code: "PER_DIEM", cost_item_name: "Суточные", section: "PER_DIEM",
      layer: "project_direct", amount_rub: 8000,
    }),

    // Техника: станок (при собственном бурении), СЗМ, доставщик ВМ, тягач эмульсии.
    makeLine({
      cost_item_code: "DRILL_DEPRECIATION", cost_item_name: "Амортизация станка", section: "DEPRECIATION",
      layer: "project_direct", amount_rub: 45000,
    }),
    makeLine({
      cost_item_code: "DRILL_INSURANCE", cost_item_name: "Страхование станка", section: "DEPRECIATION",
      layer: "production", amount_rub: 5000,
    }),
    makeLine({
      cost_item_code: "SZM_DEPRECIATION", cost_item_name: "Амортизация СЗМ", section: "DEPRECIATION",
      layer: "project_direct", amount_rub: 30000,
    }),
    makeLine({
      cost_item_code: "SZM_MAINTENANCE", cost_item_name: "ТОиР СЗМ", section: "OVERHEAD",
      layer: "production", amount_rub: 12000,
    }),
    makeLine({
      cost_item_code: "VM_TRUCK_DEPRECIATION", cost_item_name: "Амортизация доставщика ВМ", section: "DEPRECIATION",
      layer: "project_direct", amount_rub: 18000,
    }),
    makeLine({
      cost_item_code: "VM_TRUCK_INSURANCE", cost_item_name: "Страхование доставщика ВМ", section: "OVERHEAD",
      layer: "production", amount_rub: 4000,
    }),
    makeLine({
      cost_item_code: "EMULSION_TRUCK_DEPRECIATION", cost_item_name: "Амортизация тягача эмульсии", section: "DEPRECIATION",
      layer: "project_direct", amount_rub: 16000,
    }),
    makeLine({
      cost_item_code: "EMULSION_TRUCK_INSURANCE", cost_item_name: "Страхование тягача эмульсии", section: "OVERHEAD",
      layer: "production", amount_rub: 3000,
    }),

    // ГСМ.
    makeLine({
      cost_item_code: "FUEL_DIESEL", cost_item_name: "Дизельное топливо", section: "FUEL",
      layer: "variable", amount_rub: 54000, quantity: 1200, unit: "л", unit_price_rub: 45,
      quantity_origin: "CALC", price_origin: "REFERENCE",
    }),

    // Производственные услуги: доставка и хранение ВМ.
    makeLine({
      cost_item_code: "VM_LOGISTICS", cost_item_name: "Доставка и хранение ВМ", section: "VM_LOGISTICS",
      layer: "project_direct", amount_rub: 22000,
    }),
    // Услуга, введённая на вкладке вручную (входит в раздел «Услуги» по правилу `groupOf`).
    makeLine({
      cost_item_code: "SERVICE_MANUAL_1", cost_item_name: "Проживание и питание", section: "OVERHEAD",
      layer: "project_direct", amount_rub: 15000, quantity_origin: "MANUAL", price_origin: "MANUAL",
    }),

    // Постоянные и общепроизводственные расходы.
    makeLine({
      cost_item_code: "OVERHEAD_RENT", cost_item_name: "Аренда производственной площадки", section: "OVERHEAD",
      layer: "production", amount_rub: 9000,
    }),
  ];

  const layer_totals = lines.reduce<Record<CostLayer, number>>(
    (totals, line) => ({ ...totals, [line.layer]: totals[line.layer] + line.amount_rub }),
    { variable: 0, project_direct: 0, production: 0, full: 0 },
  );
  const fullCost = lines.reduce((sum, line) => sum + line.amount_rub, 0);
  const volume = 1000;

  return {
    model_version: "v1",
    block_volume_m3: volume,
    lines,
    layer_totals,
    price_per_m3: {
      marginal: layer_totals.variable / volume,
      full: fullCost / volume,
      with_overhead: fullCost / volume,
      with_margin: fullCost / volume,
      with_vat: fullCost / volume,
    },
    markup: { full_cost_rub: fullCost },
    natural: {
      values: {
        rig_shifts: "18",
        szm_shifts: "20",
        delivery_shifts: "10",
        emulsion_shifts: "8",
        drilling_rub_per_m: "260",
      },
      lineage: {
        rig_shifts: "Смены станка по производительности бурения на условиях блока",
        szm_shifts: "Смены СЗМ по массе заряжания",
        delivery_shifts: "Смены доставщика ВМ по объёму доставки",
        emulsion_shifts: "Смены тягача эмульсии по объёму эмульсии",
        // Формат сверен с тестом `DrillingSection.test.tsx` из брифа задачи 7 (часть про бурение).
        drilling_condition: "drilling_conditions.COND_GRANITE (станок + порода)",
      },
      warnings: [],
    },
    capacity: [],
    warnings: [],
    reference_revision_id: "REV-1",
  };
}
