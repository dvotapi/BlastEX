// Сдвиг скважин в осях раскладки (TASK-017, PR 1): оси, привязка, стрелки, пары.
import { describe, expect, it } from "vitest";
import type { BlockContour, Hole } from "../../types/design";
import { arrowDelta, dragDelta, fromAxes, gridSteps, layoutAxes, returnToNodeIds, snapStepM, toAxes, withFacePairs } from "./holeMove";
import liveFixture from "./testing/liveLspFixture.json";

function rectContour(freeFaces: number[][] = [[0, 1]]): BlockContour {
  // Откос — южная сторона (0,0)→(40,0), блок уходит на север.
  return {
    vertices: [
      { x: 0, y: 0, z: 0 },
      { x: 40, y: 0, z: 0 },
      { x: 40, y: 30, z: 0 },
      { x: 0, y: 30, z: 0 },
    ],
    free_faces: freeFaces,
    bench: { crest_z_m: 0, toe_z_m: -10, face_angle_deg: 75 },
    name: "Блок",
  };
}

function hole(id: string, kind: Hole["kind"] = "production"): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x: 0, y: 0, z: 0 },
    toe: { x: 0, y: 0, z: -11 },
    diameter_mm: 165,
    subdrill_m: 1,
    kind,
    source: "generated",
    enabled: true,
    intervals: [],
    water_intervals: [],
    measured_intervals: [],
    measured_water_intervals: [],
  };
}

describe("gridSteps", () => {
  it("как grid_steps_m: квадратная — b = a, без a — 5 м", () => {
    expect(gridSteps({ pattern: "square", spacing_a_m: 4, burden_b_m: 3 })).toEqual({ a: 4, b: 4 });
    expect(gridSteps({ pattern: "rectangular", spacing_a_m: 4, burden_b_m: 3 })).toEqual({ a: 4, b: 3 });
    expect(gridSteps({ pattern: "rectangular", spacing_a_m: 4 })).toEqual({ a: 4, b: 4 });
    expect(gridSteps({})).toEqual({ a: 5, b: 5 });
    expect(gridSteps(null)).toEqual({ a: 5, b: 5 });
  });

  it("шаг привязки: выкл, 0,1 м, a/4, b/4", () => {
    const steps = { a: 5, b: 4 };
    expect(snapStepM("off", steps)).toBe(0);
    expect(snapStepM("0.1", steps)).toBe(0.1);
    expect(snapStepM("a4", steps)).toBe(1.25);
    expect(snapStepM("b4", steps)).toBe(1);
  });
});

describe("layoutAxes", () => {
  it("вдоль ряда — по азимуту рядов, поперёк — к откосу", () => {
    const axes = layoutAxes(90, rectContour());
    expect(axes.along.x).toBeCloseTo(1);
    expect(axes.along.y).toBeCloseTo(0);
    // Откос на юге: ось «к откосу» смотрит на −Y.
    expect(axes.across.x).toBeCloseTo(0);
    expect(axes.across.y).toBeCloseTo(-1);
    expect(axes.towardFace).toBe(true);
  });

  it("азимут 30°: вдоль = (sin 30°, cos 30°)", () => {
    const axes = layoutAxes(30, rectContour());
    expect(axes.along.x).toBeCloseTo(0.5);
    expect(axes.along.y).toBeCloseTo(Math.sqrt(3) / 2);
    expect(axes.along.x * axes.across.x + axes.along.y * axes.across.y).toBeCloseTo(0);
    expect(axes.across.y).toBeLessThan(0);
  });

  it("без свободных поверхностей — просто поперёк", () => {
    const axes = layoutAxes(0, rectContour([]));
    expect(axes.towardFace).toBe(false);
    expect(Math.hypot(axes.across.x, axes.across.y)).toBeCloseTo(1);
  });

  it("toAxes и fromAxes взаимно обратны", () => {
    const axes = layoutAxes(30, rectContour());
    const back = fromAxes(1.25, -2, axes);
    const parts = toAxes(back, axes);
    expect(parts.along).toBeCloseTo(1.25);
    expect(parts.across).toBeCloseTo(-2);
  });
});

