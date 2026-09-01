import { describe, expect, it } from "vitest";
import type { Hole, HoleLoad } from "../../types/design";
import { computeAllHoleHealth, computeHoleHealth, summarizeHealth } from "./holeHealth";

const baseHole: Hole = {
  id: "H1",
  row: 0,
  col: 0,
  collar: { x: 0, y: 0, z: 100 },
  toe: { x: 0, y: 0, z: 90 },
  diameter_mm: 165,
  subdrill_m: 1,
  kind: "production",
  source: "generated",
  enabled: true,
  intervals: [],
  water_intervals: [],
  measured_intervals: [],
  measured_water_intervals: [],
};

describe("holeHealth", () => {
  it("marks healthy enabled holes as ok", () => {
    const health = computeHoleHealth(baseHole, {
      loadsById: {
        H1: {
          hole_id: "H1",
          decks: [],
          total_charge_kg: 120,
          influence_volume_m3: 10,
          specific_q_kg_m3: 0.5,
          primers: [1],
        },
      },
    });
    expect(health.code).toBe("ok");
    expect(health.severity).toBe(0);
  });

  it("flags missing charge when required", () => {
    const health = computeHoleHealth(baseHole, { requireCharge: true });
    expect(health.code).toBe("no_charge");
    expect(health.severity).toBe(2);
  });

  it("marks disabled holes separately", () => {
    const health = computeHoleHealth({ ...baseHole, enabled: false });
    expect(health.code).toBe("disabled");
  });

  it("aggregates warnings by hole", () => {
    const all = computeAllHoleHealth([baseHole, { ...baseHole, id: "H2" }], {
      warnings: [{ code: "stemming_short", hole_id: "H1", message: "Короткая забойка" }],
    });
    expect(all.H1.severity).toBeGreaterThan(0);
    expect(all.H2.code).toBe("ok");
  });

  it("summarizes health counts", () => {
    const all = computeAllHoleHealth(
      [baseHole, { ...baseHole, id: "H2", enabled: false }],
      { requireCharge: true },
    );
    const summary = summarizeHealth(all);
    expect(summary.total).toBe(2);
    expect(summary.error).toBe(1);
    expect(summary.disabled).toBe(1);
  });
});
