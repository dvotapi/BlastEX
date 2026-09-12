import { describe, expect, it } from "vitest";
import { defaultPanelInputs } from "./calcInputs";
import { geometryPayload } from "./holeGeometryPayload";

const CONTEXT = {
  gridAM: 4.84,
  gridBM: 4.2,
  depthM: 11,
  overdrillM: 1,
  crownMm: 152,
  holeOversizeCoeff: 1.05,
  blockVolumeM3: 22000,
  additionalHolesPct: 0.03,
};

describe("geometryPayload", () => {
  it("собирает запрос схемы заряда из полей варианта и выбранной сетки", () => {
    const inputs = { ...defaultPanelInputs("ПВВ Гранулит-РП", 2.7), nsi_per_hole: 2, detonator_delay_ms: 700 };
    expect(geometryPayload(inputs, CONTEXT)).toEqual({
      grid_a_m: 4.84,
      grid_b_m: 4.2,
      depth_m: 11,
      overdrill_m: 1,
      undercharge_m: 2.7,
      crown_mm: 152,
      hole_oversize_coeff: 1.05,
      explosive_key: "ПВВ Гранулит-РП",
      block_volume_m3: 22000,
      additional_holes_pct: 0.03,
      intermediate_detonators_per_hole: 1,
      nsi_per_hole: 2,
      nsi_length_1_m: 12,
      nsi_length_2_m: 6,
      detonator_delay_ms: 700,
      view: "charge",
    });
  });

  it("недозаряд не глубже скважины: после уменьшения уступа значение обрезается", () => {
    const inputs = defaultPanelInputs("ПВВ Гранулит-РП", 9);
    expect(geometryPayload(inputs, { ...CONTEXT, depthM: 6 }).undercharge_m).toBe(5.5);
  });
});
