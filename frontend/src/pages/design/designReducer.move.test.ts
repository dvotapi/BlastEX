// Сдвиг скважин стрелками (TASK-017, PR 1): серия нажатий без паузы больше
// 1 с и без другого действия между ними — одна запись отмены.
import { describe, expect, it } from "vitest";
import { emptyDesign, type BlastDesign, type Hole } from "../../types/design";
import { designReducer, initDesignState, MOVE_SERIES_GAP_MS, type DesignState } from "./designReducer";

function hole(id: string, x: number, y: number): Hole {
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
  };
}

function start(): DesignState {
  const design: BlastDesign = { ...emptyDesign(), design_id: "a", holes: [hole("1-01", 10, 20), hole("1-02", 15, 20)] };
  return initDesignState(design);
}

function press(state: DesignState, at: number, dx = 0.5): DesignState {
  return designReducer(state, { type: "MOVE_HOLES", ids: ["1-01"], dx, dy: 0, series: at });
}

describe("MOVE_HOLES: серия стрелок", () => {
  it("три нажатия подряд — одна запись отмены", () => {
    const state = press(press(press(start(), 1000), 1300), 1600);
    expect(state.past).toHaveLength(1);
    expect(state.present.holes[0].collar.x).toBeCloseTo(11.5);
    const undone = designReducer(state, { type: "UNDO" });
    expect(undone.present.holes[0].collar.x).toBe(10);
    expect(undone.past).toHaveLength(0);
  });

  it("пауза больше 1 с — новая запись", () => {
    const state = press(press(start(), 1000), 1000 + MOVE_SERIES_GAP_MS + 500);
    expect(state.past).toHaveLength(2);
  });

  it("другое действие между нажатиями рвёт серию", () => {
    const renamed = designReducer(press(start(), 1000), { type: "SET_NAME", name: "Блок 7" });
    const state = press(renamed, 1200);
    expect(state.past).toHaveLength(3);
    const undone = designReducer(state, { type: "UNDO" });
    expect(undone.present.name).toBe("Блок 7");
    expect(undone.present.holes[0].collar.x).toBeCloseTo(10.5);
  });

  it("отмена посреди серии — следующее нажатие начинает новую", () => {
    const undone = designReducer(press(start(), 1000), { type: "UNDO" });
    const state = press(undone, 1100);
    expect(state.past).toHaveLength(1);
    expect(state.present.holes[0].collar.x).toBeCloseTo(10.5);
  });

  it("автоматический пересчёт по кровле между нажатиями серию не рвёт", () => {
    const first = press(start(), 1000);
    const moved = first.present.holes[0];
    const recomputed = designReducer(first, {
      type: "RECOMPUTE_HOLES",
      holes: [{ ...moved, collar: { ...moved.collar, z: 1.5 }, toe: { ...moved.toe, z: -9.5 } }],
    });
    expect(recomputed.present).not.toBe(first.present);
    const state = press(recomputed, 1300);
    expect(state.past).toHaveLength(1);
    expect(designReducer(state, { type: "UNDO" }).present.holes[0].collar.x).toBe(10);
  });

  it("сдвиг мышью (без series) — всегда своя запись", () => {
    let state = start();
    state = designReducer(state, { type: "MOVE_HOLES", ids: ["1-01"], dx: 1, dy: 0 });
    state = designReducer(state, { type: "MOVE_HOLES", ids: ["1-01"], dx: 1, dy: 0 });
    expect(state.past).toHaveLength(2);
  });

  it("стрелка сразу после сдвига мышью — новая запись", () => {
    let state = designReducer(start(), { type: "MOVE_HOLES", ids: ["1-01"], dx: 1, dy: 0 });
    state = press(state, 1000);
    expect(state.past).toHaveLength(2);
  });
});
