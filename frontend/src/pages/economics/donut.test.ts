import { describe, expect, it } from "vitest";

import { GROUP_COLORS, donutSegments } from "./donut";
import { ESTIMATE_GROUPS, buildEstimate } from "./estimateModel";
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

const economics = {
  block_volume_m3: 1000,
  lines: [
    line({ section: "EXPLOSIVES", amount_rub: 600 }),
    line({ section: "DRILLING", amount_rub: 400 }),
  ],
} as BlockEconomics;

describe("GROUP_COLORS", () => {
  it("свой цвет на каждый из семи разделов", () => {
    for (const group of ESTIMATE_GROUPS) {
      expect(GROUP_COLORS[group.code]).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
});

describe("donutSegments", () => {
  it("сегменты покрывают полный круг и пропускают нулевые разделы", () => {
    const segments = donutSegments(buildEstimate(economics), 80, 22);
    expect(segments.map((s) => s.code)).toEqual(["EXPLOSIVES", "DRILLING"]);
    expect(segments.reduce((sum, s) => sum + s.share, 0)).toBeCloseTo(1);
    expect(segments[0].path).toMatch(/^M .* A .* Z$/);
    expect(segments[0].path).not.toContain("NaN");
    expect(segments[1].path).not.toContain("NaN");
  });

  it("цвет и подпись сегмента берутся из раздела", () => {
    const [explosives] = donutSegments(buildEstimate(economics), 80, 22);
    expect(explosives.label).toBe("Взрывчатые материалы");
    expect(explosives.color).toBe(GROUP_COLORS.EXPLOSIVES);
    expect(explosives.value).toBe(600);
    expect(explosives.perM3).toBeCloseTo(0.6);
  });

  it("один сегмент рисуется полным кольцом без вырожденной дуги", () => {
    const single = { block_volume_m3: 1000, lines: [line({ section: "EXPLOSIVES", amount_rub: 1000 })] } as BlockEconomics;
    const [segment] = donutSegments(buildEstimate(single), 80, 22);
    expect(segment.share).toBeCloseTo(1);
    expect(segment.path).not.toContain("NaN");
    // Полный круг рисуется двумя полукольцами: две команды M внутри пути.
    expect(segment.path.match(/M /g)?.length).toBe(2);
  });

  it("пустая смета не даёт сегментов", () => {
    const empty = { block_volume_m3: 1000, lines: [] } as unknown as BlockEconomics;
    expect(donutSegments(buildEstimate(empty), 80, 22)).toEqual([]);
  });
});
