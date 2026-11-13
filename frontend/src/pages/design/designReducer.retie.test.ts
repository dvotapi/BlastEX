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

describe("autoRetie и сохранение", () => {
  it("сохранение сразу после сдвига отметку не теряет", () => {
    const moved = move(start());
    const saved = designReducer(moved, { type: "SAVED", design: { ...moved.present, version: 2 } });
    expect(saved.autoRetie?.present).toBe(saved.present);
  });

  it("сохранение без сдвига отметки не даёт", () => {
    const saved = designReducer(start(), { type: "SAVED", design: { ...start().present, version: 2 } });
    expect(saved.autoRetie).toBeUndefined();
  });
});

// TASK-017, PR 5: набор скважин сменился — сеть тоже устарела (решение владельца
// 14.11.2026: «как после сдвига»).
describe("устаревание от набора скважин", () => {
  const THREE: InitiationNetwork = {
    ...TEMPLATE,
    connectors: [
      { from_hole: "1-01", to_hole: "1-02", delay_ms: 25, kind: "surface_nsi" },
      { from_hole: "1-02", to_hole: "1-03", delay_ms: 25, kind: "surface_nsi" },
    ],
  };

  function three(network: InitiationNetwork = THREE): DesignState {
    const design: BlastDesign = {
      ...emptyDesign(),
      design_id: "a",
      holes: [hole("1-01", 10, 20), hole("1-02", 15, 20), hole("1-03", 20, 20)],
      network,
    };
    return initDesignState(design);
  }

  const actions: [string, (state: DesignState) => DesignState][] = [
    ["добавление", (s) => designReducer(s, { type: "ADD_HOLE", hole: hole("M-1", 30, 20) })],
    ["удаление", (s) => designReducer(s, { type: "DELETE_HOLES", ids: ["1-03"] })],
    ["исключение", (s) => designReducer(s, { type: "SET_HOLES_ENABLED", ids: ["1-02"], enabled: false })],
    ["смена вида", (s) => designReducer(s, { type: "UPDATE_HOLE", id: "1-02", patch: { kind: "contour" } })],
  ];

  for (const [name, act] of actions) {
    it(`${name}: сеть шаблона помечена и пересчитается сама в той же записи отмены`, () => {
      const next = act(three());
      expect(isGeometryStale(next.present.network)).toBe(true);
      expect(next.past).toHaveLength(1);
      expect(isGeometryStale(next.past[0].network)).toBe(false);
      expect(next.autoRetie).toEqual({ present: next.present, series: false });
    });

    it(`${name}: правленая сеть — только пометка`, () => {
      const edited = { ...THREE, timing_params: { ...THREE.timing_params, origin: "edited" } };
      const next = act(three(edited));
      expect(isGeometryStale(next.present.network)).toBe(true);
      expect(next.autoRetie).toBeUndefined();
    });

    it(`${name}: пустая сеть пометки не получает`, () => {
      const next = act(three(emptyNetwork()));
      expect(isGeometryStale(next.present.network)).toBe(false);
      expect(next.autoRetie).toBeUndefined();
    });
  }

  it("исключение уже исключённой и правка без смены вида — без пометки", () => {
    const off = designReducer(three(), { type: "SET_HOLES_ENABLED", ids: ["1-02"], enabled: false });
    const fresh = designReducer(off, { type: "RETIE_NETWORK", network: THREE, base: off.present, merge: true });
    const again = designReducer(fresh, { type: "SET_HOLES_ENABLED", ids: ["1-02"], enabled: false });
    expect(isGeometryStale(again.present.network)).toBe(false);
    expect(again.autoRetie?.present).not.toBe(again.present);
    const widened = designReducer(three(), { type: "UPDATE_HOLE", id: "1-02", patch: { diameter_mm: 200 } });
    expect(isGeometryStale(widened.present.network)).toBe(false);
    const sameKind = designReducer(three(), { type: "UPDATE_HOLE", id: "1-02", patch: { kind: "production" } });
    expect(isGeometryStale(sameKind.present.network)).toBe(false);
  });

  it("исключить и включить снова — оба раза пересчёт", () => {
    const off = designReducer(three(), { type: "SET_HOLES_ENABLED", ids: ["1-02"], enabled: false });
    const fresh = designReducer(off, { type: "RETIE_NETWORK", network: THREE, base: off.present, merge: true });
    const on = designReducer(fresh, { type: "SET_HOLES_ENABLED", ids: ["1-02"], enabled: true });
    expect(isGeometryStale(on.present.network)).toBe(true);
    expect(on.autoRetie?.present).toBe(on.present);
    expect(on.past).toHaveLength(2);
  });

  it("удаление, после которого в сети ничего нет, — без пометки", () => {
    const pair: InitiationNetwork = { ...TEMPLATE, starters: ["1-01"] };
    const next = designReducer(start(pair), { type: "DELETE_HOLES", ids: ["1-01"] });
    expect(isGeometryStale(next.present.network)).toBe(false);
    expect(next.autoRetie).toBeUndefined();
  });

  it("автопересчёт после добавления вливается в его запись: одна отмена убирает скважину и сеть", () => {
    const added = designReducer(three(), { type: "ADD_HOLE", hole: hole("M-1", 30, 20) });
    const retied = designReducer(added, { type: "RETIE_NETWORK", network: REBUILT, base: added.present, merge: true });
    expect(retied.past).toHaveLength(1);
    const undone = designReducer(retied, { type: "UNDO" });
    expect(undone.present.holes).toHaveLength(3);
    expect(undone.present.network).toEqual(THREE);
  });
});
