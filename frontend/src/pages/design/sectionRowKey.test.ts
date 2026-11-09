import { describe, expect, it } from "vitest";
import { sectionRowKey } from "./SectionView";

describe("sectionRowKey", () => {
  it("separates wall bands that share a technical row", () => {
    const k1 = sectionRowKey({ kind: "contour", id: "K1-01", row: -1 });
    const k15 = sectionRowKey({ kind: "contour", id: "K15-01", row: -1 });
    const p1 = sectionRowKey({ kind: "presplit", id: "P1-01", row: -1 });
    expect(k1).not.toBe(k15);
    expect(k1).not.toBe(p1);
  });

  it("groups grid holes by technical row, not by echelon number in id", () => {
    // Id сетки — «эшелон-номер от бровки»: ряд вдоль бровки берётся из row.
    expect(sectionRowKey({ kind: "production", id: "3-05", row: 2 })).toBe("grid:2");
    expect(sectionRowKey({ kind: "production", id: "1-03", row: 2 })).toBe("grid:2");
    expect(sectionRowKey({ kind: "production", id: "1-04", row: 3 })).not.toBe("grid:2");
  });

  it("keeps trim holes in their own family, not grid row 1", () => {
    expect(sectionRowKey({ kind: "trim", id: "T1-01", row: -1 })).toBe("trim:1");
  });

  it("keeps stabilisation holes in their own family, not the production row", () => {
    expect(sectionRowKey({ kind: "stab", id: "S1-01", row: -1003 })).toBe("stab:1");
    expect(sectionRowKey({ kind: "stab", id: "S1-01", row: -1003 })).not.toBe("grid:1");
  });

  it("puts manual holes in one group regardless of their sentinel row", () => {
    expect(sectionRowKey({ kind: "production", id: "M-1", row: -1000, source: "manual" })).toBe("manual:0");
    expect(sectionRowKey({ kind: "production", id: "M-2", row: -1000, source: "manual" })).toBe("manual:0");
  });
});
