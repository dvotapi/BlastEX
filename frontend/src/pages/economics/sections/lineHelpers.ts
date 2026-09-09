/**
 * Общие приёмы сопоставления строк модели со строками, которые рисует
 * раздел конструктора сметы.
 *
 * Три и более раздела ищут свою строку одним и тем же способом — по роли
 * номенклатуры, по коду статьи или по префиксу семейства статей техники —
 * поэтому сопоставление вынесено сюда один раз, а не повторяется в каждом
 * файле раздела своей копией.
 */
import type { BlockCostLine, BlockEconomics } from "../../../types/blockEconomics";

/**
 * Строка раздела по роли номенклатуры: код выбранного материала меняется от
 * прогона к прогону, а `role_label` — нет (тот же приём, что у
 * `groupVariantsByLayerAndSection` в `estimateSections.ts`).
 */
export function lineByRoleLabel(lines: BlockCostLine[], roleLabel: string): BlockCostLine | undefined {
  return lines.find((line) => line.role_label === roleLabel);
}

/** Строка раздела по точному коду статьи. */
export function lineByCode(lines: BlockCostLine[], code: string): BlockCostLine | undefined {
  return lines.find((line) => line.cost_item_code === code);
}

/** Строки раздела, чей код статьи начинается с префикса — так узнаётся семейство статей одной машины. */
export function linesByPrefix(lines: BlockCostLine[], prefix: string): BlockCostLine[] {
  return lines.filter((line) => line.cost_item_code.startsWith(prefix));
}

/**
 * Доля строки в полной себестоимости блока (все строки расчёта, а не только
 * раздела) — тем же способом, каким `estimateModel.ts` считает долю раздела.
 * Расчёта ещё нет — доля нулевая, а не NaN.
 */
export function lineShare(line: BlockCostLine, economics: BlockEconomics | null): number {
  if (!economics) return 0;
  const total = economics.lines.reduce((sum, item) => sum + item.amount_rub, 0);
  return total > 0 ? line.amount_rub / total : 0;
}
