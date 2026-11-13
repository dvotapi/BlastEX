// Пометка сдвига (TASK-017, PR 2): сдвинутая скважина сетки помнит узел и
// смещение от него в осях раскладки; «Вернуть в узел сетки» снимает сдвиг.
import { describe, expect, it } from "vitest";
import { emptyDesign, type BlastDesign, type Hole } from "../../types/design";
import { designReducer, initDesignState, type DesignState } from "./designReducer";
import { isMovedHole, layoutAxes, type LayoutAxes } from "./holeMove";

function hole(id: string, x: number, y: number, extra: Partial<Hole> = {}): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x, y, z: 0 },
    toe: { x, y, z: -11 },
    diameter_mm: 165,
    subdrill_m: 1,
    kind: "production",
    source: "generated",
    enabled: true,
    intervals: [],
    water_intervals: [],
    measured_intervals: [],
    measured_water_intervals: [],
    ...extra,
  };
}

// Откос — юг, ряды — с запада на восток: «вдоль» — восток, «к откосу» — юг.
const contour: BlastDesign["contour"] = {
  vertices: [
    { x: 0, y: 0, z: 0 },
    { x: 40, y: 0, z: 0 },
    { x: 40, y: 30, z: 0 },
    { x: 0, y: 30, z: 0 },
  ],
  free_faces: [[0, 1]],
  bench: { crest_z_m: 0, toe_z_m: -10, face_angle_deg: 75 },
  name: "Блок",
};
const axes: LayoutAxes = layoutAxes(90, contour);

function start(holes: Hole[] = [hole("1-01", 10, 20), hole("M-1", 15, 20, { source: "manual" })]): DesignState {
  const design: BlastDesign = { ...emptyDesign(), design_id: "a", contour, holes };
  return initDesignState(design);
}

function move(state: DesignState, ids: string[], dx: number, dy: number, series?: number): DesignState {
  return designReducer(state, { type: "MOVE_HOLES", ids, dx, dy, axes, ...(series !== undefined ? { series } : {}) });
}

describe("MOVE_HOLES: пометка сдвига", () => {
  it("первый сдвиг ставит xy и узел — устье до сдвига", () => {
    const state = move(start(), ["1-01"], 0.75, 0.5);
    const moved = state.present.holes[0];
    expect(moved.manual).toEqual(["xy"]);
    // На восток 0,75 — вдоль; на север 0,5 — от откоса: −0,5 к откосу.
    expect(moved.manual_offset).toEqual({ node_x: 10, node_y: 20, along: 0.75, across: -0.5 });
    expect(isMovedHole(moved)).toBe(true);
    expect(moved.source).toBe("generated");
  });

  it("повторный сдвиг копит смещение, узел прежний", () => {
    const state = move(move(start(), ["1-01"], 0.75, 0), ["1-01"], 0.5, -1);
    expect(state.present.holes[0].manual_offset).toEqual({ node_x: 10, node_y: 20, along: 1.25, across: 1 });
  });

  it("сдвиг туда и обратно снимает пометку", () => {
    const state = move(move(start(), ["1-01"], 0.75, 0.5), ["1-01"], -0.75, -0.5);
    const back = state.present.holes[0];
    expect(back.collar.x).toBeCloseTo(10);
    expect(isMovedHole(back)).toBe(false);
    expect(back.manual ?? []).toEqual([]);
    expect("manual_offset" in back).toBe(false);
  });

  it("ручная скважина пометки не получает", () => {
    const state = move(start(), ["M-1"], 1, 0);
    const manual = state.present.holes[1];
    expect(manual.collar.x).toBe(16);
    expect(manual.manual ?? []).toEqual([]);
    expect(manual.manual_offset ?? null).toBeNull();
  });

  it("прочие ручные пометки остаются", () => {
    const state = move(start([hole("1-01", 10, 20, { manual: ["collar_z"] })]), ["1-01"], 1, 0);
    expect(state.present.holes[0].manual).toEqual(["collar_z", "xy"]);
  });

  it("серия стрелок — одна запись отмены и одно накопленное смещение", () => {
    const state = move(move(start(), ["1-01"], 0.5, 0, 1000), ["1-01"], 0.5, 0, 1300);
    expect(state.past).toHaveLength(1);
    expect(state.present.holes[0].manual_offset?.along).toBe(1);
  });

  it("без осей в действии — оси по параметрам паспорта", () => {
    const base = start();
    const withParams = { ...base, present: { ...base.present, pattern_params: { row_azimuth_deg: 90 } } };
    const state = designReducer(withParams, { type: "MOVE_HOLES", ids: ["1-01"], dx: 1, dy: 0 });
    expect(state.present.holes[0].manual_offset).toEqual({ node_x: 10, node_y: 20, along: 1, across: 0 });
  });
});

describe("RETURN_TO_NODE", () => {
  it("ставит в узел, снимает пометку, одна запись отмены", () => {
    const moved = move(move(start([hole("1-01", 10, 20), hole("1-02", 15, 20)]), ["1-01"], 1, 0.5), ["1-02"], -1, 0);
    const state = designReducer(moved, { type: "RETURN_TO_NODE", ids: ["1-01", "1-02"] });
    expect(state.past).toHaveLength(moved.past.length + 1);
    for (const [index, x] of [[0, 10], [1, 15]] as const) {
      const back = state.present.holes[index];
      expect(back.collar.x).toBeCloseTo(x);
      expect(back.collar.y).toBeCloseTo(20);
      expect(back.toe.x).toBeCloseTo(x);
      expect(isMovedHole(back)).toBe(false);
      expect("manual_offset" in back).toBe(false);
    }
    const undone = designReducer(state, { type: "UNDO" });
    expect(isMovedHole(undone.present.holes[0])).toBe(true);
  });

  it("несдвинутые не трогает; нечего возвращать — записи нет", () => {
    const state = designReducer(start(), { type: "RETURN_TO_NODE", ids: ["1-01", "M-1"] });
    expect(state.past).toHaveLength(0);
  });
});

describe("APPLY_LAYOUT и сдвиги", () => {
  it("применение варианта сбрасывает сдвиги, отмена их возвращает", () => {
    const moved = move(start(), ["1-01"], 1, 0);
    const applied = designReducer(moved, {
      type: "APPLY_LAYOUT",
      holes: [hole("1-01", 12, 20)],
      network: moved.present.network,
      pattern_params: { row_azimuth_deg: 90 },
    });
    expect(applied.present.holes.some(isMovedHole)).toBe(false);
    const undone = designReducer(applied, { type: "UNDO" });
    expect(isMovedHole(undone.present.holes[0])).toBe(true);
  });
});
