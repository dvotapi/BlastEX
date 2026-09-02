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

  it("flags holes the initiation cannot reach from the starters", () => {
    const network = emptyNetwork();
    network.starter_items = [{ id: "st-A", hole_id: "A", delay_ms: 0, kind: "starter" }];
    network.starters = ["A"];
    network.surface_connectors = [
      { id: "sc-A-B", from_hole: "A", to_hole: "B", delay_ms: 25, kind: "surface_nsi", product: "" },
      // изолированный кусок сети: коннектор есть, стартера нет
      { id: "sc-C-D", from_hole: "C", to_hole: "D", delay_ms: 25, kind: "surface_nsi", product: "" },
    ];
    const load = (id: string) => ({ hole_id: id, decks: [], total_charge_kg: 100, influence_volume_m3: 1, specific_q_kg_m3: 1, primers: [5] });
    const contour = emptyDesign().contour;
    const health = (id: string) => computeHoleHealth(sampleHole(id, 0, 0), { load: load(id), network, contour });
    expect(health("A")).toBe("ok");
    expect(health("B")).toBe("ok");
    expect(health("C")).toBe("unconnected");
    expect(health("D")).toBe("unconnected");
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
