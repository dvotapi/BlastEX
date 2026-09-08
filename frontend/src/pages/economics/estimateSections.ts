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

export type VariantSectionRow = {
  /** Статья + операция: одна строка сметы для всех вариантов, где она есть. */
  key: string;
  label: string;
  unit: string;
  /** По одному числу на вариант, в их порядке; `null` — в этом варианте строки нет. */
  amounts: Array<number | null>;
};

export type VariantSectionGroup = {
  section: EstimateSection;
  number: string;
  label: string;
  totals: number[];
  rows: VariantSectionRow[];
};

export type VariantLayerGroup = {
  layer: CostLayer;
  label: string;
  hint: string;
  totals: number[];
  sections: VariantSectionGroup[];
};

/**
 * Та же смета, но по строке на статью сразу для нескольких вариантов —
 * колонками, как в бумажной смете с несколькими сценариями рядом.
 *
 * Строит дерево, раскладывая каждый вариант через `groupByLayerAndSection`
 * по отдельности, а затем сводя их по разделам и статьям: раздел входит в
 * итог, если он есть хоть у одного варианта, строка внутри — так же. Статья,
 * которой у варианта нет, получает `null` — это и есть отметка «X» бумажной
 * сметы: строку не с чем сравнивать, а не «стоит ноль».
 *
 * Совпадающая статья+операция дважды в одном разделе одного варианта (два
 * тёзки-услуги) — редкий случай, который эта сводка не различает: обе суммы
 * попадут в одну строку последней добавленной. Для одиночного варианта их
 * по-прежнему различает `groupByLayerAndSection`.
 */
export function groupVariantsByLayerAndSection(
  variantsLines: BlockCostLine[][],
): VariantLayerGroup[] {
  const perVariant = variantsLines.map(groupByLayerAndSection);
  const groups: VariantLayerGroup[] = [];

  for (const [index, layer] of LAYERS.entries()) {
    const layerNumber = index + 1;
    const ownPerVariant = perVariant.map(
      (own) => own.find((group) => group.layer === layer.code)?.sections,
    );
    if (ownPerVariant.every((sections) => sections === undefined)) continue;

    const sections: VariantSectionGroup[] = ESTIMATE_SECTIONS.filter((section) =>
      ownPerVariant.some((sections) => sections?.some((group) => group.section === section)),
    ).map((section) => {
      const linesPerVariant = ownPerVariant.map(
        (sections) => sections?.find((group) => group.section === section)?.lines ?? [],
      );
      const rowOrder: Array<{ key: string; label: string; unit: string }> = [];
      const seen = new Set<string>();
      for (const lines of linesPerVariant) {
        for (const line of lines) {
          const key = `${line.cost_item_code}:${line.operation_code}`;
          if (seen.has(key)) continue;
          seen.add(key);
          rowOrder.push({ key, label: line.cost_item_name, unit: line.unit });
        }
      }
      const rows: VariantSectionRow[] = rowOrder.map(({ key, label, unit }) => ({
        key,
        label,
        unit,
        amounts: linesPerVariant.map(
          (lines) => lines.find((line) => `${line.cost_item_code}:${line.operation_code}` === key)
            ?.amount_rub ?? null,
        ),
      }));
      return {
        section,
        number: `${layerNumber}.${SECTION_NUMBERS[section]}`,
        label: sectionLabel(section),
        totals: ownPerVariant.map((sections) => sections?.find((group) => group.section === section)?.total ?? 0),
        rows,
      };
    });

    groups.push({
      layer: layer.code,
      label: layer.label,
      hint: layer.hint,
      totals: ownPerVariant.map((sections) => sections?.reduce((sum, group) => sum + group.total, 0) ?? 0),
      sections,
    });
  }
  return groups;
}
