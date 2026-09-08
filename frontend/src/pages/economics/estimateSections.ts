/**
 * Разделы бумажной сметы внутри слоёв себестоимости.
 *
 * Слой отвечает на вопрос «как затрата ведёт себя с объёмом» — от него
 * считается маржинальная цена. Раздел отвечает на вопрос «где эта строка в
 * смете» — по нему сметчик ищет её глазами. Поэтому слой остаётся верхним
 * уровнем, а разделы идут внутри в том же порядке, что на бумаге.
 */
import { enumLabel } from "../references/enumLabels";
import type { BlockCostLine, CostLayer, EstimateSection } from "../../types/blockEconomics";

/**
 * Номер раздела внутри слоя — свойство раздела, а не его места в списке:
 * в двух прогонах, где один раздел пуст, а другой нет, «Суточные» должны
 * называться одинаково. `Record` по типу не даёт забыть новый раздел.
 */
const SECTION_NUMBERS: Record<EstimateSection, number> = {
  EXPLOSIVES: 1,
  DRILLING: 2,
  VM_LOGISTICS: 3,
  PER_DIEM: 4,
  LABOR: 5,
  FUEL: 6,
  DEPRECIATION: 7,
  OVERHEAD: 8,
};

export const ESTIMATE_SECTIONS = Object.keys(SECTION_NUMBERS) as EstimateSection[];

const LAYERS: Array<{ code: CostLayer; label: string; hint: string }> = [
  { code: "variable", label: "Переменные затраты", hint: "растут вместе с объёмом блока" },
  { code: "project_direct", label: "Прямые затраты блока", hint: "ФОТ, амортизация по сменам, мобилизация" },
  { code: "production", label: "Постоянные затраты юнита", hint: "распределены по плановому объёму" },
  { code: "full", label: "Нераспределённые затраты", hint: "не отнесены на блок напрямую" },
];

export type SectionGroup = {
  section: EstimateSection;
  /** Номер как в смете: «1.1», «2.3». */
  number: string;
  label: string;
  total: number;
  lines: BlockCostLine[];
};

export type LayerGroup = {
  layer: CostLayer;
  label: string;
  hint: string;
  total: number;
  sections: SectionGroup[];
};

/** Подпись раздела берётся оттуда же, откуда её берёт форма справочника. */
export function sectionLabel(section: EstimateSection): string {
  return enumLabel(section);
}

/** Строки по слоям, внутри — по разделам сметы; пустые группы отбрасываются. */
export function groupByLayerAndSection(lines: BlockCostLine[]): LayerGroup[] {
  // Один проход по строкам: слой → раздел → строки. Порядок вставки в Map
  // сохраняет незнакомые разделы (справочник ушёл вперёд кода) последними.
  const byLayer = new Map<CostLayer, Map<EstimateSection, BlockCostLine[]>>();
  for (const line of lines) {
    let sections = byLayer.get(line.layer);
    if (sections === undefined) {
      sections = new Map();
      byLayer.set(line.layer, sections);
    }
    const bucket = sections.get(line.section);
    if (bucket === undefined) sections.set(line.section, [line]);
    else bucket.push(line);
  }

  const groups: LayerGroup[] = [];
  for (const [index, layer] of LAYERS.entries()) {
    const own = byLayer.get(layer.code);
    if (own === undefined) continue;
    // Номер берётся из места слоя в смете, а не из порядка непустых групп:
    // иначе один и тот же раздел назывался бы по-разному в двух прогонах —
    // с постоянными затратами юнита и без них.
    const layerNumber = index + 1;

    const order = [...own.keys()].sort(
      (left, right) => (SECTION_NUMBERS[left] ?? 99) - (SECTION_NUMBERS[right] ?? 99),
    );
    const sections: SectionGroup[] = order.map((section) => {
      const sectionLines = own.get(section) ?? [];
      return {
        section,
        number: `${layerNumber}.${SECTION_NUMBERS[section] ?? "—"}`,
        label: sectionLabel(section),
        total: sectionLines.reduce((sum, line) => sum + line.amount_rub, 0),
        lines: sectionLines,
      };
    });

    groups.push({
      layer: layer.code,
      label: layer.label,
      hint: layer.hint,
      total: sections.reduce((sum, group) => sum + group.total, 0),
      sections,
    });
  }
  return groups;
}