describe("dragDelta", () => {
  const axes = layoutAxes(30, rectContour());

  it("привязка a/4 вдоль и b/4 поперёк — по осям сетки, а не X/Y", () => {
    const raw = fromAxes(1.4, 0.7, axes);
    const delta = dragDelta(raw, axes, { lockAxis: false, stepAlong: 1.25, stepAcross: 1 });
    const parts = toAxes(delta, axes);
    expect(parts.along).toBeCloseTo(1.25, 2);
    expect(parts.across).toBeCloseTo(1, 2);
  });

  it("Shift — только по преобладающей оси раскладки", () => {
    const raw = fromAxes(0.4, 2.3, axes);
    const delta = dragDelta(raw, axes, { lockAxis: true, stepAlong: 0, stepAcross: 0 });
    const parts = toAxes(delta, axes);
    expect(parts.along).toBeCloseTo(0, 3);
    expect(parts.across).toBeCloseTo(2.3, 2);
  });

  it("без привязки — сдвиг как есть, до миллиметра", () => {
    const delta = dragDelta({ x: 0.12345, y: -0.5 }, axes, { lockAxis: false, stepAlong: 0, stepAcross: 0 });
    expect(delta).toEqual({ x: 0.123, y: -0.5 });
  });
});

describe("arrowDelta", () => {
  it("стрелка идёт по оси сетки, ближней к её направлению на экране", () => {
    const axes = layoutAxes(30, rectContour());
    const steps = { along: 1.25, across: 1 };
    const up = toAxes(arrowDelta("ArrowUp", axes, steps), axes);
    expect(up.along).toBeCloseTo(1.25, 2);
    expect(up.across).toBeCloseTo(0, 3);
    const right = toAxes(arrowDelta("ArrowRight", axes, steps), axes);
    // +X ближе к оси «поперёк» (≈ (0,87; −0,5)), чем к «вдоль» (0,5; 0,87).
    expect(Math.abs(right.across)).toBeCloseTo(1, 2);
    expect(right.along).toBeCloseTo(0, 3);
    const down = toAxes(arrowDelta("ArrowDown", axes, steps), axes);
    expect(down.along).toBeCloseTo(-1.25, 2);
  });
});

describe("withFacePairs", () => {
  const holes = [hole("4-01"), hole("4-01T", "face_toe"), hole("4-02")];

  it("вертикальная тянет свою пару у откоса", () => {
    expect(withFacePairs(["4-01"], holes)).toEqual(["4-01", "4-01T"]);
  });

  it("пару можно двигать одну", () => {
    expect(withFacePairs(["4-01T"], holes)).toEqual(["4-01T"]);
  });

  it("скважина без пары — как есть, без повторов", () => {
    expect(withFacePairs(["4-02", "4-01", "4-01T"], holes)).toEqual(["4-02", "4-01", "4-01T"]);
  });
});

describe("layoutAxes и сервер (TASK-017, PR 2)", () => {
  // Смещение от узла сетки хранится в осях раскладки: оси клиента и
  // `design/geometry.py::layout_axes` должны совпадать.
  type AxesCase = { name: string; contour: BlockContour; row_azimuth_deg: number; along: number[]; across: number[] };
  for (const item of (liveFixture as unknown as { axes: AxesCase[] }).axes) {
    it(`оси совпадают с серверными: ${item.name}`, () => {
      const axes = layoutAxes(item.row_azimuth_deg, item.contour);
      expect(axes.along.x).toBeCloseTo(item.along[0], 9);
      expect(axes.along.y).toBeCloseTo(item.along[1], 9);
      expect(axes.across.x).toBeCloseTo(item.across[0], 9);
      expect(axes.across.y).toBeCloseTo(item.across[1], 9);
    });
  }
});

describe("returnToNodeIds", () => {
  const moved = (id: string): Hole =>
    ({ id, kind: "production", source: "generated", manual: ["xy"], manual_offset: { node_x: 0, node_y: 0, along: 1, across: 0 } }) as Hole;
  const plain = (id: string): Hole => ({ id, kind: "production", source: "generated" }) as Hole;
  const holes = [moved("1-01"), moved("1-02"), plain("1-03")];

  it("скважина в выделении — все сдвинутые из выделения", () => {
    expect(returnToNodeIds("1-03", new Set(["1-01", "1-02", "1-03"]), holes)).toEqual(["1-01", "1-02"]);
  });

  it("скважина вне выделения — только она, если сдвинута", () => {
    expect(returnToNodeIds("1-02", new Set(["1-01"]), holes)).toEqual(["1-02"]);
    expect(returnToNodeIds("1-03", new Set(["1-01"]), holes)).toEqual([]);
  });
});
