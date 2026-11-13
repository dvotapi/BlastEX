import { describe, expect, it } from "vitest";
import { hitTie, tieEndAt, tiesInRect, type TieSegment } from "./tieHits";

const SEGMENTS: TieSegment[] = [
  { id: "h", a: { x: 0, y: 0 }, b: { x: 100, y: 0 } },
  { id: "v", a: { x: 50, y: 10 }, b: { x: 50, y: 110 } },
];

describe("попадания по связям", () => {
  it("линия ближе 6 px — ближайшая", () => {
    expect(hitTie({ x: 30, y: 4 }, SEGMENTS)).toBe("h");
    expect(hitTie({ x: 52, y: 60 }, SEGMENTS)).toBe("v");
    expect(hitTie({ x: 30, y: 9 }, SEGMENTS)).toBeNull();
  });

  it("рамка захватывает пересечённые отрезки", () => {
    expect(tiesInRect({ minX: 40, minY: -5, maxX: 60, maxY: 5 }, SEGMENTS)).toEqual(["h"]);
    expect(tiesInRect({ minX: 45, minY: 20, maxX: 55, maxY: 30 }, SEGMENTS)).toEqual(["v"]);
    expect(tiesInRect({ minX: 40, minY: -5, maxX: 60, maxY: 20 }, SEGMENTS).sort()).toEqual(["h", "v"]);
    expect(tiesInRect({ minX: 60, minY: 20, maxX: 90, maxY: 40 }, SEGMENTS)).toEqual([]);
    // Рамка внутри длинной линии, концы снаружи.
    expect(tiesInRect({ minX: 10, minY: -1, maxX: 20, maxY: 1 }, SEGMENTS)).toEqual(["h"]);
  });

  it("конец связи — у начала или у конца в радиусе", () => {
    expect(tieEndAt({ x: 2, y: 1 }, SEGMENTS[0], 12)).toBe("from");
    expect(tieEndAt({ x: 95, y: 0 }, SEGMENTS[0], 12)).toBe("to");
    expect(tieEndAt({ x: 50, y: 0 }, SEGMENTS[0], 12)).toBeNull();
  });
});
