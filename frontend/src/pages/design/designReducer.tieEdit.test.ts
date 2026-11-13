// Правка коммутации на плане (TASK-017, PR 4): протяжка цепочки — одна запись
// отмены, правленая сеть после сдвига сама не пересчитывается.
import { describe, expect, it } from "vitest";
import { emptyDesign, emptyNetwork, networkTies, type BlastDesign, type InitiationNetwork } from "../../types/design";
import { designReducer, initDesignState } from "./designReducer";
import { addTies } from "./tieEdits";

const TEMPLATE: InitiationNetwork = {
  ...emptyNetwork(),
  starters: ["a"],
  timing_params: { scheme: "trunk_chains", origin: "template", trunk_ms: 25 },
};

describe("правка связей и история", () => {
  it("протяжка через 4 скважины — одна запись отмены", () => {
    const design: BlastDesign = { ...emptyDesign(), design_id: "x", network: TEMPLATE };
    const state = initDesignState(design);
    const edit = addTies(state.present.network, ["a", "b", "c", "d"], 17);
    const next = designReducer(state, { type: "SET_NETWORK", network: edit.network });
    expect(networkTies(next.present.network)).toHaveLength(3);
    expect(next.past).toHaveLength(1);
    const undone = designReducer(next, { type: "UNDO" });
    expect(undone.present.network).toBe(state.present.network);
  });
});
