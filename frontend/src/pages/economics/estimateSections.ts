/**
 * Разделы бумажной сметы внутри слоёв себестоимости.
 *
 * Слой отвечает на вопрос «как затрата ведёт себя с объёмом» — от него
 * считается маржинальная цена. Раздел отвечает на вопрос «где эта строка в
 * смете» — по нему сметчик ищет её глазами. Поэтому слой остаётся верхним
 * уровнем, а разделы идут внутри в том же порядке, что на бумаге.
 */
import type { BlockCostLine, CostLayer, EstimateSection } from "../../types/blockEconomics";

export const ESTIMATE_SECTIONS: EstimateSection[] = [
  "EXPLOSIVES",
  "DRILLING",
  "VM_LOGISTICS",
  "PER_DIEM",
  "LABOR",
  "FUEL",
  "DEPRECIATION",
  "OVERHEAD",
];

const SECTION_LABELS: Record<EstimateSection, string> = {
  EXPLOSIVES: "Расходы на ВМ",
  DRILLING: "Расходы на бурение",
  VM_LOGISTICS: "Хранение, производство и доставка ВМ",
  PER_DIEM: "Суточные, вахтовые, проживание",
  LABOR: "Фонд оплаты труда",
  FUEL: "ГСМ",
  DEPRECIATION: "Амортизация",
  OVERHEAD: "Общепроизводственные затраты",
};

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

export function sectionLabel(section: EstimateSection): string {
  return SECTION_LABELS[section] ?? section;
}

/** Строки по слоям, внутри — по разделам сметы; пустые группы отбрасываются. */
export function groupByLayerAndSection(lines: BlockCostLine[]): LayerGroup[] {
  const groups: LayerGroup[] = [];

  for (const [index, layer] of LAYERS.entries()) {
    const own = lines.filter((line) => line.layer === layer.code);
    if (own.length === 0) continue;
    // Номер берётся из места слоя в смете, а не из порядка непустых групп:
    // иначе один и тот же раздел назывался бы по-разному в двух прогонах —
    // с постоянными затратами юнита и без них.
    const layerNumber = index + 1;

    const sections: SectionGroup[] = [];
    // Незнакомый раздел (справочник ушёл вперёд кода) не теряется: он идёт
    // последним, под своим кодом, а не исчезает из сметы.
    const order = [...ESTIMATE_SECTIONS, ...new Set(own.map((line) => line.section))];
    for (const section of order) {
      if (sections.some((group) => group.section === section)) continue;
      const sectionLines = own.filter((line) => line.section === section);
      if (sectionLines.length === 0) continue;
      sections.push({
        section,
        number: `${layerNumber}.${sections.length + 1}`,
        label: sectionLabel(section),
        total: sectionLines.reduce((sum, line) => sum + line.amount_rub, 0),
        lines: sectionLines,
      });
    }

    groups.push({
      layer: layer.code,
      label: layer.label,
      hint: layer.hint,
      total: own.reduce((sum, line) => sum + line.amount_rub, 0),
      sections,
    });
  }
  return groups;
}
