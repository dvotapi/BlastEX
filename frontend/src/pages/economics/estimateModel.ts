/**
 * Инженерные разделы сметы-конструктора.
 *
 * Это другая группировка строк, чем «слой → раздел» из `estimateSections.ts`
 * (вкладка «Структура затрат», бумажная смета). Здесь строки собраны по
 * инженерному смыслу статьи — где сметчик её редактирует на вкладке
 * «Смета» — а не по месту в бумажной форме: например, ТОиР СЗМ формально
 * относится к общепроизводственным расходам, но здесь идёт в раздел
 * «Техника и оборудование», рядом с амортизацией той же машины.
 */
import type { BlockCostLine, BlockEconomics } from "../../types/blockEconomics";

export type EstimateGroupCode =
  | "EXPLOSIVES"
  | "DRILLING"
  | "LABOR"
  | "EQUIPMENT"
  | "FUEL"
  | "SERVICES"
  | "FIXED";

export type EstimateGroup = {
  code: EstimateGroupCode;
  /** Номер раздела как в конструкторе сметы: 1..7, не зависит от того, пуст ли раздел. */
  number: number;
  label: string;
  lines: BlockCostLine[];
  total: number;
  /** ₽/м³ объёма блока; null — объём блока ещё не задан (делить не на что). */
  perM3: number | null;
  /** Доля раздела в себестоимости, 0..1; 0 — себестоимость ещё нулевая. */
  share: number;
};

/** Порядок и подписи семи разделов конструктора — фиксированы, не зависят от данных. */
export const ESTIMATE_GROUPS: ReadonlyArray<{ code: EstimateGroupCode; label: string }> = [
  { code: "EXPLOSIVES", label: "Взрывчатые материалы" },
  { code: "DRILLING", label: "Бурение" },
  { code: "LABOR", label: "Персонал" },
  { code: "EQUIPMENT", label: "Техника и оборудование" },
  { code: "FUEL", label: "ГСМ" },
  { code: "SERVICES", label: "Производственные услуги" },
  { code: "FIXED", label: "Постоянные и общепроизводственные расходы" },
];

/** Префиксы кода статьи, по которым строка техники узнаётся вне зависимости от раздела. */
const MACHINE_PREFIXES = ["SZM_", "VM_TRUCK_", "EMULSION_TRUCK_"];

/** Раздел конструктора для одной строки сметы — см. правило в шапке файла. */
export function groupOf(line: BlockCostLine): EstimateGroupCode {
  if (line.section === "EXPLOSIVES") return "EXPLOSIVES";
  if (line.section === "DRILLING") return "DRILLING";
  if (line.section === "LABOR" || line.section === "PER_DIEM") return "LABOR";
  if (line.section === "DEPRECIATION") return "EQUIPMENT";
  if (MACHINE_PREFIXES.some((prefix) => line.cost_item_code.startsWith(prefix))) return "EQUIPMENT";
  if (line.section === "FUEL") return "FUEL";
  if (line.section === "VM_LOGISTICS") return "SERVICES";
  // Ручная услуга с вкладки: и количество, и цена введены сметчиком, а не
  // взяты из модели или справочника — это производственная услуга.
  if (line.quantity_origin === "MANUAL" && line.price_origin === "MANUAL") return "SERVICES";
  return "FIXED";
}

/**
 * Семь разделов конструктора, всегда в порядке `ESTIMATE_GROUPS` — пустой
 * раздел не пропадает из списка, а приходит с нулевым итогом: сметчик видит
 * всю структуру сметы, даже если часть статей ещё не заполнена.
 */
export function buildEstimate(economics: BlockEconomics): EstimateGroup[] {
  const byGroup = new Map<EstimateGroupCode, BlockCostLine[]>();
  for (const line of economics.lines) {
    const code = groupOf(line);
    const bucket = byGroup.get(code);
    if (bucket === undefined) byGroup.set(code, [line]);
    else bucket.push(line);
  }

  // Итог себестоимости — сумма всех строк без исключений; совпадает с
  // `markup.full_cost_rub`, который присылает бэкенд, но здесь не читается
  // из ответа модели, чтобы разделы всегда были согласованы со своими строками.
  const costTotal = economics.lines.reduce((sum, line) => sum + line.amount_rub, 0);
  const volume = economics.block_volume_m3;

  return ESTIMATE_GROUPS.map(({ code, label }, index) => {
    const lines = byGroup.get(code) ?? [];
    const total = lines.reduce((sum, line) => sum + line.amount_rub, 0);
    return {
      code,
      number: index + 1,
      label,
      lines,
      total,
      perM3: volume > 0 ? total / volume : null,
      share: costTotal > 0 ? total / costTotal : 0,
    };
  });
}

/** Номер строки внутри раздела: «1.3» — раздел 1, третья строка. */
export function lineNumber(group: EstimateGroup, index: number): string {
  return `${group.number}.${index + 1}`;
}
