import { describe, expect, it } from "vitest";

import { ESTIMATE_GROUPS, buildEstimate, groupOf, lineNumber } from "./estimateModel";
import type { BlockCostLine, BlockEconomics } from "../../types/blockEconomics";

const line = (patch: Partial<BlockCostLine>): BlockCostLine => ({
  month: "",
  service_line_id: "",
  service_line_name: "",
  operation_code: "",
  cost_item_code: "X",
  cost_item_name: "x",
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
});

describe("ESTIMATE_GROUPS", () => {
  it("семь разделов без повторов кодов", () => {
    expect(ESTIMATE_GROUPS).toHaveLength(7);
    expect(new Set(ESTIMATE_GROUPS.map((group) => group.code)).size).toBe(7);
  });
});

describe("groupOf", () => {
  it("ВМ и бурение относятся к своим разделам напрямую по section", () => {
    expect(groupOf(line({ section: "EXPLOSIVES" }))).toBe("EXPLOSIVES");
    expect(groupOf(line({ section: "DRILLING" }))).toBe("DRILLING");
  });

  it("ТОиР СЗМ относится к технике, хотя в бумажной смете это общепроизводственные", () => {
    expect(groupOf(line({ section: "OVERHEAD", cost_item_code: "SZM_MAINTENANCE" }))).toBe("EQUIPMENT");
  });

  it("амортизация — техника независимо от кода статьи", () => {
    expect(groupOf(line({ section: "DEPRECIATION", cost_item_code: "DRILL_DEPRECIATION" }))).toBe("EQUIPMENT");
  });

  it("транспорт ВМ и тягач эмульсии узнаются по префиксу кода даже вне раздела DEPRECIATION", () => {
    expect(groupOf(line({ section: "OVERHEAD", cost_item_code: "VM_TRUCK_INSURANCE" }))).toBe("EQUIPMENT");
    expect(groupOf(line({ section: "OVERHEAD", cost_item_code: "EMULSION_TRUCK_INSURANCE" }))).toBe("EQUIPMENT");
  });

  it("суточные идут к персоналу", () => {
    expect(groupOf(line({ section: "PER_DIEM" }))).toBe("LABOR");
  });

  it("ФОТ идёт к персоналу", () => {
    expect(groupOf(line({ section: "LABOR" }))).toBe("LABOR");
  });

  it("ГСМ — свой раздел", () => {
    expect(groupOf(line({ section: "FUEL" }))).toBe("FUEL");
  });

  it("строка топлива техники (SZM_FUEL) попадает в ГСМ, а не в Технику, несмотря на префикс кода", () => {
    // Раздел из данных бэкенда (`section: "FUEL"`, см. `cost/model/logistics.py::_vehicle_fuel`)
    // важнее эвристики по префиксу кода статьи техники (`MACHINE_PREFIXES`):
    // код "SZM_FUEL" начинается с "SZM_" и раньше уходил в «Технику» первым же совпадением.
    expect(groupOf(line({ section: "FUEL", cost_item_code: "SZM_FUEL" }))).toBe("FUEL");
    expect(groupOf(line({ section: "FUEL", cost_item_code: "EMULSION_TRUCK_FUEL" }))).toBe("FUEL");
    expect(groupOf(line({ section: "FUEL", cost_item_code: "VM_TRUCK_FUEL" }))).toBe("FUEL");
  });

  it("хранение и доставка ВМ — производственная услуга", () => {
    expect(groupOf(line({ section: "VM_LOGISTICS" }))).toBe("SERVICES");
  });

  it("услуга с вкладки — производственная услуга", () => {
    expect(groupOf(line({ quantity_origin: "MANUAL", price_origin: "MANUAL" }))).toBe("SERVICES");
  });

  it("строка с одним ручным полем — ещё не услуга с вкладки, остаётся постоянными", () => {
    expect(groupOf(line({ quantity_origin: "MANUAL", price_origin: "REFERENCE" }))).toBe("FIXED");
  });

  it("всё, что не подошло под остальные правила — постоянные и общепроизводственные", () => {
    expect(groupOf(line({ section: "OVERHEAD" }))).toBe("FIXED");
  });
});

describe("buildEstimate", () => {
  const economics = {
    block_volume_m3: 1000,
    lines: [
      line({ section: "EXPLOSIVES", amount_rub: 600 }),
      line({ section: "DRILLING", amount_rub: 400 }),
    ],
  } as BlockEconomics;

  it("всегда возвращает семь разделов по порядку, пустые — нулями", () => {
    const groups = buildEstimate(economics);
    expect(groups.map((g) => g.code)).toEqual(ESTIMATE_GROUPS.map((g) => g.code));
    expect(groups.map((g) => g.number)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(groups[2].total).toBe(0);
    expect(groups[2].lines).toEqual([]);
    expect(groups[2].perM3).toBe(0);
    expect(groups[2].share).toBe(0);
  });

  it("считает долю и ₽/м³ от объёма блока", () => {
    const [explosives] = buildEstimate(economics);
    expect(explosives.total).toBe(600);
    expect(explosives.share).toBeCloseTo(0.6);
    expect(explosives.perM3).toBeCloseTo(0.6);
  });

  it("при нулевом объёме ₽/м³ — null, а не Infinity", () => {
    const [explosives] = buildEstimate({ ...economics, block_volume_m3: 0 });
    expect(explosives.perM3).toBeNull();
  });

  it("при нулевой себестоимости доля — 0, а не NaN", () => {
    const empty = { block_volume_m3: 1000, lines: [] } as unknown as BlockEconomics;
    const groups = buildEstimate(empty);
    expect(groups.every((group) => group.share === 0)).toBe(true);
    expect(groups.every((group) => group.total === 0)).toBe(true);
  });

  it("сумма разделов равна сумме всех строк сметы", () => {
    const groups = buildEstimate(economics);
    const total = groups.reduce((sum, group) => sum + group.total, 0);
    const linesTotal = economics.lines.reduce((sum, l) => sum + l.amount_rub, 0);
    expect(total).toBe(linesTotal);
  });
});

describe("lineNumber", () => {
  it("собирает номер раздел.строка", () => {
    const [explosives] = buildEstimate({
      block_volume_m3: 1000,
      lines: [line({ section: "EXPLOSIVES" }), line({ section: "EXPLOSIVES" }), line({ section: "EXPLOSIVES" })],
    } as BlockEconomics);
    expect(lineNumber(explosives, 0)).toBe("1.1");
    expect(lineNumber(explosives, 2)).toBe("1.3");
  });
});
