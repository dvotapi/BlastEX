import { describe, expect, it } from "vitest";
import type { ModelParameters } from "../types/blockEconomics";
import type { WorkspaceState } from "../types";
import { buildCostContext } from "./costContext";

const state = {
  snapshot: {
    labor_assignment_records: [{ id: "a1" }],
    labor_shifts_per_month: 7,
    scenario_phase_overrides: { p1: false },
  },
} as unknown as WorkspaceState;

describe("buildCostContext", () => {
  it("несёт параметры черновика сметы для цены метра бурения", () => {
    const parameters = { rig_code: "RIG_1", package_code: "DRILL_AND_BLAST" } as unknown as ModelParameters;
    const context = buildCostContext(state, parameters);
    expect(context.drilling_model).toEqual({ parameters });
    expect(context.labor_settings).toEqual({ shifts_per_month: 7 });
    expect(context.scenario_phase_overrides).toEqual({ p1: false });
  });

  it("без черновика ключа drilling_model нет — сервер вернёт нулевую цену с пояснением", () => {
    expect("drilling_model" in buildCostContext(state)).toBe(false);
    expect("drilling_model" in buildCostContext(state, null)).toBe(false);
  });

  it("старого ввода калькулятора бурения в контексте нет", () => {
    expect("drilling_input" in buildCostContext(state)).toBe(false);
  });
});
