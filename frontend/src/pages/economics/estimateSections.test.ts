import { describe, expect, it } from "vitest";

import { ESTIMATE_SECTIONS, groupByLayerAndSection, sectionLabel } from "./estimateSections";
import type { BlockCostLine, CostLayer, EstimateSection } from "../../types/blockEconomics";

const line = (
  code: string,
  layer: CostLayer,
  section: EstimateSection,
  amount: number,
): BlockCostLine =>
  ({
    cost_item_code: code,
    cost_item_name: code,
    operation_code: "",
    layer,
    amount_rub: amount,
    formula: "",
    resource_code: "",
    section,
    quantity: null,
    unit: "",
    unit_price_rub: null,
  }) as BlockCostLine;

describe("группировка сметы", () => {
  it("складывает строки в разделы внутри слоёв и держит порядок сметы", () => {
    const groups = groupByLayerAndSection([
      line("SZM_FUEL", "variable", "FUEL", 10),
      line("MATERIAL_EXPLOSIVE", "variable", "EXPLOSIVES", 100),
      line("DRILL_TOOLING", "variable", "DRILLING", 50),
      line("LABOR_X", "project_direct", "LABOR", 70),
    ]);

    expect(groups.map((group) => group.layer)).toEqual(["variable", "project_direct"]);
    expect(groups[0].sections.map((section) => section.label)).toEqual([
      "Расходы на ВМ",
      "Расходы на бурение",
      "ГСМ",
    ]);
    expect(groups[0].total).toBe(160);
    expect(groups[0].sections[0].total).toBe(100);
    expect(groups[1].sections[0].lines).toHaveLength(1);
  });

  it("пустых разделов и слоёв не показывает", () => {
    const groups = groupByLayerAndSection([line("LABOR_X", "project_direct", "LABOR", 70)]);

    expect(groups).toHaveLength(1);
    expect(groups[0].sections).toHaveLength(1);
  });

  it("нумерует разделы как в смете: слой — первая цифра, раздел — вторая", () => {
    const groups = groupByLayerAndSection([
      line("MATERIAL_EXPLOSIVE", "variable", "EXPLOSIVES", 100),
      line("DRILL_TOOLING", "variable", "DRILLING", 50),
      line("LABOR_X", "project_direct", "LABOR", 70),
      line("UNIT_PPE", "production", "OVERHEAD", 5),
    ]);

    expect(groups[0].sections.map((s) => s.number)).toEqual(["1.1", "1.2"]);
    expect(groups[1].sections.map((s) => s.number)).toEqual(["2.5"]);
    expect(groups[2].sections.map((s) => s.number)).toEqual(["3.8"]);
  });

  it("незнакомый раздел не теряет строку и идёт последним", () => {
    const groups = groupByLayerAndSection([
      { ...line("X", "variable", "EXPLOSIVES", 1), section: "НЕЧТО" as EstimateSection },
      line("MATERIAL", "variable", "EXPLOSIVES", 2),
    ]);

    expect(groups[0].sections.map((s) => s.section)).toEqual(["EXPLOSIVES", "НЕЧТО"]);
    expect(groups[0].sections[1].lines).toHaveLength(1);
    expect(groups[0].total).toBe(3);
  });

  it("подписи есть у всех разделов модели", () => {
    for (const section of ESTIMATE_SECTIONS) {
      expect(sectionLabel(section)).not.toBe(section);
    }
  });
});

describe("нумерация разделов", () => {
  it("привязана к слою, а не к порядку: пропуск слоя не сдвигает номера", () => {
    const withProduction = groupByLayerAndSection([
      line("MATERIAL", "variable", "EXPLOSIVES", 100),
      line("LABOR_X", "project_direct", "LABOR", 70),
      line("UNIT_PPE", "production", "OVERHEAD", 5),
      line("UNALLOCATED", "full", "DRILLING", 3),
    ]);
    const withoutProduction = groupByLayerAndSection([
      line("MATERIAL", "variable", "EXPLOSIVES", 100),
      line("LABOR_X", "project_direct", "LABOR", 70),
      line("UNALLOCATED", "full", "DRILLING", 3),
    ]);

    expect(withProduction.map((g) => g.sections[0].number)).toEqual(["1.1", "2.5", "3.8", "4.2"]);
    // Тот же раздел того же слоя называется так же, есть постоянные затраты или нет.
    expect(withoutProduction.map((g) => g.sections[0].number)).toEqual(["1.1", "2.5", "4.2"]);
  });

  it("не зависит от того, какие разделы слоя оказались пустыми", () => {
    const withMobilization = groupByLayerAndSection([
      line("MOBILIZATION", "project_direct", "VM_LOGISTICS", 10),
      line("LABOR_PER_DIEM", "project_direct", "PER_DIEM", 20),
      line("LABOR_X", "project_direct", "LABOR", 30),
    ]);
    const withoutMobilization = groupByLayerAndSection([
      line("LABOR_PER_DIEM", "project_direct", "PER_DIEM", 20),
      line("LABOR_X", "project_direct", "LABOR", 30),
    ]);

    const number = (groups: ReturnType<typeof groupByLayerAndSection>) =>
      groups[0].sections.find((s) => s.section === "PER_DIEM")?.number;
    // «Суточные» называются одинаково в обоих прогонах: номер — свойство
    // раздела, а не его места среди непустых.
    expect(number(withMobilization)).toBe("2.4");
    expect(number(withoutMobilization)).toBe("2.4");
  });
});
