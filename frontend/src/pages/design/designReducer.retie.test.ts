// Пересчёт коммутации после сдвига (TASK-017, PR 3): пометка сети и
// применение ответа к тому документу, по которому он спрошен.
import { describe, expect, it } from "vitest";
import { emptyDesign, emptyNetwork, type BlastDesign, type Hole, type InitiationNetwork } from "../../types/design";
import { designReducer, initDesignState, type DesignState } from "./designReducer";
import { isGeometryStale } from "./retie";

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

const TEMPLATE: InitiationNetwork = {
  ...emptyNetwork(),
  starters: ["1-01"],
  connectors: [{ from_hole: "1-01", to_hole: "1-02", delay_ms: 25, kind: "surface_nsi" }],
  timing_params: { scheme: "trunk_chains", origin: "template", trunk_ms: 25 },
};

const REBUILT: InitiationNetwork = {
  ...emptyNetwork(),
  starters: ["1-02"],
  connectors: [{ from_hole: "1-02", to_hole: "1-01", delay_ms: 25, kind: "surface_nsi" }],
  timing_params: { scheme: "trunk_chains", origin: "template", trunk_ms: 25 },
};

function start(network: InitiationNetwork = TEMPLATE): DesignState {
  const design: BlastDesign = { ...emptyDesign(), design_id: "a", holes: [hole("1-01", 10, 20), hole("1-02", 15, 20)], network };
  return initDesignState(design);
}

function move(state: DesignState): DesignState {
  return designReducer(state, { type: "MOVE_HOLES", ids: ["1-01"], dx: 1, dy: 0 });
}

describe("пометка «устарела по геометрии»", () => {
  it("сдвиг при непустой сети помечает её в той же записи отмены", () => {
    const moved = move(start());
    expect(isGeometryStale(moved.present.network)).toBe(true);
    expect(moved.past).toHaveLength(1);
    expect(isGeometryStale(moved.past[0].network)).toBe(false);
  });

  it("сдвиг при пустой сети пометки не ставит", () => {
    const moved = move(start(emptyNetwork()));
    expect(isGeometryStale(moved.present.network)).toBe(false);
  });

  it("«Вернуть в узел» — тоже сдвиг", () => {
    const moved = move(start());
    const fresh = designReducer(moved, { type: "RETIE_NETWORK", network: REBUILT, base: moved.present, merge: true });
    const back = designReducer(fresh, { type: "RETURN_TO_NODE", ids: ["1-01"] });
    expect(isGeometryStale(back.present.network)).toBe(true);
  });
});

describe("RETIE_NETWORK", () => {
  it("автопересчёт вливается в запись сдвига: одна отмена возвращает скважины и сеть", () => {
    const moved = move(start());
    const retied = designReducer(moved, { type: "RETIE_NETWORK", network: REBUILT, base: moved.present, merge: true });
    expect(retied.past).toHaveLength(1);
    expect(retied.present.network.starters).toEqual(["1-02"]);
    expect(retied.present.holes[0].collar.x).toBe(11);
    const undone = designReducer(retied, { type: "UNDO" });
    expect(undone.present.holes[0].collar.x).toBe(10);
    expect(undone.present.network).toEqual(TEMPLATE);
    const redone = designReducer(undone, { type: "REDO" });
    expect(redone.present.holes[0].collar.x).toBe(11);
    expect(redone.present.network.starters).toEqual(["1-02"]);
  });

  it("документ сменился после запроса — ответ отбрасывается", () => {
    const moved = move(start());
    const again = move(moved);
    const retied = designReducer(again, { type: "RETIE_NETWORK", network: REBUILT, base: moved.present, merge: true });
    expect(retied).toBe(again);
    const undone = designReducer(moved, { type: "UNDO" });
    expect(designReducer(undone, { type: "RETIE_NETWORK", network: REBUILT, base: moved.present, merge: true })).toBe(undone);
  });

  it("ручной пересчёт — своя запись отмены", () => {
    const moved = move(start());
    const retied = designReducer(moved, { type: "RETIE_NETWORK", network: REBUILT, base: moved.present, merge: false });
    expect(retied.past).toHaveLength(2);
    const undone = designReducer(retied, { type: "UNDO" });
    expect(undone.present.holes[0].collar.x).toBe(11);
    expect(isGeometryStale(undone.present.network)).toBe(true);
  });
});

describe("autoRetie: когда пересчитывать самим", () => {
  it("сдвиг сети шаблона ставит отметку на новый документ; стрелки — с серией", () => {
    const moved = move(start());
    expect(moved.autoRetie).toEqual({ present: moved.present, series: false });
    const pressed = designReducer(start(), { type: "MOVE_HOLES", ids: ["1-01"], dx: 1, dy: 0, series: 1000 });
    expect(pressed.autoRetie?.series).toBe(true);
  });

  it("правленая сеть, сеть до PR 3 и пустая — без отметки", () => {
    const edited = { ...TEMPLATE, timing_params: { ...TEMPLATE.timing_params, origin: "edited" } };
    expect(move(start(edited)).autoRetie).toBeUndefined();
    const old = { ...TEMPLATE, timing_params: { scheme: "trunk_chains", trunk_ms: 25 } };
    expect(move(start(old)).autoRetie).toBeUndefined();
    expect(move(start(emptyNetwork())).autoRetie).toBeUndefined();
  });

  it("пересчёт по кровле отметку переносит, правка пользователя — нет", () => {
    const moved = move(start());
    const lifted = designReducer(moved, {
      type: "RECOMPUTE_HOLES",
      holes: moved.present.holes.map((h) => ({ ...h, collar: { ...h.collar, z: 5 } })),
    });
    expect(lifted.autoRetie?.present).toBe(lifted.present);
    const renamed = designReducer(moved, { type: "SET_NAME", name: "Б" });
    expect(renamed.autoRetie?.present).not.toBe(renamed.present);
  });

  it("загрузка паспорта с уже помеченной сетью отметки не ставит", () => {
    const moved = move(start());
    const loaded = designReducer(moved, { type: "LOAD", design: moved.present });
    expect(loaded.autoRetie).toBeUndefined();
  });
});
