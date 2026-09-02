import { describe, expect, it } from "vitest";
import { emptyDesign, emptyHoleGeology, emptyNetwork } from "../../types/design";
import { computeAllHoleHealth, computeHoleHealth, summarizeHealth } from "./holeHealth";

function sampleHole(id: string, x: number, y: number) {
  return {
    id,
    row: 1,
    col: 1,
    collar: { x, y, z: 100 },
    toe: { x, y, z: 80 },
    diameter_mm: 215,
    subdrill_m: 1,
    kind: "production" as const,
    source: "generated" as const,
    enabled: true,
    ...emptyHoleGeology(),
  };
}

describe("holeHealth", () => {
  it("flags production holes without charge", () => {
    const hole = sampleHole("H1", 0, 0);
    const code = computeHoleHealth(hole, {
      network: emptyNetwork(),
      contour: emptyDesign().contour,
    });
    expect(code).toBe("missing_charge");
  });

  it("flags holes outside contour polygon", () => {
    const design = emptyDesign();
    design.contour.vertices = [
      { x: 0, y: 0, z: 0 },
      { x: 10, y: 0, z: 0 },
      { x: 10, y: 10, z: 0 },
    ];
    const hole = sampleHole("H2", 20, 20);
    const code = computeHoleHealth(hole, {
      load: { hole_id: "H2", decks: [], total_charge_kg: 100, influence_volume_m3: 1, specific_q_kg_m3: 1, primers: [5] },
      network: emptyNetwork(),
      contour: design.contour,
    });
    expect(code).toBe("outside_contour");
  });

  it("summarizes issue count for review preset", () => {
    const holes = [sampleHole("H1", 0, 0), sampleHole("H2", 2, 0)];
    const map = computeAllHoleHealth({
      holes,
      loadsById: {},
      network: emptyNetwork(),
      contour: emptyDesign().contour,
      designHoleIds: new Set(holes.map((h) => h.id)),
    });
    const summary = summarizeHealth(map, holes);
    expect(summary.issueCount).toBeGreaterThan(0);
    expect(summary.byCode.missing_charge.length).toBe(2);
  });
});
