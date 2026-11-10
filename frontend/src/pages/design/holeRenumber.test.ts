// Перенумерация скважин по правилу эшелонов (доработки 10.11.2026): номера
// меняются одним шагом отмены, а заряды, сеть и исполнение остаются при своих
// скважинах.
import { describe, expect, it } from "vitest";
import { emptyDesign, emptyNetwork, type BlastDesign, type Hole } from "../../types/design";
import { designReducer, initDesignState } from "./designReducer";
import { renameHoleIds } from "./holeRenumber";

function hole(id: string, x: number): Hole {
  return {
    ...(emptyDesign().holes[0] ?? {}),
    id, row: 0, col: 0, collar: { x, y: 0, z: 410 }, toe: { x, y: 0, z: 400 }, diameter_mm: 140, subdrill_m: 1,
    kind: "production", source: "generated", enabled: true, intervals: [], water_intervals: [],
  } as Hole;
}

function design(): BlastDesign {
  const network = emptyNetwork();
  return {
    ...emptyDesign(),
    design_id: "b67",
    holes: [hole("5-08", 0), hole("5-09", 4), hole("5-08T", 1)],
    loads: [{ hole_id: "5-08", decks: [] } as never, { hole_id: "5-09", decks: [] } as never],
    network: {
      ...network,
      starters: ["5-08"],
      connectors: [{ from_hole: "5-08", to_hole: "5-09", delay_ms: 42, kind: "surface_nsi" }],
      downhole_delay_ms: { "5-08": 500, "5-09": 500 },
      electronic_times_ms: { "5-09": 25 },
      detonators: [
        { id: "det-5-08", hole_id: "5-08", delay_ms: 500, product: "", kind: "nonel", deck_index: null, primer_index: null, channel_id: "ch-5-08" },
      ],
      surface_connectors: [{ id: "sc-5-08-5-09", from_hole: "5-08", to_hole: "5-09", delay_ms: 42, kind: "surface_nsi", product: "" }],
      downhole_connectors: [{ id: "dh-5-09", hole_id: "5-09", delay_ms: 500, kind: "downhole_nsi", deck_index: null, primer_index: null, product: "" }],
      detonating_cords: [{ id: "cord-1", hole_ids: ["5-08", "5-09"], velocity_m_s: 6500, relay_delay_ms: 0, product: "" }],
      starter_items: [{ id: "st-5-08", hole_id: "5-08", delay_ms: 0, kind: "" }],
      electronic_channels: [{ id: "ch-5-08", hole_id: "5-08", time_ms: 0, deck_index: null, primer_index: null, label: "" }],
      firing_events: [
        { id: "fire-5-09-d1", hole_id: "5-09", time_ms: 542, level: "deck", deck_index: 1, primer_index: null, mass_kg: 10 },
      ],
      selected_hole_ids: ["5-09"],
    },
    as_drilled_holes: [{ design_hole_id: "5-08" } as never],
    as_charged_holes: [{ design_hole_id: "5-09" } as never],
    as_fired_holes: [{ design_hole_id: "5-08", detonator: { id: "det-5-08", hole_id: "5-08" } } as never],
  };
}

// Перестановка: «5-08» и «5-09» меняются номерами, пара — за своей вертикальной.
const SWAP = { "5-08": "5-09", "5-09": "5-08", "5-08T": "5-09T" };

describe("renameHoleIds", () => {
  it("перестановка номеров — без каскада", () => {
    const renamed = renameHoleIds(design(), SWAP);
    expect(renamed.holes.map((h) => [h.id, h.collar.x])).toEqual([["5-09", 0], ["5-08", 4], ["5-09T", 1]]);
  });

  it("заряды, сеть и исполнение — у тех же скважин под новыми номерами", () => {
    const { loads, network, as_drilled_holes, as_charged_holes, as_fired_holes } = renameHoleIds(design(), SWAP);
    expect(loads.map((ld) => ld.hole_id)).toEqual(["5-09", "5-08"]);
    expect(network.starters).toEqual(["5-09"]);
    expect(network.connectors[0]).toMatchObject({ from_hole: "5-09", to_hole: "5-08" });
    expect(network.downhole_delay_ms).toEqual({ "5-09": 500, "5-08": 500 });
    expect(network.electronic_times_ms).toEqual({ "5-08": 25 });
    expect(network.detonators[0]).toMatchObject({ id: "det-5-09", hole_id: "5-09", channel_id: "ch-5-09" });
    expect(network.surface_connectors[0]).toMatchObject({ id: "sc-5-09-5-08", from_hole: "5-09", to_hole: "5-08" });
    expect(network.downhole_connectors[0]).toMatchObject({ id: "dh-5-08", hole_id: "5-08" });
    expect(network.detonating_cords[0].hole_ids).toEqual(["5-09", "5-08"]);
    expect(network.starter_items[0]).toMatchObject({ id: "st-5-09", hole_id: "5-09" });
    expect(network.electronic_channels[0]).toMatchObject({ id: "ch-5-09", hole_id: "5-09" });
    expect(network.firing_events[0]).toMatchObject({ id: "fire-5-08-d1", hole_id: "5-08" });
    expect(network.selected_hole_ids).toEqual(["5-08"]);
    expect(as_drilled_holes[0].design_hole_id).toBe("5-09");
    expect(as_charged_holes[0].design_hole_id).toBe("5-08");
    expect(as_fired_holes[0]).toMatchObject({ design_hole_id: "5-09", detonator: { id: "det-5-09", hole_id: "5-09" } });
  });

  it("пустое соответствие — документ без изменений", () => {
    const doc = design();
    expect(renameHoleIds(doc, {})).toBe(doc);
  });
});

describe("RENUMBER_HOLES", () => {
  it("один шаг отмены возвращает прежние номера", () => {
    const state = initDesignState(design());
    const renumbered = designReducer(state, { type: "RENUMBER_HOLES", mapping: SWAP });
    expect(renumbered.present.holes[0].id).toBe("5-09");
    const undone = designReducer(renumbered, { type: "UNDO" });
    expect(undone.present.holes[0].id).toBe("5-08");
    expect(undone.present.network.starters).toEqual(["5-08"]);
  });
});
