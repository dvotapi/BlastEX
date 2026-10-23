// Предупреждения построения схемы принадлежат построенной сети: после другой
// сети (новое построение, отмена, правка связей) они скрыты, а анализ,
// дописавший в сеть времена срабатывания, их не скрывает.
import { describe, expect, it } from "vitest";
import { emptyDesign, normalizeNetwork, type InitiationNetwork } from "../../types/design";
import { designReducer, initDesignState } from "./designReducer";
import { tieWarningsFor, withTieWarnings } from "./tieWarnings";

function built(starter: string): InitiationNetwork {
  return normalizeNetwork({
    system: "nonel",
    starters: [starter],
    connectors: [{ from_hole: starter, to_hole: "2", delay_ms: 25, kind: "nonel_surface" }],
    timing_params: { scheme: "trunk_chains", downhole_delay_ms: 1000 },
  } as Partial<InitiationNetwork>);
}

const WARNINGS = ["Фронт инициирования отстаёт: в радиусе 30 м импульс не успевает до взрыва скважины — возможен подбой."];

describe("tieWarningsFor", () => {
  it("показывает предупреждения, пока в документе сеть, для которой они получены", () => {
    const network = built("1");
    const state = designReducer(initDesignState(emptyDesign()), { type: "SET_NETWORK", network });
    const stored = withTieWarnings(network, WARNINGS);
    expect(tieWarningsFor(stored, state.present.network)).toEqual(WARNINGS);
  });

  it("скрывает их после построения другой сети", () => {
    const first = built("1");
    const stored = withTieWarnings(first, WARNINGS);
    let state = designReducer(initDesignState(emptyDesign()), { type: "SET_NETWORK", network: first });
    state = designReducer(state, { type: "SET_NETWORK", network: built("3") });
    expect(tieWarningsFor(stored, state.present.network)).toEqual([]);
  });

  it("скрывает их после отмены и показывает снова после повтора", () => {
    const network = built("1");
    const stored = withTieWarnings(network, WARNINGS);
    let state = designReducer(initDesignState(emptyDesign()), { type: "SET_NETWORK", network });
    state = designReducer(state, { type: "UNDO" });
    expect(tieWarningsFor(stored, state.present.network)).toEqual([]);
    state = designReducer(state, { type: "REDO" });
    expect(tieWarningsFor(stored, state.present.network)).toEqual(WARNINGS);
  });

  it("не скрывает их, когда анализ дописал в сеть времена срабатывания", () => {
    const network = built("1");
    const stored = withTieWarnings(network, WARNINGS);
    let state = designReducer(initDesignState(emptyDesign()), { type: "SET_NETWORK", network });
    state = designReducer(state, {
      type: "SET_NETWORK",
      network: { ...normalizeNetwork(state.present.network), firing_events: [{ hole_id: "1", time_ms: 1000 }] } as InitiationNetwork,
    });
    expect(tieWarningsFor(stored, state.present.network)).toEqual(WARNINGS);
  });

  it("без построения предупреждений нет", () => {
    expect(tieWarningsFor(null, built("1"))).toEqual([]);
  });
});
