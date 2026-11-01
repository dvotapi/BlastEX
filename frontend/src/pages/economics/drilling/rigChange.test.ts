import { describe, expect, it } from "vitest";
import type { ModelDefaults, ModelParameters } from "../../../types/blockEconomics";
import { rigChangePatch } from "./OwnDrillingEditor";

const defaults = {
  rig_crews: {
    RIG_A: [{ position_code: "DRILLER", headcount: "1", shifts_per_block: null }],
    RIG_B: [
      { position_code: "DRILLER", headcount: "1", shifts_per_block: null },
      { position_code: "ASSISTANT", headcount: "1", shifts_per_block: null },
    ],
  },
} as unknown as ModelDefaults;

const params = (crew: ModelParameters["crew"]) => ({ rig_code: "RIG_A", crew }) as unknown as ModelParameters;

describe("rigChangePatch", () => {
  it("заменяет экипаж бурения экипажем нового станка и сохраняет остальную бригаду", () => {
    const current = params([
      { position_code: "BLASTER", headcount: "2", shifts_per_block: null },
      { position_code: "DRILLER", headcount: "1", shifts_per_block: null },
    ]);
    const patch = rigChangePatch(current, defaults, "RIG_B");
    expect(patch.rig_code).toBe("RIG_B");
    expect(patch.crew?.map((m) => m.position_code)).toEqual(["BLASTER", "DRILLER", "ASSISTANT"]);
  });

  it("при переходе на станок без своего экипажа убирает экипаж бурения прежнего", () => {
    const current = params([
      { position_code: "BLASTER", headcount: "2", shifts_per_block: null },
      { position_code: "DRILLER", headcount: "1", shifts_per_block: null },
    ]);
    const patch = rigChangePatch(current, defaults, "RIG_C");
    expect(patch.crew?.map((m) => m.position_code)).toEqual(["BLASTER"]);
  });

  it("без станко-зависимых составов в справочнике меняет только станок", () => {
    const patch = rigChangePatch(params([]), { rig_crews: {} } as unknown as ModelDefaults, "RIG_B");
    expect(patch).toEqual({ rig_code: "RIG_B" });
  });
});
