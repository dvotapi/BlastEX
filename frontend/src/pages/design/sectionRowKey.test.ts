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

  it("groups production and auxiliary grid holes of one positional row together", () => {
    expect(sectionRowKey({ kind: "production", id: "3-05", row: 2 })).toBe("grid:3");
    expect(sectionRowKey({ kind: "stab", id: "3-06", row: 2 })).toBe("grid:3");
  });

  it("puts manual holes in one group regardless of their sentinel row", () => {
    expect(sectionRowKey({ kind: "production", id: "M-1", row: -1000, source: "manual" })).toBe("manual:0");
    expect(sectionRowKey({ kind: "production", id: "M-2", row: -1000, source: "manual" })).toBe("manual:0");
  });
});
