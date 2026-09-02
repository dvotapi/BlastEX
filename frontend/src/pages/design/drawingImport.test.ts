import { describe, expect, it } from "vitest";
import { guessBenchLines } from "./DrawingImportDialog";
import type { DrawingPolyline } from "../../types/design";

function line(id: string, layer: string, lengthM: number, z: number, points = 4): DrawingPolyline {
  return {
    id,
    layer,
    entity: "LWPOLYLINE",
    closed: false,
    points: Array.from({ length: points }, (_, i) => ({ x: i, y: i, z })),
    length_m: lengthM,
    area_m2: 0,
    z_min: z,
    z_max: z,
  };
}

describe("guessBenchLines", () => {
  it("picks the bench lines and ignores service graphics lying at zero elevation", () => {
    // Так выглядит типовая выгрузка: две бровки и россыпь осей на Z=0.
    const scan = [
      line("crest", "BROVKA_VERH", 340, 124),
      line("toe", "BROVKA_NIZ", 232, 112),
      line("axis1", "OSI", 70, 0, 2),
      line("axis2", "OSI", 70, 0, 2),
      line("axis3", "OSI", 70, 0, 2),
    ];
    expect(guessBenchLines(scan)).toEqual({ crest: "crest", toe: "toe" });
  });

  it("uses elevation to tell crest from toe when both lines are long", () => {
    const scan = [line("a", "L1", 300, 90), line("b", "L2", 320, 105)];
    expect(guessBenchLines(scan)).toEqual({ crest: "b", toe: "a" });
  });

  it("still proposes a pair when every line sits at the same elevation", () => {
    const scan = [line("a", "L1", 300, 50), line("b", "L2", 100, 50)];
    const guess = guessBenchLines(scan);
    expect(guess.crest).not.toBe("");
    expect(guess.toe).not.toBe("");
    expect(guess.crest).not.toBe(guess.toe);
  });

  it("leaves the second slot empty when the drawing has a single line", () => {
    expect(guessBenchLines([line("only", "L1", 10, 5)])).toEqual({ crest: "only", toe: "" });
  });

  it("returns empty ids for an empty scan", () => {
    expect(guessBenchLines([])).toEqual({ crest: "", toe: "" });
  });
});
