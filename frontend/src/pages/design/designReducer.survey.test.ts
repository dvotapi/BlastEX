// «Применить съёмку» (TASK-014, PR 5а): одно действие, один шаг отмены.
import { describe, expect, it } from "vitest";
import {
  emptyAsDrilled,
  emptyDesign,
  emptyHoleGeology,
  emptyNetwork,
  type AsFiredHole,
  type Hole,
  type HoleLoad,
  type InitiationNetwork,
  type SurveyApplication,
} from "../../types/design";
import { designReducer, initDesignState } from "./designReducer";

function hole(id: string, x = 10): Hole {
  return {
    id,
    row: 0,
    col: 0,
    collar: { x, y: 5, z: 420 },
    toe: { x, y: 5, z: 408 },
    diameter_mm: 152,
    subdrill_m: 1,
    kind: "production",
    source: "generated",
    enabled: true,
    ...emptyHoleGeology(),
  };
}

const NETWORK: InitiationNetwork = {
  ...emptyNetwork(),
  starters: ["a"],
  connectors: [{ id: "c1", from_hole: "a", to_hole: "b", delay_ms: 42, kind: "surface" } as InitiationNetwork["connectors"][number]],
};
const TEMPLATE_NETWORK: InitiationNetwork = {
  ...NETWORK,
  timing_params: { origin: "template", scheme: "trunk_chains" },
} as InitiationNetwork;

const APPLICATION = { survey_date: "2026-11-14" } as SurveyApplication;

function base(network: InitiationNetwork = NETWORK) {
  return {
    ...emptyDesign(),
    holes: [hole("a"), hole("b", 14)],
    loads: [{ hole_id: "a" } as HoleLoad],
    as_fired_holes: [{ design_hole_id: "a" } as AsFiredHole],
    pattern_params: { spacing_a_m: 4 },
    network,
  };
}

function apply(before: ReturnType<typeof base>, changed: string[], loads: HoleLoad[] | null = null) {
  return designReducer(initDesignState(before), {
    type: "APPLY_SURVEY",
    holes: [hole("a", 10.5), hole("b", 14)],
    loads,
    as_drilled_holes: [emptyAsDrilled(hole("a"))],
    survey_application: APPLICATION,
    changed_ids: changed,
  });
}

describe("APPLY_SURVEY", () => {
  it("одна запись отмены, UNDO возвращает документ целиком", () => {
    const before = base();
    const applied = apply(before, ["a"]);
    expect(applied.past).toHaveLength(1);
    const undone = designReducer(applied, { type: "UNDO" });
    expect(undone.present).toBe(before);
  });

  it("заменяет holes, loads (если не null), as_drilled_holes; дописывает survey_applications", () => {
    const before = { ...base(), survey_applications: [{ survey_date: "2026-10-01" } as SurveyApplication] };
    const newLoads = [{ hole_id: "z" } as HoleLoad];
    const applied = apply(before, ["a"], newLoads).present;
    expect(applied.holes[0].collar.x).toBe(10.5);
    expect(applied.loads).toBe(newLoads);
    expect(applied.as_drilled_holes).toHaveLength(1);
    expect(applied.survey_applications).toEqual([{ survey_date: "2026-10-01" }, APPLICATION]);
    expect(apply(base(), ["a"], null).present.loads).toEqual(before.loads);
  });

  it("не трогает as_charged_holes, as_fired_holes, pattern_params", () => {
    const before = base();
    const applied = apply(before, ["a"]).present;
    expect(applied.as_fired_holes).toBe(before.as_fired_holes);
    expect(applied.as_charged_holes).toBe(before.as_charged_holes);
    expect(applied.pattern_params).toBe(before.pattern_params);
  });

  it("при changed_ids непустом сеть помечена geometry_stale и ставится autoRetie для сети шаблона", () => {
    const applied = apply(base(TEMPLATE_NETWORK), ["a"]);
    expect(applied.present.network.timing_params?.geometry_stale).toBe(true);
    expect(applied.autoRetie?.present).toBe(applied.present);
    expect(applied.past).toHaveLength(1);
  });

  it("при пустом changed_ids сеть не помечается", () => {
    const applied = apply(base(TEMPLATE_NETWORK), []);
    expect(applied.present.network.timing_params?.geometry_stale).toBeUndefined();
    expect(applied.autoRetie).toBeUndefined();
  });
});
